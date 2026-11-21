#!/usr/bin/env python3
"""Legacy/reference ECAD generator for IU-MIC_ORIGIN (Stage 1 + Stage 2 architecture).

Produces:
    * KiCad project, schematic, and PCB files for Main PCB (4-layer) and MEMS Tip PCB (2-layer)
    * JLCPCB/LCSC BOM (``bom_lcsc.csv``, ``bom_jlcpcb_smt.csv``) and Pick & Place (``cpl_jlcpcb.csv``)
    * High-definition SVG renders for architectural schematic, Main PCB (Front/Back), and MEMS Tip PCB
    * JLCPCB-compliant RS-274X Protel Gerbers + Excellon drill ZIP archives (via ``kicad-cli`` or built-in fallback)
"""
import csv
import json
import math
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text())
MAIN_DIR = ROOT / "hardware" / "main_pcb"
TIP_DIR = ROOT / "hardware" / "mems_tip_pcb"
RENDER_DIR = ROOT / "exports" / "renders"
GERBER_DIR = ROOT / "exports" / "gerbers"

MAIN_DIR.mkdir(parents=True, exist_ok=True)
TIP_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)
GERBER_DIR.mkdir(parents=True, exist_ok=True)


def uid() -> str:
    """Generates a random UUIDv4 string for KiCad S-expression nodes."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. BOM & COMPONENT PLACEMENT (Single Source of Truth)
# ---------------------------------------------------------------------------
BOM_ITEMS = [
    # Designator, Comment, Footprint, Qty, LCSC, Manufacturer, MPN, Board, X, Y, Rot, Layer, Notes, EstUnitEUR
    ("MK1", "IM73A135V01", "MEMS_Infineon_4x3mm", 1, "C5149218", "Infineon", "IM73A135V01XTSA1", "TIP", 0.0, 0.0, 0, "F.Cu", "Capsula MEMS Omni Diff 73dB SNR 135dB AOP", 3.80),
    ("C_M1", "100nF 16V C0G", "C_0402_1005Metric", 1, "C1525", "Samsung", "CL05B104KO5NNNC", "TIP", 0.0, -2.6, 0, "F.Cu", "Disaccoppiamento VDD MEMS", 0.05),
    ("J_TIP1", "4-Pin Shielded Pad", "Pad_4x1_1.27mm", 1, "—", "Custom", "PAD-4P-1.27", "TIP", 0.0, 0.0, 0, "B.Cu", "Collegamento schermato diff al Main PCB", 0.00),

    # Main PCB — Sezione PoE, Ethernet & XLR Analog Output (Y: 0..32 mm dal bordo posteriore)
    ("J1", "RJ45 MagJack PoE", "RJ45_HanRun_HR911130A", 1, "C54408", "HanRun", "HR911130A", "MAIN", 9.0, 10.5, 0, "F.Cu", "RJ45 100M con magnetici PoE 802.3af", 2.40),
    ("J4", "XLR-3M Balanced Out", "XLR_Neutrik_NC3MD-LX", 1, "C2847901", "Neutrik", "NC3MD-LX", "MAIN", 23.0, 10.5, 0, "F.Cu", "Uscita Analogica Bilanciata XLR-3M (Pin1 GND, Pin2+, Pin3-)", 3.90),
    ("U10", "THAT1646W16-U", "SOIC-16_3.9x9.9mm", 1, "C512904", "THAT Corp", "THAT1646W16-U", "MAIN", 24.0, 26.5, 0, "F.Cu", "Driver Bilanciato OutSmart per XLR-3M + protezione 48V", 4.80),
    ("D2", "BAS21 Phantom Prot", "SOT-23", 4, "C85097", "ON Semi", "BAS21LT1G", "MAIN", 25.0, 20.5, 0, "B.Cu", "Diodi clamp protezione +48V Phantom su uscita XLR", 0.12),
    ("U1", "TPS23753APWR", "TSSOP-14_4.4x5mm", 1, "C133443", "TI", "TPS23753APWR", "MAIN", 5.5, 25.5, 90, "F.Cu", "Controller PoE 802.3af PD + DC-DC Flyback", 2.60),
    ("T1", "Flyback 48V->5V PoE", "Transformer_EP7_SMD", 1, "C2682952", "Wurth", "750311564", "MAIN", 15.0, 25.5, 0, "F.Cu", "Trasformatore isolamento galvanico 1.5kV PoE", 4.20),
    ("D1", "MB10S Bridge", "SOP-4_4.4x3.9mm", 2, "C2488", "MDD", "MB10S", "MAIN", 5.0, 19.0, 0, "B.Cu", "Ponte raddrizzatore PoE (Mode A + B)", 0.15),

    # Main PCB — Sezione Digitale, Ethernet PHY, USB-C, MCU (Y: 32..62 mm)
    ("J2", "USB-C 16-Pin", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", 1, "C165948", "Korean Hroparts", "TYPE-C-31-M-12", "MAIN", 28.8, 34.0, 270, "F.Cu", "USB-C Debug / Firmware / CLI", 0.45),
    ("U2", "LAN8742A-CZ", "QFN-24_4x4mm", 1, "C46749", "Microchip", "LAN8742A-CZ-TR", "MAIN", 10.0, 36.5, 0, "F.Cu", "Ethernet 100M PHY RMII + PTP", 1.85),
    ("Y1", "25.000MHz Crystal", "Crystal_SMD_3225", 1, "C9006", "Yangxing", "X322525MOB4SI", "MAIN", 4.5, 41.5, 0, "F.Cu", "Clock Ethernet PHY", 0.30),
    ("U3", "STM32H743VIT6", "LQFP-100_14x14mm", 1, "C136694", "ST", "STM32H743VIT6", "MAIN", 14.5, 50.5, 0, "F.Cu", "MCU 480MHz Cortex-M7 + Eth PTPv2 + SAI 32-bit", 9.50),
    ("Y2", "24.576MHz TCXO", "Oscillator_SMD_3225", 1, "C284664", "Abracon", "ASTX-H11-24.576MHZ", "MAIN", 24.5, 61.5, 0, "F.Cu", "Master Clock Audio ultra-low jitter (192kHz*128)", 2.90),
    ("U4", "TPS7A2033PDBVR", "SOT-23-5", 2, "C2845258", "TI", "TPS7A2033PDBVR", "MAIN", 5.2, 62.5, 0, "F.Cu", "LDO Ultra-Low-Noise 6.5uVrms (+3.3V_ANA / +3.3V_DIG)", 0.95),
    ("U5", "TPS7A4700RGWR", "VQFN-20_5x5mm", 1, "C129132", "TI", "TPS7A4700RGWR", "MAIN", 14.0, 65.5, 0, "B.Cu", "LDO Ultra-Low-Noise 4uVrms (+5V_ANA)", 4.50),

    # Main PCB — Switch Fisici HPF/LPF + LED + ADC + Analog Front-End (Y: 54..98 mm)
    ("SW1", "Slide Switch HPF 20Hz", "SW_SPDT_MSK12C02", 1, "C431540", "SHOU HAN", "MSK12C02", "MAIN", 29.0, 54.0, 270, "F.Cu", "Switch fisico inserimento HPF 20 Hz", 0.35),
    ("SW2", "Slide Switch LPF 20kHz", "SW_SPDT_MSK12C02", 1, "C431540", "SHOU HAN", "MSK12C02", "MAIN", 29.0, 68.0, 270, "F.Cu", "Switch fisico inserimento LPF 20 kHz", 0.35),
    ("LED1", "RGB Status LED", "LED_0606_RGB", 1, "C2843785", "Everlight", "19-337/R6GHBHC", "MAIN", 29.0, 82.0, 0, "F.Cu", "Stato PoE / PTP Lock / Clip / Filtri", 0.25),
    ("U6", "AK5572EN", "QFN-48_7x7mm", 1, "C489121", "AKM", "AK5572EN", "MAIN", 13.5, 73.0, 0, "F.Cu", "ADC Stereo 32-bit 768kHz (Dual-Gain @ 192kHz)", 7.80),
    ("U7", "OPA1656IDR", "SOIC-8_3.9x4.9mm", 2, "C2654935", "TI", "OPA1656IDR", "MAIN", 9.5, 85.5, 0, "F.Cu", "Op-Amp Ultra-Low-Noise FET (Pre + HPF/LPF)", 3.40),
    ("U8", "OPA1656IDR", "SOIC-8_3.9x4.9mm", 1, "C2654935", "TI", "OPA1656IDR", "MAIN", 20.0, 85.5, 0, "F.Cu", "Op-Amp Dual-Gain Stage (High +24dB / Low 0dB)", 3.40),
    ("U9", "TMUX1104DGSR", "VSSOP-10_3x3mm", 2, "C2848112", "TI", "TMUX1104DGSR", "MAIN", 15.0, 81.0, 0, "B.Cu", "Analog Switch bassissima distorsione per bypass HPF/LPF", 1.60),
    ("J3", "JST-SH 4-Pin MEMS", "JST_SH_SM04B-SRSS-TB", 1, "C160404", "JST", "SM04B-SRSS-TB", "MAIN", 16.0, 94.0, 0, "F.Cu", "Connessione differenziale schermata al Puntale MEMS", 0.30),

    # Passivi critici filtri Sallen-Key (C0G/NP0 + Res 0.1% Thin Film)
    ("R_HPF", "78.7k 0.1% ThinFilm", "R_0603_1608Metric", 2, "C22976", "YAGEO", "RT0603BRD0778K7L", "MAIN", 5.5, 88.0, 0, "F.Cu", "HPF 20.2 Hz Butterworth (fc=1/(2pi*R*C))", 0.22),
    ("C_HPF", "100nF 50V C0G/Film", "C_0805_2012Metric", 2, "C49678", "TDK", "CGA4J2C0G1H104J", "MAIN", 8.5, 88.0, 0, "F.Cu", "HPF 20.2 Hz (zero effetto piezoelettrico)", 0.45),
    ("R_LPF", "7.87k 0.1% ThinFilm", "R_0603_1608Metric", 2, "C23045", "YAGEO", "RT0603BRD077K87L", "MAIN", 13.5, 88.0, 0, "F.Cu", "LPF 20.2 kHz Butterworth", 0.22),
    ("C_LPF", "1nF 50V C0G/NP0", "C_0603_1608Metric", 2, "C1588", "Samsung", "CL10C102JB8NNNC", "MAIN", 16.5, 88.0, 0, "F.Cu", "LPF 20.2 kHz C0G ultra-lineare", 0.10),
    ("R_AA", "1.74k 0.1% ThinFilm", "R_0603_1608Metric", 4, "C23102", "YAGEO", "RT0603BRD071K74L", "MAIN", 11.0, 76.5, 0, "F.Cu", "Filtro Anti-Aliasing fisso 91.5 kHz pre-ADC", 0.22),
    ("C_AA", "1nF 50V C0G/NP0", "C_0603_1608Metric", 4, "C1588", "Samsung", "CL10C102JB8NNNC", "MAIN", 14.5, 76.5, 0, "F.Cu", "Filtro Anti-Aliasing fisso 91.5 kHz C0G", 0.10),
]


def write_bom_and_cpl():
    """Exports ``bom_lcsc.csv``, ``cpl_jlcpcb.csv``, and ``bom_jlcpcb_smt.csv`` from ``BOM_ITEMS``."""
    bom_path = ROOT / "hardware" / "bom_lcsc.csv"
    with bom_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Comment", "Footprint", "Quantity", "LCSC Part #", "Manufacturer", "MPN", "Board", "Notes", "Est Unit EUR"])
        for row in BOM_ITEMS:
            w.writerow([row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[12], f"{row[13]:.2f}"])

    cpl_path = ROOT / "hardware" / "cpl_jlcpcb.csv"
    with cpl_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        # Official JLCPCB SMT Pick & Place headers
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in BOM_ITEMS:
            if row[7] != "MAIN" or row[4] == "—":
                continue
            layer = "Top" if row[11] == "F.Cu" else "Bottom"
            w.writerow([row[0], f"{row[8]:.2f}mm", f"{row[9]:.2f}mm", layer, row[10]])

    # Official JLCPCB SMT BOM (4 exact columns expected by JLCPCB SMT uploader)
    smt_bom_path = ROOT / "hardware" / "bom_jlcpcb_smt.csv"
    with smt_bom_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part #"])
        for row in BOM_ITEMS:
            if row[7] != "MAIN" or row[4] == "—":
                continue
            w.writerow([row[1], row[0], row[2], row[4]])


# ---------------------------------------------------------------------------
# 2. KICAD 8 PROJECT, SCHEMATIC & PCB GENERATORS
# ---------------------------------------------------------------------------
def write_kicad_pro(path: Path, name: str, layers: int):
    """Writes a minimal ``.kicad_pro`` project file with JLCPCB design rules.

    Args:
        path: Output ``.kicad_pro`` path.
        name: Project name stem.
        layers: Copper layer count (2 or 4).
    """
    pro = {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.15,
                    "min_track_width": 0.15,
                    "min_via_annular_width": 0.15,
                    "min_via_diameter": 0.5,
                }
            }
        },
        "meta": {"filename": f"{name}.kicad_pro", "version": 1},
        "project": {"name": name, "copper_layers": layers},
    }
    path.write_text(json.dumps(pro, indent=2), encoding="utf-8")


def write_kicad_sch(path: Path, title: str, board_tag: str):
    """Generates an architectural block-note ``.kicad_sch`` for the given board tag.

    Args:
        path: Output ``.kicad_sch`` path.
        title: Title block string.
        board_tag: Board filter tag (``"MAIN"`` or ``"TIP"``).
    """
    items = [r for r in BOM_ITEMS if r[7] == board_tag]
    lines = [
        f'(kicad_sch (version 20231120) (generator "iu-mic-origin-ecad")',
        f'  (uuid "{uid()}")',
        '  (paper "A3")',
        '  (title_block',
        f'    (title "{title}")',
        '    (date "2026-11-19")',
        '    (rev "1.0")',
        '    (company "MAKERZ — IU-MIC_ORIGIN")',
        '    (comment 1 "1 Hz - 90 kHz | 192 kHz 32-bit Float Dual-Gain | AES67/RAVENNA/Dante PoE")',
        '  )',
        '  (lib_symbols)',
    ]
    # Emit structured labels & text notes representing the full netlist blocks
    blocks = [
        (30, 30, "1. PoE 802.3af ISOLATO (J1 MagJack -> D1 -> U1 TPS23753A -> T1 Flyback 5V)"),
        (30, 60, "2. ALIMENTAZIONE LOW-NOISE (U4 TPS7A20 +3.3V_DIG/+3.3V_ANA, U5 TPS7A4700 +5V_ANA)"),
        (30, 90, "3. ETHERNET & MCU (J1 <-> U2 LAN8742A RMII <-> U3 STM32H743 + PTPv2 + Y2 24.576MHz + J2 USB-C)"),
        (30, 120, "4. ANALOG FRONT-END (J3 MEMS_DIFF -> U7 OPA1656 Pre -> HPF 20Hz [SW1/U9] -> LPF 20kHz [SW2/U9])"),
        (30, 150, "5. DUAL-GAIN 32-BIT FLOAT (U8 OPA1656 High+24dB / Low 0dB -> AA 91.5kHz -> U6 AK5572EN -> SAI I2S)"),
    ] if board_tag == "MAIN" else [
        (30, 30, "MEMS TIP DAUGHTERBOARD (Ø 8mm): MK1 Infineon IM73A135V01 -> C_M1 100nF -> J_TIP1 Shielded Diff"),
    ]
    for bx, by, txt in blocks:
        lines.append(f'  (text "{txt}" (exclude_from_sim no) (at {bx} {by} 0) (effects (font (size 2.0 2.0) bold) (justify left)) (uuid "{uid()}"))')

    y_pos = 185 if board_tag == "MAIN" else 65
    for idx, r in enumerate(items):
        cx = 30 + (idx % 3) * 115
        cy = y_pos + (idx // 3) * 12
        lines.append(
            f'  (text "{r[0]}: {r[1]} [{r[2]}] LCSC:{r[4]} — {r[12]}" (exclude_from_sim no) '
            f'(at {cx} {cy} 0) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{uid()}"))'
        )
    lines.append(")")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_kicad_pcb_main(path: Path):
    """Generates the reference 4-layer Main PCB ``.kicad_pcb`` layout."""
    w = DIM["main_pcb"]["width"]
    l = DIM["main_pcb"]["length"]
    ox, oy = 100.0, 50.0  # Board origin on KiCad sheet

    nets = [
        (0, ""), (1, "GND"), (2, "+3V3_DIG"), (3, "+3V3_ANA"), (4, "+5V_ANA"),
        (5, "POE_48V_P"), (6, "POE_48V_N"), (7, "MEMS_P"), (8, "MEMS_N"),
        (9, "AFE_PRE_OUT"), (10, "HPF_OUT"), (11, "LPF_OUT"),
        (12, "ADC_HIGH_P"), (13, "ADC_LOW_P"), (14, "I2S_MCLK"), (15, "I2S_BCK"),
        (16, "I2S_LRCK"), (17, "I2S_SDATA"), (18, "ETH_TXP"), (19, "ETH_TXN"),
        (20, "ETH_RXP"), (21, "ETH_RXN"), (22, "USB_DP"), (23, "USB_DM"),
    ]

    lines = [
        '(kicad_pcb (version 20240108) (generator "iu-mic-origin-ecad")',
        '  (general (thickness 1.6) (legacy_teardrops no))',
        '  (paper "A4")',
        '  (layers',
        '    (0 "F.Cu" signal)',
        '    (1 "In1.Cu" power "GND")',
        '    (2 "In2.Cu" power "PWR")',
        '    (31 "B.Cu" signal)',
        '    (36 "B.SilkS" user "B.Silkscreen")',
        '    (37 "F.SilkS" user "F.Silkscreen")',
        '    (38 "B.Mask" user)',
        '    (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user)',
        '  )',
        '  (setup (pad_to_mask_clearance 0.05) (pcbplotparams (layerselection 0x00010fc_ffffffff)))',
    ]
    for nid, nname in nets:
        lines.append(f'  (net {nid} "{nname}")')

    # Edge.Cuts rectangle (22 x 95 mm)
    lines += [
        f'  (gr_rect (start {ox} {oy}) (end {ox+w} {oy+l}) (stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))',
        f'  (gr_text "IU-MIC_ORIGIN MAIN v1.0" (at {ox+w/2} {oy+46} 90) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1.2 1.2) (thickness 0.2))))',
    ]

    # Footprints from BOM
    for r in BOM_ITEMS:
        if r[7] != "MAIN":
            continue
        ref, val, fp, _, lcsc, _, _, _, x, y, rot, layer, *_ = r
        px, py = ox + x, oy + y
        lines += [
            f'  (footprint "IU_MIC:{fp}" (layer "{layer}") (uuid "{uid()}") (at {px:.2f} {py:.2f} {rot})',
            f'    (property "Reference" "{ref}" (at 0 -2.2 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.15))))',
            f'    (property "Value" "{val}" (at 0 2.2 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.15))))',
            f'    (pad "1" smd rect (at -1.0 0) (size 0.8 0.8) (layers "{layer}" "F.Mask") (net 1 "GND") (uuid "{uid()}"))',
            f'    (pad "2" smd rect (at 1.0 0) (size 0.8 0.8) (layers "{layer}" "F.Mask") (net 2 "+3V3_DIG") (uuid "{uid()}"))',
            '  )',
        ]

    # Representative copper traces (Signal flow: MEMS -> AFE -> ADC -> MCU -> PHY -> RJ45)
    traces = [
        (11.0, 91.5, 6.5, 83.5, 0.25, "F.Cu", 7),
        (11.0, 91.5, 7.2, 83.5, 0.25, "F.Cu", 8),
        (6.5, 83.5, 15.0, 83.5, 0.25, "F.Cu", 10),
        (15.0, 83.5, 9.5, 72.0, 0.25, "F.Cu", 12),
        (9.5, 72.0, 10.5, 50.5, 0.20, "F.Cu", 14),
        (10.5, 50.5, 8.0, 36.5, 0.20, "F.Cu", 18),
        (8.0, 36.5, 11.0, 10.5, 0.20, "F.Cu", 20),
        (11.0, 10.5, 5.5, 25.5, 0.50, "B.Cu", 5),
        (5.5, 25.5, 15.8, 25.5, 0.50, "B.Cu", 6),
    ]
    for x1, y1, x2, y2, tw, lay, nid in traces:
        lines.append(f'  (segment (start {ox+x1:.2f} {oy+y1:.2f}) (end {ox+x2:.2f} {oy+y2:.2f}) (width {tw}) (layer "{lay}") (net {nid}) (uuid "{uid()}"))')

    # Solid GND plane zone on In1.Cu
    lines += [
        f'  (zone (net 1) (net_name "GND") (layer "In1.Cu") (uuid "{uid()}") (hatch edge 0.5)',
        '    (connect_pads (clearance 0.2)) (min_thickness 0.2)',
        f'    (polygon (pts (xy {ox+0.4} {oy+0.4}) (xy {ox+w-0.4} {oy+0.4}) (xy {ox+w-0.4} {oy+l-0.4}) (xy {ox+0.4} {oy+l-0.4})))',
        '  )',
        ')',
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_kicad_pcb_tip(path: Path):
    """Generates the reference 2-layer circular Ø 8.0 mm MEMS Tip ``.kicad_pcb``."""
    r = DIM["mems_tip_pcb"]["diameter"] / 2.0
    cx, cy = 100.0, 100.0
    lines = [
        '(kicad_pcb (version 20240108) (generator "iu-mic-origin-ecad")',
        '  (general (thickness 1.6))',
        '  (paper "A4")',
        '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (37 "F.SilkS" user) (44 "Edge.Cuts" user))',
        '  (net 0 "") (net 1 "GND") (net 2 "+3V3_ANA") (net 3 "MEMS_P") (net 4 "MEMS_N")',
        f'  (gr_circle (center {cx} {cy}) (end {cx+r} {cy}) (stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))',
        f'  (footprint "IU_MIC:MEMS_Infineon_4x3mm" (layer "F.Cu") (uuid "{uid()}") (at {cx} {cy} 0)',
        f'    (property "Reference" "MK1" (at 0 -2.6 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.7 0.7) (thickness 0.12))))',
        f'    (pad "1" smd rect (at -1.5 -1.0) (size 0.8 0.6) (layers "F.Cu" "F.Mask") (net 2 "+3V3_ANA") (uuid "{uid()}"))',
        f'    (pad "2" smd rect (at 1.5 -1.0) (size 0.8 0.6) (layers "F.Cu" "F.Mask") (net 1 "GND") (uuid "{uid()}"))',
        f'    (pad "3" smd rect (at -1.5 1.0) (size 0.8 0.6) (layers "F.Cu" "F.Mask") (net 3 "MEMS_P") (uuid "{uid()}"))',
        f'    (pad "4" smd rect (at 1.5 1.0) (size 0.8 0.6) (layers "F.Cu" "F.Mask") (net 4 "MEMS_N") (uuid "{uid()}"))',
        '  )',
        ')',
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. HIGH-PRECISION SVG RENDERERS (Schematic + Main PCB Front/Back + Tip PCB)
# ---------------------------------------------------------------------------
def render_schematic_svg(path: Path):
    """Writes a stylized dark-theme architectural schematic SVG for MAKERZ Studio."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1400 860" width="1400" height="860">
  <defs>
    <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#1e293b" stroke-width="0.6"/>
    </pattern>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8"/>
    </marker>
    <marker id="arrow-pwr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#f59e0b"/>
    </marker>
  </defs>
  <rect width="1400" height="860" fill="#0b1020"/>
  <rect width="1400" height="860" fill="url(#grid)"/>

  <!-- Title Block -->
  <rect x="24" y="20" width="1352" height="62" rx="8" fill="#111827" stroke="#334155" stroke-width="1.5"/>
  <text x="44" y="47" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="20" font-weight="bold">IU-MIC_ORIGIN — SCHEMA ELETTRICO ARCHITETTURALE (Rev 1.0)</text>
  <text x="44" y="68" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="12">1 Hz – 90 kHz · 192 kHz / 32-bit IEEE 754 Float (Dual-Gain) · HPF 20 Hz + LPF 20 kHz Analogici · AES67 / RAVENNA / Dante · PoE 802.3af</text>
  <text x="1356" y="56" text-anchor="end" fill="#38bdf8" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">4-LAYER MIXED-SIGNAL</text>

  <!-- Zone 1: MEMS Tip -->
  <rect x="30" y="110" width="210" height="250" rx="10" fill="#0f172a" stroke="#14b8a6" stroke-width="1.8" stroke-dasharray="6,4"/>
  <text x="44" y="134" fill="#2dd4bf" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">PUNTALE Ø 10mm (TIP PCB)</text>
  <rect x="52" y="160" width="166" height="105" rx="6" fill="#134e4a" stroke="#2dd4bf" stroke-width="1.5"/>
  <text x="135" y="188" text-anchor="middle" fill="#f0fdfa" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">MK1: IM73A135V01</text>
  <text x="135" y="208" text-anchor="middle" fill="#99f6e4" font-family="ui-monospace,monospace" font-size="11">MEMS Omni Diff.</text>
  <text x="135" y="226" text-anchor="middle" fill="#99f6e4" font-family="ui-monospace,monospace" font-size="10">73 dB SNR · 135 dB AOP</text>
  <text x="135" y="244" text-anchor="middle" fill="#5eead4" font-family="ui-monospace,monospace" font-size="10">Porta Acustica &lt; 1 mm</text>
  <text x="135" y="300" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">C_M1: 100nF C0G + GND Guard</text>
  <text x="135" y="325" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">J_TIP1 ── Cavo Schermato Diff ──&gt; J3</text>

  <!-- Zone 2: Analog Front-End -->
  <rect x="275" y="110" width="600" height="390" rx="10" fill="#0f172a" stroke="#38bdf8" stroke-width="1.8"/>
  <text x="292" y="134" fill="#38bdf8" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">ANALOG FRONT-END (SEZIONE ANALOGICA ISOLATA — +3.3V_ANA / +5V_ANA)</text>

  <!-- Preamp -->
  <rect x="298" y="162" width="132" height="96" rx="6" fill="#1e293b" stroke="#60a5fa" stroke-width="1.4"/>
  <text x="364" y="188" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U7A: OPA1656</text>
  <text x="364" y="208" text-anchor="middle" fill="#93c5fd" font-family="ui-monospace,monospace" font-size="10">Pre-Amp Diff.</text>
  <text x="364" y="226" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">2.9 nV/√Hz · DC-100kHz</text>
  <text x="364" y="244" text-anchor="middle" fill="#64748b" font-family="ui-monospace,monospace" font-size="9">HPF DC-Block ~1 Hz</text>

  <!-- HPF 20Hz -->
  <rect x="462" y="152" width="142" height="114" rx="6" fill="#1e293b" stroke="#a78bfa" stroke-width="1.4"/>
  <text x="533" y="176" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">HPF 20 Hz (2° Ord)</text>
  <text x="533" y="195" text-anchor="middle" fill="#c4b5fd" font-family="ui-monospace,monospace" font-size="10">Sallen-Key Butterworth</text>
  <text x="533" y="213" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">R=78.7k 0.1% · C=100nF</text>
  <text x="533" y="232" text-anchor="middle" fill="#f472b6" font-family="ui-monospace,monospace" font-size="10">SW1 + U9A TMUX1104</text>
  <text x="533" y="250" text-anchor="middle" fill="#64748b" font-family="ui-monospace,monospace" font-size="9">Bypass: 1 Hz Full-Band</text>

  <!-- LPF 20kHz -->
  <rect x="636" y="152" width="142" height="114" rx="6" fill="#1e293b" stroke="#a78bfa" stroke-width="1.4"/>
  <text x="707" y="176" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">LPF 20 kHz (2° Ord)</text>
  <text x="707" y="195" text-anchor="middle" fill="#c4b5fd" font-family="ui-monospace,monospace" font-size="10">Sallen-Key Butterworth</text>
  <text x="707" y="213" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">R=7.87k 0.1% · C=1nF</text>
  <text x="707" y="232" text-anchor="middle" fill="#f472b6" font-family="ui-monospace,monospace" font-size="10">SW2 + U9B TMUX1104</text>
  <text x="707" y="250" text-anchor="middle" fill="#64748b" font-family="ui-monospace,monospace" font-size="9">Bypass: 90 kHz Ultra</text>

  <!-- Dual Gain High & Low -->
  <rect x="330" y="315" width="215" height="72" rx="6" fill="#172554" stroke="#38bdf8" stroke-width="1.4"/>
  <text x="437" y="340" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U8A: HIGH-GAIN (+24 dB)</text>
  <text x="437" y="360" text-anchor="middle" fill="#7dd3fc" font-family="ui-monospace,monospace" font-size="10">+ Anti-Aliasing 91.5 kHz (1.74k / 1nF)</text>
  <text x="437" y="376" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Segnali deboli / Ultra-low Noise Floor</text>

  <rect x="330" y="405" width="215" height="72" rx="6" fill="#172554" stroke="#38bdf8" stroke-width="1.4"/>
  <text x="437" y="430" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U8B: LOW-GAIN (0 dB)</text>
  <text x="437" y="450" text-anchor="middle" fill="#7dd3fc" font-family="ui-monospace,monospace" font-size="10">+ Anti-Aliasing 91.5 kHz (1.74k / 1nF)</text>
  <text x="437" y="466" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Picchi fino a 135 dB SPL (Zero Clip)</text>

  <!-- ADC -->
  <rect x="615" y="330" width="235" height="135" rx="8" fill="#1e1b4b" stroke="#818cf8" stroke-width="2"/>
  <text x="732" y="362" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="14" font-weight="bold">U6: AK5572EN</text>
  <text x="732" y="384" text-anchor="middle" fill="#a5b4fc" font-family="ui-monospace,monospace" font-size="11">ADC Stereo 32-bit / 768 kHz</text>
  <text x="732" y="406" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">CH-L: High Gain · CH-R: Low Gain</text>
  <text x="732" y="426" text-anchor="middle" fill="#38bdf8" font-family="ui-monospace,monospace" font-size="10">Fs = 192 kHz · MCLK = 24.576 MHz</text>
  <text x="732" y="446" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Modulatore ΔΣ interno a 6.144 MHz</text>

  <!-- Analog Balanced XLR-3M Output -->
  <rect x="30" y="385" width="210" height="115" rx="8" fill="#1e1b4b" stroke="#f59e0b" stroke-width="1.8"/>
  <text x="135" y="412" text-anchor="middle" fill="#fef3c7" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">J4: XLR-3M OUT</text>
  <text x="135" y="432" text-anchor="middle" fill="#fcd34d" font-family="ui-monospace,monospace" font-size="10">U10: THAT1646 Balanced</text>
  <text x="135" y="452" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">Neutrik NC3MD-LX (3-Pin)</text>
  <text x="135" y="472" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">D2 BAS21 Prot. +48V Phantom</text>
  <path d="M 310 351 L 240 442" stroke="#f59e0b" stroke-width="2" fill="none" marker-end="url(#arrow-pwr)"/>

  <!-- Zone 3: Digital & AoIP -->
  <rect x="915" y="110" width="455" height="390" rx="10" fill="#0f172a" stroke="#22c55e" stroke-width="1.8"/>
  <text x="932" y="134" fill="#4ade80" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">SEZIONE DIGITALE, DSP 32-BIT FLOAT &amp; AoIP</text>

  <rect x="945" y="165" width="215" height="175" rx="8" fill="#052e16" stroke="#4ade80" stroke-width="1.8"/>
  <text x="1052" y="194" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="14" font-weight="bold">U3: STM32H743VIT6</text>
  <text x="1052" y="216" text-anchor="middle" fill="#86efac" font-family="ui-monospace,monospace" font-size="10">ARM Cortex-M7 @ 480 MHz</text>
  <text x="1052" y="238" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">• Fusione Dual-Gain -&gt; IEEE 754 F32</text>
  <text x="1052" y="258" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">• MAC Ethernet + PTPv2 Hardware</text>
  <text x="1052" y="278" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">• AES67 / RAVENNA / Dante / RTP-F32</text>
  <text x="1052" y="298" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">• Controllo Remoto HPF/LPF &amp; LED1</text>
  <text x="1052" y="322" text-anchor="middle" fill="#38bdf8" font-family="ui-monospace,monospace" font-size="10">Y2: 24.576 MHz TCXO Low-Jitter</text>

  <rect x="1195" y="170" width="150" height="90" rx="6" fill="#1e293b" stroke="#4ade80" stroke-width="1.4"/>
  <text x="1270" y="198" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U2: LAN8742A</text>
  <text x="1270" y="218" text-anchor="middle" fill="#86efac" font-family="ui-monospace,monospace" font-size="10">100BASE-TX PHY</text>
  <text x="1270" y="238" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">RMII · Y1 25 MHz</text>

  <rect x="1195" y="295" width="150" height="105" rx="6" fill="#1e293b" stroke="#f59e0b" stroke-width="1.8"/>
  <text x="1270" y="325" text-anchor="middle" fill="#fef3c7" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">J1: RJ45 PoE</text>
  <text x="1270" y="346" text-anchor="middle" fill="#fcd34d" font-family="ui-monospace,monospace" font-size="10">HanRun HR911130A</text>
  <text x="1270" y="366" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">Dati 100M + 48V PoE</text>
  <text x="1270" y="384" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Singolo Cavo Ethernet</text>

  <rect x="945" y="385" width="165" height="75" rx="6" fill="#1e293b" stroke="#94a3b8" stroke-width="1.2"/>
  <text x="1027" y="413" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">J2: USB-C</text>
  <text x="1027" y="434" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="10">Debug / DFU / Config</text>

  <!-- Zone 4: Power PoE Isolated -->
  <rect x="30" y="540" width="1340" height="285" rx="10" fill="#0f172a" stroke="#f59e0b" stroke-width="1.8"/>
  <text x="48" y="566" fill="#fbbf24" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">ALIMENTAZIONE ISOLATA PoE 802.3af (BARRIERA ISOLAMENTO GALVANICO 1.5 kV — ZERO GROUND LOOPS)</text>

  <rect x="60" y="600" width="240" height="125" rx="8" fill="#451a03" stroke="#f59e0b" stroke-width="1.6"/>
  <text x="180" y="630" text-anchor="middle" fill="#fef3c7" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">U1: TPS23753A + D1</text>
  <text x="180" y="652" text-anchor="middle" fill="#fcd34d" font-family="ui-monospace,monospace" font-size="10">IEEE 802.3af PD Controller</text>
  <text x="180" y="672" text-anchor="middle" fill="#fed7aa" font-family="ui-monospace,monospace" font-size="10">Ingresso 37–57V PoE (Mode A/B)</text>
  <text x="180" y="694" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Primario Isolato (Clearance ≥1.5mm)</text>

  <!-- Isolation Barrier -->
  <line x1="360" y1="585" x2="360" y2="800" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="8,6"/>
  <text x="370" y="605" fill="#f87171" font-family="ui-monospace,monospace" font-size="11" font-weight="bold">BARRIERA 1.5 kV</text>

  <rect x="405" y="600" width="215" height="125" rx="8" fill="#1e293b" stroke="#f59e0b" stroke-width="1.6"/>
  <text x="512" y="630" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="13" font-weight="bold">T1: Flyback PoE</text>
  <text x="512" y="652" text-anchor="middle" fill="#fcd34d" font-family="ui-monospace,monospace" font-size="10">Wurth 750311564</text>
  <text x="512" y="674" text-anchor="middle" fill="#cbd5e1" font-family="ui-monospace,monospace" font-size="10">Uscita Isolata: +5.5V_ISO</text>
  <text x="512" y="696" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">OR-ing con +5V_USB</text>

  <rect x="690" y="595" width="280" height="88" rx="8" fill="#1e293b" stroke="#38bdf8" stroke-width="1.6"/>
  <text x="830" y="622" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U5: TPS7A4700 (+5V_ANA)</text>
  <text x="830" y="642" text-anchor="middle" fill="#7dd3fc" font-family="ui-monospace,monospace" font-size="10">Ultra-Low-Noise 4 µVrms · PSRR 82 dB</text>
  <text x="830" y="662" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Alimenta OPA1656 + AVDD AK5572EN</text>

  <rect x="690" y="705" width="280" height="88" rx="8" fill="#1e293b" stroke="#2dd4bf" stroke-width="1.6"/>
  <text x="830" y="732" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U4A: TPS7A2033 (+3.3V_ANA)</text>
  <text x="830" y="752" text-anchor="middle" fill="#5eead4" font-family="ui-monospace,monospace" font-size="10">Ultra-Low-Noise 6.5 µVrms · Ferrite Bead</text>
  <text x="830" y="772" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Alimenta Capsula MEMS IM73A135V01 + VREF</text>

  <rect x="1030" y="645" width="295" height="98" rx="8" fill="#1e293b" stroke="#4ade80" stroke-width="1.6"/>
  <text x="1177" y="675" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">U4B: TPS7A2033 (+3.3V_DIG)</text>
  <text x="1177" y="696" text-anchor="middle" fill="#86efac" font-family="ui-monospace,monospace" font-size="10">Dominio Digitale Separato (In2.Cu)</text>
  <text x="1177" y="718" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="9">Alimenta STM32H743 + LAN8742A + TCXO</text>

  <!-- Signal Wires -->
  <path d="M 218 212 L 298 212" stroke="#2dd4bf" stroke-width="2.2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 430 210 L 462 210" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 604 210 L 636 210" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 707 266 L 707 292 L 310 292 L 310 351 L 330 351" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 310 351 L 310 441 L 330 441" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 545 351 L 615 375" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 545 441 L 615 415" stroke="#38bdf8" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 850 395 L 892 395 L 892 250 L 945 250" stroke="#4ade80" stroke-width="2.4" fill="none" marker-end="url(#arrow)"/>
  <text x="896" y="325" fill="#86efac" font-family="ui-monospace,monospace" font-size="10" transform="rotate(-90 896 325)">SAI / I2S 32b 192kHz</text>
  <path d="M 1160 215 L 1195 215" stroke="#4ade80" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 1270 260 L 1270 295" stroke="#4ade80" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
  <path d="M 1027 385 L 1027 340" stroke="#94a3b8" stroke-width="1.8" fill="none" marker-end="url(#arrow)"/>

  <!-- Power Wires -->
  <path d="M 300 662 L 405 662" stroke="#f59e0b" stroke-width="2.2" fill="none" marker-end="url(#arrow-pwr)"/>
  <path d="M 620 662 L 655 662 L 655 638 L 690 638" stroke="#f59e0b" stroke-width="2" fill="none" marker-end="url(#arrow-pwr)"/>
  <path d="M 655 662 L 655 748 L 690 748" stroke="#f59e0b" stroke-width="2" fill="none" marker-end="url(#arrow-pwr)"/>
  <path d="M 655 694 L 1030 694" stroke="#f59e0b" stroke-width="2" fill="none" marker-end="url(#arrow-pwr)"/>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


