#!/usr/bin/env python3
"""FreeRouting 1.9.0 CLI + KiCad 10 native Gerber/Drill/CPL pipeline for SPIRIT-IP_LDC.

Routes both ``SPIRIT-IP_Main`` (4-layer) and ``SPIRIT-IP_Headamp`` (2-layer)
via Specctra DSN/SES exchange, adds QFN thermal GND vias, fills copper zones,
runs ``kicad-cli`` DRC verification, and exports JLCPCB-ready Gerber ZIPs,
SVG renders, and exact Gerber-coordinate Pick & Place (CPL) CSVs.
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
MAIN_PCB = ROOT / "hardware" / "main_pcb" / "SPIRIT-IP_Main.kicad_pcb"
HEAD_PCB = ROOT / "hardware" / "headamp_pcb" / "SPIRIT-IP_Headamp.kicad_pcb"
GERBER_DIR = ROOT / "exports" / "gerbers"
RENDER_DIR = ROOT / "exports" / "renders"
DRC_DIR = ROOT / "hardware" / "drc_reports"

for d in (GERBER_DIR, RENDER_DIR, DRC_DIR):
    d.mkdir(parents=True, exist_ok=True)

KICAD_CLI = shutil.which("kicad-cli") or "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JAVA_BIN = (
    os.environ.get("JAVA_BIN")
    or (
        "/opt/homebrew/opt/openjdk@21/bin/java"
        if Path("/opt/homebrew/opt/openjdk@21/bin/java").exists()
        else (shutil.which("java") or "java")
    )
)
FREEROUTING_JAR = Path(
    os.environ.get("FREEROUTING_JAR", str(Path.home() / ".gemini/config/tools/freerouting.jar"))
)


def route_and_export(
    label: str,
    pcb_path: Path,
    is_4l: bool,
    bom_smt_path: Path,
    cpl_out_path: Path,
    zip_name: str,
    rot_overrides: dict[str, float] | None = None,
) -> None:
    """Autoroutes a KiCad PCB, verifies DRC, and exports Gerbers, SVGs, and CPL.

    Args:
        label: Human-readable board label (e.g., ``"Main"`` or ``"Headamp"``).
        pcb_path: Path to the target ``.kicad_pcb`` file.
        is_4l: True for 4-layer stackup (adds QFN thermal vias and inner copper layers).
        bom_smt_path: Path to the JLCPCB SMT BOM CSV used to filter CPL rows.
        cpl_out_path: Output path for the JLCPCB Pick & Place CSV.
        zip_name: Output filename for the Gerber + Excellon drill ZIP archive.
        rot_overrides: Optional per-designator rotation offsets in degrees for JLCPCB SMT.

    Raises:
        RuntimeError: If Specctra DSN export or FreeRouting SES generation fails.
    """
    rot_overrides = rot_overrides or {}
    print(f"\n========== ROUTING {label}: {pcb_path.name} ==========")
    dsn_path = pcb_path.with_suffix(".dsn")
    ses_path = pcb_path.with_suffix(".ses")
    log_path = DRC_DIR / f"freerouting_{label.lower()}.log"

    board = pcbnew.LoadBoard(str(pcb_path))
    ok = pcbnew.ExportSpecctraDSN(board, str(dsn_path))
    if not ok:
        raise RuntimeError(f"ExportSpecctraDSN failed for {pcb_path}")

    cmd = [JAVA_BIN, "-jar", str(FREEROUTING_JAR), "-de", str(dsn_path), "-do", str(ses_path), "-mp", "25", "-da"]
    print("Running FreeRouting:", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    log_path.write_text(res.stdout + "\n" + res.stderr, encoding="utf-8")
    if not ses_path.exists():
        raise RuntimeError(f"FreeRouting failed to produce {ses_path}; see {log_path}")

    board = pcbnew.LoadBoard(str(pcb_path))
    pcbnew.ImportSpecctraSES(board, str(ses_path))

    # Post-route QFN thermal GND vias on Main PCB (U2 @ 118.5, 81.0; U6 @ 115.0, 123.5)
    if is_4l:
        gnd_net = board.FindNet("GND")
        if gnd_net:
            qfn_vias = [
                # U2 LAN8742A exposed pad (2.6 x 2.6 mm centered at 118.5, 81.0)
                (118.5, 81.0), (117.9, 80.4), (119.1, 80.4), (117.9, 81.6), (119.1, 81.6),
                # U6 AK5572EN exposed pad (5.15 x 5.15 mm centered at 115.0, 123.5)
                (115.0, 123.5), (113.6, 122.1), (115.0, 122.1), (116.4, 122.1),
                (113.6, 123.5), (116.4, 123.5),
                (113.6, 124.9), (115.0, 124.9), (116.4, 124.9),
            ]
            for vx, vy in qfn_vias:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(vx), pcbnew.FromMM(vy)))
                v.SetWidth(pcbnew.FromMM(0.55))
                v.SetDrill(pcbnew.FromMM(0.30))
                v.SetNet(gnd_net)
                board.Add(v)

    # Fill copper GND zones and persist routed board
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(str(pcb_path), board)

    # Run KiCad DRC and summarize errors / unconnected nets
    drc_json = DRC_DIR / f"drc_{label.lower()}.json"
    subprocess.run(
        [KICAD_CLI, "pcb", "drc", "--format", "json", "--severity-all", "-o", str(drc_json), str(pcb_path)],
        capture_output=True,
    )
    rep = json.loads(drc_json.read_text(encoding="utf-8"))
    errs = [v for v in rep.get("violations", []) if v.get("severity") == "error"]
    unconn = rep.get("unconnected_items", [])
    print(f"=== {label} DRC: {len(errs)} errors, {len(unconn)} unconnected ===")
    for v in errs[:10]:
        print("  [DRC ERR]", v.get("type"), "-", v.get("description"))

    # Export Gerbers + Excellon drill files into a clean ZIP archive
    tmp_g = Path(f"/tmp/spirit_gerbers_{label.lower()}")
    shutil.rmtree(tmp_g, ignore_errors=True)
    tmp_g.mkdir(parents=True, exist_ok=True)
    layers = (
        "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
        if is_4l
        else "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
    )
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "gerbers", "-l", layers, "-o", str(tmp_g), str(pcb_path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "drill", "--format", "excellon", "--drill-origin", "absolute", "-o", str(tmp_g) + "/", str(pcb_path)],
        check=True,
        capture_output=True,
    )

    zpath = GERBER_DIR / zip_name
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp_g.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                zf.write(p, p.name)
    print(f"Exported Gerbers ZIP -> {zpath}")

    # Export front/back SVG renders for MAKERZ Studio
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "svg", "-l", "F.Cu,F.Silkscreen,F.Mask,Edge.Cuts",
         "-o", str(RENDER_DIR / f"kicad_{label.lower()}_front.svg"), str(pcb_path)],
        capture_output=True,
    )
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "svg", "-l", "B.Cu,B.Silkscreen,B.Mask,Edge.Cuts", "--mirror",
         "-o", str(RENDER_DIR / f"kicad_{label.lower()}_back.svg"), str(pcb_path)],
        capture_output=True,
    )

    # Export exact Gerber-coordinate CPL directly from kicad-cli pcb export pos
    tmp_pos = Path(f"/tmp/spirit_pos_{label.lower()}.csv")
    subprocess.run(
        [KICAD_CLI, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front",
         "-o", str(tmp_pos), str(pcb_path)],
        check=True,
        capture_output=True,
    )

    bom_refs = set()
    with open(bom_smt_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref = (row.get("Designator") or "").strip()
            if ref:
                bom_refs.add(ref)

    cpl_rows = []
    with open(tmp_pos, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref = row["Ref"].strip()
            if ref not in bom_refs:
                continue
            x = float(row["PosX"])
            y = float(row["PosY"])
            rot = (float(row["Rot"]) + rot_overrides.get(ref, 0.0)) % 360.0
            layer = "Top" if row["Side"].strip().lower() == "top" else "Bottom"
            cpl_rows.append((ref, f"{x:.2f}mm", f"{y:.2f}mm", layer, f"{rot:.1f}"))

    with open(cpl_out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(cpl_rows)
    print(f"Exported Exact-Gerber CPL ({len(cpl_rows)} SMD rows) -> {cpl_out_path}")


if __name__ == "__main__":
    # Verified JLCPCB SMT rotation offsets from live Part Placement previews
    main_rots = {"U1": 270.0, "U3": 270.0, "U4": 180.0, "U6": 270.0}
    head_rots = {"U_A1": 270.0, "U_A2": 270.0}
    route_and_export(
        "Main",
        MAIN_PCB,
        True,
        ROOT / "hardware" / "BOM_Main_JLCPCB_SMT.csv",
        ROOT / "hardware" / "CPL_Main_JLCPCB_SMT.csv",
        "SPIRIT-IP_Main_4L_JLCPCB_Gerbers.zip",
        rot_overrides=main_rots,
    )
    route_and_export(
        "Headamp",
        HEAD_PCB,
        False,
        ROOT / "hardware" / "BOM_Headamp_JLCPCB_SMT.csv",
        ROOT / "hardware" / "CPL_Headamp_JLCPCB_SMT.csv",
        "SPIRIT-IP_Headamp_2L_JLCPCB_Gerbers.zip",
        rot_overrides=head_rots,
    )
