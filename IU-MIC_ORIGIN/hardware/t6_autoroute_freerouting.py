#!/usr/bin/env python3
"""T6 — Automated KiCad 10 + FreeRouting 1.9.0 PCB autorouting pipeline for IU-MIC_ORIGIN.

Executes the full routing and manufacturing export workflow:
    KiCad 10 ``pcbnew`` -> Specctra DSN -> FreeRouting 1.9.0 (OpenJDK 21)
    -> Specctra SES import -> QFN thermal vias + In1.Cu GND pour
    -> ``kicad-cli`` DRC + Protel Gerbers + Excellon drill + JLCPCB CPL CSV.
"""

import csv
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
MAIN_PCB = ROOT / "hardware" / "main_pcb" / "IU-MIC_ORIGIN_Main.kicad_pcb"
DRC_DIR = ROOT / "hardware" / "drc_reports"
GERBER_DIR = ROOT / "exports" / "gerbers"
RENDER_DIR = ROOT / "exports" / "renders"

JAVA_BIN = os.environ.get("JAVA_BIN") or shutil.which("java") or "/opt/homebrew/opt/openjdk@21/bin/java"
if not Path(JAVA_BIN).exists() or JAVA_BIN == "/usr/bin/java":
    JAVA_BIN = "/opt/homebrew/opt/openjdk@21/bin/java"