def render_main_pcb_svg(path: Path, side: str = "front"):
    """Renders a 2D SVG preview of the Main PCB front or back copper side.

    Args:
        path: Output SVG file path.
        side: Board side to render (``"front"`` or ``"back"``).
    """
    scale = 10.0  # 10 px per mm -> 220 x 950 px board
    w_mm, l_mm = DIM["main_pcb"]["width"], DIM["main_pcb"]["length"]
    pad_x, pad_y = 140, 80
    svg_w = int(l_mm * scale + pad_x * 2)  # Horizontal orientation for wide screens!
    svg_h = int(w_mm * scale + pad_y * 2)
    target_layer = "F.Cu" if side == "front" else "B.Cu"
    board_color = "#064e3b" if side == "front" else "#065f46"
    accent = "#10b981" if side == "front" else "#34d399"

    # Helper: map PCB (x in 0..22, y in 0..95) -> SVG horizontal (Y goes left-to-right: Rear RJ45 -> Tip J3)
    def pt(x_mm, y_mm):
        sx = pad_x + y_mm * scale
        sy = pad_y + (w_mm - x_mm if side == "front" else x_mm) * scale
        return sx, sy

    els = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">',
        f'  <rect width="{svg_w}" height="{svg_h}" fill="#0b1020"/>',
        f'  <text x="{pad_x}" y="38" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="18" font-weight="bold">IU-MIC_ORIGIN MAIN PCB ({side.upper()}) — 95.0 × 22.0 mm · 4-Layer JLCPCB (Sig / GND / PWR / Sig)</text>',
        f'  <text x="{pad_x}" y="58" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="11">Partizionamento fisico: [PoE 48V Isolato 0–30mm] ── [Digitale STM32H7/PHY 30–66mm] ── [Analogico ADC/AFE 66–95mm]</text>',
        # Board outline
        f'  <rect x="{pad_x}" y="{pad_y}" width="{l_mm*scale}" height="{w_mm*scale}" rx="8" fill="{board_color}" stroke="{accent}" stroke-width="2.5"/>',
        # Partition zones
        f'  <rect x="{pad_x+2}" y="{pad_y+2}" width="{30*scale}" height="{w_mm*scale-4}" fill="#f59e0b" fill-opacity="0.08" stroke="#f59e0b" stroke-dasharray="5,4" stroke-width="1"/>',
        f'  <rect x="{pad_x+30*scale}" y="{pad_y+2}" width="{36*scale}" height="{w_mm*scale-4}" fill="#22c55e" fill-opacity="0.06" stroke="#22c55e" stroke-dasharray="5,4" stroke-width="1"/>',
        f'  <rect x="{pad_x+66*scale}" y="{pad_y+2}" width="{29*scale-2}" height="{w_mm*scale-4}" fill="#38bdf8" fill-opacity="0.08" stroke="#38bdf8" stroke-dasharray="5,4" stroke-width="1"/>',
        f'  <text x="{pad_x+15*scale}" y="{pad_y+w_mm*scale+24}" text-anchor="middle" fill="#fbbf24" font-family="ui-monospace,monospace" font-size="11">PoE 802.3af &amp; RJ45</text>',
        f'  <text x="{pad_x+48*scale}" y="{pad_y+w_mm*scale+24}" text-anchor="middle" fill="#4ade80" font-family="ui-monospace,monospace" font-size="11">STM32H743 + PHY + USB-C</text>',
        f'  <text x="{pad_x+80.5*scale}" y="{pad_y+w_mm*scale+24}" text-anchor="middle" fill="#38bdf8" font-family="ui-monospace,monospace" font-size="11">AK5572 + OPA1656 + Filtri</text>',
    ]

    # Representative copper traces
    copper = "#ef4444" if side == "front" else "#3b82f6"
    trace_pts = [
        (11.0, 91.5, 6.5, 83.5), (11.0, 91.5, 7.8, 83.5), (6.5, 83.5, 15.0, 83.5),
        (15.0, 83.5, 9.5, 72.0), (9.5, 72.0, 10.5, 50.5), (10.5, 50.5, 8.0, 36.5),
        (8.0, 36.5, 11.0, 10.5), (11.0, 10.5, 5.5, 25.5), (5.5, 25.5, 15.8, 25.5),
    ]
    for x1, y1, x2, y2 in trace_pts:
        sx1, sy1 = pt(x1, y1)
        sx2, sy2 = pt(x2, y2)
        els.append(f'  <line x1="{sx1:.1f}" y1="{sy1:.1f}" x2="{sx2:.1f}" y2="{sy2:.1f}" stroke="{copper}" stroke-width="2.4" stroke-opacity="0.75"/>')

    # Component footprints
    size_map = {
        "J1": (20.0, 14.0), "J4": (19.0, 19.0), "U10": (10.0, 4.5), "U3": (14.0, 14.0),
        "U6": (7.5, 7.5), "T1": (9.0, 8.0), "J2": (7.5, 9.0), "U2": (5.0, 5.0),
        "U1": (5.0, 5.5), "U7": (5.0, 4.5), "U8": (5.0, 4.5), "SW1": (7.0, 3.6),
        "SW2": (7.0, 3.6), "J3": (4.5, 6.5), "U5": (5.5, 5.5), "U9": (3.5, 3.5),
    }
    for r in BOM_ITEMS:
        if r[7] != "MAIN":
            continue
        ref, val, fp, _, _, _, _, _, x, y, rot, lay, *_ = r
        on_this_side = (lay == target_layer)
        sx, sy = pt(x, y)
        bw, bh = size_map.get(ref, (3.2, 2.2))
        bw_px, bh_px = bw * scale, bh * scale
        opacity = "0.95" if on_this_side else "0.22"
        fill = "#1e293b" if on_this_side else "#0f172a"
        stroke = "#f8fafc" if on_this_side else "#64748b"
        els.append(
            f'  <g opacity="{opacity}">'
            f'<rect x="{sx-bw_px/2:.1f}" y="{sy-bh_px/2:.1f}" width="{bw_px:.1f}" height="{bh_px:.1f}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>'
            f'<text x="{sx:.1f}" y="{sy+3:.1f}" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="9" font-weight="bold">{ref}</text>'
            f'</g>'
        )

    els.append("</svg>")
    path.write_text("\n".join(els), encoding="utf-8")


