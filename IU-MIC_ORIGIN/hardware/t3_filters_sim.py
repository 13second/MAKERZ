#!/usr/bin/env python3
"""T3 — Analog filter design and ngspice verification for IU-MIC_ORIGIN (Stage 1).

Synthesizes and simulates the three 2nd-order Unity-Gain Sallen-Key Butterworth
filters (Q = 0.7071) with TMUX1104 analog bypass switches (Ron = 2.5 Ohm,
Con = 40 pF) and an OPA1656 behavioral macromodel:
    * 20 Hz HPF (R_gnd = 2 * R_fb)
    * 20 kHz LPF (C_fb = 2 * C_gnd)
    * 140 kHz Anti-Aliasing LPF (aligned with D2 Fs = 384 kHz, 20 Hz – 80 kHz band)

Generates a Bode comparison plot and automatically evaluates Gate T3
(passband deviation from ideal Butterworth < 0.5 dB).
"""

import re
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CIR_PATH = ROOT / "hardware" / "t3_filters.cir"
DATA_DIR = ROOT / "hardware" / "sim_data"
RENDER_DIR = ROOT / "exports" / "renders"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)

SPICE_NETLIST = """* IU-MIC_ORIGIN T3 — Butterworth Q=0.707 Filters + TMUX1104 Bypass + OPA1656 Model
* OPA1656 parameters from TI datasheet: GBW = 53 MHz, Aol = 120 dB (1e6), en = 2.9 nV/rtHz

.subckt OPA1656_MODEL inp inn out
* High-Z input + equivalent input voltage noise 2.9 nV/rtHz (R_eq = 507 Ohm @ 300K)
Rin inp inn 1e12
Rnoise inp n_in 507
* Gain stage + dominant pole: fp = GBW / Aol = 53e6 / 1e6 = 53 Hz (R=1e6, C=3.003nF)
G1 0 n1 n_in inn 1.0
R1 n1 0 1e6
C1 n1 0 3.003n
* Low-impedance output buffer (Ro = 10 Ohm)
Eout n2 0 n1 0 1.0
Rout n2 out 10
.ends

* TMUX1104 model (TI datasheet: Ron = 2.5 Ohm typ, Con = 40 pF)
.subckt TMUX1104_SW in out
Rsw in out 2.5
Csw out 0 40p
.ends

* AC + SIN source for AC, Noise, and THD analyses (1.0 Vrms = 1.4142 Vpk @ 1 kHz)
Vin in_src 0 DC 0 AC 1 SIN(0 1.4142 1k)

* =========================================================================
* 1. HPF 20 Hz (Butterworth Q=0.7071, Unity Gain, R_gnd = 2*R_fb)
*    C1 = C2 = 100 nF, R_fb = 56.2 kOhm, R_gnd = 113 kOhm -> fc = 19.97 Hz
* =========================================================================
C_hpf1 in_src hpf_n1 100n
C_hpf2 hpf_n1 hpf_inp 100n
R_hpf_fb hpf_n1 hpf_op 56.2k
R_hpf_gnd hpf_inp 0 113k
X_hpf hpf_inp hpf_op hpf_op OPA1656_MODEL
X_sw_hpf hpf_op hpf_out TMUX1104_SW

* =========================================================================
* 2. LPF 20 kHz (Butterworth Q=0.7071, Unity Gain, C_fb = 2*C_gnd)
*    R1 = R2 = 2.55 kOhm, C_gnd = 2.2 nF, C_fb = 4.4 nF (2x 2.2nF) -> fc = 20.06 kHz
* =========================================================================
R_lpf1 in_src lpf_n1 2.55k
R_lpf2 lpf_n1 lpf_inp 2.55k
C_lpf_fb lpf_n1 lpf_op 4.4n
C_lpf_gnd lpf_inp 0 2.2n
X_lpf lpf_inp lpf_op lpf_op OPA1656_MODEL
X_sw_lpf lpf_op lpf_out TMUX1104_SW

* =========================================================================
* 3. ANTI-ALIASING 140 kHz (aligned with D2 Fs=384 kHz, 20-80 kHz band)
*    R1 = R2 = 806 Ohm, C_gnd = 1.0 nF, C_fb = 2.0 nF (2x 1.0nF) -> fc = 139.6 kHz
* =========================================================================
R_aa1 in_src aa_n1 806
R_aa2 aa_n1 aa_inp 806
C_aa_fb aa_n1 aa_op 2.0n
C_aa_gnd aa_inp 0 1.0n
X_aa aa_inp aa_op aa_op OPA1656_MODEL
X_sw_aa aa_op aa_out TMUX1104_SW

* Full-Band chain (HPF + LPF bypassed via TMUX1104 -> AA 140 kHz)
X_sw_byp1 in_src byp_n1 TMUX1104_SW
X_sw_byp2 byp_n1 byp_n2 TMUX1104_SW
R_fb_aa1 byp_n2 fb_aa_n1 806
R_fb_aa2 fb_aa_n1 fb_aa_inp 806
C_fb_aa_fb fb_aa_n1 fb_aa_op 2.0n
C_fb_aa_gnd fb_aa_inp 0 1.0n
X_fb_aa fb_aa_inp fb_aa_op fb_aa_op OPA1656_MODEL

.control
set wr_vecnames
set wr_singlescale

* 1) AC Sweep: 1 Hz -> 10 MHz (100 pt/dec)
ac dec 100 1 10meg
wrdata ac_sweep.dat vdb(hpf_out) vdb(lpf_out) vdb(aa_out) vdb(fb_aa_op)

* 2) Noise Analysis: Full-Band (20 Hz -> 80 kHz)
noise v(fb_aa_op) Vin dec 50 20 80k
print onoise_total

* 3) Noise Analysis: LPF 20k Active (20 Hz -> 20 kHz)
noise v(lpf_out) Vin dec 50 20 20k
print onoise_total

* 4) Transient + THD @ 1 kHz (1 Vrms) on Full-Band & LPF 20k
tran 1u 10m 5m
fourier 1k v(fb_aa_op) v(lpf_out)
quit
.endc
.end
"""


