# Skill & Toolchain Utilizzate — Progetto IU-MIC_ORIGIN

Questo documento raccoglie tutte le **skill personalizzate**, le **metodologie di workflow** e la **toolchain locale** create e impiegate per progettare, verificare e visualizzare **IU-MIC_ORIGIN** e **MAKERZ Studio**.

---

## 1. Skill Permanenti ECAD / MCAD Create (`~/.gemini/config/skills/`)

Queste 3 skill sono salvate in modo permanente nella tua configurazione globale di Antigravity e verranno riutilizzate automaticamente in tutti i futuri progetti hardware di **MAKERZ**:

### 1.1 `pcb-design-eda`
- **Percorso**: `~/.gemini/config/skills/pcb-design-eda/SKILL.md`
- **Script di verifica**: `~/.gemini/config/skills/pcb-design-eda/scripts/verify_pcb.sh`
- **Ruolo nel progetto**:
  - Definizione stackup **4-Layer JLCPCB** (`F.Cu` / `In1.Cu` GND solido / `In2.Cu` PWR partizionato / `B.Cu`) e partizionamento fisico PoE → Digitale → Analogico.
  - Generazione file **KiCad 8** (`.kicad_pro`, `.kicad_sch`, `.kicad_pcb`) per **Main PCB (`32 × 98 mm`)** e **MEMS Tip PCB (`Ø 8 mm`)**.
  - Export **Gerber RS-274X con estensioni Protel ufficiali JLCPCB** (`.GTL`, `.G2L`, `.G3L`, `.GBL`, `.GTS`, `.GBS`, `.GTP`, `.GBP`, `.GTO`, `.GBO`, `.GKO`) e **Excellon Drill Metric Decimal** (`-PTH.TXT` / `-NPTH.TXT`).
  - Generazione **BOM LCSC/Octopart** (`bom_lcsc.csv`), **BOM SMT JLCPCB** (`bom_jlcpcb_smt.csv`) e **Pick & Place** (`cpl_jlcpcb.csv`).
  - Supporto automatico a `kicad-cli` (ERC, DRC, export Gerber/Drill/STEP/SVG) appena installato sul Mac.

### 1.2 `parametric-cad-3d`
- **Percorso**: `~/.gemini/config/skills/parametric-cad-3d/SKILL.md`
- **Script di verifica**: `~/.gemini/config/skills/parametric-cad-3d/scripts/verify_model.py`
- **Ruolo nel progetto**:
  - Modellazione solida **B-rep 100% parametrica** in Python con **`build123d`** (`enclosure/pencil_mic.py`).
  - Applicazione delle regole DFM per **JLCPCB 3D Printing** (`Wall thickness > 1.2 mm`, `Thinnest part ≥ 0.8 mm`, tolleranze accoppiamento `0.15–0.25 mm`, finitura Grigio Antracite `#2C3038`, serigrafia 3D `IU-MIC` e nomi porte).
  - Export in **STEP** (CAD/CNC), **STL** (ZIP pulito 3× STL per stampa 3D) e **GLB** (viewer Three.js).
  - **Verification Gate obbligatorio**: controllo automatico `watertight == True`, bounding box reale in millimetri, volume e rendering multi-angolo PNG 2×2 ispezionato visivamente.

### 1.3 `ecad-mcad-codesign`
- **Percorso**: `~/.gemini/config/skills/ecad-mcad-codesign/SKILL.md`
- **Ruolo nel progetto**:
  - Sincronizzazione fisica tra i due PCB e la scocca 3D tramite un unico file *Single Source of Truth* ([dimensions.json](../dimensions.json)).
  - Allineamento al decimo di millimetro di **XLR-3M**, **RJ45 MagJack PoE**, **USB-C**, switch fisici **HPF 20 Hz / LPF 20 kHz**, **LED Status**, slitte interne PCB e sede frontale della capsula **Infineon IM73A135V01**.

---

## 2. Comandi & Metodologie di Workflow Utilizzate

| Comando / Metodologia | Come è stato usato |
| :--- | :--- |
| **`/plan`** | Valutazione iniziale delle capacità ECAD/MCAD del sistema, progettazione dell'architettura delle skill e redazione del piano di implementazione prima di scrivere codice o installare tool. |
| **`/grill-me`** | Intervista guidata ramo-per-ramo per risolvere tutti i vincoli fisici e di progetto (Nyquist 192 kHz vs banda 1 Hz–90 kHz, figura polare omnidirezionale, capsula MEMS wideband, filtri HPF/LPF, Dual-Gain 32-bit float, AES67/RAVENNA/Dante + PoE, fattore di forma Pencil Mic, link Octopart BOM). |
| **Web Dev / Three.js (Zero-Dependency)** | Sviluppo di **MAKERZ Studio** (`../makerz-studio/`): server locale Node.js puro + viewer 3D interattivo Three.js (`GLTFLoader`, `OrbitControls`, Vista Esplosa) + pan/zoom SVG + registro progetti persistente su SSD (`.makerz_registry.json`). |

---

## 3. Toolchain Locale Configurata

- **Python CAD Environment (`uv`)**: `/Users/simonegaudimonte/.gemini/config/cad-venv` (Python 3.12 ARM64) con `build123d`, `cadquery-ocp-novtk`, `trimesh`, `matplotlib`, `numpy`, `pillow`, `ezdxf`, `lib3mf`.
- **Node.js**: runtime per il server locale di **MAKERZ Studio** (`http://127.0.0.1:4173`).
- **KiCad CLI *(opzionale da completare)***: per abilitare ERC/DRC nativi da terminale tramite `verify_pcb.sh`, esegui una sola volta:
  ```bash
  sudo xcodebuild -license accept && brew install --cask kicad
  ```
