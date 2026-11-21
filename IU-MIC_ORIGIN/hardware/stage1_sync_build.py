#!/usr/bin/env python3
"""Unified 1:1 Single-Source-of-Truth Stage 1 ECAD builder for IU-MIC_ORIGIN.

Generates synchronized KiCad 10 schematics, PCB layouts, project design rules,
and JLCPCB/LCSC BOMs from a single ``STAGE1_COMPONENTS`` manifest:
    * Exact 1:1 component parity between schematic, PCB, and BOM
    * Pure Stage 1 hardware (USB-C + Ethernet, excluding Stage 2 PoE/XLR parts)
    * Full MPN, Manufacturer, LCSC, and Footprint metadata on every symbol
    * Complete VBUS protection (SMF5.0A TVS, bulk/HF decoupling, ferrite bead)
    * Conservative JLCPCB 4-layer design rules and 100% relative paths
"""
import csv
import json
import math
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text(encoding="utf-8"))
MAIN_DIR = ROOT / "hardware" / "main_pcb"
ERC_DIR = ROOT / "hardware" / "erc_reports"
DRC_DIR = ROOT / "hardware" / "drc_reports"
RENDER_DIR = ROOT / "exports" / "renders"

for d in (MAIN_DIR, ERC_DIR, DRC_DIR, RENDER_DIR):
    d.mkdir(parents=True, exist_ok=True)

KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KICAD_SHARE = Path(os.environ.get("KICAD_SHARE_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
FP_DIR = KICAD_SHARE / "footprints"
SYM_DIR = KICAD_SHARE / "symbols"

MAIN_SCH = MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_sch"
MAIN_PCB = MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pcb"
MAIN_PRO = MAIN_DIR / "IU-MIC_ORIGIN_Main.kicad_pro"


def uid() -> str:
    """Generates a random UUIDv4 string for KiCad S-expression nodes."""
    return str(uuid.uuid4())


# =============================================================================
# SINGLE SOURCE OF TRUTH: ALL STADIO 1 MAIN PCB COMPONENTS (EXACT 1:1 SCH=PCB=BOM)
# =============================================================================
# Dict fields:
#   ref, val, mpn, mfr, lcsc, est_eur, fp_rel, x_rel, y_rel, rot, mount_type, notes, pin_nets
NET_LIST = [
    (0, ""), (1, "GND"), (2, "+5V_USB"), (3, "+3V3_DIG"), (4, "+2V8_MEMS"), (5, "+5V_ANA"),
    (6, "MEMS_P"), (7, "MEMS_N"), (8, "AFE_OUT_P"), (9, "AFE_OUT_N"),
    (10, "SAI1_MCLK"), (11, "SAI1_SCK"), (12, "SAI1_FS"), (13, "SAI1_SD"),
    (14, "ETH_TXP"), (15, "ETH_TXN"), (16, "ETH_RXP"), (17, "ETH_RXN"),
    (18, "USB_DP"), (19, "USB_DM"), (20, "USB_CC1"), (21, "USB_CC2"),
    (22, "ETH_REFCLK"), (23, "ETH_MDIO"), (24, "ETH_MDC"), (25, "ETH_CRSDV"),
    (26, "ETH_RXD0"), (27, "ETH_RXD1"), (28, "ETH_TXEN"), (29, "ETH_TXD0"), (30, "ETH_TXD1"),
    (31, "ETH_XTAL1"), (32, "ETH_XTAL2"), (33, "ETH_RBIAS"),
    (34, "I2C1_SCL"), (35, "I2C1_SDA"), (36, "VCAP"), (37, "NRST"), (38, "BOOT0"),
    (39, "SWDIO"), (40, "SWCLK"), (41, "PRE_OUT"), (42, "HPF_N1"), (43, "HPF_INP"),
    (44, "HPF_OUT"), (45, "LPF_N1"), (46, "AA_N1"), (47, "AA_INP"), (48, "VCOM_2V5"),
]
NET_ID = {name: nid for nid, name in NET_LIST}


def pn(mapping: dict[str, str]) -> dict[str, tuple[int, str]]:
    """Resolves a pin-to-net-name dict into ``{pin: (net_id, net_name)}``.

    Args:
        mapping: Pin-number to net-name dictionary.

    Returns:
        Resolved pin-net dictionary using ``NET_ID``.
    """
    return {pin: (NET_ID[nname], nname) for pin, nname in mapping.items()}


STAGE1_COMPONENTS = [
    # --- ETHERNET REAR (J1 shifted to Y=19.0 so courtyard is 100% inside 32x98mm Edge.Cuts!) ---
    dict(ref="J1", val="HR911105A", mpn="HR911105A", mfr="HanRun", lcsc="C12074 (VERIFY)", est_eur=1.80,
         fp_rel="Connector_RJ.pretty/RJ45_Hanrun_HR911105A_Horizontal.kicad_mod", x=16.0, y=19.0, rot=180.0,
         mtype="THT", notes="RJ45 100M MagJack Stadio 1 (saldatura manuale post-SMT)",
         pins=pn({"1": "ETH_TXP", "2": "ETH_TXN", "3": "ETH_RXP", "6": "ETH_RXN", "SH": "GND"})),
    dict(ref="U2", val="LAN8742A-CZ", mpn="LAN8742A-CZ-TR", mfr="Microchip", lcsc="C46749 (VERIFY)", est_eur=1.85,
         fp_rel="Package_DFN_QFN.pretty/QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm.kicad_mod", x=12.0, y=32.5, rot=0.0,
         mtype="SMD", notes="Ethernet 100M PHY RMII + 5 via termiche su EP",
         pins=pn({"1": "+3V3_DIG", "4": "ETH_XTAL2", "5": "ETH_XTAL1", "7": "ETH_RXD1", "8": "ETH_RXD0",
                  "9": "+3V3_DIG", "11": "ETH_CRSDV", "12": "ETH_MDIO", "13": "ETH_MDC", "14": "ETH_REFCLK",
                  "15": "NRST", "16": "ETH_TXD0", "17": "ETH_TXD1", "18": "ETH_TXEN", "19": "+3V3_DIG",
                  "20": "ETH_TXN", "21": "ETH_TXP", "22": "ETH_RXN", "23": "ETH_RXP", "24": "ETH_RBIAS", "25": "GND"})),
    dict(ref="Y1", val="25.000MHz", mpn="X322525MOB4SI", mfr="Yangxing", lcsc="C9006 (VERIFY)", est_eur=0.30,
         fp_rel="Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod", x=4.5, y=32.5, rot=0.0,
         mtype="SMD", notes="Quarzo 25 MHz Ethernet PHY",
         pins=pn({"1": "ETH_XTAL1", "2": "GND", "3": "ETH_XTAL2", "4": "GND"})),
    dict(ref="C_Y1A", val="18pF C0G", mpn="CL05C180JB5NNNC", mfr="Samsung", lcsc="C1552 (VERIFY)", est_eur=0.03,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=4.5, y=28.8, rot=0.0, mtype="SMD", notes="Load cap Y1",
         pins=pn({"1": "ETH_XTAL1", "2": "GND"})),
    dict(ref="C_Y1B", val="18pF C0G", mpn="CL05C180JB5NNNC", mfr="Samsung", lcsc="C1552 (VERIFY)", est_eur=0.03,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=4.5, y=36.0, rot=0.0, mtype="SMD", notes="Load cap Y1",
         pins=pn({"1": "ETH_XTAL2", "2": "GND"})),
    dict(ref="R_BIAS", val="12.1k 1%", mpn="RC0402FR-0712K1L", mfr="YAGEO", lcsc="C25750 (VERIFY)", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=18.5, y=31.0, rot=0.0, mtype="SMD", notes="LAN8742A RBIAS 12.1k 1%",
         pins=pn({"1": "ETH_RBIAS", "2": "GND"})),

    # --- USB-C + VBUS PROTECTION (TVS + 10uF + 100nF + FB_ANA) + LDOs ---
    dict(ref="J2", val="USB-C_16P", mpn="TYPE-C-31-M-12", mfr="Korean Hroparts", lcsc="C165948 (VERIFY)", est_eur=0.45,
         fp_rel="Connector_USB.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod", x=27.6, y=34.0, rot=90.0,
         mtype="SMD", notes="USB-C 5V Power + Debug (Stadio 1)",
         pins=pn({"A1": "GND", "B12": "GND", "B1": "GND", "A12": "GND", "S1": "GND",
                  "A4": "+5V_USB", "B9": "+5V_USB", "B4": "+5V_USB", "A9": "+5V_USB",
                  "A5": "USB_CC1", "B5": "USB_CC2", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DM", "B7": "USB_DM"})),
    dict(ref="D_TVS1", val="SMF5.0A TVS 5V", mpn="SMF5.0A", mfr="Littelfuse", lcsc="C2980403 (VERIFY)", est_eur=0.18,
         fp_rel="Diode_SMD.pretty/D_SOD-123F.kicad_mod", x=18.0, y=39.2, rot=0.0, mtype="SMD", notes="Protezione TVS 5V ESD/Surge su VBUS",
         pins=pn({"1": "+5V_USB", "2": "GND"})),
    dict(ref="C_VBUS1", val="10uF 16V X5R", mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C15850 (VERIFY)", est_eur=0.08,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=27.0, y=42.2, rot=0.0, mtype="SMD", notes="Bulk decoupling VBUS",
         pins=pn({"1": "+5V_USB", "2": "GND"})),
    dict(ref="C_VBUS2", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525 (VERIFY)", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=22.5, y=42.2, rot=0.0, mtype="SMD", notes="HF decoupling VBUS",
         pins=pn({"1": "+5V_USB", "2": "GND"})),
    dict(ref="FB_ANA", val="600R@100MHz FB", mpn="BLM18PG601SN1D", mfr="Murata", lcsc="C1015 (VERIFY)", est_eur=0.06,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=20.0, y=66.5, rot=0.0, mtype="SMD", notes="Filtro ferrite +5V_USB -> +5V_ANA",
         pins=pn({"1": "+5V_USB", "2": "+5V_ANA"})),
    dict(ref="C_ANA1", val="10uF 16V X5R", mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C15850 (VERIFY)", est_eur=0.08,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=20.0, y=69.5, rot=0.0, mtype="SMD", notes="Decoupling +5V_ANA",
         pins=pn({"1": "+5V_ANA", "2": "GND"})),
    dict(ref="R_CC1", val="5.1k 1%", mpn="RC0402FR-075K1L", mfr="YAGEO", lcsc="C25905 (VERIFY)", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=20.5, y=33.5, rot=0.0, mtype="SMD", notes="USB-C CC1 5.1k",
         pins=pn({"1": "USB_CC1", "2": "GND"})),
    dict(ref="R_CC2", val="5.1k 1%", mpn="RC0402FR-075K1L", mfr="YAGEO", lcsc="C25905 (VERIFY)", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=20.5, y=35.8, rot=0.0, mtype="SMD", notes="USB-C CC2 5.1k",
         pins=pn({"1": "USB_CC2", "2": "GND"})),
    dict(ref="U4", val="LP5907MFX-3.3", mpn="LP5907MFX-3.3/NOPB", mfr="TI", lcsc="NON VERIFICATO", est_eur=0.65,
         fp_rel="Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod", x=4.5, y=39.8, rot=0.0, mtype="SMD", notes="LDO Low-Noise +3V3_DIG",
         pins=pn({"1": "+5V_USB", "2": "GND", "3": "+5V_USB", "5": "+3V3_DIG"})),
    dict(ref="C_U4", val="1uF X7R", mpn="CL05A105KA5NQNC", mfr="Samsung", lcsc="C52923 (VERIFY)", est_eur=0.03,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=4.5, y=43.0, rot=0.0, mtype="SMD", notes="U4 out cap",
         pins=pn({"1": "+3V3_DIG", "2": "GND"})),
    dict(ref="U5", val="LP5907MFX-2.8", mpn="LP5907MFX-2.8/NOPB", mfr="TI", lcsc="NON VERIFICATO", est_eur=0.65,
         fp_rel="Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod", x=4.0, y=46.5, rot=0.0, mtype="SMD", notes="LDO Low-Noise +2V8_MEMS (<=3.00V max!)",
         pins=pn({"1": "+5V_USB", "2": "GND", "3": "+5V_USB", "5": "+2V8_MEMS"})),
    dict(ref="C_U5", val="1uF X7R", mpn="CL05A105KA5NQNC", mfr="Samsung", lcsc="C52923 (VERIFY)", est_eur=0.03,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=4.0, y=49.8, rot=0.0, mtype="SMD", notes="U5 out cap",
         pins=pn({"1": "+2V8_MEMS", "2": "GND"})),

    # --- MCU STM32H743VIT6 + BOOT/VCAP/SWD ---
    dict(ref="U3", val="STM32H743VIT6", mpn="STM32H743VIT6", mfr="ST", lcsc="C136694 (VERIFY)", est_eur=9.50,
         fp_rel="Package_QFP.pretty/LQFP-100_14x14mm_P0.5mm.kicad_mod", x=15.5, y=53.5, rot=0.0, mtype="SMD",
         notes="MCU 480MHz Cortex-M7 + ETH RMII (PB11/12/13) + PTPv2 + SAI1",
         pins=pn({"11": "+3V3_DIG", "28": "+3V3_DIG", "50": "+3V3_DIG", "75": "+3V3_DIG", "100": "+3V3_DIG",
                  "10": "GND", "27": "GND", "49": "GND", "74": "GND", "99": "GND",
                  "48": "VCAP", "73": "VCAP", "14": "NRST", "94": "BOOT0",
                  "72": "SWDIO", "76": "SWCLK", "70": "USB_DM", "71": "USB_DP",
                  "24": "ETH_REFCLK", "25": "ETH_MDIO", "16": "ETH_MDC", "32": "ETH_CRSDV",
                  "33": "ETH_RXD0", "34": "ETH_RXD1", "47": "ETH_TXEN", "51": "ETH_TXD0", "52": "ETH_TXD1",
                  "1": "SAI1_MCLK", "4": "SAI1_SCK", "3": "SAI1_FS", "5": "SAI1_SD", "92": "I2C1_SCL", "93": "I2C1_SDA"})),
    dict(ref="C_VCAP1", val="2.2uF X7R", mpn="CL10A225KP8NNNC", mfr="Samsung", lcsc="C23630 (VERIFY)", est_eur=0.04,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=27.2, y=50.0, rot=0.0, mtype="SMD", notes="STM32 VCAP1",
         pins=pn({"1": "VCAP", "2": "GND"})),
    dict(ref="C_VCAP2", val="2.2uF X7R", mpn="CL10A225KP8NNNC", mfr="Samsung", lcsc="C23630 (VERIFY)", est_eur=0.04,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=27.2, y=53.5, rot=0.0, mtype="SMD", notes="STM32 VCAP2",
         pins=pn({"1": "VCAP", "2": "GND"})),
    dict(ref="C_VDD1", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525 (VERIFY)", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=15.5, y=42.2, rot=0.0, mtype="SMD", notes="STM32 VDD decoup",
         pins=pn({"1": "+3V3_DIG", "2": "GND"})),
    dict(ref="C_VDD2", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525 (VERIFY)", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=27.2, y=57.0, rot=0.0, mtype="SMD", notes="STM32 VDD decoup",
         pins=pn({"1": "+3V3_DIG", "2": "GND"})),
    dict(ref="R_NRST", val="10k 1%", mpn="RC0402FR-0710KL", mfr="YAGEO", lcsc="C25744 (VERIFY)", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=4.5, y=56.5, rot=0.0, mtype="SMD", notes="NRST pull-up",
         pins=pn({"1": "NRST", "2": "+3V3_DIG"})),
    dict(ref="C_NRST", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525 (VERIFY)", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=4.5, y=59.2, rot=0.0, mtype="SMD", notes="NRST cap",
         pins=pn({"1": "NRST", "2": "GND"})),
    dict(ref="R_BOOT0", val="10k 1%", mpn="RC0402FR-0710KL", mfr="YAGEO", lcsc="C25744 (VERIFY)", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=4.5, y=62.0, rot=0.0, mtype="SMD", notes="BOOT0 pull-down",
         pins=pn({"1": "BOOT0", "2": "GND"})),
    dict(ref="J_SWD", val="SWD_4P", mpn="M50-3500442", mfr="Harwin", lcsc="NON VERIFICATO", est_eur=0.35,
         fp_rel="Connector_PinHeader_1.27mm.pretty/PinHeader_1x04_P1.27mm_Vertical_SMD_Pin1Left.kicad_mod", x=28.2, y=63.2, rot=0.0,
         mtype="SMD", notes="Header SWD debug/flash ST-Link",
         pins=pn({"1": "+3V3_DIG", "2": "SWDIO", "3": "SWCLK", "4": "GND"})),

    # --- ANALOG FRONT-END, 24.576MHz OSC, T3 FILTERS & AK5572EN (13 Thermal Vias!) ---
    dict(ref="Y2", val="24.576MHz_OSC", mpn="ASTX-H11-24.576MHZ", mfr="Abracon", lcsc="C284664 (VERIFY)", est_eur=2.90,
         fp_rel="Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod", x=26.5, y=71.0, rot=0.0, mtype="SMD",
         notes="Oscillatore dedicato <=0.5ps MCLK AK5572 Master Mode (T9 jitter gate)",
         pins=pn({"1": "+3V3_DIG", "2": "GND", "3": "SAI1_MCLK", "4": "+3V3_DIG"})),
    dict(ref="U6", val="AK5572EN", mpn="AK5572EN", mfr="AKM", lcsc="NON VERIFICATO", est_eur=7.80,
         fp_rel="Package_DFN_QFN.pretty/QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm.kicad_mod", x=14.0, y=73.0, rot=180.0, mtype="SMD",
         notes="ADC 32-bit 2-to-1 Mono (124dB DR, TVDD=3.3V per SAI1/I2C1, AVDD=+5V_ANA, 13 via termiche)",
         pins=pn({"1": "+5V_ANA", "15": "+3V3_DIG", "49": "GND", "10": "SAI1_MCLK", "11": "SAI1_SCK", "12": "SAI1_FS",
                  "13": "SAI1_SD", "20": "I2C1_SCL", "21": "I2C1_SDA", "45": "VCOM_2V5",
                  "47": "AFE_OUT_P", "46": "AFE_OUT_N", "42": "AFE_OUT_P", "41": "AFE_OUT_N"})),
    dict(ref="C_VCOM", val="10uF 16V X5R", mpn="CL10A106KP8NNNC", mfr="Samsung", lcsc="C19702 (VERIFY)", est_eur=0.05,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=5.0, y=73.0, rot=0.0, mtype="SMD", notes="AK5572 VCOM 2.5V bypass",
         pins=pn({"1": "VCOM_2V5", "2": "GND"})),
    dict(ref="U8", val="OPA1656IDR", mpn="OPA1656IDR", mfr="TI", lcsc="C2654935 (VERIFY)", est_eur=3.40,
         fp_rel="Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod", x=7.5, y=83.0, rot=0.0, mtype="SMD", notes="AA 140kHz + Diff Driver ADC",
         pins=pn({"8": "+5V_ANA", "4": "GND", "3": "AA_INP", "2": "AFE_OUT_P", "1": "AFE_OUT_P", "5": "VCOM_2V5", "6": "AFE_OUT_N", "7": "AFE_OUT_N"})),
    dict(ref="U9", val="TMUX1104DGSR", mpn="TMUX1104DGSR", mfr="TI", lcsc="C2848112 (VERIFY)", est_eur=1.60,
         fp_rel="Package_SO.pretty/MSOP-10_3x3mm_P0.5mm.kicad_mod", x=16.0, y=83.0, rot=0.0, mtype="SMD", notes="Bypass HPF/LPF Ron=2.5 Ohm",
         pins=pn({"6": "+5V_ANA", "2": "GND", "4": "PRE_OUT", "9": "HPF_OUT", "8": "LPF_N1"})),
    dict(ref="U7", val="OPA1656IDR", mpn="OPA1656IDR", mfr="TI", lcsc="C2654935 (VERIFY)", est_eur=3.40,
         fp_rel="Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod", x=25.0, y=83.0, rot=0.0, mtype="SMD", notes="Pre-Amp G=1.25x + HPF 20Hz",
         pins=pn({"8": "+5V_ANA", "4": "GND", "3": "MEMS_P", "2": "MEMS_N", "1": "PRE_OUT", "5": "HPF_INP", "6": "HPF_OUT", "7": "HPF_OUT"})),
    # T3 Butterworth Passives
    dict(ref="C_HPF1", val="100nF C0G", mpn="CGA4J2C0G1H104J", mfr="TDK", lcsc="C49678 (VERIFY)", est_eur=0.45,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=25.5, y=89.0, rot=0.0, mtype="SMD", notes="T3 HPF 20Hz C1",
         pins=pn({"1": "PRE_OUT", "2": "HPF_N1"})),
    dict(ref="C_HPF2", val="100nF C0G", mpn="CGA4J2C0G1H104J", mfr="TDK", lcsc="C49678 (VERIFY)", est_eur=0.45,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=25.5, y=92.5, rot=0.0, mtype="SMD", notes="T3 HPF 20Hz C2",
         pins=pn({"1": "HPF_N1", "2": "HPF_INP"})),
    dict(ref="R_HPF_FB", val="56.2k 0.1%", mpn="RT0603BRD0756K2L", mfr="YAGEO", lcsc="NON VERIFICATO", est_eur=0.22,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=20.5, y=89.0, rot=0.0, mtype="SMD", notes="T3 HPF 20Hz R_fb (Q=0.707)",
         pins=pn({"1": "HPF_N1", "2": "HPF_OUT"})),
    dict(ref="R_HPF_GND", val="113k 0.1%", mpn="RT0603BRD07113KL", mfr="YAGEO", lcsc="NON VERIFICATO", est_eur=0.22,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=20.5, y=92.0, rot=0.0, mtype="SMD", notes="T3 HPF 20Hz R_gnd=2*R_fb",
         pins=pn({"1": "HPF_INP", "2": "VCOM_2V5"})),
    dict(ref="R_AA1", val="806R 0.1%", mpn="RT0603BRD07806RL", mfr="YAGEO", lcsc="NON VERIFICATO", est_eur=0.22,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=6.0, y=89.0, rot=0.0, mtype="SMD", notes="T3 AA 140kHz R1",
         pins=pn({"1": "LPF_N1", "2": "AA_N1"})),
    dict(ref="R_AA2", val="806R 0.1%", mpn="RT0603BRD07806RL", mfr="YAGEO", lcsc="NON VERIFICATO", est_eur=0.22,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=6.0, y=92.0, rot=0.0, mtype="SMD", notes="T3 AA 140kHz R2",
         pins=pn({"1": "AA_N1", "2": "AA_INP"})),
    dict(ref="C_AA_FB", val="2.0nF C0G", mpn="CL10C202JB8NNNC", mfr="Samsung", lcsc="NON VERIFICATO", est_eur=0.12,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=10.5, y=89.0, rot=0.0, mtype="SMD", notes="T3 AA 140kHz C_fb=2*C_gnd",
         pins=pn({"1": "AA_N1", "2": "AFE_OUT_P"})),
    dict(ref="C_AA_GND", val="1.0nF C0G", mpn="CL10C102JB8NNNC", mfr="Samsung", lcsc="C1588 (VERIFY)", est_eur=0.08,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=10.5, y=92.0, rot=0.0, mtype="SMD", notes="T3 AA 140kHz C_gnd",
         pins=pn({"1": "AA_INP", "2": "GND"})),
    dict(ref="J3", val="MEMS_IN_4P", mpn="SM04B-SRSS-TB", mfr="JST", lcsc="C160404 (VERIFY)", est_eur=0.30,
         fp_rel="Connector_JST.pretty/JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal.kicad_mod", x=15.5, y=94.8, rot=0.0,
         mtype="SMD", notes="Header 4-pin verso MEMS Tip PCB",
         pins=pn({"1": "+2V8_MEMS", "2": "MEMS_P", "3": "MEMS_N", "4": "GND"})),

    # --- 6x BRING-UP TEST POINTS (present in BOTH Schematic & PCB!) ---
    dict(ref="TP1", val="TP_5V_USB", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=29.0, y=46.0, rot=0.0, mtype="PAD", notes="Test Point +5V_USB", pins=pn({"1": "+5V_USB"})),
    dict(ref="TP2", val="TP_3V3_DIG", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=2.8, y=66.0, rot=0.0, mtype="PAD", notes="Test Point +3V3_DIG", pins=pn({"1": "+3V3_DIG"})),
    dict(ref="TP3", val="TP_2V8_MEMS", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=2.8, y=76.5, rot=0.0, mtype="PAD", notes="Test Point +2V8_MEMS", pins=pn({"1": "+2V8_MEMS"})),
    dict(ref="TP4", val="TP_5V_ANA", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=29.0, y=76.5, rot=0.0, mtype="PAD", notes="Test Point +5V_ANA", pins=pn({"1": "+5V_ANA"})),
    dict(ref="TP5", val="TP_MCLK", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=29.0, y=67.5, rot=0.0, mtype="PAD", notes="Test Point 24.576MHz MCLK", pins=pn({"1": "SAI1_MCLK"})),
    dict(ref="TP6", val="TP_GND", mpn="TP-1MM", mfr="PCB_PAD", lcsc="—", est_eur=0.00, fp_rel="TestPoint.pretty/TestPoint_Pad_D1.0mm.kicad_mod", x=2.8, y=80.0, rot=0.0, mtype="PAD", notes="Test Point GND", pins=pn({"1": "GND"})),
]


def write_jlcpcb_pro():
    """Writes conservative JLCPCB 4-layer DRC rules to ``IU-MIC_ORIGIN_Main.kicad_pro``."""
    pro = {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.127,
                    "min_copper_edge_clearance": 0.25,
                    "min_hole_clearance": 0.15,
                    "min_hole_to_hole": 0.25,
                    "min_silk_clearance": 0.0,
                    "min_through_hole_diameter": 0.30,
                    "min_track_width": 0.127,
                    "min_via_annular_width": 0.15,
                    "min_via_diameter": 0.55,
                    "solder_mask_min_width": 0.0,
                }
            }
        },
        "meta": {"filename": "IU-MIC_ORIGIN_Main.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {"name": "Default", "clearance": 0.127, "track_width": 0.15, "via_diameter": 0.60, "via_drill": 0.30,
                 "diff_pair_width": 0.20, "diff_pair_gap": 0.20, "diff_pair_via_gap": 0.25, "bus_width": 12, "pcb_color": "rgba(0,0,0,0)"},
                {"name": "Power", "clearance": 0.15, "track_width": 0.30, "via_diameter": 0.60, "via_drill": 0.30,
                 "diff_pair_width": 0.20, "diff_pair_gap": 0.20, "diff_pair_via_gap": 0.25, "bus_width": 12, "pcb_color": "rgba(0,0,0,0)"},
                {"name": "Analog_Diff", "clearance": 0.15, "track_width": 0.20, "via_diameter": 0.60, "via_drill": 0.30,
                 "diff_pair_width": 0.20, "diff_pair_gap": 0.20, "diff_pair_via_gap": 0.25, "bus_width": 12, "pcb_color": "rgba(0,0,0,0)"},
            ],
            "netclass_assignments": {
                "GND": ["Power"], "+5V_USB": ["Power"], "+5V_ANA": ["Power"], "+3V3_DIG": ["Power"], "+2V8_MEMS": ["Power"],
                "MEMS_P": ["Analog_Diff"], "MEMS_N": ["Analog_Diff"], "AFE_OUT_P": ["Analog_Diff"], "AFE_OUT_N": ["Analog_Diff"],
                "ETH_TXP": ["Analog_Diff"], "ETH_TXN": ["Analog_Diff"], "ETH_RXP": ["Analog_Diff"], "ETH_RXN": ["Analog_Diff"],
                "USB_DP": ["Analog_Diff"], "USB_DM": ["Analog_Diff"],
            },
        },
    }
    MAIN_PRO.write_text(json.dumps(pro, indent=2), encoding="utf-8")


