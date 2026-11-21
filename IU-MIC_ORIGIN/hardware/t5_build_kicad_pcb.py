#!/usr/bin/env python3
"""T5 & T6 — KiCad 10 PCB generator, JLCPCB 4-layer rules, DRC, and Gerber exporter.

Builds both Stage 1 boards using official KiCad 10 ``.kicad_mod`` footprints:
    * Board 1: MEMS Tip PCB (Ø 8.0 mm, 2-layer) with ``Infineon_PG-LLGA-5-2``
      aligned to 0.00 mm with the nose-cone acoustic port axis.
    * Board 2: Main PCB Stage 1 (32.0 x 98.0 mm, 4-layer: F.Cu / In1.Cu GND /
      In2.Cu PWR / B.Cu, USB-C + Ethernet, excluding Stage 2 PoE/XLR).

Executes ``kicad-cli pcb drc`` and exports native KiCad 10 Protel Gerbers,
Excellon drill files, and front/back SVG renders.
"""
import json
import math
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text(encoding="utf-8"))
KICAD_SHARE = Path(os.environ.get("KICAD_SHARE_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
FP_DIR = KICAD_SHARE / "footprints"
KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

TIP_DIR = ROOT / "hardware" / "mems_tip_pcb"
MAIN_DIR = ROOT / "hardware" / "main_pcb"
TIP_PCB = TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_pcb"
MAIN_PCB = MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pcb"
DRC_DIR = ROOT / "hardware" / "drc_reports"
GERBER_DIR = ROOT / "exports" / "gerbers"
RENDER_DIR = ROOT / "exports" / "renders"

for d in (DRC_DIR, GERBER_DIR, RENDER_DIR):
    d.mkdir(parents=True, exist_ok=True)


def uid() -> str:
    """Generates a random UUIDv4 string for KiCad PCB elements."""
    return str(uuid.uuid4())


def write_jlcpcb_kicad_pro(pro_path: Path, name: str):
    """Writes JLCPCB 4-layer DRC rules and default netclass settings to ``.kicad_pro``.

    Args:
        pro_path: Output path for the ``.kicad_pro`` JSON file.
        name: Project filename stem.
    """
    pro = {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.10,
                    "min_copper_edge_clearance": 0.25,
                    "min_hole_clearance": 0.15,
                    "min_hole_to_hole": 0.25,
                    "min_silk_clearance": 0.0,
                    "min_through_hole_diameter": 0.25,
                    "min_track_width": 0.10,
                    "min_via_annular_width": 0.125,
                    "min_via_diameter": 0.5,
                    "solder_mask_min_width": 0.0,
                }
            }
        },
        "meta": {"filename": f"{name}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.127,
                    "diff_pair_gap": 0.2,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.15,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.15,
                    "via_diameter": 0.55,
                    "via_drill": 0.3,
                }
            ]
        },
    }
    pro_path.write_text(json.dumps(pro, indent=2), encoding="utf-8")