def render_tip_pcb_svg(path: Path):
    """Writes a 2D SVG preview of the circular Ø 8.0 mm MEMS Tip PCB."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 420" width="520" height="420">
  <rect width="520" height="420" fill="#0b1020"/>
  <text x="260" y="34" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="16" font-weight="bold">IU-MIC_ORIGIN MEMS TIP PCB (Ø 8.0 mm · 2-Layer)</text>
  <text x="260" y="54" text-anchor="middle" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="11">Infineon IM73A135V01 + Guard Ring GND + Disaccoppiamento C0G</text>
  <circle cx="260" cy="230" r="140" fill="#064e3b" stroke="#10b981" stroke-width="3"/>
  <circle cx="260" cy="230" r="126" fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="6,4"/>
  <!-- MEMS Footprint 4x3 mm scaled 35 px/mm -->
  <rect x="190" y="178" width="140" height="104" rx="6" fill="#1e293b" stroke="#38bdf8" stroke-width="2"/>
  <circle cx="260" cy="230" r="17" fill="#0b1020" stroke="#fbbf24" stroke-width="2.5"/>
  <text x="260" y="198" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="12" font-weight="bold">MK1: IM73A135V01</text>
  <text x="260" y="270" text-anchor="middle" fill="#7dd3fc" font-family="ui-monospace,monospace" font-size="10">Porta Acustica Ø 1.0 mm</text>
  <!-- Decoupling cap -->
  <rect x="235" y="305" width="50" height="24" rx="3" fill="#334155" stroke="#e2e8f0" stroke-width="1.5"/>
  <text x="260" y="321" text-anchor="middle" fill="#f8fafc" font-family="ui-monospace,monospace" font-size="10">C_M1</text>
</svg>
"""
    path.write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# 4. JLCPCB RS-274X GERBER + EXCELLON DRILL + ZIP EXPORTER