FREEROUTING_JAR = os.environ.get("FREEROUTING_JAR", str(Path.home() / ".gemini/config/tools/freerouting.jar"))
KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def autoroute_board(pcb_path: Path, max_passes: int = 25, timeout_sec: int = 180) -> None:
    """Autoroutes a KiCad PCB with FreeRouting, adds QFN thermal vias, and exports Gerbers/CPL.

    Args:
        pcb_path: Path to the input ``.kicad_pcb`` file.
        max_passes: Maximum FreeRouting optimization passes.
        timeout_sec: Subprocess timeout in seconds for FreeRouting execution.

    Raises:
        RuntimeError: If Specctra DSN export, FreeRouting, or SES import fails.
    """
    work_dir = Path("/tmp/iu_mic_route")
    work_dir.mkdir(parents=True, exist_ok=True)
    dsn_path = work_dir / f"{pcb_path.stem}.dsn"
    ses_path = work_dir / f"{pcb_path.stem}.ses"
    log_path = DRC_DIR / "freerouting.log"
    if ses_path.exists():
        ses_path.unlink()

    print(f"[1/5] Loading {pcb_path.name} in KiCad 10 pcbnew...")
    board = pcbnew.LoadBoard(str(pcb_path))

    print(f"[2/5] Exporting Specctra DSN -> {dsn_path}...")
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn_path))
    if not ok:
        raise RuntimeError("ExportSpecctraDSN failed!")

    print(f"[3/5] Running FreeRouting 1.9.0 CLI (max_passes={max_passes}, timeout={timeout_sec}s, log={log_path.name})...")
    cmd = [
        JAVA_BIN, "-jar", FREEROUTING_JAR,
        "-de", str(dsn_path),
        "-do", str(ses_path),
        "-mp", str(max_passes),
        "-mt", "4",
        "-da",
    ]
    with log_path.open("w", encoding="utf-8") as lf:
        proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout_sec)
    if not ses_path.exists():
        raise RuntimeError(f"FreeRouting failed (rc={proc.returncode}), see {log_path}")

    print("[4/5] Importing routed Specctra SES, adding QFN thermal vias (5 on U2, 13 on U6) & pouring In1.Cu GND...")
    ok = pcbnew.ImportSpecctraSES(board, str(ses_path))
    if not ok:
        raise RuntimeError("ImportSpecctraSES failed!")

    # Add fixed QFN thermal GND vias (5 on U2 EP, 13 on U6 EP) after FreeRouting
    n_gnd = board.FindNet("GND")
    ox, oy = 100.0, 50.0
    thermal_coords = [(ox + 12.0 + dx, oy + 32.5 + dy) for dx, dy in [(0, 0), (-0.75, -0.75), (0.75, -0.75), (-0.75, 0.75), (0.75, 0.75)]]
    thermal_coords += [(ox + 14.0 + dx, oy + 73.0 + dy) for dx in (-1.6, 0.0, 1.6) for dy in (-1.6, 0.0, 1.6)]
    thermal_coords += [(ox + 14.0 + dx, oy + 73.0 + dy) for dx in (-0.8, 0.8) for dy in (-0.8, 0.8)]
    for vx, vy in thermal_coords:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
        v.SetWidth(pcbnew.FromMM(0.60))
        v.SetDrill(pcbnew.FromMM(0.30))
        v.SetNet(n_gnd)
        board.Add(v)

    # Add post-routing GND shield pour on In1.Cu with automatic dead-island removal
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.In1_Cu)
    z.SetNet(board.FindNet("GND"))
    z.SetLocalClearance(pcbnew.FromMM(0.20))
    z.SetMinThickness(pcbnew.FromMM(0.20))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    outline = z.Outline()
    outline.NewOutline()
    for (zx, zy) in [(100.5, 50.5), (131.5, 50.5), (131.5, 147.5), (100.5, 147.5)]:
        outline.Append(pcbnew.FromMM(zx), pcbnew.FromMM(zy))
    board.Add(z)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(pcb_path), board)

    # Export JLCPCB CPL directly from routed KiCad board footprints
    cpl_path = ROOT / "hardware" / "cpl_jlcpcb.csv"
    with cpl_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(board.GetFootprints(), key=lambda m: m.GetReference()):
            ref = fp.GetReference()
            if ref.startswith("FID") or ref.startswith("TP"):
                continue
            pos = fp.GetPosition()
            x_mm = pcbnew.ToMM(pos.x) - 100.0
            y_mm = pcbnew.ToMM(pos.y) - 50.0
            layer = "Top" if fp.GetLayer() == pcbnew.F_Cu else "Bottom"
            rot = round(fp.GetOrientationDegrees() % 360.0, 1)
            w.writerow([ref, f"{x_mm:.2f}mm", f"{y_mm:.2f}mm", layer, rot])

    print("[5/5] Running kicad-cli DRC + native Gerber Protel & Drill export...")
    drc_json = DRC_DIR / "drc_main_stage1_routed.json"
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "-o", str(drc_json), str(pcb_path)], capture_output=True)
    drc = json.loads(drc_json.read_text(encoding="utf-8"))
    errs = [v for v in drc.get("violations", []) if v.get("severity") == "error"]
    unconn = drc.get("unconnected_items", [])

    # Export native KiCad 10 Gerbers, Excellon drill files, and SVG renders
    tmp_g = GERBER_DIR / "kicad10_main_stage1"
    if tmp_g.exists():
        shutil.rmtree(tmp_g, ignore_errors=True)
    tmp_g.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        KICAD_CLI, "pcb", "export", "gerbers",
        "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask",
        "--output", str(tmp_g),
        str(pcb_path),
    ], capture_output=True)
    subprocess.run([
        KICAD_CLI, "pcb", "export", "drill",
        "--format", "excellon",
        "--excellon-units", "mm",
        "--excellon-zeros-format", "decimal",
        "--excellon-oval-format", "alternate",
        "--output", str(tmp_g),
        str(pcb_path),
    ], capture_output=True)
    subprocess.run([KICAD_CLI, "pcb", "export", "svg", "-l", "F.Cu,F.Silkscreen,F.Mask,Edge.Cuts", "-o", str(RENDER_DIR / "kicad_main_stage1_front.svg"), str(pcb_path)], capture_output=True)
    subprocess.run([KICAD_CLI, "pcb", "export", "svg", "-l", "B.Cu,B.Silkscreen,B.Mask,Edge.Cuts", "--mirror", "-o", str(RENDER_DIR / "kicad_main_stage1_back.svg"), str(pcb_path)], capture_output=True)

    zpath = GERBER_DIR / "IU-MIC_ORIGIN_Main_JLCPCB_Gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp_g.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, p.name)

    print(f"=== ROUTED MAIN PCB DRC: {len(errs)} errors, {len(unconn)} unconnected ===")
    for v in errs[:10]:
        print("  [DRC ERR]", v.get("type"), "-", v.get("description"))


if __name__ == "__main__":
    autoroute_board(MAIN_PCB)