def load_kicad_mod(rel_path: str, ref: str, val: str, x: float, y: float, rot: float = 0.0, pad_nets: dict[str, tuple[int, str]] | None = None, layer: str = "F.Cu") -> str:
    """Loads an official KiCad ``.kicad_mod`` footprint and injects placement, layer, and nets.

    Args:
        rel_path: Relative path inside ``FP_DIR``.
        ref: Component reference designator.
        val: Component value string.
        x: Absolute board X coordinate in millimeters.
        y: Absolute board Y coordinate in millimeters.
        rot: Footprint rotation in degrees.
        pad_nets: Optional mapping from pad number to ``(net_id, net_name)``.
        layer: Copper side (``"F.Cu"`` or ``"B.Cu"``).

    Returns:
        Embedded KiCad S-expression footprint block.
    """
    raw = (FP_DIR / rel_path).read_text(encoding="utf-8")
    raw = re.sub(r'\(version\s+\d+\)\s*', '', raw)
    raw = re.sub(r'\(generator\s+"[^"]*"\)\s*', '', raw)
    raw = re.sub(r'\(generator_version\s+"[^"]*"\)\s*', '', raw)

    raw = re.sub(
        r'(\(footprint\s+"[^"]+")',
        rf'\1\n    (at {x:.3f} {y:.3f} {rot:.1f})\n    (uuid "{uid()}")',
        raw,
        count=1,
    )
    raw = re.sub(r'(\(property\s+"Reference"\s+)"[^"]*"', rf'\1"{ref}"', raw, count=1)
    raw = re.sub(r'(\(property\s+"Value"\s+)"[^"]*"', rf'\1"{val}"', raw, count=1)

    if layer == "B.Cu":
        raw = raw.replace('"F.Cu"', '"B.Cu"').replace('"F.Mask"', '"B.Mask"').replace('"F.Paste"', '"B.Paste"').replace('"F.SilkS"', '"B.SilkS"').replace('"F.Fab"', '"B.Fab"').replace('"F.CrtYd"', '"B.CrtYd"')

    if pad_nets or rot != 0.0:
        out = []
        idx = 0
        for m in re.finditer(r'\(pad\s+"([^"]*)"', raw):
            out.append(raw[idx:m.start()])
            depth = 0
            end = m.start()
            for j in range(m.start(), len(raw)):
                if raw[j] == "(":
                    depth += 1
                elif raw[j] == ")":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            pad_blk = raw[m.start():end]
            # KiCad .kicad_pcb stores pad rotation in board-absolute degrees
            if rot != 0.0:
                def _rot_pad_at(pm):
                    px, py = pm.group(1), pm.group(2)
                    pang = float(pm.group(3)) if pm.group(3) else 0.0
                    new_ang = (pang + rot) % 360.0
                    return f"(at {px} {py} {new_ang:.1f})"
                pad_blk = re.sub(r'\(at\s+([0-9.-]+)\s+([0-9.-]+)(?:\s+([0-9.-]+))?\)', _rot_pad_at, pad_blk, count=1)
            pnum = m.group(1)
            if pad_nets and pnum in pad_nets and "(net " not in pad_blk:
                nid, nname = pad_nets[pnum]
                pad_blk = pad_blk[:-1] + f' (net {nid} "{nname}"))'
            out.append(pad_blk)
            idx = end
        out.append(raw[idx:])
        raw = "".join(out)

    return raw


def seg(x1, y1, x2, y2, w, layer, nid):
    """Formats a copper track segment S-expression."""
    return f'  (segment (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) (width {w:.3f}) (layer "{layer}") (net {nid}) (uuid "{uid()}"))'


def via(x, y, nid, size=0.6, drill=0.3):
    """Formats a through-hole copper via S-expression."""
    return f'  (via (at {x:.3f} {y:.3f}) (size {size:.2f}) (drill {drill:.2f}) (layers "F.Cu" "B.Cu") (net {nid}) (uuid "{uid()}"))'


