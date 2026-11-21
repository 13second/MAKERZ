# T7 — Audit Produzione JLCPCB & Lista Verifica LCSC (Stadio 1)

*Nessun codice LCSC viene dichiarato "in stock" senza verifica diretta sul portale `https://jlcpcb.com/parts`.*

## 1. Avvisi Critici PCBA JLCPCB (Stadio 1)

| Aspetto PCBA | MEMS Tip PCB (`Ø 8.0 mm`, 2L) | Main PCB Stadio 1 (`32 × 98 mm`, 4L) | Impatto su Ordine JLCPCB |
| :--- | :--- | :--- | :--- |
| **Lato Assemblaggio SMT** | **Solo Top** (`MK1`, `C_M1`) — i 4 pad `B.Cu` sono piazzole saldabili a mano | **Solo Top** nello Stadio 1 (nessun componente SMT sul Bottom!) | Consente **Economic PCBA (Single-Sided Top)**, evitando il sovrapprezzo Standard PCBA / pannellizzazione obbligatoria del double-sided |
| **Componenti THT** | Nessuno | **`J1` (`HR911105A` RJ45 MagJack)** è Through-Hole | Saldatura manuale post-SMT consigliata (oppure Standard PCBA con costo extra wave/hand-solder) |
| **Parti Extended** | `MK1` (`IM73A135V01`) | `U2` (`LAN8742A`), `U3` (`STM32H743`), `U4/U5` (`LP5907`), `U6` (`AK5572EN`), `U7/U8` (`OPA1656`), `U9` (`TMUX1104`), `J2`, `J3`, resistenze 0.1% | Ogni codice **Extended** comporta una fee feeder JLCPCB (~`$3` cad.) |
| **Stato Routing & Gerber** | **0 errori DRC · 0 net non connesse** (pronto per verifica visiva Gerber) | **0 errori DRC · 41 net non connesse** (**NON ancora pronto per ordine**) | Completare il routing del Main PCB + passivi filtri T3 prima dell'upload |

---

## 2. Lista Componenti Stadio 1 da Verificare Manualmente su `jlcpcb.com/parts`

| Ref | Scheda | MPN (Verificato T1) | Package Reale | Montaggio / Tipo | Categoria Stimata | Codice LCSC da Verificare |
| :--- | :---: | :--- | :--- | :---: | :---: | :--- |
| `MK1` | Tip | `IM73A135V01XTSA1` | PG-LLGA-5-2 (5-pin Bottom-Port) | Top / SMD | Extended | **NON VERIFICATO** — cercare `IM73A135V01` su `jlcpcb.com/parts` (in alternativa ordinare su Mouser/DigiKey) |
| `C_M1` | Tip | `CL05B104KO5NNNC` (o `100nF C0G/X7R 0402`) | C_0402_1005Metric | Top / SMD | Basic | Verificare `C1525` (Basic) su `jlcpcb.com/parts` |
| `J1` | Main | `HR911105A` (RJ45 100M MagJack) | RJ45 THT Horizontal | Top / **THT** | Extended | Verificare `C12074` / `HR911105A` (saldatura manuale) |
| `J2` | Main | `TYPE-C-31-M-12` (USB-C 16-pin) | USB-C SMD + 4 shell THT | Top / SMD+THT | Extended | Verificare `C165948` su `jlcpcb.com/parts` |
| `J3` | Main | `SM04B-SRSS-TB` (JST-SH 4-pin) | JST-SH 1.0 mm SMD | Top / SMD | Extended | Verificare `C160404` su `jlcpcb.com/parts` |
| `U2` | Main | `LAN8742A-CZ-TR` | SQFN-24 (4×4 mm + EP) | Top / SMD | Extended | Verificare `C46749` su `jlcpcb.com/parts` |
| `U3` | Main | `STM32H743VIT6` | LQFP-100 (14×14 mm) | Top / SMD | Extended | Verificare `C136694` su `jlcpcb.com/parts` |
| `U4` | Main | `LP5907MFX-3.3/NOPB` | SOT-23-5 | Top / SMD | Extended | **NON VERIFICATO** — cercare `LP5907MFX-3.3` su `jlcpcb.com/parts` |
| `U5` | Main | `LP5907MFX-2.8/NOPB` | SOT-23-5 | Top / SMD | Extended | **NON VERIFICATO** — cercare `LP5907MFX-2.8` (obbligatorio ≤ 3.00 V per `IM73A135V01`!) |
| `U6` | Main | `AK5572EN` | QFN-48 (7×7 mm + EP) | Top / SMD | Extended | **NON VERIFICATO** — cercare `AK5572EN` su `jlcpcb.com/parts` (alta probabilità di acquisto su Mouser/DigiKey) |
| `U7, U8` | Main | `OPA1656IDR` | SOIC-8 (3.9×4.9 mm) | Top / SMD | Extended | Verificare `C2654935` su `jlcpcb.com/parts` |
| `U9` | Main | `TMUX1104DGSR` | VSSOP-10 / MSOP-10 | Top / SMD | Extended | Verificare `C2848112` su `jlcpcb.com/parts` |
| `R_hpf` | Main | `56.2k` & `113k` 0.1% Thin Film (T3) | R_0603_1608Metric | Top / SMD | Extended | Cercare E96 0.1% 0603 su `jlcpcb.com/parts` |
| `C_hpf` | Main | `100nF` C0G/NP0 50V (T3, ×2) | C_0805_2012Metric | Top / SMD | Extended | Cercare `100nF C0G 0805` su `jlcpcb.com/parts` |
| `R_lpf` | Main | `2.55k` 0.1% Thin Film (T3, ×2) | R_0603_1608Metric | Top / SMD | Extended | Cercare `2.55k 0.1% 0603` su `jlcpcb.com/parts` |
| `C_lpf` | Main | `2.2nF` C0G/NP0 50V (T3, ×3: 1 + 2 in parall.) | C_0603_1608Metric | Top / SMD | Basic/Ext | Cercare `2.2nF C0G 0603` su `jlcpcb.com/parts` |
| `R_aa` | Main | `806 Ω` 0.1% Thin Film (T3, ×2) | R_0603_1608Metric | Top / SMD | Extended | Cercare `806R 0.1% 0603` su `jlcpcb.com/parts` |
| `C_aa` | Main | `1.0nF` C0G/NP0 50V (T3, ×3: 1 + 2 in parall.) | C_0603_1608Metric | Top / SMD | Basic | Cercare `1nF C0G 0603` su `jlcpcb.com/parts` |