# ---------------------------------------------------------------------------
def _gcoord(val_mm: float) -> int:
    """Converts millimeters to RS-274X 4.6 metric integer coordinates."""
    return int(round(val_mm * 1_000_000))


def _gerber_header(layer_func: str) -> list[str]:
    """Builds the RS-274X Protel Gerber header with standard aperture definitions."""
    return [
        f"G04 IU-MIC_ORIGIN JLCPCB RS-274X (Protel Standard) — {layer_func}*",
        "%TF.GenerationSoftware,MAKERZ,IU-MIC_ORIGIN,1.1*%",
        f"%TF.FileFunction,{layer_func}*%",
        "%FSLAX46Y46*%",
        "%MOMM*%",
        "%LPD*%",
        "%ADD10C,0.150000*%",             # Edge.Cuts / Silkscreen line
        "%ADD11C,0.250000*%",             # Signal trace
        "%ADD12C,0.500000*%",             # Power trace
        "%ADD13R,1.200000X0.800000*%",    # SMD Copper Pad
        "%ADD14R,1.300000X0.900000*%",    # Soldermask Opening (+0.10mm expansion)
        "%ADD15R,1.100000X0.700000*%",    # Solder Paste Aperture (SMT Stencil)
        "%ADD16C,0.600000*%",             # Via annular ring
        "G01*",
    ]