def build_tip_pcb():
    """Generates the fully routed 2-layer Ø 8.0 mm MEMS Tip PCB."""
    write_jlcpcb_kicad_pro(TIP_DIR / "IU-MIC_ORIGIN_MEMS_Tip.kicad_pro", "IU-MIC_ORIGIN_MEMS_Tip")
    r = DIM["mems_tip_pcb"]["diameter"] / 2.0
    cx, cy = 100.0, 100.0

    nets = [(0, ""), (1, "GND"), (2, "+2V8_MEMS"), (3, "MEMS_P"), (4, "MEMS_N")]
    lines = [
        '(kicad_pcb (version 20240108) (generator "iu-mic-origin-t5")',
        '  (general (thickness 1.6) (legacy_teardrops no))',
        '  (paper "A4")',
        '  (layers',
        '    (0 "F.Cu" signal) (31 "B.Cu" signal)',
        '    (34 "B.Paste" user) (35 "F.Paste" user)',
        '    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")',
        '    (38 "B.Mask" user) (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user)',
        '    (48 "B.Fab" user) (49 "F.Fab" user)',
        '  )',
        '  (setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints yes))',
    ]
    for nid, nname in nets:
        lines.append(f'  (net {nid} "{nname}")')

    lines.append(
        f'  (gr_circle (center {cx:.3f} {cy:.3f}) (end {cx+r:.3f} {cy:.3f}) '
        f'(stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))'
    )

    # MK1: Official Infineon_PG-LLGA-5-2 offset by (-0.68, 0) so its bottom acoustic port (at +0.68, 0)
    # sits dead-center at (100.00, 100.00), aligned to 0.00 mm with the nose_cone acoustic axis!
    # Pad coords: P1(97.82,99.15) MEMS_P, P2(98.52,99.15) +2V8, P3(97.82,100.85) MEMS_N, P4(98.52,100.85) GND, P5(99.19,100.0) GND
    lines.append(load_kicad_mod(
        "Sensor_Audio.pretty/Infineon_PG-LLGA-5-2.kicad_mod",
        "MK1", "IM73A135V01", cx - 0.68, cy, 0.0,
        pad_nets={"1": (3, "MEMS_P"), "2": (2, "+2V8_MEMS"), "3": (4, "MEMS_N"), "4": (1, "GND"), "5": (1, "GND")},
    ))
    # C_M1: 100nF C0G at (99.00, 97.50) -> P1(98.52,97.50) +2V8_MEMS, P2(99.48,97.50) GND
    lines.append(load_kicad_mod(
        "Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod",
        "C_M1", "100nF C0G", 99.00, 97.50, 0.0,
        pad_nets={"1": (2, "+2V8_MEMS"), "2": (1, "GND")},
    ))

    # 4 Rear Solder Test Pads on B.Cu (hand-soldered shielded cable; keeps SMT Top-Only for JLCPCB Economic!)
    for idx, (px, py, nm, nid) in enumerate([
        (99.25, 97.65, "+2V8_MEMS", 2),
        (97.45, 99.35, "MEMS_P", 3),
        (97.70, 101.55, "MEMS_N", 4),
        (101.50, 101.65, "GND", 1),
    ], start=1):
        lines.append(load_kicad_mod(
            "TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod",
            f"TP_T{idx}", nm, px, py, 0.0,
            pad_nets={"1": (nid, nm)}, layer="B.Cu",
        ))

    # --- COMPLETE COPPER ROUTING (0 unconnected_items, 0 DRC errors) ---
    # Net 2 (+2V8_MEMS): MK1.2(98.52,99.15) -> C_M1.1(98.52,97.50) -> via(97.85,97.75) -> B.Cu -> TP_T1(99.25,97.65)
    lines.append(seg(98.52, 99.15, 98.52, 97.50, 0.25, "F.Cu", 2))
    lines.append(seg(98.52, 97.50, 97.85, 97.75, 0.25, "F.Cu", 2))
    lines.append(via(97.85, 97.75, 2, size=0.55, drill=0.30))
    lines.append(seg(97.85, 97.75, 99.25, 97.65, 0.25, "B.Cu", 2))

    # Net 3 (MEMS_P): MK1.1(97.82,99.15) -> via(97.05,99.15) -> B.Cu -> TP_T2(97.45,99.35)
    lines.append(seg(97.82, 99.15, 97.05, 99.15, 0.20, "F.Cu", 3))
    lines.append(via(97.05, 99.15, 3, size=0.55, drill=0.30))
    lines.append(seg(97.05, 99.15, 97.45, 99.35, 0.20, "B.Cu", 3))

    # Net 4 (MEMS_N): MK1.3(97.82,100.85) -> via(97.05,100.85) -> B.Cu -> TP_T3(97.70,101.55)
    lines.append(seg(97.82, 100.85, 97.05, 100.85, 0.20, "F.Cu", 4))
    lines.append(via(97.05, 100.85, 4, size=0.55, drill=0.30))
    lines.append(seg(97.05, 100.85, 97.70, 101.55, 0.20, "B.Cu", 4))

    # Net 1 (GND): MK1.4(98.52,100.85) -> MK1.5(99.19,100.00); MK1.4 -> via(99.40,101.75) -> B.Cu -> TP_T4(101.50,101.65)
    #              C_M1.2(99.48,97.50) -> via(100.85,97.65) -> B.Cu -> (101.50,98.80) -> TP_T4(101.50,101.65)
    lines.append(seg(98.52, 100.85, 99.19, 100.00, 0.25, "F.Cu", 1))
    lines.append(seg(98.52, 100.85, 99.40, 101.75, 0.25, "F.Cu", 1))
    lines.append(via(99.40, 101.75, 1, size=0.55, drill=0.30))
    lines.append(seg(99.40, 101.75, 101.50, 101.65, 0.30, "B.Cu", 1))
    lines.append(seg(99.48, 97.50, 100.85, 97.65, 0.25, "F.Cu", 1))
    lines.append(via(100.85, 97.65, 1, size=0.55, drill=0.30))
    lines.append(seg(100.85, 97.65, 101.50, 98.80, 0.30, "B.Cu", 1))
    lines.append(seg(101.50, 98.80, 101.50, 101.65, 0.30, "B.Cu", 1))

    lines.append(")")
    TIP_PCB.write_text("\n".join(lines), encoding="utf-8")


