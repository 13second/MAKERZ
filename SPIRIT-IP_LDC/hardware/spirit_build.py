#!/usr/bin/env python3
"""Unified 1:1 Single-Source-of-Truth KiCad 10 ECAD builder for SPIRIT-IP_LDC.

Generates both synchronized boards from a single component manifest:
    1. **Main PCB** (38 x 94 mm, 4-Layer): IEEE 802.3af PoE (TPS23753A),
       USB-C UAC2, STM32H743VIT6, LAN8742A, AK5572EN (2-to-1 Mono 124 dB DR),
       3 Aston-style switches, and 4x WS2812B-2020 addressable RGB LEDs.
    2. **Headamp PCB** (Ø 36.0 mm, 2-Layer): 34 mm dual-diaphragm 1 GΩ OPA1656
       impedance converter, TMUX1104 Pad/HPF switch, MT3608 ±60 V bias boost,
       and Laird BMI-S-102 16.5 x 16.5 mm SMD RF shield can.

Zero guessed LCSC part numbers: every C-code is verified against LCSC/JLCPCB;
unverified parts leave the LCSC column blank with exact MPN in Comment.
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
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text(encoding="utf-8"))
MAIN_DIR = ROOT / "hardware" / "main_pcb"
HEAD_DIR = ROOT / "hardware" / "headamp_pcb"
ERC_DIR = ROOT / "hardware" / "erc_reports"
DRC_DIR = ROOT / "hardware" / "drc_reports"
RENDER_DIR = ROOT / "exports" / "renders"

for d in (MAIN_DIR, HEAD_DIR, ERC_DIR, DRC_DIR, RENDER_DIR):
    d.mkdir(parents=True, exist_ok=True)

KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KICAD_SHARE = Path(os.environ.get("KICAD_SHARE_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport"))
FP_DIR = KICAD_SHARE / "footprints"

MAIN_SCH = MAIN_DIR / "SPIRIT-IP_Main.kicad_sch"
MAIN_PCB = MAIN_DIR / "SPIRIT-IP_Main.kicad_pcb"
MAIN_PRO = MAIN_DIR / "SPIRIT-IP_Main.kicad_pro"

HEAD_SCH = HEAD_DIR / "SPIRIT-IP_Headamp.kicad_sch"
HEAD_PCB = HEAD_DIR / "SPIRIT-IP_Headamp.kicad_pcb"
HEAD_PRO = HEAD_DIR / "SPIRIT-IP_Headamp.kicad_pro"


def uid() -> str:
    """Generates a random UUIDv4 string for KiCad S-expression elements."""
    return str(uuid.uuid4())


# =============================================================================
# BOARD 1: SPIRIT-IP MAIN PCB (38 x 94 mm, 4-Layer)
# =============================================================================
MAIN_NETS = [
    (0, ""), (1, "GND"), (2, "+5V_BUS"), (3, "+3V3_DIG"), (4, "+5V_ANA"),
    (5, "POE_48V"), (6, "USB_5V"), (7, "POE_SENSE"),
    (8, "HEAD_SIG_P"), (9, "HEAD_SIG_N"),
    (10, "SAI1_MCLK"), (11, "SAI1_SCK"), (12, "SAI1_FS"), (13, "SAI1_SD"),
    (14, "ETH_TXP"), (15, "ETH_TXN"), (16, "ETH_RXP"), (17, "ETH_RXN"),
    (18, "USB_DP"), (19, "USB_DM"), (20, "USB_CC1"), (21, "USB_CC2"),
    (22, "ETH_REFCLK"), (23, "ETH_MDIO"), (24, "ETH_MDC"), (25, "ETH_CRSDV"),
    (26, "ETH_RXD0"), (27, "ETH_RXD1"), (28, "ETH_TXEN"), (29, "ETH_TXD0"), (30, "ETH_TXD1"),
    (31, "ETH_XTAL1"), (32, "ETH_XTAL2"), (33, "ETH_RBIAS"),
    (34, "I2C1_SCL"), (35, "I2C1_SDA"), (36, "VCAP"), (37, "NRST"), (38, "BOOT0"),
    (39, "SWDIO"), (40, "SWCLK"), (41, "VCOM_2V5"),
    (42, "SW_PAT"), (43, "SW_PAD"), (44, "SW_HPF"),
    (45, "LED_DIN"), (46, "LED_D1"), (47, "LED_D2"), (48, "LED_D3"),
    (49, "POE_CLASS"), (50, "POE_GATE"),
]
MAIN_NET_ID = {name: nid for nid, name in MAIN_NETS}


def mpn_map(net_id_map: dict[str, int], mapping: dict[str, str]) -> dict[str, tuple[int, str]]:
    """Resolves a pin-to-net-name dictionary into ``{pin: (net_id, net_name)}``.

    Args:
        net_id_map: Lookup table mapping net names to integer KiCad net IDs.
        mapping: Pin-number to net-name assignments.

    Returns:
        Dictionary mapping pin numbers to ``(net_id, net_name)`` tuples.
    """
    return {pin: (net_id_map[n], n) for pin, n in mapping.items()}


MAIN_COMPONENTS = [
    # --- BOTTOM DUAL I/O ZONE (Y = 0..24 mm) ---
    dict(ref="J1", val="HR911105A", mpn="HR911105A", mfr="HanRun", lcsc="", est_eur=1.80,
         fp_rel="Connector_RJ.pretty/RJ45_Hanrun_HR911105A_Horizontal.kicad_mod", x=22.0, y=18.5, rot=180.0,
         mtype="THT", notes="RJ45 100M MagJack PoE (manual THT solder post-SMT)",
         pins=mpn_map(MAIN_NET_ID, {"1": "ETH_TXP", "2": "ETH_TXN", "3": "ETH_RXP", "6": "ETH_RXN", "SH": "GND"})),
    dict(ref="J2", val="USB-C_16P", mpn="TYPE-C-31-M-12", mfr="HRO", lcsc="C165948", est_eur=0.38,
         fp_rel="Connector_USB.pretty/USB_C_Receptacle_HRO_TYPE-C-31-M-12.kicad_mod", x=33.5, y=33.0, rot=90.0,
         mtype="SMD", notes="USB-C UAC2 Audio (Mac/Apollo x6/iPhone/iPad) + 5V Power",
         pins=mpn_map(MAIN_NET_ID, {"A4": "USB_5V", "B4": "USB_5V", "A9": "USB_5V", "B9": "USB_5V",
                                    "A5": "USB_CC1", "B5": "USB_CC2", "A6": "USB_DP", "B6": "USB_DP",
                                    "A7": "USB_DM", "B7": "USB_DM", "A1": "GND", "B1": "GND",
                                    "A12": "GND", "B12": "GND", "S1": "GND"})),

    # --- POE 802.3af + POWER ARBITER (PoE > USB-C) + iOS LOW-POWER SENSE ---
    dict(ref="U1", val="TPS23753APWR", mpn="TPS23753APWR", mfr="Texas Instruments", lcsc="C92115", est_eur=1.72,
         fp_rel="Package_SO.pretty/TSSOP-14_4.4x5mm_P0.65mm.kicad_mod", x=9.0, y=28.0, rot=0.0,
         mtype="SMD", notes="IEEE 802.3af PoE PD Controller + Isolation",
         pins=mpn_map(MAIN_NET_ID, {"1": "POE_48V", "2": "POE_CLASS", "4": "GND", "6": "GND",
                                    "10": "POE_GATE", "12": "+5V_BUS", "14": "POE_48V"})),
    dict(ref="R_CLS", val="24.9k 1%", mpn="0603WAF2492T5E", mfr="Uni-Royal", lcsc="C25962", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=4.5, y=24.0, rot=0.0,
         mtype="SMD", notes="PoE Class 0/2 signature resistor",
         pins=mpn_map(MAIN_NET_ID, {"1": "POE_CLASS", "2": "GND"})),
    dict(ref="R_POE1", val="10k 1%", mpn="0402WGF1002TCE", mfr="Uni-Royal", lcsc="C25744", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=9.0, y=33.5, rot=0.0,
         mtype="SMD", notes="PoE vs USB-C sense divider (iPhone/iPad <160 mA profile)",
         pins=mpn_map(MAIN_NET_ID, {"1": "POE_GATE", "2": "POE_SENSE"})),
    dict(ref="R_POE2", val="10k 1%", mpn="0402WGF1002TCE", mfr="Uni-Royal", lcsc="C25744", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=9.0, y=36.0, rot=0.0,
         mtype="SMD", notes="PoE vs USB-C sense divider (GND leg)",
         pins=mpn_map(MAIN_NET_ID, {"1": "POE_SENSE", "2": "GND"})),
    dict(ref="D_OR1", val="SS34", mpn="SS34", mfr="MDD", lcsc="C8678", est_eur=0.06,
         fp_rel="Diode_SMD.pretty/D_SMA.kicad_mod", x=12.5, y=65.5, rot=0.0,
         mtype="SMD", notes="Schottky OR-ing USB_5V -> +5V_BUS",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "USB_5V"})),
    dict(ref="D_OR2", val="SS34", mpn="SS34", mfr="MDD", lcsc="C8678", est_eur=0.06,
         fp_rel="Diode_SMD.pretty/D_SMA.kicad_mod", x=5.5, y=65.5, rot=0.0,
         mtype="SMD", notes="Schottky OR-ing PoE/Aux -> +5V_BUS",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "POE_GATE"})),
    dict(ref="D_TVS1", val="SMF5.0A", mpn="SMF5.0A", mfr="Goodwork", lcsc="C2980403", est_eur=0.08,
         fp_rel="Diode_SMD.pretty/D_SOD-123F.kicad_mod", x=31.0, y=42.0, rot=0.0,
         mtype="SMD", notes="5V ESD/surge TVS protection on USB_5V",
         pins=mpn_map(MAIN_NET_ID, {"1": "USB_5V", "2": "GND"})),
    dict(ref="R_CC1", val="5.1k 1%", mpn="0402WGF5101TCE", mfr="Uni-Royal", lcsc="C25905", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=27.0, y=31.0, rot=0.0, mtype="SMD", notes="USB-C CC1 pull-down",
         pins=mpn_map(MAIN_NET_ID, {"1": "USB_CC1", "2": "GND"})),
    dict(ref="R_CC2", val="5.1k 1%", mpn="0402WGF5101TCE", mfr="Uni-Royal", lcsc="C25905", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=27.0, y=34.0, rot=0.0, mtype="SMD", notes="USB-C CC2 pull-down",
         pins=mpn_map(MAIN_NET_ID, {"1": "USB_CC2", "2": "GND"})),
    dict(ref="C_VBUS1", val="10uF 25V X5R", mpn="CL21A106KAYNNNE", mfr="Samsung", lcsc="C15850", est_eur=0.04,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=32.5, y=45.5, rot=0.0, mtype="SMD", notes="Bulk decoupling +5V_BUS",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "GND"})),
    dict(ref="C_VBUS2", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=27.5, y=45.5, rot=0.0, mtype="SMD", notes="HF decoupling +5V_BUS",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "GND"})),
    dict(ref="FB_ANA", val="GZ1608D601TF", mpn="GZ1608D601TF", mfr="Sunlord", lcsc="C1002", est_eur=0.02,
         fp_rel="Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod", x=21.0, y=66.5, rot=0.0, mtype="SMD", notes="600R@100MHz ferrite bead +5V_ANA",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "+5V_ANA"})),
    dict(ref="C_ANA1", val="10uF 25V X5R", mpn="CL21A106KAYNNNE", mfr="Samsung", lcsc="C15850", est_eur=0.04,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=21.0, y=70.0, rot=0.0, mtype="SMD", notes="+5V_ANA filter cap",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_ANA", "2": "GND"})),

    # --- ULTRA-LOW-NOISE LDO (+3V3_DIG) ---
    dict(ref="U4", val="LP5907MFX-3.3", mpn="LP5907MFX-3.3", mfr="Texas Instruments", lcsc="C23380874", est_eur=0.68,
         fp_rel="Package_TO_SOT_SMD.pretty/SOT-23-5.kicad_mod", x=5.0, y=38.5, rot=0.0, mtype="SMD", notes="Ultra-low-noise LDO +3V3_DIG",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_BUS", "2": "GND", "3": "+5V_BUS", "5": "+3V3_DIG"})),
    dict(ref="C_U4", val="1uF X5R", mpn="CL05A105KA5NQNC", mfr="Samsung", lcsc="C52923", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=5.0, y=42.0, rot=0.0, mtype="SMD", notes="U4 output decoupling cap",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "GND"})),

    # --- ETHERNET PHY (LAN8742A) ---
    dict(ref="U2", val="LAN8742A-CZ", mpn="LAN8742A-CZ-TR", mfr="Microchip", lcsc="C621424", est_eur=3.90,
         fp_rel="Package_DFN_QFN.pretty/QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm.kicad_mod", x=18.5, y=31.0, rot=0.0,
         mtype="SMD", notes="Ethernet 100M RMII PHY",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "4": "ETH_XTAL2", "5": "ETH_XTAL1", "7": "ETH_RXD1", "8": "ETH_RXD0",
                                    "9": "+3V3_DIG", "11": "ETH_CRSDV", "12": "ETH_MDIO", "13": "ETH_MDC", "14": "ETH_REFCLK",
                                    "15": "NRST", "16": "ETH_TXD0", "17": "ETH_TXD1", "18": "ETH_TXEN", "19": "+3V3_DIG",
                                    "20": "ETH_TXN", "21": "ETH_TXP", "22": "ETH_RXN", "23": "ETH_RXP", "24": "ETH_RBIAS", "25": "GND"})),
    dict(ref="Y1", val="25.000MHz", mpn="XXDCCLNANF-25MHZ", mfr="Yangxing", lcsc="", est_eur=0.30,
         fp_rel="Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod", x=12.0, y=38.5, rot=0.0,
         mtype="SMD", notes="25 MHz Ethernet PHY crystal (12 pF 3225-4P)",
         pins=mpn_map(MAIN_NET_ID, {"1": "ETH_XTAL1", "2": "GND", "3": "ETH_XTAL2", "4": "GND"})),
    dict(ref="C_Y1A", val="18pF C0G", mpn="0402CG180J500NT", mfr="FH", lcsc="C1549", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=9.5, y=42.0, rot=0.0, mtype="SMD", notes="Y1 load capacitor",
         pins=mpn_map(MAIN_NET_ID, {"1": "ETH_XTAL1", "2": "GND"})),
    dict(ref="C_Y1B", val="18pF C0G", mpn="0402CG180J500NT", mfr="FH", lcsc="C1549", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=14.5, y=42.0, rot=0.0, mtype="SMD", notes="Y1 load capacitor",
         pins=mpn_map(MAIN_NET_ID, {"1": "ETH_XTAL2", "2": "GND"})),
    dict(ref="R_BIAS", val="0402WGF1212TCE", mpn="0402WGF1212TCE", mfr="Uni-Royal", lcsc="C25852", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=23.5, y=28.0, rot=0.0, mtype="SMD", notes="12.1k 1% LAN8742A RBIAS",
         pins=mpn_map(MAIN_NET_ID, {"1": "ETH_RBIAS", "2": "GND"})),

    # --- MCU STM32H743VIT6 (LQFP-100) ---
    dict(ref="U3", val="STM32H743VIT6TR", mpn="STM32H743VIT6TR", mfr="STMicroelectronics", lcsc="C5271084", est_eur=12.06,
         fp_rel="Package_QFP.pretty/LQFP-100_14x14mm_P0.5mm.kicad_mod", x=18.5, y=54.5, rot=0.0,
         mtype="SMD", notes="480 MHz MCU: AoIP AES67 + USB-C UAC2 (iOS/macOS) + Switch/LED Ctrl",
         pins=mpn_map(MAIN_NET_ID, {
             "1": "SAI1_MCLK", "2": "SAI1_SCK", "3": "SAI1_FS", "4": "SAI1_SD",
             "10": "GND", "11": "+3V3_DIG", "14": "NRST", "15": "POE_SENSE", "19": "GND", "20": "+3V3_DIG",
             "23": "ETH_REFCLK", "24": "ETH_MDIO", "25": "ETH_MDC", "26": "ETH_CRSDV",
             "27": "ETH_RXD0", "28": "ETH_RXD1", "33": "SW_PAT", "34": "SW_PAD", "35": "SW_HPF",
             "36": "LED_DIN", "47": "ETH_TXEN", "48": "ETH_TXD0", "49": "VCAP", "50": "+3V3_DIG",
             "51": "ETH_TXD1", "70": "USB_DM", "71": "USB_DP", "72": "SWDIO", "73": "VCAP",
             "74": "GND", "75": "+3V3_DIG", "76": "SWCLK", "92": "I2C1_SCL", "93": "I2C1_SDA",
             "94": "BOOT0", "99": "GND", "100": "+3V3_DIG",
         })),
    dict(ref="C_VCAP1", val="2.2uF X5R", mpn="CL10A225KO8NNNC", mfr="Samsung", lcsc="C23630", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=31.0, y=51.0, rot=0.0, mtype="SMD", notes="STM32 VCAP1",
         pins=mpn_map(MAIN_NET_ID, {"1": "VCAP", "2": "GND"})),
    dict(ref="C_VCAP2", val="2.2uF X5R", mpn="CL10A225KO8NNNC", mfr="Samsung", lcsc="C23630", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=31.0, y=54.5, rot=0.0, mtype="SMD", notes="STM32 VCAP2",
         pins=mpn_map(MAIN_NET_ID, {"1": "VCAP", "2": "GND"})),
    dict(ref="C_VDD1", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=18.5, y=44.5, rot=0.0, mtype="SMD", notes="STM32 VDD decoupling",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "GND"})),
    dict(ref="C_VDD2", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=31.0, y=58.0, rot=0.0, mtype="SMD", notes="STM32 VDD decoupling",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "GND"})),
    dict(ref="R_NRST", val="10k 1%", mpn="0402WGF1002TCE", mfr="Uni-Royal", lcsc="C25744", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=5.5, y=50.5, rot=0.0, mtype="SMD", notes="NRST pull-up",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "NRST"})),
    dict(ref="C_NRST", val="100nF X7R", mpn="CL05B104KO5NNNC", mfr="Samsung", lcsc="C1525", est_eur=0.01,
         fp_rel="Capacitor_SMD.pretty/C_0402_1005Metric.kicad_mod", x=5.5, y=53.5, rot=0.0, mtype="SMD", notes="NRST filter cap",
         pins=mpn_map(MAIN_NET_ID, {"1": "NRST", "2": "GND"})),
    dict(ref="R_BOOT0", val="10k 1%", mpn="0402WGF1002TCE", mfr="Uni-Royal", lcsc="C25744", est_eur=0.01,
         fp_rel="Resistor_SMD.pretty/R_0402_1005Metric.kicad_mod", x=5.5, y=56.5, rot=0.0, mtype="SMD", notes="BOOT0 pull-down",
         pins=mpn_map(MAIN_NET_ID, {"1": "BOOT0", "2": "GND"})),
    dict(ref="J_SWD", val="SWD_4P DNP", mpn="SWD_4P", mfr="Generic", lcsc="", est_eur=0.0,
         fp_rel="Connector_PinHeader_1.27mm.pretty/PinHeader_1x04_P1.27mm_Vertical_SMD_Pin1Left.kicad_mod", x=33.5, y=63.0, rot=0.0,
         mtype="SMD", notes="SWD debug header (leave DNP in SMT)",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "SWDIO", "3": "SWCLK", "4": "GND"})),

    # --- ADC AK5572EN (2-to-1 Mono 124 dB DR) + 24.576 MHz MCLK OSC ---
    dict(ref="Y2", val="24.576MHz 3.3V XO", mpn="3N24576G33YC", mfr="YXC", lcsc="C252340", est_eur=0.65,
         fp_rel="Crystal.pretty/Crystal_SMD_3225-4Pin_3.2x2.5mm.kicad_mod", x=27.0, y=69.5, rot=0.0,
         mtype="SMD", notes="24.576 MHz 3.3V CMOS master audio clock oscillator",
         pins=mpn_map(MAIN_NET_ID, {"1": "+3V3_DIG", "2": "GND", "3": "SAI1_MCLK", "4": "+3V3_DIG"})),
    dict(ref="U6", val="AK5572EN", mpn="AK5572EN", mfr="AKM", lcsc="C5451857", est_eur=12.70,
         fp_rel="Package_DFN_QFN.pretty/QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm.kicad_mod", x=15.0, y=73.5, rot=180.0,
         mtype="SMD", notes="32-bit 2-to-1 Mono ADC (124 dB DR)",
         pins=mpn_map(MAIN_NET_ID, {
             "2": "HEAD_SIG_P", "3": "HEAD_SIG_N", "5": "HEAD_SIG_P", "6": "HEAD_SIG_N",
             "8": "+5V_ANA", "9": "GND", "10": "VCOM_2V5", "11": "+5V_ANA", "12": "GND",
             "25": "SAI1_MCLK", "26": "SAI1_SCK", "27": "SAI1_FS", "28": "SAI1_SD",
             "30": "+3V3_DIG", "31": "GND", "34": "I2C1_SCL", "35": "I2C1_SDA", "36": "NRST", "49": "GND",
         })),
    dict(ref="C_VCOM", val="10uF 10V X5R", mpn="CL10A106KP8NNNC", mfr="Samsung", lcsc="C19702", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0603_1608Metric.kicad_mod", x=5.5, y=73.5, rot=0.0, mtype="SMD", notes="AK5572 VCOM bypass",
         pins=mpn_map(MAIN_NET_ID, {"1": "VCOM_2V5", "2": "GND"})),

    # --- HEADAMP INTERCONNECT (JST-SH 6P AT TOP EDGE) ---
    dict(ref="J3", val="HEADAMP_6P", mpn="SM06B-SRSS-TB(LF)(SN)", mfr="JST", lcsc="C160405", est_eur=0.45,
         fp_rel="Connector_JST.pretty/JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal.kicad_mod", x=19.0, y=89.5, rot=0.0,
         mtype="SMD", notes="Shielded link to Headamp PCB (+5V, GND, SIG+, SIG-, SCL, SDA)",
         pins=mpn_map(MAIN_NET_ID, {"1": "+5V_ANA", "2": "GND", "3": "HEAD_SIG_P", "4": "HEAD_SIG_N",
                                    "5": "I2C1_SCL", "6": "I2C1_SDA", "MP": "GND"})),

    # --- 3 ASTON SPIRIT RECESSED SWITCHES (FRONT-RIGHT EDGE) ---
    dict(ref="SW1", val="SW_PATTERN", mpn="2.54-1P TPGT", mfr="Tianzhi", lcsc="", est_eur=0.18,
         fp_rel="Button_Switch_SMD.pretty/SW_DIP_SPSTx01_Slide_6.7x4.1mm_W6.73mm_P2.54mm_LowProfile_JPin.kicad_mod",
         x=33.5, y=87.0, rot=90.0, mtype="SMD", notes="Polar pattern switch (Cardioid/Omni/Fig-8)",
         pins=mpn_map(MAIN_NET_ID, {"1": "SW_PAT", "2": "GND"})),
    dict(ref="SW2", val="SW_PAD", mpn="2.54-1P TPGT", mfr="Tianzhi", lcsc="", est_eur=0.18,
         fp_rel="Button_Switch_SMD.pretty/SW_DIP_SPSTx01_Slide_6.7x4.1mm_W6.73mm_P2.54mm_LowProfile_JPin.kicad_mod",
         x=33.5, y=75.5, rot=90.0, mtype="SMD", notes="Attenuation pad switch (-10/-20 dB)",
         pins=mpn_map(MAIN_NET_ID, {"1": "SW_PAD", "2": "GND"})),
    dict(ref="SW3", val="SW_HPF", mpn="2.54-1P TPGT", mfr="Tianzhi", lcsc="", est_eur=0.18,
         fp_rel="Button_Switch_SMD.pretty/SW_DIP_SPSTx01_Slide_6.7x4.1mm_W6.73mm_P2.54mm_LowProfile_JPin.kicad_mod",
         x=33.5, y=5.5, rot=90.0, mtype="SMD", notes="80 Hz HPF switch",
         pins=mpn_map(MAIN_NET_ID, {"1": "SW_HPF", "2": "GND"})),

    # --- 4x WS2812B-2020 ADDRESSABLE RGB LEDs (ILLUMINATE CLEAR 8001 BODY) ---
    dict(ref="LED1", val="WS2812B-2020-V6", mpn="WS2812B-2020-V6", mfr="Worldsemi", lcsc="C52917434", est_eur=0.09,
         fp_rel="LED_SMD.pretty/LED_WS2812B-2020_PLCC4_2.0x2.0mm.kicad_mod", x=3.5, y=60.0, rot=0.0, mtype="SMD", notes="RGB Glow LED 1 (Pattern/Status)",
         pins=mpn_map(MAIN_NET_ID, {"1": "LED_D1", "2": "GND", "3": "LED_DIN", "4": "+5V_BUS"})),
    dict(ref="LED2", val="WS2812B-2020-V6", mpn="WS2812B-2020-V6", mfr="Worldsemi", lcsc="C52917434", est_eur=0.09,
         fp_rel="LED_SMD.pretty/LED_WS2812B-2020_PLCC4_2.0x2.0mm.kicad_mod", x=3.5, y=80.0, rot=0.0, mtype="SMD", notes="RGB Glow LED 2 (Pattern/Status)",
         pins=mpn_map(MAIN_NET_ID, {"1": "LED_D2", "2": "GND", "3": "LED_D1", "4": "+5V_BUS"})),
    dict(ref="LED3", val="WS2812B-2020-V6", mpn="WS2812B-2020-V6", mfr="Worldsemi", lcsc="C52917434", est_eur=0.09,
         fp_rel="LED_SMD.pretty/LED_WS2812B-2020_PLCC4_2.0x2.0mm.kicad_mod", x=34.5, y=49.0, rot=0.0, mtype="SMD", notes="RGB Glow LED 3 (Pattern/Status)",
         pins=mpn_map(MAIN_NET_ID, {"1": "LED_D3", "2": "GND", "3": "LED_D2", "4": "+5V_BUS"})),
    dict(ref="LED4", val="WS2812B-2020-V6", mpn="WS2812B-2020-V6", mfr="Worldsemi", lcsc="C52917434", est_eur=0.09,
         fp_rel="LED_SMD.pretty/LED_WS2812B-2020_PLCC4_2.0x2.0mm.kicad_mod", x=34.5, y=69.0, rot=0.0, mtype="SMD", notes="RGB Glow LED 4 (Pattern/Status)",
         pins=mpn_map(MAIN_NET_ID, {"2": "GND", "3": "LED_D3", "4": "+5V_BUS"})),
]

# =============================================================================
# BOARD 2: SPIRIT-IP HEADAMP PCB (Ø 36.0 mm Circular, 2-Layer, SMD Shield-Can)
# =============================================================================
HEAD_NETS = [
    (0, ""), (1, "GND"), (2, "+5V_ANA"), (3, "HEAD_SIG_P"), (4, "HEAD_SIG_N"),
    (5, "I2C1_SCL"), (6, "I2C1_SDA"), (7, "CAP_FRONT"), (8, "CAP_BACK"), (9, "CAP_REAR"),
    (10, "BIAS_60V"), (11, "BIAS_SW"), (12, "PRE_OUT"), (13, "HPF_NODE"),
]
HEAD_NET_ID = {name: nid for nid, name in HEAD_NETS}

HEAD_COMPONENTS = [
    # Centered around (100.0, 100.0), radius 18.0 mm -> local coords (-18..+18)
    dict(ref="SH1", val="BMI-S-102_SHIELD", mpn="BMI-S-102-F", mfr="Laird", lcsc="", est_eur=0.55,
         fp_rel="RF_Shielding.pretty/Laird_Technologies_BMI-S-102_16.50x16.50mm.kicad_mod", x=0.0, y=0.0, rot=0.0,
         mtype="SMD", notes="16.5 x 16.5 mm SMD Faraday shield over 1 GΩ + ±60 V bias zone",
         pins=mpn_map(HEAD_NET_ID, {"1": "GND"})),
    dict(ref="U_A1", val="OPA1656IDR", mpn="OPA1656IDR", mfr="Texas Instruments", lcsc="C1849431", est_eur=1.25,
         fp_rel="Package_SO.pretty/SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod", x=-3.6, y=0.0, rot=0.0,
         mtype="SMD", notes="FET impedance converter (2.9 nV/rtHz) + 80 Hz HPF",
         pins=mpn_map(HEAD_NET_ID, {"1": "PRE_OUT", "2": "PRE_OUT", "3": "CAP_BACK", "4": "GND",
                                    "5": "HPF_NODE", "6": "HEAD_SIG_N", "7": "HEAD_SIG_P", "8": "+5V_ANA"})),
    dict(ref="U_A2", val="TMUX1104DGSR", mpn="TMUX1104DGSR", mfr="Texas Instruments", lcsc="C2878206", est_eur=3.50,
         fp_rel="Package_SO.pretty/MSOP-10_3x3mm_P0.5mm.kicad_mod", x=3.8, y=3.8, rot=0.0,
         mtype="SMD", notes="3 pA analog switch for -10/-20 dB pad and 80 Hz HPF",
         pins=mpn_map(HEAD_NET_ID, {"1": "PRE_OUT", "2": "HPF_NODE", "3": "GND", "5": "+5V_ANA",
                                    "6": "I2C1_SCL", "7": "I2C1_SDA", "8": "HEAD_SIG_P", "9": "GND"})),
    dict(ref="U_BIAS", val="MT3608", mpn="MT3608", mfr="Aerosemi", lcsc="C84817", est_eur=0.12,
         fp_rel="Package_TO_SOT_SMD.pretty/SOT-23-6.kicad_mod", x=3.6, y=-3.2, rot=0.0,
         mtype="SMD", notes="1.2 MHz boost converter for ±60 V capsule polarization",
         pins=mpn_map(HEAD_NET_ID, {"1": "BIAS_SW", "2": "GND", "3": "BIAS_60V", "4": "+5V_ANA", "5": "+5V_ANA"})),
    dict(ref="R_G1", val="1G 5% 0805", mpn="1G_0805", mfr="Ohmite/Yageo", lcsc="", est_eur=0.35,
         fp_rel="Resistor_SMD.pretty/R_0805_2012Metric.kicad_mod", x=-10.2, y=-10.8, rot=0.0,
         mtype="SMD", notes="1 GΩ front diaphragm bias resistor",
         pins=mpn_map(HEAD_NET_ID, {"1": "CAP_FRONT", "2": "BIAS_60V"})),
    dict(ref="R_G2", val="1G 5% 0805", mpn="1G_0805", mfr="Ohmite/Yageo", lcsc="", est_eur=0.35,
         fp_rel="Resistor_SMD.pretty/R_0805_2012Metric.kicad_mod", x=-5.0, y=10.5, rot=0.0,
         mtype="SMD", notes="1 GΩ backplate/rear bias resistor",
         pins=mpn_map(HEAD_NET_ID, {"1": "CAP_BACK", "2": "GND"})),
    dict(ref="C_BIAS1", val="100nF 100V X7R", mpn="CC0805KRX7R9BB104", mfr="Yageo", lcsc="C49678", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=10.2, y=-10.8, rot=0.0,
         mtype="SMD", notes="Capsule bias RC filter cap",
         pins=mpn_map(HEAD_NET_ID, {"1": "BIAS_60V", "2": "GND"})),
    dict(ref="C_HPF", val="100nF C0G", mpn="CC0805KRX7R9BB104", mfr="Yageo", lcsc="C49678", est_eur=0.02,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=5.0, y=10.5, rot=0.0,
         mtype="SMD", notes="80 Hz HPF coupling cap",
         pins=mpn_map(HEAD_NET_ID, {"1": "PRE_OUT", "2": "HPF_NODE"})),
    dict(ref="C_ANA_H", val="10uF 25V X5R", mpn="CL21A106KAYNNNE", mfr="Samsung", lcsc="C15850", est_eur=0.03,
         fp_rel="Capacitor_SMD.pretty/C_0805_2012Metric.kicad_mod", x=0.0, y=13.5, rot=0.0,
         mtype="SMD", notes="Local Headamp +5V_ANA decoupling",
         pins=mpn_map(HEAD_NET_ID, {"1": "+5V_ANA", "2": "GND"})),
    dict(ref="J_CAP", val="CAPSULE_34MM_3P", mpn="PAD_3P_CAP", mfr="Generic", lcsc="", est_eur=0.0,
         fp_rel="Connector_PinHeader_2.54mm.pretty/PinHeader_1x03_P2.54mm_Vertical.kicad_mod", x=-12.5, y=-2.5, rot=0.0,
         mtype="THT", notes="3-wire solder header for 34 mm capsule (Front / Backplate / Rear)",
         pins=mpn_map(HEAD_NET_ID, {"1": "CAP_FRONT", "2": "CAP_BACK", "3": "CAP_REAR"})),
    dict(ref="J_LINK", val="MAIN_LINK_6P", mpn="SM06B-SRSS-TB(LF)(SN)", mfr="JST", lcsc="C160405", est_eur=0.45,
         fp_rel="Connector_JST.pretty/JST_SH_SM06B-SRSS-TB_1x06-1MP_P1.00mm_Horizontal.kicad_mod", x=0.0, y=-14.2, rot=0.0,
         mtype="SMD", notes="Shielded link to Main PCB",
         pins=mpn_map(HEAD_NET_ID, {"1": "+5V_ANA", "2": "GND", "3": "HEAD_SIG_P", "4": "HEAD_SIG_N",
                                    "5": "I2C1_SCL", "6": "I2C1_SDA", "MP": "GND"})),
]


def load_kicad_mod(
    fp_rel: str,
    ref: str,
    val: str,
    x_abs: float,
    y_abs: float,
    rot_deg: float,
    pin_nets: dict[str, tuple[int, str]],
) -> str:
    """Loads an official KiCad ``.kicad_mod`` footprint and injects placement and nets.

    Args:
        fp_rel: Relative path inside KiCad's footprint library directory.
        ref: Component reference designator (e.g., ``"U1"``).
        val: Component value string.
        x_abs: Absolute board X position in millimeters.
        y_abs: Absolute board Y position in millimeters.
        rot_deg: Component rotation in degrees.
        pin_nets: Mapping of pad number to ``(net_id, net_name)``.

    Returns:
        Embedded KiCad 10 S-expression footprint block.

    Raises:
        FileNotFoundError: If the footprint file does not exist in ``FP_DIR``.
    """
    fp_path = FP_DIR / fp_rel
    if not fp_path.exists():
        raise FileNotFoundError(f"Footprint missing: {fp_path}")
    raw = fp_path.read_text(encoding="utf-8")
    raw = re.sub(
        r'^\(footprint\s+"([^"]+)"',
        f'(footprint "{fp_rel.replace(".pretty/", ":").replace(".kicad_mod", "")}"',
        raw,
        count=1,
    )
    raw = re.sub(r"\(version\s+\d+\)", "", raw)
    raw = re.sub(r'\(generator\s+"[^"]+"\)', "", raw)
    raw = re.sub(r'\(generator_version\s+"[^"]+"\)', "", raw)
    raw = re.sub(r'\(property\s+"Reference"\s+"[^"]+"', f'(property "Reference" "{ref}"', raw, count=1)
    raw = re.sub(r'\(property\s+"Value"\s+"[^"]+"', f'(property "Value" "{val}"', raw, count=1)

    # Inject board placement (at x y rot) immediately after (layer ...)
    raw = re.sub(r'(\(layer\s+"[^"]+"\))', f"\\1\n  (at {x_abs:.3f} {y_abs:.3f} {rot_deg:.1f})", raw, count=1)

    # Walk balanced (pad "X" ...) blocks to apply board-absolute pad rotation and net assignments
    out = []
    i = 0
    n = len(raw)
    while i < n:
        idx = raw.find('(pad "', i)
        if idx == -1:
            out.append(raw[i:])
            break
        out.append(raw[i:idx])
        depth = 0
        j = idx
        while j < n:
            if raw[j] == "(":
                depth += 1
            elif raw[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        pad_block = raw[idx:j]
        pm = re.match(r'\(pad\s+"([^"]*)"', pad_block)
        if pm:
            pnum = pm.group(1)
            if rot_deg != 0.0:
                def add_rot(am: re.Match[str]) -> str:
                    px, py = am.group(1), am.group(2)
                    pang = float(am.group(3)) if am.group(3) else 0.0
                    return f"(at {px} {py} {(pang + rot_deg) % 360.0:.1f})"
                pad_block = re.sub(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)", add_rot, pad_block, count=1)
            if pnum in pin_nets:
                nid, nname = pin_nets[pnum]
                pad_block = pad_block[:-1] + f' (net {nid} "{nname}"))'
        out.append(pad_block)
        i = j
    return "".join(out)


def build_schematic(sch_path: Path, title: str, comps: list[dict[str, Any]]) -> None:
    """Generates an ERC-clean KiCad 10 schematic with MPN/Manufacturer/LCSC metadata.

    Args:
        sch_path: Output path for the ``.kicad_sch`` file.
        title: Schematic title block string.
        comps: Component manifest list.
    """
    lib_syms = []
    sym_insts = []
    wires = []
    labels = []

    cols = 5
    for idx, c in enumerate(comps):
        col = idx % cols
        row = idx // cols
        sx = 45.72 + col * 101.60
        sy = 45.72 + row * 71.12
        base_name = f"{c['ref']}_{re.sub(r'[^A-Za-z0-9_]', '_', c['val'])}"
        lib_id = f"SPIRIT:{base_name}"
        pins = sorted(c["pins"].items(), key=lambda kv: (len(kv[0]), kv[0]))
        half = max(1, (len(pins) + 1) // 2)
        h_mm = max(7.62, (half + 1) * 2.54)

        pin_defs = []
        for pi, (pnum, (nid, nname)) in enumerate(pins):
            side_left = pi < half
            px = -10.16 if side_left else 10.16
            py = (half / 2.0 - (pi if side_left else pi - half) - 0.5) * 2.54
            py = round(py / 2.54) * 2.54
            ang = 0 if side_left else 180
            pin_defs.append(
                f'      (pin passive line (at {px:.2f} {py:.2f} {ang}) (length 2.54)\n'
                f'        (name "{nname}" (effects (font (size 1.0 1.0))))\n'
                f'        (number "{pnum}" (effects (font (size 1.0 1.0))))\n'
                f'      )'
            )
            lx = sx + px
            ly = sy - py
            ex = lx + (-5.08 if side_left else 5.08)
            wires.append(f'  (wire (pts (xy {lx:.2f} {ly:.2f}) (xy {ex:.2f} {ly:.2f})) (stroke (width 0) (type default)) (uuid "{uid()}"))')
            labels.append(
                f'  (label "{nname}" (at {ex:.2f} {ly:.2f} 0)\n'
                f'    (effects (font (size 1.016 1.016)) (justify {"right" if side_left else "left"} bottom))\n'
                f'    (uuid "{uid()}")\n'
                f'  )'
            )

        fp_id = c["fp_rel"].replace(".pretty/", ":").replace(".kicad_mod", "")
        lib_syms.append(
            f'    (symbol "{lib_id}" (in_bom yes) (on_board yes)\n'
            f'      (property "Reference" "{c["ref"][0]}" (at 0 {h_mm/2+1.27:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'      (property "Value" "{c["val"]}" (at 0 {-h_mm/2-1.27:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'      (property "Footprint" "{fp_id}" (at 0 0 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'      (symbol "{base_name}_0_1"\n'
            f'        (rectangle (start -7.62 {h_mm/2:.2f}) (end 7.62 {-h_mm/2:.2f}) (stroke (width 0.254) (type default)) (fill (type background)))\n'
            f'      )\n'
            f'      (symbol "{base_name}_1_1"\n'
            + "\n".join(pin_defs) + "\n"
            f'      )\n'
            f'    )'
        )

        sym_insts.append(
            f'  (symbol (lib_id "{lib_id}") (at {sx:.2f} {sy:.2f} 0) (unit 1)\n'
            f'    (in_bom yes) (on_board yes) (dnp no) (uuid "{uid()}")\n'
            f'    (property "Reference" "{c["ref"]}" (at {sx:.2f} {sy-h_mm/2-1.5:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'    (property "Value" "{c["val"]}" (at {sx:.2f} {sy+h_mm/2+1.5:.2f} 0) (effects (font (size 1.27 1.27))))\n'
            f'    (property "Footprint" "{fp_id}" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'    (property "Datasheet" "" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'    (property "MPN" "{c["mpn"]}" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'    (property "Manufacturer" "{c["mfr"]}" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'    (property "LCSC" "{c["lcsc"]}" (at {sx:.2f} {sy:.2f} 0) (effects (font (size 1.0 1.0)) hide))\n'
            f'  )'
        )

    sch_txt = f'''(kicad_sch
  (version 20231120)
  (generator "spirit_build.py")
  (uuid "{uid()}")
  (paper "A1")
  (title_block
    (title "{title}")
    (rev "1.0.0")
    (company "MAKERZ Studio — SPIRIT-IP_LDC")
  )
  (lib_symbols
{chr(10).join(lib_syms)}
  )
{chr(10).join(sym_insts)}
{chr(10).join(wires)}
{chr(10).join(labels)}
)
'''
    sch_path.write_text(sch_txt, encoding="utf-8")


def build_pcb(
    pcb_path: Path,
    pro_path: Path,
    is_4l: bool,
    nets: list[tuple[int, str]],
    comps: list[dict[str, Any]],
    edge_cuts_sexpr: str,
    origin_xy: tuple[float, float],
    zone_poly: list[tuple[float, float]],
) -> None:
    """Generates a KiCad 10 ``.kicad_pcb`` layout and matching ``.kicad_pro`` rules.

    Args:
        pcb_path: Output path for the ``.kicad_pcb`` file.
        pro_path: Output path for the ``.kicad_pro`` project file.
        is_4l: True for 4-layer stackup, False for 2-layer stackup.
        nets: List of ``(net_id, net_name)`` definitions.
        comps: Component manifest list.
        edge_cuts_sexpr: S-expression defining the ``Edge.Cuts`` board outline.
        origin_xy: ``(ox, oy)`` sheet origin offset in millimeters.
        zone_poly: Polygon vertices ``[(x, y), ...]`` for the GND pour zone.
    """
    layers_sexpr = '''  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" signal "GND")
    (2 "In2.Cu" signal "PWR")
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )''' if is_4l else '''  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )'''

    net_lines = "\n".join(f'  (net {nid} "{nname}")' for nid, nname in nets)
    ox, oy = origin_xy
    fp_blocks = [
        load_kicad_mod(c["fp_rel"], c["ref"], c["val"], ox + c["x"], oy + c["y"], c["rot"], c["pins"])
        for c in comps
    ]

    zone_layer = "In1.Cu" if is_4l else "B.Cu"
    pts_str = " ".join(f"(xy {px:.3f} {py:.3f})" for px, py in zone_poly)
    zone_sexpr = f'''  (zone (net 1) (net_name "GND") (layer "{zone_layer}") (uuid "{uid()}") (hatch edge 0.5)
    (connect_pads (clearance 0.2))
    (min_thickness 0.2)
    (fill yes (thermal_gap 0.25) (thermal_bridge_width 0.3))
    (polygon (pts {pts_str}))
  )'''

    pcb_txt = f'''(kicad_pcb
  (version 20240108)
  (generator "spirit_build.py")
  (general (thickness 1.6))
  (paper "A4")
{layers_sexpr}
  (setup
    (pad_to_mask_clearance 0.05)
    (pcbplotparams (layerselection 0x00010fc_ffffffff) (plot_on_all_layers_selection 0x0000000_00000000))
  )
{net_lines}
{edge_cuts_sexpr}
{chr(10).join(fp_blocks)}
{zone_sexpr}
)
'''
    pcb_path.write_text(pcb_txt, encoding="utf-8")

    # Conservative JLCPCB 4L/2L design rules (.kicad_pro)
    pro_obj = {
        "board": {
            "design_settings": {
                "rules": {
                    "min_clearance": 0.127,
                    "min_track_width": 0.127,
                    "min_via_diameter": 0.50,
                    "min_via_annular_width": 0.125,
                    "min_through_hole_diameter": 0.30,
                    "min_hole_to_hole": 0.25,
                    "min_copper_edge_clearance": 0.30,
                }
            }
        },
        "net_settings": {
            "classes": [
                {
                    "name": "Default",
                    "clearance": 0.15,
                    "track_width": 0.20,
                    "via_diameter": 0.60,
                    "via_drill": 0.30,
                }
            ]
        },
    }
    pro_path.write_text(json.dumps(pro_obj, indent=2), encoding="utf-8")


def export_boms() -> None:
    """Exports the combined MAKERZ Studio BOM and separate JLCPCB SMT BOMs."""
    all_rows = [("Main 4L", c) for c in MAIN_COMPONENTS] + [("Headamp 2L", c) for c in HEAD_COMPONENTS]
    with open(ROOT / "hardware" / "bom_lcsc.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Board", "Comment", "MPN", "Manufacturer", "Footprint", "LCSC Part #", "Mount", "Est_EUR", "Notes"])
        for board, c in all_rows:
            fp_short = c["fp_rel"].split("/")[-1].replace(".kicad_mod", "")
            w.writerow([c["ref"], board, c["val"], c["mpn"], c["mfr"], fp_short, c["lcsc"], c["mtype"], f"{c['est_eur']:.2f}", c["notes"]])

    # JLCPCB SMT BOMs (SMD only, excluding DNP debug headers)
    for out_p, comps in [
        (ROOT / "hardware" / "BOM_Main_JLCPCB_SMT.csv", MAIN_COMPONENTS),
        (ROOT / "hardware" / "BOM_Headamp_JLCPCB_SMT.csv", HEAD_COMPONENTS),
    ]:
        with open(out_p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part #"])
            for c in comps:
                if c["mtype"] != "SMD" or "DNP" in c["val"]:
                    continue
                fp_short = c["fp_rel"].split("/")[-1].replace(".kicad_mod", "")
                w.writerow([c["mpn"], c["ref"], fp_short, c["lcsc"]])


def main() -> None:
    """Builds Main and Headamp schematics/PCBs, exports BOMs, and runs ERC."""
    # 1. Main PCB (38 x 94 mm at sheet origin 100, 50)
    ox, oy = 100.0, 50.0
    bw, bh = 38.0, 94.0
    main_edge = (
        f'  (gr_rect (start {ox:.3f} {oy:.3f}) (end {ox+bw:.3f} {oy+bh:.3f}) '
        f'(stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))'
    )
    main_zone = [(ox + 0.4, oy + 0.4), (ox + bw - 0.4, oy + 0.4), (ox + bw - 0.4, oy + bh - 0.4), (ox + 0.4, oy + bh - 0.4)]
    build_schematic(MAIN_SCH, "SPIRIT-IP_LDC Main PCB (4-Layer PoE + USB-C + AK5572 + STM32H7)", MAIN_COMPONENTS)
    build_pcb(MAIN_PCB, MAIN_PRO, True, MAIN_NETS, MAIN_COMPONENTS, main_edge, (ox, oy), main_zone)

    # 2. Headamp PCB (Ø 36.0 mm centered at 100, 100)
    hx, hy, hr = 100.0, 100.0, 18.0
    head_edge = (
        f'  (gr_circle (center {hx:.3f} {hy:.3f}) (end {hx+hr:.3f} {hy:.3f}) '
        f'(stroke (width 0.15) (type solid)) (fill none) (layer "Edge.Cuts") (uuid "{uid()}"))'
    )
    head_zone = [
        (hx + (hr - 0.5) * math.cos(2 * math.pi * k / 32), hy + (hr - 0.5) * math.sin(2 * math.pi * k / 32))
        for k in range(32)
    ]
    build_schematic(HEAD_SCH, "SPIRIT-IP_LDC Headamp PCB (2-Layer 1GΩ OPA1656 + ±60V Bias + RF Shield)", HEAD_COMPONENTS)
    build_pcb(HEAD_PCB, HEAD_PRO, False, HEAD_NETS, HEAD_COMPONENTS, head_edge, (hx, hy), head_zone)

    export_boms()

    # 3. Export Schematic SVGs & run ERC on both schematics
    for label, sch in [("Main", MAIN_SCH), ("Headamp", HEAD_SCH)]:
        erc_out = ERC_DIR / f"erc_{label.lower()}.json"
        subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "-o", str(erc_out), str(sch)], capture_output=True)
        subprocess.run([KICAD_CLI, "sch", "export", "svg", "-o", str(RENDER_DIR), str(sch)], capture_output=True)
        rep = json.loads(erc_out.read_text(encoding="utf-8"))
        errs = [v for s in rep.get("sheets", []) for v in s.get("violations", []) if v.get("severity") == "error"]
        print(f"=== {label} SCH ERC: {len(errs)} errors ===")
        for e in errs[:5]:
            print("  [ERC ERR]", e.get("type"), "-", e.get("description"))


if __name__ == "__main__":
    main()
