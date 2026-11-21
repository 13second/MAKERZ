# Guida Rapida Upload su JLCPCB — IU-MIC_ORIGIN (Stadio 1)

Tutti i file pronti all'upload sono organizzati in **3 sottocartelle** dentro `exports/JLCPCB_STADIO1_READY/`.

---

## 1. Ordine 1 — Main PCB 4-Layer + SMT (`1_MAIN_PCB_4Layer_SMT/`)
- **Gerber ZIP**: `IU-MIC_ORIGIN_Main_JLCPCB_Gerbers.zip` *(0 ERC, 0 DRC, 0 unconnected)*
- **Impostazioni PCB consigliate su `jlcpcb.com`**:
  - **Layers**: `4` · **Dimensions**: `32 × 98 mm` · **PCB Thickness**: `1.6 mm`
  - **Surface Finish**: **`ENIG-RoHS`** *(consigliato per QFN-48 `AK5572EN` e QFN-24 `LAN8742A`)*
  - **PCB Assembly**: **`Economic`** · **Assembly Side**: **`Top Side`** (solo lato Top!)
- **Upload SMT**:
  - **BOM**: `BOM_Main_JLCPCB_SMT.csv` *(41 componenti SMD Top)*
  - **CPL**: `CPL_Main_JLCPCB_SMT.csv` *(41 righe sincronizzate 1:1)*
- **Controlli obbligatori nel BOM Matcher & 3D Preview di JLCPCB**:
  1. Selezionare/confermare i codici LCSC marcati `NON` / `NON_VERIFICATO` direttamente dal selettore JLCPCB (`AK5572EN`, `LP5907MFX-3.3`, `LP5907MFX-2.8`, `R_HPF_FB 56.2k 0.1%`, `R_HPF_GND 113k 0.1%`, `R_AA1/2 806R 0.1%`, `C_AA_FB 2.0nF C0G`, `J_SWD`). Se `AK5572EN` non è in stock su LCSC, lasciarlo **DNP** (Do Not Place) su JLCPCB e ordinarlo su Mouser/DigiKey per saldatura ad aria calda.
  2. Verificare nella **3D SMT Preview di JLCPCB** l'orientamento **Pin 1** di `U3` (`STM32H743VIT6`), `U6` (`AK5572EN`, ruotato `180°`), `U2` (`LAN8742A`), `U7/U8` (`OPA1656`), `U9` (`TMUX1104`), `D_TVS1` e `J2` (`USB-C`).
  3. **`J1` (`HR911105A` RJ45 MagJack)** è **THT** (escluso volutamente dalla BOM SMT): acquistarlo separatamente e saldarlo a mano dopo l'arrivo della scheda.

---

## 2. Ordine 2 — MEMS Tip PCB 2-Layer + SMT (`2_MEMS_TIP_PCB_2Layer_SMT/`)
- **Gerber ZIP**: `IU-MIC_ORIGIN_MEMS_Tip_JLCPCB_Gerbers.zip` *(0 ERC, 0 DRC, 0 unconnected, foro acustico Ø 1.0 mm centrato a 0.00 mm)*
- **Impostazioni PCB**:
  - **Layers**: `2` · **Dimensions**: `Ø 8.0 mm` · **Thickness**: `1.6 mm` · **Surface Finish**: **`ENIG-RoHS`**
  - **PCB Assembly**: **`Economic`** · **Assembly Side**: **`Top Side`**
- **Upload SMT**:
  - **BOM**: `BOM_MEMS_Tip_JLCPCB_SMT.csv` (`MK1`, `C_M1`)
  - **CPL**: `CPL_MEMS_Tip_JLCPCB_SMT.csv` (2 righe)
  - *Nota*: verificare stock di `IM73A135V01` su JLCPCB (se non disponibile su LCSC, ordinare il PCB nudo + `C_M1` e saldare la capsula `IM73A135V01` acquistata da Mouser/DigiKey con piastra/aria calda a bassa temperatura senza flussante nel foro acustico!).

---

## 3. Ordine 3 — Scocca 3D Stadio 1 (`3_SCOCCA_3D_PRINT/`)
- **File da caricare su JLCPCB 3D Printing**: `IU-MIC_ORIGIN_Stage1_JLCPCB_3DPrint_STL.zip` *(158 KB, 3× STL watertight, pareti `> 1.2 mm` ovunque, include `rear_cap_stage1.stl` solo RJ45)*.
- **Materiale consigliato**: **SLA Resin (8001 / Imagine Black / Grey)** oppure **MJF PA12 Nylon (Dyed Black / Anthracite)**.
- **Inserto filettato**: inserire a caldo 1× inserto ottone **1/4"-20** (`Ø est. 8 mm`) nella sella treppiede del corpo principale.