def build_main_pcb_stage1():
    """Generates the unrouted 4-layer Stage 1 Main PCB ready for FreeRouting."""
    write_jlcpcb_kicad_pro(MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pro", "IU-MIC_ORIGIN_Main")
    w = DIM["main_pcb"]["width"]
    l = DIM["main_pcb"]["length"]
    ox, oy = 100.0, 50.0

    nets = [
        (0, ""), (1, "GND"), (2, "+5V_USB"), (3, "+3V3_DIG"), (4, "+2V8_MEMS"),
        (5, "MEMS_P"), (6, "MEMS_N"), (7, "AFE_OUT_P"), (8, "AFE_OUT_N"),
        (9, "SAI1_MCLK"), (10, "SAI1_SCK"), (11, "SAI1_FS"), (12, "SAI1_SD"),
        (13, "ETH_TXP"), (14, "ETH_TXN"), (15, "ETH_RXP"), (16, "ETH_RXN"),
        (17, "USB_DP"), (18, "USB_DM"), (19, "USB_CC1"), (20, "USB_CC2"),
        (21, "ETH_REFCLK"), (22, "ETH_MDIO"), (23, "ETH_MDC"), (24, "ETH_CRSDV"),
        (25, "ETH_RXD0"), (26, "ETH_RXD1"), (27, "ETH_TXEN"), (28, "ETH_TXD0"), (29, "ETH_TXD1"),
        (30, "ETH_XTAL1"), (31, "ETH_XTAL2"), (32, "ETH_RBIAS"),
        (33, "I2C1_SCL"), (34, "I2C1_SDA"), (35, "VCAP"), (36, "NRST"), (37, "BOOT0"),
        (38, "SWDIO"), (39, "SWCLK"), (40, "PRE_OUT"), (41, "HPF_N1"), (42, "HPF_INP"),
        (43, "HPF_OUT"), (44, "LPF_N1"), (45, "LPF_INP"), (46, "AA_N1"), (47, "AA_INP"),
        (48, "VCOM_2V5"),
    ]

    lines = [
        '(kicad_pcb (version 20240108) (generator "iu-mic-origin-t5")',
        '  (general (thickness 1.6) (legacy_teardrops no))',
        '  (paper "A4")',
        '  (layers',
        # In1.Cu & In2.Cu declared as signal so FreeRouting can route/via directly into solid GND/+3V3 zones!
        '    (0 "F.Cu" signal) (1 "In1.Cu" signal "GND") (2 "In2.Cu" signal "PWR") (31 "B.Cu" signal)',
        '    (34 "B.Paste" user) (35 "F.Paste" user)',
        '    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")',
        '    (38 "B.Mask" user) (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user)',
        '    (48 "B.Fab" user) (49 "F.Fab" user)',
        '  )',
        '  (setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints yes))',
    ]
    for nid, nname in nets:
        lines.append(f'  (net {nid} "{nname}")')

    lines.append(
        f'  (gr_rect (start {ox:.3f} {oy:.3f}) (end {ox+w:.3f} {oy+l:.3f}) '
        f'(stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))'
    )

    # --- SECTION 1: ETHERNET REAR (Y: 0..32 mm) ---
    lines.append(load_kicad_mod(
        "Connector_RJ.pretty/RJ45_Hanrun_HR911105A_Horizontal.kicad_mod",
        "J1", "HR911105A", ox + 16.0, oy + 12.5, 180.0,
        pad_nets={"1": (13, "ETH_TXP"), "2": (14, "ETH_TXN"), "3": (15, "ETH_RXP"), "6": (16, "ETH_RXN"), "SH": (1, "GND")},
    ))
    lines.append(load_kicad_mod(
        "Package_DFN_QFN.pretty/QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm.kicad_mod",
        "U2", "LAN8742A-CZ", ox + 12.0, oy + 29.0, 0.0,
        pad_nets={
            "1": (3, "+3V3_DIG"), "4": (31, "ETH_XTAL2"), "5": (30, "ETH_XTAL1"),
            "7": (26, "ETH_RXD1"), "8": (25, "ETH_RXD0"), "9": (3, "+3V3_DIG"),
            "11": (24, "ETH_CRSDV"), "12": (22, "ETH_MDIO"), "13": (23, "ETH_MDC"),
            "14": (21, "ETH_REFCLK"), "15": (36, "NRST"),
            "16": (28, "ETH_TXD0"), "17": (29, "ETH_TXD1"), "18": (27, "ETH_TXEN"),
            "19": (3, "+3V3_DIG"), "20": (14, "ETH_TXN"), "21": (13, "ETH_TXP"),
            "22": (16, "ETH_RXN"), "23": (15, "ETH_RXP"), "24": (32, "ETH_RBIAS"),
            "25": (1, "GND"),
        },
    ))
    # Y1: 25.000 MHz Crystal + Load Caps + RBIAS 12.1k 1%
    lines.append(load_kicad_mod(
        "Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod",
        "Y1", "25.000MHz", ox + 4.5, oy + 29.0, 0.0,
        pad_nets={"1": (30, "ETH_XTAL1"), "2": (1, "GND"), "3": (31, "ETH_XTAL2"), "4": (1, "GND")},
    ))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_Y1A", "18pF", ox + 4.5, oy + 25.2, 0.0, pad_nets={"1": (30, "ETH_XTAL1"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_Y1B", "18pF", ox + 4.5, oy + 32.8, 0.0, pad_nets={"1": (31, "ETH_XTAL2"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "R_BIAS", "12.1k 1%", ox + 19.0, oy + 27.5, 0.0, pad_nets={"1": (32, "ETH_RBIAS"), "2": (1, "GND")}))

    # --- SECTION 2: USB-C POWER, LDOs, SWD & STM32H743 (Mid Y: 33..66 mm) ---
    lines.append(load_kicad_mod(
        "Connector_USB.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod",
        "J2", "USB-C_16P", ox + 27.6, oy + 34.0, 90.0,
        pad_nets={
            "A1": (1, "GND"), "B12": (1, "GND"), "B1": (1, "GND"), "A12": (1, "GND"), "S1": (1, "GND"),
            "A4": (2, "+5V_USB"), "B9": (2, "+5V_USB"), "B4": (2, "+5V_USB"), "A9": (2, "+5V_USB"),
            "A5": (19, "USB_CC1"), "B5": (20, "USB_CC2"),
            "A6": (17, "USB_DP"), "B6": (17, "USB_DP"), "A7": (18, "USB_DM"), "B7": (18, "USB_DM"),
        },
    ))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "R_CC1", "5.1k", ox + 20.5, oy + 32.5, 0.0, pad_nets={"1": (19, "USB_CC1"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "R_CC2", "5.1k", ox + 20.5, oy + 35.5, 0.0, pad_nets={"1": (20, "USB_CC2"), "2": (1, "GND")}))

    lines.append(load_kicad_mod(
        "Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod",
        "U4", "LP5907MFX-3.3", ox + 5.5, oy + 38.0, 0.0,
        pad_nets={"1": (2, "+5V_USB"), "2": (1, "GND"), "3": (2, "+5V_USB"), "5": (3, "+3V3_DIG")},
    ))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_U4", "1uF", ox + 5.5, oy + 41.2, 0.0, pad_nets={"1": (3, "+3V3_DIG"), "2": (1, "GND")}))
    lines.append(load_kicad_mod(
        "Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod",
        "U5", "LP5907MFX-2.8", ox + 4.0, oy + 45.0, 0.0,
        pad_nets={"1": (2, "+5V_USB"), "2": (1, "GND"), "3": (2, "+5V_USB"), "5": (4, "+2V8_MEMS")},
    ))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_U5", "1uF", ox + 4.0, oy + 48.5, 0.0, pad_nets={"1": (4, "+2V8_MEMS"), "2": (1, "GND")}))

    # U3: STM32H743VIT6 (LQFP-100) — shifted 1.0mm left for generous right-edge routing channel
    lines.append(load_kicad_mod(
        "Package_QFP.pretty/LQFP-100_14x14mm_P0.5mm.kicad_mod",
        "U3", "STM32H743VIT6", ox + 15.5, oy + 52.0, 0.0,
        pad_nets={
            # Power & VCAP & Boot/Reset
            "11": (3, "+3V3_DIG"), "28": (3, "+3V3_DIG"), "50": (3, "+3V3_DIG"), "75": (3, "+3V3_DIG"), "100": (3, "+3V3_DIG"),
            "10": (1, "GND"), "27": (1, "GND"), "49": (1, "GND"), "74": (1, "GND"), "99": (1, "GND"),
            "48": (35, "VCAP"), "73": (35, "VCAP"), "14": (36, "NRST"), "94": (37, "BOOT0"),
            # SWD Debug (PA13=72, PA14=76)
            "72": (38, "SWDIO"), "76": (39, "SWCLK"),
            # USB (PA11=70, PA12=71)
            "70": (18, "USB_DM"), "71": (17, "USB_DP"),
            # ETH RMII LQFP-100 verified (PA1=24, PA2=25, PC1=16, PA7=32, PC4=33, PC5=34, PB11=47, PB12=51, PB13=52)
            "24": (21, "ETH_REFCLK"), "25": (22, "ETH_MDIO"), "16": (23, "ETH_MDC"),
            "32": (24, "ETH_CRSDV"), "33": (25, "ETH_RXD0"), "34": (26, "ETH_RXD1"),
            "47": (27, "ETH_TXEN"), "51": (28, "ETH_TXD0"), "52": (29, "ETH_TXD1"),
            # SAI1 (PE2=1 MCLK, PE5=4 SCK, PE4=3 FS, PE6=5 SD) & I2C1 (PB6=92 SCL, PB7=93 SDA)
            "1": (9, "SAI1_MCLK"), "4": (10, "SAI1_SCK"), "3": (11, "SAI1_FS"), "5": (12, "SAI1_SD"),
            "92": (33, "I2C1_SCL"), "93": (34, "I2C1_SDA"),
        },
    ))
    # STM32 VCAP (2x 2.2uF), Decoupling, NRST, BOOT0, SWD Header (1.5mm clear of right edge!)
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "C_VCAP1", "2.2uF", ox + 27.0, oy + 49.0, 0.0, pad_nets={"1": (35, "VCAP"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "C_VCAP2", "2.2uF", ox + 27.0, oy + 53.0, 0.0, pad_nets={"1": (35, "VCAP"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_VDD1", "100nF", ox + 15.5, oy + 41.0, 0.0, pad_nets={"1": (3, "+3V3_DIG"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_VDD2", "100nF", ox + 27.0, oy + 56.5, 0.0, pad_nets={"1": (3, "+3V3_DIG"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "R_NRST", "10k", ox + 4.5, oy + 56.0, 0.0, pad_nets={"1": (36, "NRST"), "2": (3, "+3V3_DIG")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", "C_NRST", "100nF", ox + 4.5, oy + 58.5, 0.0, pad_nets={"1": (36, "NRST"), "2": (1, "GND")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", "R_BOOT0", "10k", ox + 4.5, oy + 61.0, 0.0, pad_nets={"1": (37, "BOOT0"), "2": (1, "GND")}))
    lines.append(load_kicad_mod(
        "Connector_PinHeader_1.27mm.pretty/PinHeader_1x04_P1.27mm_Vertical_SMD_Pin1Left.kicad_mod",
        "J_SWD", "SWD_4P", ox + 27.0, oy + 61.5, 0.0,
        pad_nets={"1": (3, "+3V3_DIG"), "2": (38, "SWDIO"), "3": (39, "SWCLK"), "4": (1, "GND")},
    ))

    # --- SECTION 3: ANALOG FRONT-END, 24.576MHz OSC, FILTRI T3 & AK5572EN (Y: 66..98 mm) ---
    # Y2: Dedicated 24.576 MHz Low-Jitter Oscillator (<= 0.5 ps) clocking AK5572EN Master Mode!
    lines.append(load_kicad_mod(
        "Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod",
        "Y2", "24.576MHz_TCXO", ox + 26.5, oy + 69.5, 0.0,
        pad_nets={"1": (3, "+3V3_DIG"), "2": (1, "GND"), "3": (9, "SAI1_MCLK"), "4": (3, "+3V3_DIG")},
    ))
    lines.append(load_kicad_mod(
        "Package_DFN_QFN.pretty/QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm.kicad_mod",
        "U6", "AK5572EN", ox + 15.0, oy + 71.0, 0.0,
        pad_nets={
            "1": (2, "+5V_USB"), "15": (3, "+3V3_DIG"), "49": (1, "GND"),
            "10": (9, "SAI1_MCLK"), "11": (10, "SAI1_SCK"), "12": (11, "SAI1_FS"), "13": (12, "SAI1_SD"),
            "20": (33, "I2C1_SCL"), "21": (34, "I2C1_SDA"),
            "45": (48, "VCOM_2V5"),
            "47": (7, "AFE_OUT_P"), "46": (8, "AFE_OUT_N"),
            "42": (7, "AFE_OUT_P"), "41": (8, "AFE_OUT_N"),
        },
    ))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "C_VCOM", "10uF", ox + 5.5, oy + 71.0, 0.0, pad_nets={"1": (48, "VCOM_2V5"), "2": (1, "GND")}))

    # AFE Op-Amps & TMUX1104 Bypass
    lines.append(load_kicad_mod(
        "Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod",
        "U8", "OPA1656IDR", ox + 7.5, oy + 82.0, 0.0,
        pad_nets={"8": (2, "+5V_USB"), "4": (1, "GND"), "3": (47, "AA_INP"), "2": (7, "AFE_OUT_P"), "1": (7, "AFE_OUT_P"), "5": (48, "VCOM_2V5"), "6": (8, "AFE_OUT_N"), "7": (8, "AFE_OUT_N")},
    ))
    lines.append(load_kicad_mod(
        "Package_SO.pretty/MSOP-10_3x3mm_P0.5mm.kicad_mod",
        "U9", "TMUX1104DGSR", ox + 16.0, oy + 82.0, 0.0,
        pad_nets={"6": (2, "+5V_USB"), "2": (1, "GND"), "4": (40, "PRE_OUT"), "9": (43, "HPF_OUT"), "8": (44, "LPF_N1")},
    ))
    lines.append(load_kicad_mod(
        "Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod",
        "U7", "OPA1656IDR", ox + 25.0, oy + 82.0, 0.0,
        pad_nets={"8": (2, "+5V_USB"), "4": (1, "GND"), "3": (5, "MEMS_P"), "2": (6, "MEMS_N"), "1": (40, "PRE_OUT"), "5": (42, "HPF_INP"), "6": (43, "HPF_OUT"), "7": (43, "HPF_OUT")},
    ))

    # T3 Butterworth Filter Discrete Passives (HPF 20Hz + AA 140kHz)
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", "C_HPF1", "100nF C0G", ox + 25.5, oy + 88.5, 0.0, pad_nets={"1": (40, "PRE_OUT"), "2": (41, "HPF_N1")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", "C_HPF2", "100nF C0G", ox + 25.5, oy + 92.0, 0.0, pad_nets={"1": (41, "HPF_N1"), "2": (42, "HPF_INP")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", "R_HPF_FB", "56.2k 0.1%", ox + 20.5, oy + 88.5, 0.0, pad_nets={"1": (41, "HPF_N1"), "2": (43, "HPF_OUT")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", "R_HPF_GND", "113k 0.1%", ox + 20.5, oy + 91.5, 0.0, pad_nets={"1": (42, "HPF_INP"), "2": (48, "VCOM_2V5")}))

    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", "R_AA1", "806R 0.1%", ox + 6.0, oy + 88.5, 0.0, pad_nets={"1": (44, "LPF_N1"), "2": (46, "AA_N1")}))
    lines.append(load_kicad_mod("Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", "R_AA2", "806R 0.1%", ox + 6.0, oy + 91.5, 0.0, pad_nets={"1": (46, "AA_N1"), "2": (47, "AA_INP")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "C_AA_FB", "2.0nF C0G", ox + 10.5, oy + 88.5, 0.0, pad_nets={"1": (46, "AA_N1"), "2": (7, "AFE_OUT_P")}))
    lines.append(load_kicad_mod("Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", "C_AA_GND", "1.0nF C0G", ox + 10.5, oy + 91.5, 0.0, pad_nets={"1": (47, "AA_INP"), "2": (1, "GND")}))

    # J3: JST-SH 4-pin MEMS Header at front tip edge
    lines.append(load_kicad_mod(
        "Connector_JST.pretty/JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal.kicad_mod",
        "J3", "MEMS_IN_4P", ox + 15.5, oy + 94.5, 0.0,
        pad_nets={"1": (4, "+2V8_MEMS"), "2": (5, "MEMS_P"), "3": (6, "MEMS_N"), "4": (1, "GND")},
    ))

    # 3x Asymmetric Optical Fiducials + 4x Bring-up Test Points
    for idx, (fx, fy) in enumerate([(3.0, 20.5), (29.0, 20.5), (3.0, 95.0)], start=1):
        lines.append(load_kicad_mod("Fiducial.pretty/Fiducial_1mm_Mask2mm.kicad_mod", f"FID{idx}", "FID", ox + fx, oy + fy, 0.0))
    for idx, (tx, ty, nm, nid) in enumerate([
        (29.0, 44.0, "TP_5V", 2), (2.8, 65.0, "TP_3V3", 3), (2.8, 75.5, "TP_2V8", 4), (29.0, 75.5, "TP_MCLK", 9),
    ], start=1):
        lines.append(load_kicad_mod(
            "TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod",
            f"TP{idx}", nm, ox + tx, oy + ty, 0.0,
            pad_nets={"1": (nid, nm)},
        ))

    # Standard QFN Thermal & RF Ground Vias directly into solid In1.Cu GND plane (U2 LAN8742A & U6 AK5572EN)
    lines.append(via(ox + 12.0, oy + 29.0, 1, size=0.60, drill=0.30))
    lines.append(via(ox + 15.0, oy + 71.0, 1, size=0.60, drill=0.30))
    lines.append(via(ox + 14.0, oy + 70.0, 1, size=0.60, drill=0.30))
    lines.append(via(ox + 16.0, oy + 72.0, 1, size=0.60, drill=0.30))

    # No pre-routing zones: FreeRouting routes 100% of all 128 nets (incl. GND/+3V3_DIG) explicitly
    # across all 4 layers, then t6_autoroute_freerouting.py pours the In1.Cu GND shield plane!

    lines.append(")")
    MAIN_PCB.write_text("\n".join(lines), encoding="utf-8")


def run_drc_and_export(pcb_path: Path, name: str, layers_csv: str, zip_name: str):
    """Runs KiCad DRC and exports Gerbers, Excellon drills, SVGs, and a JLCPCB ZIP.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        name: Short board identifier used in output filenames.
        layers_csv: Comma-separated KiCad layer list for Gerber export.
        zip_name: Output Gerber ZIP filename inside ``GERBER_DIR``.

    Returns:
        Tuple of ``(drc_errors, unconnected_items, zip_path)``.
    """
    drc_json = DRC_DIR / f"drc_{name}.json"
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "-o", str(drc_json), str(pcb_path)], capture_output=True)
    drc = json.loads(drc_json.read_text(encoding="utf-8"))
    errs = [v for v in drc.get("violations", []) if v.get("severity") == "error"]
    unconn = drc.get("unconnected_items", [])

    tmp_dir = GERBER_DIR / f"kicad10_{name}"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # KiCad 10 native Gerber export (Protel extensions enabled by default!)
    subprocess.run([
        KICAD_CLI, "pcb", "export", "gerbers",
        "--layers", layers_csv,
        "--subtract-soldermask",
        "--output", str(tmp_dir),
        str(pcb_path),
    ], capture_output=True)
    subprocess.run([
        KICAD_CLI, "pcb", "export", "drill",
        "--format", "excellon",
        "--excellon-units", "mm",
        "--excellon-zeros-format", "decimal",
        "--excellon-oval-format", "alternate",
        "--output", str(tmp_dir),
        str(pcb_path),
    ], capture_output=True)

    # Native KiCad 10 SVG renders
    subprocess.run([KICAD_CLI, "pcb", "export", "svg", "-l", "F.Cu,F.Silkscreen,F.Mask,Edge.Cuts", "-o", str(RENDER_DIR / f"kicad_{name}_front.svg"), str(pcb_path)], capture_output=True)
    subprocess.run([KICAD_CLI, "pcb", "export", "svg", "-l", "B.Cu,B.Silkscreen,B.Mask,Edge.Cuts", "--mirror", "-o", str(RENDER_DIR / f"kicad_{name}_back.svg"), str(pcb_path)], capture_output=True)

    zpath = GERBER_DIR / zip_name
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp_dir.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, p.name)

    return errs, unconn, zpath


def main():
    """Builds MEMS Tip and Main Stage 1 PCBs, runs DRC, and exports Gerber ZIPs."""
    build_tip_pcb()
    build_main_pcb_stage1()
    e_tip, u_tip, z_tip = run_drc_and_export(
        TIP_PCB, "mems_tip",
        "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
        "IU-MIC_ORIGIN_MEMS_Tip_JLCPCB_Gerbers.zip",
    )
    e_main, u_main, z_main = run_drc_and_export(
        MAIN_PCB, "main_stage1",
        "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
        "IU-MIC_ORIGIN_Main_JLCPCB_Gerbers.zip",
    )
    print(f"DRC MEMS Tip:     {len(e_tip)} errors, {len(u_tip)} unconnected | ZIP: {z_tip.name}")
    for v in e_tip[:5]:
        print("  [DRC TIP]", v.get("type"), "-", v.get("description"))
    print(f"DRC Main Stadio1: {len(e_main)} errors, {len(u_main)} unconnected | ZIP: {z_main.name}")
    for v in e_main[:5]:
        print("  [DRC MAIN]", v.get("type"), "-", v.get("description"))


if __name__ == "__main__":
    main()
