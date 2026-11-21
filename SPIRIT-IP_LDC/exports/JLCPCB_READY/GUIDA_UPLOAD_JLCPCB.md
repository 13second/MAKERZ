# SPIRIT-IP_LDC v1.2.1 "Pure Digital" — Guida Upload JLCPCB + JLC3DP

Versione **100% Digitale (RJ45 PoE + USB-C UAC2, senza XLR)**: compatibile plug & play con **Mac + UAD Apollo x6 (Aggregate Device)**, Windows, **iPhone / iPad USB-C** (profilo automatico `<160 mA` tramite `POE_SENSE`) e reti **AES67 / PTPv2**.

---

## 1. Main PCB 4-Layer + SMT (`1_MAIN_PCB_4Layer_SMT/`) — 100% JLCPCB Turnkey!
- **Gerber ZIP**: `SPIRIT-IP_Main_4L_JLCPCB_Gerbers.zip`
- **Impostazioni PCB**: 4 Layers, `1.6 mm`, **Impedance Control: JLC04161H-7628**, Finitura **ENIG**, Colore **Nero opaco** o **Verde**.
- **PCB Assembly (SMT)**: Top Side, **Qty = 2**, carica:
  - `BOM_Main_JLCPCB_SMT.csv` *(tutti i codici LCSC **In Stock** già inclusi, zero componenti Mouser obbligatori!)*
  - `CPL_Main_JLCPCB_SMT.csv` *(coordinate Gerber native + rotazioni già verificate: `U1=270°`, `U3=270°`, `U4=180°`, `U6=90°`)*
- **Saldatura manuale post-SMT**: solo la presa RJ45 THT `J1` (`Hanrun HR911105A`).

## 2. Headamp PCB 2-Layer + SMT (`2_HEADAMP_PCB_2Layer_SMT/`)
- **Gerber ZIP**: `SPIRIT-IP_Headamp_2L_JLCPCB_Gerbers.zip`
- **Impostazioni PCB**: 2 Layers, `1.6 mm`, Finitura **ENIG**, **Qty = 2**.
- **PCB Assembly (SMT)**: Top Side, carica `BOM_Headamp_JLCPCB_SMT.csv` + `CPL_Headamp_JLCPCB_SMT.csv`.
- **Note**: `R_G1, R_G2` (`1 GΩ 0805`) e `SH1` (`Laird BMI-S-102` shield-can 16.5×16.5 mm) si saldano a mano se non in stock su LCSC.

## 3. Scocca 3D (`3_SCOCCA_3D_JLC3DP/`)
- **`SPIRIT-IP_body_clear_8001.stl`** → **JLC3DP `8001` Transparent Resin** (*Sanding + Clear Oil*).
- **`SPIRIT-IP_grille_316L_metal.stl`** → **JLC3DP `316L` Stainless Steel (SLM Metal)**.
- **`SPIRIT-IP_bottom_cap_triple_port.stl`** *(ora Dual-Port: RJ45 + USB-C + sede `5/8"-27`)* + **`SPIRIT-IP_capsule_saddle.stl`** → **JLC3DP `9600` Resin / PA12 Black**.


## v1.2 — modifiche scocca
- Sella ridisegnata (gradino + chiavette, culla R18.5 @Z146, asola J_CAP 6x9 @x=-12.5).
- NUOVO: `SPIRIT-IP_capsule_shockmount_TPU.stl` (1.5 mm) NON e' nello ZIP rigido: va ordinato a parte in un materiale flessibile (TPU/silicone) — verifica la disponibilita' sul servizio scelto.
- I PCB KiCad e i Gerber/BOM/CPL sono invariati.

## v1.2.1 — rifiniture DFM JLC3DP e tolleranze
- Shock-mount TPU portato a larghezza 12.6 mm (bordini 1.3 mm), asola dedicata 5.0×7.0 mm (ponti 2.8 mm) e 3 tamponi smorzanti (5.0 mm, precarico 0.3 mm) a -22°/0°/+22° fuori dall'asola.
- Gioco radiale corpo 8001 ↔ griglia 316L aumentato a 0.25 mm/lato (spalla R=25.30, collare ID R=25.55) e cordoli centraggio Headamp portati a 1.40 mm (R=18.2..19.6).
- Pacchetto `JLCPCB_READY/` rigenerato e ripulito da file `._*`; PCB KiCad, Gerber, BOM e CPL invariati.