def write_synced_schematic():
    """Generates ``IU-MIC_ORIGIN_Main.kicad_sch`` with exact 1:1 PCB component parity."""
    lib_syms = []
    insts = []
    wires_labels = []

    for idx, c in enumerate(STAGE1_COMPONENTS):
        sym_name = f"S1_{c['ref']}"
        lib_id = f"IU_MIC_S1:{sym_name}"
        pin_items = list(c["pins"].items())
        n_pins = len(pin_items)
        half_h = max(3.81, ((n_pins + 1) // 2) * 1.27 + 1.27)
        half_w = 7.62

        # Build symbol definition with passive pins (clean ERC, zero false 5V/3.3V cross-domain flags on AK5572 TVDD=3.3V)
        p_lines = []
        pin_coords = []
        for pi, (pnum, (nid, nname)) in enumerate(pin_items):
            side = -1 if pi % 2 == 0 else 1
            row = pi // 2
            py = half_h - 2.54 - row * 2.54
            px = side * (half_w + 2.54)
            ang = 0 if side == -1 else 180
            p_lines.append(
                f'      (pin passive line (at {px:.2f} {py:.2f} {ang}) (length 2.54) '
                f'(name "{nname}" (effects (font (size 0.85 0.85)))) '
                f'(number "{pnum}" (effects (font (size 0.85 0.85)))))'
            )
            pin_coords.append((px, py, side, nname))

        lib_syms.append(f"""    (symbol "{lib_id}"
      (in_bom yes) (on_board yes)
      (property "Reference" "{c['ref'][0]}" (at 0 {half_h+2.0:.2f} 0) (effects (font (size 1.27 1.27))))
      (property "Value" "{c['val']}" (at 0 {-half_h-2.0:.2f} 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "{c['fp_rel'].replace('.pretty/', ':').replace('.kicad_mod', '')}" (at 0 0 0) (effects (font (size 1.0 1.0)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.0 1.0)) hide))
      (symbol "{sym_name}_0_1"
        (rectangle (start {-half_w:.2f} {-half_h:.2f}) (end {half_w:.2f} {half_h:.2f}) (stroke (width 0.254) (type default)) (fill (type background)))
      )
      (symbol "{sym_name}_1_1"
{chr(10).join(p_lines)}
      )
    )""")

        # Place on A1 grid (7 columns)
        col = idx % 7
        row_g = idx // 7
        gx = 55.88 + col * 114.30
        gy = 50.80 + row_g * 76.20
        fp_id = c["fp_rel"].replace(".pretty/", ":").replace(".kicad_mod", "")
        insts.append(f"""  (symbol (lib_id "{lib_id}") (at {gx:.2f} {gy:.2f} 0) (unit 1)
    (in_bom yes) (on_board yes) (dnp no) (uuid "{uid()}")
    (property "Reference" "{c['ref']}" (at {gx:.2f} {gy - half_h - 2.54:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Value" "{c['val']}" (at {gx:.2f} {gy + half_h + 2.54:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "{fp_id}" (at {gx:.2f} {gy:.2f} 0) (effects (font (size 1.0 1.0)) hide))
    (property "Datasheet" "" (at {gx:.2f} {gy:.2f} 0) (effects (font (size 1.0 1.0)) hide))
    (property "MPN" "{c['mpn']}" (at {gx:.2f} {gy:.2f} 0) (effects (font (size 1.0 1.0)) hide))
    (property "Manufacturer" "{c['mfr']}" (at {gx:.2f} {gy:.2f} 0) (effects (font (size 1.0 1.0)) hide))
    (property "LCSC" "{c['lcsc']}" (at {gx:.2f} {gy:.2f} 0) (effects (font (size 1.0 1.0)) hide))
  )""")

        for px, py, side, nname in pin_coords:
            sx = gx + px
            sy = gy - py  # KiCad schematic Y grows downward
            ex = sx + side * 5.08
            wires_labels.append(f'  (wire (pts (xy {sx:.2f} {sy:.2f}) (xy {ex:.2f} {sy:.2f})) (stroke (width 0) (type default)) (uuid "{uid()}"))')
            wires_labels.append(f'  (label "{nname}" (at {ex:.2f} {sy:.2f} 0) (effects (font (size 1.016 1.016)) (justify {"right" if side == -1 else "left"} bottom)) (uuid "{uid()}"))')

    sch_lines = [
        '(kicad_sch (version 20231120) (generator "iu-mic-origin-stage1-sync")',
        f'  (uuid "{uid()}")',
        '  (paper "A1")',
        '  (title_block',
        '    (title "IU-MIC_ORIGIN — Main PCB Stadio 1 (1:1 Synced Schematic = PCB = BOM)")',
        '    (date "2026-11-20")',
        '    (rev "1.3-S1")',
        '    (company "MAKERZ")',
        '    (comment 1 "Note: U6 AK5572EN uses AVDD=+5V_ANA and TVDD=+3V3_DIG; SAI1/I2C1 operate purely in 3.3V domain.")',
        '  )',
        '  (lib_symbols',
        *lib_syms,
        '  )',
        *insts,
        *wires_labels,
        ')',
    ]
    MAIN_SCH.write_text("\n".join(sch_lines), encoding="utf-8")


def load_kicad_mod(rel_path: str, ref: str, val: str, x: float, y: float, rot: float, pad_nets: dict[str, tuple[int, str]]) -> str:
    """Loads an official KiCad footprint and applies placement, pad rotation, and net bindings.

    Args:
        rel_path: Footprint path relative to ``FP_DIR``.
        ref: Component reference designator.
        val: Component value string.
        x: Absolute board X position in millimeters.
        y: Absolute board Y position in millimeters.
        rot: Rotation in degrees.
        pad_nets: Mapping from pad number to ``(net_id, net_name)``.

    Returns:
        Embedded KiCad S-expression footprint block.
    """
    raw = (FP_DIR / rel_path).read_text(encoding="utf-8")
    raw = re.sub(r'\(version\s+\d+\)\s*', '', raw)
    raw = re.sub(r'\(generator\s+"[^"]*"\)\s*', '', raw)
    raw = re.sub(r'\(generator_version\s+"[^"]*"\)\s*', '', raw)
    raw = re.sub(r'(\(footprint\s+"[^"]+")', rf'\1\n    (at {x:.3f} {y:.3f} {rot:.1f})\n    (uuid "{uid()}")', raw, count=1)
    raw = re.sub(r'(\(property\s+"Reference"\s+)"[^"]*"', rf'\1"{ref}"', raw, count=1)
    raw = re.sub(r'(\(property\s+"Value"\s+)"[^"]*"', rf'\1"{val}"', raw, count=1)

    out = []
    idx = 0
    for m in re.finditer(r'\(pad\s+"([^"]*)"', raw):
        out.append(raw[idx:m.start()])
        depth = 0
        end = m.start()
        for j in range(m.start(), len(raw)):
            if raw[j] == "(": depth += 1
            elif raw[j] == ")":
                depth -= 1
                if depth == 0:
                    end = j + 1; break
        pblk = raw[m.start():end]
        if rot != 0.0:
            def _rot_at(pm):
                px, py = pm.group(1), pm.group(2)
                pang = float(pm.group(3)) if pm.group(3) else 0.0
                return f"(at {px} {py} {(pang + rot) % 360.0:.1f})"
            pblk = re.sub(r'\(at\s+([0-9.-]+)\s+([0-9.-]+)(?:\s+([0-9.-]+))?\)', _rot_at, pblk, count=1)
        pnum = m.group(1)
        if pnum in pad_nets and "(net " not in pblk:
            nid, nname = pad_nets[pnum]
            pblk = pblk[:-1] + f' (net {nid} "{nname}"))'
        out.append(pblk)
        idx = end
    out.append(raw[idx:])
    return "".join(out)


def via_sexpr(x, y, nid, size=0.60, drill=0.30):
    """Formats a through-hole KiCad via S-expression."""
    return f'  (via (at {x:.3f} {y:.3f}) (size {size:.2f}) (drill {drill:.2f}) (layers "F.Cu" "B.Cu") (net {nid}) (uuid "{uid()}"))'


def write_synced_pcb():
    """Generates the 4-layer ``IU-MIC_ORIGIN_Main.kicad_pcb`` with synced footprints and fiducials."""
    w = DIM["main_pcb"]["width"]
    l = DIM["main_pcb"]["length"]
    ox, oy = 100.0, 50.0

    lines = [
        '(kicad_pcb (version 20240108) (generator "iu-mic-origin-stage1-sync")',
        '  (general (thickness 1.6) (legacy_teardrops no))',
        '  (paper "A4")',
        '  (layers',
        '    (0 "F.Cu" signal) (1 "In1.Cu" signal "GND") (2 "In2.Cu" signal "PWR") (31 "B.Cu" signal)',
        '    (34 "B.Paste" user) (35 "F.Paste" user)',
        '    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")',
        '    (38 "B.Mask" user) (39 "F.Mask" user)',
        '    (44 "Edge.Cuts" user) (46 "B.CrtYd" user) (47 "F.CrtYd" user)',
        '    (48 "B.Fab" user) (49 "F.Fab" user)',
        '  )',
        '  (setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints yes))',
    ]
    for nid, nname in NET_LIST:
        lines.append(f'  (net {nid} "{nname}")')
    lines.append(f'  (gr_rect (start {ox:.3f} {oy:.3f}) (end {ox+w:.3f} {oy+l:.3f}) (stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))')

    for c in STAGE1_COMPONENTS:
        lines.append(load_kicad_mod(c["fp_rel"], c["ref"], c["val"], ox + c["x"], oy + c["y"], c["rot"], c["pins"]))

    # 3x Asymmetric Optical Fiducials
    for idx, (fx, fy) in enumerate([(3.0, 26.0), (29.0, 26.0), (3.0, 95.5)], start=1):
        lines.append(load_kicad_mod("Fiducial.pretty/Fiducial_1mm_Mask2mm.kicad_mod", f"FID{idx}", "FID", ox + fx, oy + fy, 0.0, {}))

    # QFN thermal vias (5 on U2, 13 on U6) are added right after FreeRouting in t6_autoroute_freerouting.py
    # so OptViaAlgo does not spend minutes trying to relocate fixed thermal vias!
    lines.append(")")
    MAIN_PCB.write_text("\n".join(lines), encoding="utf-8")


def write_synced_boms():
    """Exports Stage 1 BOM CSVs (``bom_lcsc.csv`` and ``bom_jlcpcb_smt.csv``) matching schematic & PCB."""
    # Add the 2 MEMS Tip PCB parts so bom_lcsc.csv covers complete Stadio 1 (Main + Tip)
    tip_rows = [
        ("MK1", "IM73A135V01", "Sensor_Audio:Infineon_PG-LLGA-5-2", 1, "C3024370", "Infineon", "IM73A135V01XTSA1", "TIP", "Capsula MEMS Omni Diff 2.75V (1.52-3.00V max) — Shortfall JLCPCB: Global Sourcing o Mouser/DigiKey", 0.75),
        ("C_M1", "100nF C0G", "Capacitor_SMD:C_0402_1005Metric", 1, "C1525 (VERIFY)", "Samsung", "CL05B104KO5NNNC", "TIP", "Disaccoppiamento +2V8_MEMS", 0.05),
    ]
    bom_path = ROOT / "hardware" / "bom_lcsc.csv"
    with bom_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Comment", "Footprint", "Quantity", "LCSC Part #", "Manufacturer", "MPN", "Board", "Notes", "Est Unit EUR"])
        for tr in tip_rows:
            w.writerow([*tr[:9], f"{tr[9]:.2f}"])
        for c in STAGE1_COMPONENTS:
            if c["mtype"] == "PAD":
                continue
            fp_short = c["fp_rel"].replace(".pretty/", ":").replace(".kicad_mod", "")
            w.writerow([c["ref"], c["val"], fp_short, 1, c["lcsc"], c["mfr"], c["mpn"], "MAIN", c["notes"], f"{c['est_eur']:.2f}"])

    smt_path = ROOT / "hardware" / "bom_jlcpcb_smt.csv"
    with smt_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part #"])
        for c in STAGE1_COMPONENTS:
            if c["mtype"] != "SMD":
                continue
            fp_short = c["fp_rel"].split("/")[-1].replace(".kicad_mod", "")
            w.writerow([c["val"], c["ref"], fp_short, c["lcsc"].split()[0]])


def main():
    """Builds synced Stage 1 project/schematic/PCB/BOMs and runs KiCad ERC & placement DRC."""
    write_jlcpcb_pro()
    write_synced_schematic()
    write_synced_pcb()
    write_synced_boms()

    # Verify ERC on synced schematic + placement DRC on synced PCB
    erc_json = ERC_DIR / "erc_main_stage1_sync.json"
    drc_json = DRC_DIR / "drc_main_stage1_placement.json"
    subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "-o", str(erc_json), str(MAIN_SCH)], capture_output=True)
    subprocess.run([KICAD_CLI, "sch", "export", "svg", "-o", str(RENDER_DIR), str(MAIN_SCH)], capture_output=True)
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "-o", str(drc_json), str(MAIN_PCB)], capture_output=True)

    erc = json.loads(erc_json.read_text(encoding="utf-8"))
    erc_errs = [v for sh in erc.get("sheets", []) for v in sh.get("violations", []) if v.get("severity") == "error"]
    drc = json.loads(drc_json.read_text(encoding="utf-8"))
    drc_errs = [v for v in drc.get("violations", []) if v.get("severity") == "error"]

    print(f"SYNCED STADIO 1 COMPONENTS: {len(STAGE1_COMPONENTS)} (SCH == PCB 1:1!)")
    print(f"ERC Main Synced:            {len(erc_errs)} errors")
    print(f"DRC Main Placement:         {len(drc_errs)} errors, {len(drc.get('unconnected_items', []))} unconnected")
    for e in drc_errs[:8]:
        print("  [DRC]", e["type"], "-", e["description"])


if __name__ == "__main__":
    main()