def ideal_butterworth_hpf_db(f: np.ndarray, fc: float) -> np.ndarray:
    """Computes the ideal 2nd-order Butterworth high-pass magnitude response in dB.

    Args:
        f: Frequency array in Hz.
        fc: Cutoff (-3 dB) frequency in Hz.

    Returns:
        Magnitude response array in dB.
    """
    return 20.0 * np.log10((f / fc) ** 2 / np.sqrt(1.0 + (f / fc) ** 4))


def ideal_butterworth_lpf_db(f: np.ndarray, fc: float) -> np.ndarray:
    """Computes the ideal 2nd-order Butterworth low-pass magnitude response in dB.

    Args:
        f: Frequency array in Hz.
        fc: Cutoff (-3 dB) frequency in Hz.

    Returns:
        Magnitude response array in dB.
    """
    return 20.0 * np.log10(1.0 / np.sqrt(1.0 + (f / fc) ** 4))


def main() -> None:
    """Writes the SPICE netlist, runs ngspice, plots Bode curves, and checks Gate T3."""
    CIR_PATH.write_text(SPICE_NETLIST, encoding="utf-8")
    proc = subprocess.run(["ngspice", "-b", str(CIR_PATH)], cwd=str(DATA_DIR), capture_output=True, text=True)
    stdout = proc.stdout + "\n" + proc.stderr
    (DATA_DIR / "ngspice_log.txt").write_text(stdout, encoding="utf-8")
    if proc.returncode != 0:
        print("NGSPICE ERROR:\n", stdout)
        raise SystemExit(1)

    # Parse AC sweep data
    raw = np.loadtxt(DATA_DIR / "ac_sweep.dat", skiprows=1)
    freq = raw[:, 0]
    hpf_db = raw[:, 1]
    lpf_db = raw[:, 2]
    aa_db = raw[:, 3]
    fb_db = raw[:, 4]

    # Compare against ideal 2nd-order Butterworth curves in passband
    hpf_ideal = ideal_butterworth_hpf_db(freq, 20.0)
    lpf_ideal = ideal_butterworth_lpf_db(freq, 20000.0)
    aa_ideal = ideal_butterworth_lpf_db(freq, 140000.0)

    m_hpf = (freq >= 20.0) & (freq <= 80000.0)
    m_lpf = (freq >= 20.0) & (freq <= 20000.0)
    m_aa = (freq >= 20.0) & (freq <= 80000.0)

    err_hpf = float(np.max(np.abs(hpf_db[m_hpf] - hpf_ideal[m_hpf])))
    err_lpf = float(np.max(np.abs(lpf_db[m_lpf] - lpf_ideal[m_lpf])))
    err_aa = float(np.max(np.abs(aa_db[m_aa] - aa_ideal[m_aa])))

    droop_80k = float(np.interp(80000.0, freq, fb_db))
    atten_6m = float(np.interp(6144000.0, freq, fb_db))
    hpf_at_20 = float(np.interp(20.0, freq, hpf_db))
    lpf_at_20k = float(np.interp(20000.0, freq, lpf_db))

    # Parse integrated noise and THD from ngspice log
    noises = re.findall(r"onoise_total\s*=\s*([0-9eE.+-]+)", stdout)
    thds = re.findall(r"THD:\s*([0-9eE.+-]+)\s*%", stdout)

    # Plot Bode comparison
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150, facecolor="#0b1020")
    ax.set_facecolor("#0f172a")
    ax.semilogx(freq, hpf_db, color="#a78bfa", lw=2, label="HPF 20 Hz (ngspice)")
    ax.semilogx(freq, hpf_ideal, "--", color="#c4b5fd", lw=1, alpha=0.7, label="HPF 20 Hz Ideal Butt.")
    ax.semilogx(freq, lpf_db, color="#38bdf8", lw=2, label="LPF 20 kHz (ngspice)")
    ax.semilogx(freq, lpf_ideal, "--", color="#7dd3fc", lw=1, alpha=0.7, label="LPF 20 kHz Ideal Butt.")
    ax.semilogx(freq, fb_db, color="#2dd4bf", lw=2.2, label="Full-Band + AA 140 kHz (ngspice)")
    ax.axvline(80000, color="#f59e0b", ls=":", lw=1.2, label="Usable band 80 kHz")
    ax.axvline(192000, color="#ef4444", ls=":", lw=1.2, label="Nyquist 192 kHz (Fs=384k)")
    ax.set_ylim(-50, 3)
    ax.set_xlim(2, 1e7)
    ax.set_xlabel("Frequency (Hz)", color="#e2e8f0")
    ax.set_ylabel("Gain (dB)", color="#e2e8f0")
    ax.set_title("T3 — ngspice Butterworth Filter Simulation (Q=0.707) + TMUX1104 Bypass", color="#f8fafc")
    ax.grid(True, which="both", color="#1e293b", lw=0.6)
    ax.tick_params(colors="#94a3b8")
    ax.legend(loc="lower left", fontsize=8, facecolor="#0f172a", edgecolor="#334155", labelcolor="#e2e8f0")
    plt.tight_layout()
    plt.savefig(RENDER_DIR / "t3_filters_bode.png", facecolor=fig.get_facecolor())
    plt.close(fig)

    gate_pass = (err_hpf < 0.5) and (err_lpf < 0.5) and (err_aa < 0.5)
    print("=== T3: NGSPICE SIMULATION RESULTS ===")
    print(f"HPF 20 Hz @ 20 Hz:            {hpf_at_20:.2f} dB (ideal -3.01 dB) | Max passband error: {err_hpf:.4f} dB")
    print(f"LPF 20 kHz @ 20 kHz:          {lpf_at_20k:.2f} dB (ideal -3.01 dB) | Max passband error: {err_lpf:.4f} dB")
    print(f"AA 140 kHz (Full-Band) @ 80k: {droop_80k:.2f} dB | @ 6.144 MHz (MCLK/2): {atten_6m:.1f} dB | Max err vs Butt.: {err_aa:.4f} dB")
    if len(noises) >= 2:
        print(f"Integrated noise Full-Band (20 Hz-80 kHz): {float(noises[0])*1e6:.3f} uVrms")
        print(f"Integrated noise LPF 20k  (20 Hz-20 kHz):  {float(noises[1])*1e6:.3f} uVrms")
    if thds:
        print(f"THD @ 1 kHz, 1.0 Vrms (Full-Band / LPF20k): {', '.join(t + '%' for t in thds)}")
    print(f"GATE T3 (< 0.5 dB vs Butterworth): {'PASS' if gate_pass else 'FAIL'}")


if __name__ == "__main__":
    main()
