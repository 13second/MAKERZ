# MAKERZ

> Makerz: Automated ECAD/MCAD co-design studio and hardware pipeline for devices: KiCad schematics/PCBs, SPICE simulations, parametric 3D enclosures, firmware, and JLCPCB/3D-print manufacturing exports.

---

## Repository Structure

```text
MAKERZ/
├── Avvia MAKERZ Studio.command   # macOS one-click launcher for MAKERZ Studio
├── makerz-studio/                # Local zero-dependency Node.js + Three.js workbench
│   ├── server.mjs                # HTTP API, project registry, and on-demand ECAD/MCAD runner
│   └── public/                   # Frontend UI (Three.js 3D viewer, SVG pan/zoom, BOM table)
├── IU-MIC_ORIGIN/                # Ultrasonic AoIP MEMS Measurement Microphone (20 Hz – 80 kHz)
│   ├── dimensions.json           # Shared ECAD/MCAD single-source-of-truth dimensions
│   ├── project.json              # MAKERZ Studio project manifest
│   ├── enclosure/pencil_mic.py   # Parametric 3D enclosure generator (build123d)
│   ├── hardware/                 # Noise budget, ngspice sims, KiCad 10 & FreeRouting pipeline
│   ├── docs/                     # Datasheet verification & JLCPCB BOM audits
│   └── exports/                  # Gerbers, 3D STEP/STL/GLB, renders, JLCPCB packages
└── SPIRIT-IP_LDC/                # Large-Diaphragm 34 mm Pure-Digital AoIP/USB-C Condenser Mic
    ├── dimensions.json           # Shared ECAD/MCAD single-source-of-truth dimensions
    ├── project.json              # MAKERZ Studio project manifest
    ├── enclosure/spirit_mic.py   # Parametric 3D enclosure & TPU shock-mount generator (build123d)
    ├── hardware/                 # Unified 4L Main + 2L Headamp KiCad 10 & FreeRouting pipeline
    └── exports/                  # Gerbers, 3D STEP/STL/GLB, renders, JLCPCB packages
```

---

## Projects

### 1. `SPIRIT-IP_LDC` (v1.2.1)
Studio large-diaphragm condenser microphone (34 mm gold-sputtered dual-diaphragm K67/CK12 capsule) with a pure-digital signal chain:
- **Main PCB (38 × 94 mm, 4-Layer):** IEEE 802.3af PoE (`TPS23753A`), USB-C UAC2 audio + power, `STM32H743VIT6` MCU, `LAN8742A` 100M Ethernet PHY, `AK5572EN` 32-bit 2-to-1 Mono ADC (124 dB DR), 3 Aston-style switches (Pattern, Pad, HPF), and 4× `WS2812B-2020` RGB LEDs.
- **Headamp PCB (Ø 36 mm, 2-Layer):** 1 GΩ `OPA1656` FET impedance converter, `TMUX1104` analog switch, `MT3608` ±60 V capsule bias generator, and `Laird BMI-S-102` SMD RF shield can.
- **Mechanical Enclosure:** JLC3DP 8001 clear resin body, 316L stainless steel grille, dual-port bottom cap (RJ45 + USB-C + 5/8"-27 mount), rigid capsule saddle, and 1.5 mm TPU/silicone shock-mount.

### 2. `IU-MIC_ORIGIN` (v1.2.0-S1)
Ultrasonic omnidirectional measurement & AoIP microphone (Stage 1: 20 Hz – 80 kHz, 384 kHz / 24-bit):
- **MEMS Tip PCB (Ø 8.0 mm, 2-Layer):** `Infineon IM73A135V01` bottom-port MEMS capsule (73 dB(A) SNR, 135 dB AOP) aligned to 0.00 mm with the nose-cone acoustic axis.
- **Main PCB (32 × 98 mm, 4-Layer):** USB-C 5 V power with ultra-low-noise `LP5907` LDOs (+3.3 V digital / +2.8 V MEMS), `OPA1656` analog front-end, `ngspice`-verified 2nd-order Butterworth HPF (20 Hz) / LPF (20 kHz) / AA (140 kHz) filters with `TMUX1104` bypass, `AK5572EN` ADC, `STM32H743VIT6`, and `LAN8742A` Ethernet PHY.
- **Mechanical Enclosure:** Sculpted Ø 46 mm anthracite body, Ø 11.2 mm ultrasonic nose cone, rear cap (Stage 1 RJ45-only and Stage 2 XLR+RJ45 variants), and 3D extruded serigraphy.

---

## Quick Start

### Launch MAKERZ Studio
```bash
node makerz-studio/server.mjs
# Then open http://127.0.0.1:4173
```
On macOS, double-click `Avvia MAKERZ Studio.command`.

### Environment Variables (Optional)
| Variable | Purpose | Default |
|---|---|---|
| `PORT` | HTTP port for MAKERZ Studio | `4173` |
| `MAKERZ_PYTHON` | Python interpreter for CAD/ECAD regeneration | `~/.gemini/config/cad-venv/bin/python` or `python3` |
| `KICAD_SHARE_DIR` | Path to KiCad SharedSupport directory | `/Applications/KiCad/KiCad.app/Contents/SharedSupport` |
| `FREEROUTING_JAR` | Path to `freerouting.jar` CLI | `~/.gemini/config/tools/freerouting.jar` |
| `JAVA_BIN` | Path to OpenJDK 21 `java` binary | `java` on `PATH` or Homebrew OpenJDK 21 |

---

## Documentation & Code Review

- See [`CODE_REVIEW.md`](./CODE_REVIEW.md) for the full security, bug-fix, and architecture audit applied across all JavaScript and Python sources.
- Every `.mjs`, `.js`, and `.py` module is documented in English with JSDoc and Google-style Python docstrings.