def _write_gerber_file(path: Path, layer_func: str, body: list[str]):
    """Writes a complete RS-274X Gerber file with header, body, and M02 footer."""
    lines = _gerber_header(layer_func) + body + ["M02*"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_excellon_drill(path: Path, holes: list[tuple[float, float, float]], plated: bool = True):
    """JLCPCB-compliant Excellon NC Drill: Metric mm, explicit decimal format, absolute origin."""
    kind = "PTH" if plated else "NPTH"
    unique_diams = sorted({round(d, 3) for _, _, d in holes})
    if not unique_diams:
        return
    lines = [
        "M48",
        f"; IU-MIC_ORIGIN JLCPCB Excellon Drill ({kind}) — Metric Decimal",
        "FMAT,2",
        "METRIC",
    ]
    tool_map = {}
    for idx, d in enumerate(unique_diams, start=1):
        tool_map[d] = f"T{idx}"
        lines.append(f"T{idx}C{d:.3f}")
    lines += ["%", "G90", "G05"]
    for d in unique_diams:
        lines.append(tool_map[d])
        for x, y, hd in holes:
            if round(hd, 3) == d:
                lines.append(f"X{x:.3f}Y{y:.3f}")
    lines += ["T0", "M30"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try_kicad_cli_gerbers(pcb_path: Path, out_dir: Path, layers_csv: str) -> bool:
    """Attempts native Gerber and Excellon drill export via ``kicad-cli``.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        out_dir: Directory where exported Gerber/drill files are written.
        layers_csv: Comma-separated KiCad layer list.

    Returns:
        True if both Gerber and Excellon drill exports succeeded.
    """
    cli = shutil.which("kicad-cli")
    if not cli and Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli").exists():
        cli = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
    if not cli:
        return False
    r1 = subprocess.run(
        [
            cli, "pcb", "export", "gerbers",
            "--layers", layers_csv,
            "--use-protel-extensions",
            "--subtract-soldermask",
            "--output", str(out_dir),
            str(pcb_path),
        ],
        capture_output=True,
    )
    r2 = subprocess.run(
        [
            cli, "pcb", "export", "drill",
            "--format", "excellon",
            "--excellon-units", "mm",
            "--excellon-zeros-format", "decimal",
            "--excellon-oval-format", "alternate",
            "--output", str(out_dir),
            str(pcb_path),
        ],
        capture_output=True,
    )
    return r1.returncode == 0 and r2.returncode == 0


def export_jlcpcb_gerbers():
    """Exports JLCPCB-ready Gerber + Excellon drill ZIPs for Main and MEMS Tip PCBs.

    Returns:
        Dictionary with ``main_zip``, ``tip_zip``, and ``engine`` keys.
    """
    # --- 1. Main PCB (4-Layer Protel Standard: GTL, G2L, G3L, GBL, GTS, GBS, GTO, GBO, GTP, GBP, GKO, TXT) ---
    main_tmp = GERBER_DIR / "main_pcb_files"
    if main_tmp.exists():
        shutil.rmtree(main_tmp, ignore_errors=True)
    main_tmp.mkdir(parents=True, exist_ok=True)

    used_kicad = _try_kicad_cli_gerbers(
        MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pcb",
        main_tmp,
        "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
    )
    if not used_kicad:
        w, l = DIM["main_pcb"]["width"], DIM["main_pcb"]["length"]
        # Board Outline (.GKO)
        edge = [
            "D10*",
            f"X{_gcoord(0)}Y{_gcoord(0)}D02*",
            f"X{_gcoord(w)}Y{_gcoord(0)}D01*",
            f"X{_gcoord(w)}Y{_gcoord(l)}D01*",
            f"X{_gcoord(0)}Y{_gcoord(l)}D01*",
            f"X{_gcoord(0)}Y{_gcoord(0)}D01*",
        ]
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GKO", "Profile,NP", edge)

        f_cu, b_cu = ["D13*"], ["D13*"]
        f_mask, b_mask = ["D14*"], ["D14*"]
        f_paste, b_paste = ["D15*"], ["D15*"]
        f_silk, b_silk = ["D10*"], ["D10*"]
        pth_holes = []
        for r in BOM_ITEMS:
            if r[7] != "MAIN":
                continue
            x, y, lay = r[8], r[9], r[11]
            for dx in (-1.0, 1.0):
                cmd = f"X{_gcoord(x+dx)}Y{_gcoord(y)}D03*"
                if lay == "F.Cu":
                    f_cu.append(cmd)
                    f_mask.append(cmd)
                    f_paste.append(cmd)
                else:
                    b_cu.append(cmd)
                    b_mask.append(cmd)
                    b_paste.append(cmd)
            pth_holes.append((x, y + 1.8, 0.300))
            bx1, by1, bx2, by2 = x - 1.6, y - 1.2, x + 1.6, y + 1.2
            box_cmds = [
                f"X{_gcoord(bx1)}Y{_gcoord(by1)}D02*",
                f"X{_gcoord(bx2)}Y{_gcoord(by1)}D01*",
                f"X{_gcoord(bx2)}Y{_gcoord(by2)}D01*",
                f"X{_gcoord(bx1)}Y{_gcoord(by2)}D01*",
                f"X{_gcoord(bx1)}Y{_gcoord(by1)}D01*",
            ]
            (f_silk if lay == "F.Cu" else b_silk).extend(box_cmds)

        f_cu.append("D11*")
        for x1, y1, x2, y2 in [
            (16.0, 94.0, 9.5, 85.5), (9.5, 85.5, 20.0, 85.5), (20.0, 85.5, 13.5, 73.0),
            (13.5, 73.0, 14.5, 50.5), (14.5, 50.5, 10.0, 36.5), (10.0, 36.5, 9.0, 10.5),
            (20.0, 85.5, 24.0, 26.5), (24.0, 26.5, 23.0, 10.5),
        ]:
            f_cu += [f"X{_gcoord(x1)}Y{_gcoord(y1)}D02*", f"X{_gcoord(x2)}Y{_gcoord(y2)}D01*"]

        plane_poly = [
            "G36*",
            f"X{_gcoord(0.5)}Y{_gcoord(0.5)}D02*",
            f"X{_gcoord(w-0.5)}Y{_gcoord(0.5)}D01*",
            f"X{_gcoord(w-0.5)}Y{_gcoord(l-0.5)}D01*",
            f"X{_gcoord(0.5)}Y{_gcoord(l-0.5)}D01*",
            f"X{_gcoord(0.5)}Y{_gcoord(0.5)}D01*",
            "G37*",
        ]

        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GTL", "Copper,L1,Top", f_cu)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.G2L", "Copper,L2,Inr", plane_poly)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.G3L", "Copper,L3,Inr", plane_poly)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GBL", "Copper,L4,Bot", b_cu)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GTS", "Soldermask,Top", f_mask)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GBS", "Soldermask,Bot", b_mask)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GTP", "Paste,Top", f_paste)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GBP", "Paste,Bot", b_paste)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GTO", "Legend,Top", f_silk)
        _write_gerber_file(main_tmp / "IU-MIC_ORIGIN_Main.GBO", "Legend,Bot", b_silk)
        _write_excellon_drill(main_tmp / "IU-MIC_ORIGIN_Main-PTH.TXT", pth_holes, plated=True)

    main_zip = GERBER_DIR / "IU-MIC_ORIGIN_Main_JLCPCB_Gerbers.zip"
    with zipfile.ZipFile(main_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(main_tmp.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, p.name)

    # --- 2. MEMS Tip PCB (2-Layer Circular Ø 8.0 mm Protel Standard + separate PTH/NPTH) ---
    tip_tmp = GERBER_DIR / "mems_tip_files"
    if tip_tmp.exists():
        shutil.rmtree(tip_tmp, ignore_errors=True)
    tip_tmp.mkdir(parents=True, exist_ok=True)

    used_kicad_tip = _try_kicad_cli_gerbers(
        TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_pcb",
        tip_tmp,
        "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
    )
    if not used_kicad_tip:
        r_tip = DIM["mems_tip_pcb"]["diameter"] / 2.0
        cx, cy = r_tip, r_tip
        edge = ["D10*"]
        steps = 48
        for i in range(steps + 1):
            ang = 2 * math.pi * i / steps
            px, py = cx + r_tip * math.cos(ang), cy + r_tip * math.sin(ang)
            edge.append(f"X{_gcoord(px)}Y{_gcoord(py)}{'D02' if i == 0 else 'D01'}*")
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GKO", "Profile,NP", edge)

        pad_coords = [(-1.5, -1.0), (1.5, -1.0), (-1.5, 1.0), (1.5, 1.0), (-0.8, -2.6), (0.8, -2.6)]
        cu_cmds = ["D13*"] + [f"X{_gcoord(cx+dx)}Y{_gcoord(cy+dy)}D03*" for dx, dy in pad_coords]
        mask_cmds = ["D14*"] + [f"X{_gcoord(cx+dx)}Y{_gcoord(cy+dy)}D03*" for dx, dy in pad_coords]
        paste_cmds = ["D15*"] + [f"X{_gcoord(cx+dx)}Y{_gcoord(cy+dy)}D03*" for dx, dy in pad_coords]

        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GTL", "Copper,L1,Top", cu_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GBL", "Copper,L2,Bot", cu_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GTS", "Soldermask,Top", mask_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GBS", "Soldermask,Bot", mask_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GTP", "Paste,Top", paste_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GBP", "Paste,Bot", paste_cmds)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GTO", "Legend,Top", edge)
        _write_gerber_file(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip.GBO", "Legend,Bot", edge)
        # Plated vias (PTH) vs Non-Plated acoustic port hole (NPTH)
        _write_excellon_drill(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip-PTH.TXT", [(cx - 2.2, cy, 0.300), (cx + 2.2, cy, 0.300)], plated=True)
        _write_excellon_drill(tip_tmp / "IU-MIC_ORIGIN_MEMS_Tip-NPTH.TXT", [(cx, cy, 1.000)], plated=False)

    tip_zip = GERBER_DIR / "IU-MIC_ORIGIN_MEMS_Tip_JLCPCB_Gerbers.zip"
    with zipfile.ZipFile(tip_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tip_tmp.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, p.name)

    return {"main_zip": str(main_zip), "tip_zip": str(tip_zip), "engine": "kicad-cli" if used_kicad else "rs274x-protel-jlcpcb"}


def main():
    """Runs the complete legacy ECAD, BOM/CPL, SVG, and Gerber ZIP export pipeline."""
    write_bom_and_cpl()
    write_kicad_pro(MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pro", "IU-MIC_ORIGIN_Main", 4)
    write_kicad_sch(MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_sch", "IU-MIC_ORIGIN Main PCB", "MAIN")
    write_kicad_pcb_main(MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pcb")

    write_kicad_pro(TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_pro", "IU-MIC_ORIGIN_MEMS_Tip", 2)
    write_kicad_sch(TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_sch", "IU-MIC_ORIGIN MEMS Tip PCB", "TIP")
    write_kicad_pcb_tip(TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_pcb")

    render_schematic_svg(RENDER_DIR / "main_schematic.svg")
    render_main_pcb_svg(RENDER_DIR / "main_pcb_front.svg", "front")
    render_main_pcb_svg(RENDER_DIR / "main_pcb_back.svg", "back")
    render_tip_pcb_svg(RENDER_DIR / "mems_tip_pcb.svg")
    g_info = export_jlcpcb_gerbers()
    print(f"[OK] ECAD KiCad files, BOM/CPL, SVG renders, and JLCPCB Gerber ZIPs generated ({g_info['engine']}).")


if __name__ == "__main__":
    main()
