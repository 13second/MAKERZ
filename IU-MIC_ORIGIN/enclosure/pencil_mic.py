#!/usr/bin/env python3
"""Parametric 3D MCAD enclosure generator for IU-MIC_ORIGIN Rev 1.1 (build123d).

Generates all printable enclosure parts, internal PCB reference models, 3D
extruded serigraphy, and JLCPCB 3D-printing STL archives from ``dimensions.json``:
    * Satin anthracite finish (#2C3038)
    * Sculpted Ø 46 mm cylindrical body with machined tactile grip rings,
      recessed side control bezel, contoured tripod saddle, and Ø 11.2 mm
      ultrasonic measurement nose cone
    * Dual rear-cap variants: Stage 2 (XLR-3M + RJ45 PoE) and Stage 1 (RJ45-only)
    * 3D extruded front, side, and rear port serigraphy
"""
import json
import zipfile
from pathlib import Path
import numpy as np
import trimesh
from build123d import (
    Align,
    Box,
    BuildPart,
    BuildSketch,
    Compound,
    Cone,
    Cylinder,
    FontStyle,
    Locations,
    Mode,
    Plane,
    Text,
    export_step,
    export_stl,
    extrude,
)

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text())
OUT_3D = ROOT / "exports" / "3d"
OUT_3D.mkdir(parents=True, exist_ok=True)

ENC = DIM["enclosure"]
PCB = DIM["main_pcb"]
TIP = DIM["mems_tip_pcb"]
TOL = DIM["tolerance_fdm"]

R_BODY = ENC["body_outer_diameter"] / 2.0   # 23.0 mm (Ø 46 mm — JLCPCB 3D wall > 1.2mm everywhere)
WALL = ENC["wall_thickness"]                 # 2.6 mm
R_INNER = R_BODY - WALL                      # 20.4 mm
L_BODY = ENC["body_length"]                  # 108.0 mm
L_CONE = ENC["cone_length"]                  # 26.0 mm
R_TIP = ENC["tip_outer_diameter"] / 2.0      # 5.6 mm (Ø 11.2 mm — wall >= 1.45 mm around MEMS seat)
L_TIP = ENC["tip_length"]                    # 52.0 mm
PCB_Z0 = 6.0

FLAT_FRONT_Y = R_BODY - 0.8                  # Y = +22.2 mm -> min wall 1.8 mm (> 1.2 mm JLCPCB)
FLAT_SIDE_X = R_BODY - 1.0                   # X = +22.0 mm -> min wall 1.6 mm (> 1.2 mm JLCPCB)


def build_body_main():
    """Constructs the sculpted Ø 46 mm main cylindrical microphone body.

    Includes tactile grip grooves, tripod boss with 1/4"-20 heat-set insert bore,
    recessed branding and side-control facets, internal PCB guide rails, and
    cutouts for USB-C, HPF/LPF switches, and status LED.

    Returns:
        ``build123d`` solid representing the main body enclosure.
    """
    with BuildPart() as p:
        # 1. Main cylindrical body with subtle chamfered rear & front collars
        Cylinder(radius=R_BODY, height=L_BODY, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Sculpted front & rear chamfer bevels (subtract conical rings)
        with Locations((0, 0, L_BODY - 2.0)):
            Cylinder(radius=R_BODY + 1.0, height=2.2, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations((0, 0, L_BODY - 2.0)):
            Cone(bottom_radius=R_BODY, top_radius=R_BODY - 1.2, height=2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 3 precision machined tactile grip grooves near rear (Z = 10, 14, 18 mm)
        for gz in (10.0, 14.0, 18.0):
            with Locations((0, 0, gz)):
                Cylinder(radius=R_BODY + 0.5, height=1.2, align=(Align.CENTER, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)
            with Locations((0, 0, gz)):
                Cylinder(radius=R_BODY - 0.65, height=1.3, align=(Align.CENTER, Align.CENTER, Align.CENTER))

        # 2. Contoured sleek tripod/stand saddle on -Y side
        boss_z = PCB_Z0 + ENC["tripod_boss_y_from_rear"]
        with Locations((0, -(R_BODY - 2.0), boss_z)):
            Cylinder(
                radius=8.5,
                height=8.0,
                rotation=(90, 0, 0),
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        # 3. Recessed flat front branding facet (+Y) for crisp "IU-MIC" serigraphy
        with Locations((0, FLAT_FRONT_Y, L_BODY / 2.0)):
            Box(18.0, 4.0, 74.0, align=(Align.CENTER, Align.MIN, Align.CENTER), mode=Mode.SUBTRACT)

        # 4. Recessed flat side control bezel (+X) for USB-C, HPF, LPF, STATUS + serigraphy
        with Locations((FLAT_SIDE_X, 0, PCB_Z0 + 58.0)):
            Box(4.0, 17.0, 68.0, align=(Align.MIN, Align.CENTER, Align.CENTER), mode=Mode.SUBTRACT)

        # 5. Hollow interior
        Cylinder(
            radius=R_INNER,
            height=L_BODY + 2.0,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )

        # 6. Internal PCB guide rails along ±X (for 32 × 98 × 1.6 mm Main PCB)
        rail_z0 = PCB_Z0 + 2.0
        rail_len = PCB["length"] - 4.0
        for sx in (-1, 1):
            for sy_off in (-1.9, 1.9):
                with Locations((sx * (R_INNER - 2.1), sy_off, rail_z0)):
                    Box(4.8, 1.8, rail_len, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # 7. Cutouts on +X control bezel (shifted to Y = -2.8 mm to leave room for serigraphy at Y = +4.2 mm)
        usbc_z = PCB_Z0 + PCB["usb_c"]["y_from_rear"]
        with Locations((FLAT_SIDE_X, -2.8, usbc_z)):
            Box(WALL * 3.5, PCB["usb_c"]["height"] + 1.2, PCB["usb_c"]["width"] + 1.2, mode=Mode.SUBTRACT)

        for sw_key in ("switch_hpf", "switch_lpf"):
            sw = PCB[sw_key]
            sw_z = PCB_Z0 + sw["y_from_rear"]
            with Locations((FLAT_SIDE_X, -2.8, sw_z)):
                Box(WALL * 3.5, sw["height"] + 1.2, sw["width"] + 1.2, mode=Mode.SUBTRACT)

        led_z = PCB_Z0 + PCB["status_led"]["y_from_rear"]
        with Locations((FLAT_SIDE_X, -2.8, led_z)):
            Cylinder(
                radius=(PCB["status_led"]["diameter"] + 0.5) / 2.0,
                height=WALL * 3.5,
                rotation=(0, 90, 0),
                mode=Mode.SUBTRACT,
            )

        # 8. Bore for 1/4"-20 brass heat-set insert inside contoured saddle
        with Locations((0, -(R_BODY + 6.2), boss_z)):
            Cylinder(
                radius=ENC["tripod_insert_bore_diameter"] / 2.0,
                height=8.5,
                rotation=(90, 0, 0),
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    return p.part


def build_nose_cone():
    """Constructs the tapered ultrasonic measurement nose cone and MEMS tip seat.

    Returns:
        ``build123d`` solid representing the front nose cone.
    """
    z_base = L_BODY
    z_collar = z_base + 3.0
    z_cone_end = z_collar + L_CONE
    z_tip_end = z_cone_end + L_TIP

    with BuildPart() as p:
        # Rear slip-fit collar into body_main
        with Locations((0, 0, z_base - 6.0)):
            Cylinder(radius=R_INNER - TOL, height=6.0, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Stepped accent shoulder ring
        with Locations((0, 0, z_base)):
            Cone(bottom_radius=R_BODY - 1.2, top_radius=R_BODY - 0.4, height=3.0, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Smooth taper cone (Ø 41.2 -> Ø 10 mm)
        with Locations((0, 0, z_collar)):
            Cone(bottom_radius=R_BODY - 0.4, top_radius=R_TIP, height=L_CONE, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Slender ultrasonic measurement probe tube (Ø 10 mm × 52 mm)
        with Locations((0, 0, z_cone_end)):
            Cylinder(radius=R_TIP, height=L_TIP, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Subtle collar ring at base of ultrasonic probe
        with Locations((0, 0, z_cone_end)):
            Cylinder(radius=R_TIP + 0.7, height=2.2, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Hollow interior & wire channel
        with Locations((0, 0, z_base - 7.0)):
            Cylinder(radius=R_INNER - TOL - 2.2, height=10.5, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations((0, 0, z_collar)):
            Cone(bottom_radius=R_INNER - TOL - 2.2, top_radius=3.0, height=L_CONE + 0.5, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        with Locations((0, 0, z_cone_end - 0.5)):
            Cylinder(radius=3.0, height=L_TIP - 4.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # Precision circular seat for Ø 8.0 mm MEMS Tip PCB (wall = 5.6 - 4.15 = 1.45 mm > 1.2 mm)
        with Locations((0, 0, z_tip_end - 5.2)):
            Cylinder(radius=(TIP["diameter"] / 2.0) + 0.15, height=3.4, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # Calibrated front acoustic port (front cap thickness = 1.8 mm > 1.2 mm, sturdy ribs >= 1.2 mm)
        with Locations((0, 0, z_tip_end - 2.6)):
            Cylinder(radius=1.0, height=3.5, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        for angle in (0, 90):
            with Locations((0, 0, z_tip_end - 0.5)):
                Box(7.2, 1.0, 1.0, rotation=(0, 0, angle), mode=Mode.SUBTRACT)

    return p.part


def build_rear_cap():
    """Constructs the Stage 2 dual-output rear cap (XLR-3M + RJ45 MagJack).

    Returns:
        ``build123d`` solid representing the dual-port rear cap.
    """
    rj = PCB["rj45_magjack"]
    xlr = PCB["xlr_3m"]
    with BuildPart() as p:
        # Chamfered outer rear flange (Z: -5 -> 0)
        with Locations((0, 0, -5.0)):
            Cone(bottom_radius=R_BODY - 1.2, top_radius=R_BODY, height=2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, 0, -3.0)):
            Cylinder(radius=R_BODY, height=3.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        # Slip-fit collar into body_main (Z: 0 -> 7)
        with Locations((0, 0, 0.0)):
            Cylinder(radius=R_INNER - TOL, height=7.0, align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Cutout 1: XLR-3M Balanced Analog Output (Y = +8.0 mm, Ø 19.4 mm)
        with Locations((0, xlr["y_offset_in_cap"], -6.0)):
            Cylinder(
                radius=(xlr["diameter"] / 2.0) + 0.2,
                height=15.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

        # Cutout 2: RJ45 MagJack PoE (Y = -9.5 mm, 16.6 x 14.2 mm)
        with Locations((0, rj["y_offset_in_cap"], -6.0)):
            Box(
                rj["width"] + 0.6,
                rj["height"] + 0.6,
                15.0,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )
    return p.part


def build_rear_cap_stage1():
    """Constructs the Stage 1 rear cap with a centered RJ45 cutout only (no XLR).

    Returns:
        ``build123d`` solid representing the Stage 1 rear cap.
    """
    rj = PCB["rj45_magjack"]
    with BuildPart() as p:
        with Locations((0, 0, -5.0)):
            Cone(bottom_radius=R_BODY - 1.2, top_radius=R_BODY, height=2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, 0, -3.0)):
            Cylinder(radius=R_BODY, height=3.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, 0, 0.0)):
            Cylinder(radius=R_INNER - TOL, height=7.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        # Centered RJ45 MagJack cutout for Stage 1 Main PCB
        with Locations((0, 0, -6.0)):
            Box(rj["width"] + 0.6, rj["height"] + 0.6, 15.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    return p.part


def build_xlr_hardware():
    """Realistic 3-pin Gold XLR-3M shroud + 3 pins inside the Rear Cap."""
    xlr = PCB["xlr_3m"]
    cy = xlr["y_offset_in_cap"]
    with BuildPart() as p:
        # Recessed XLR barrel ring
        with Locations((0, cy, -5.0)):
            Cylinder(radius=9.5, height=11.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, cy, -5.5)):
            Cylinder(radius=7.8, height=9.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        # 3 standard XLR-3M male pins (Pin 1 GND, Pin 2 Hot, Pin 3 Cold)
        pin_coords = [(-3.6, cy + 1.5), (3.6, cy + 1.5), (0.0, cy - 3.6)]
        for px, py in pin_coords:
            with Locations((px, py, -3.2)):
                Cylinder(radius=0.95, height=7.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return p.part


def build_serigraphy():
    """Real 3D extruded serigraphy: 'IU-MIC' on front + all port names on side & rear."""
    with BuildPart() as p:
        # 1. FRONT BRANDING (+Y flat face): "IU-MIC" + "ORIGIN · 1Hz-90kHz"
        front_plane = Plane(origin=(0, FLAT_FRONT_Y, L_BODY / 2.0 + 4.0), x_dir=(0, 0, -1), z_dir=(0, 1, 0))
        with BuildSketch(front_plane):
            Text("IU-MIC", font_size=8.8, font_style=FontStyle.BOLD, align=(Align.CENTER, Align.CENTER))
        extrude(amount=0.45)

        front_sub = Plane(origin=(0, FLAT_FRONT_Y, L_BODY / 2.0 + 4.0), x_dir=(0, 0, -1), z_dir=(0, 1, 0))
        with BuildSketch(front_sub):
            with Locations((0, -6.4)):
                Text("ORIGIN  1Hz-90kHz", font_size=2.7, font_style=FontStyle.REGULAR, align=(Align.CENTER, Align.CENTER))
        extrude(amount=0.35)

        # 2. SIDE PORT LABELS (+X control bezel, aligned beside each cutout at Y = +3.8 mm)
        side_labels = [
            (PCB_Z0 + PCB["usb_c"]["y_from_rear"], "USB-C"),
            (PCB_Z0 + PCB["switch_hpf"]["y_from_rear"], "HPF 20Hz"),
            (PCB_Z0 + PCB["switch_lpf"]["y_from_rear"], "LPF 20kHz"),
            (PCB_Z0 + PCB["status_led"]["y_from_rear"], "STATUS"),
        ]
        for z_pos, label in side_labels:
            side_plane = Plane(origin=(FLAT_SIDE_X, 3.8, z_pos), x_dir=(0, 0, -1), z_dir=(1, 0, 0))
            with BuildSketch(side_plane):
                Text(label, font_size=2.5, font_style=FontStyle.BOLD, align=(Align.CENTER, Align.CENTER))
            extrude(amount=0.35)

        # 3. REAR CAP PORT LABELS (-Z face): "XLR OUT" & "PoE / AoIP"
        rear_xlr_plane = Plane(origin=(0, 18.6, -5.0), x_dir=(-1, 0, 0), z_dir=(0, 0, -1))
        with BuildSketch(rear_xlr_plane):
            Text("XLR OUT", font_size=2.2, font_style=FontStyle.BOLD, align=(Align.CENTER, Align.CENTER))
        extrude(amount=0.35)

        rear_poe_plane = Plane(origin=(0, -17.6, -5.0), x_dir=(-1, 0, 0), z_dir=(0, 0, -1))
        with BuildSketch(rear_poe_plane):
            Text("PoE / AoIP", font_size=2.1, font_style=FontStyle.BOLD, align=(Align.CENTER, Align.CENTER))
        extrude(amount=0.35)

    return p.part


def build_main_pcb_3d():
    """Builds a simplified 3D reference solid of the 4-layer Main PCB assembly.

    Returns:
        ``build123d`` solid representing the Main PCB with major IC/connector envelopes.
    """
    rj = PCB["rj45_magjack"]
    with BuildPart() as p:
        with Locations((0, 0, PCB_Z0)):
            Box(PCB["width"], PCB["thickness"], PCB["length"], align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, rj["y_offset_in_cap"], PCB_Z0)):
            Box(rj["width"], rj["height"], rj["depth"], align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, PCB["thickness"] / 2.0, PCB_Z0 + 50.5)):
            Box(14.0, 1.6, 14.0, align=(Align.CENTER, Align.MIN, Align.CENTER))
        with Locations((-1.5, PCB["thickness"] / 2.0, PCB_Z0 + 73.0)):
            Box(7.0, 1.1, 7.0, align=(Align.CENTER, Align.MIN, Align.CENTER))
    return p.part


def build_mems_tip_pcb_3d():
    """Builds a simplified 3D reference solid of the circular Ø 8.0 mm MEMS Tip PCB.

    Returns:
        ``build123d`` solid representing the MEMS daughterboard and capsule envelope.
    """
    z_seat = L_BODY + 3.0 + L_CONE + L_TIP - 4.8
    with BuildPart() as p:
        with Locations((0, 0, z_seat)):
            Cylinder(radius=TIP["diameter"] / 2.0, height=TIP["thickness"], align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((0, 0, z_seat + TIP["thickness"])):
            Box(4.0, 3.0, 1.2, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return p.part


def export_part_all(part, stem: str, rgba: list[int], export_step_flag: bool = True):
    """Exports a part to STL, GLB (vertex-colored), and optionally STEP.

    Args:
        part: ``build123d`` solid to export.
        stem: Output filename stem without extension.
        rgba: 4-element ``[R, G, B, A]`` face color list (0..255) for GLB preview.
        export_step_flag: Whether to also write a B-rep ``.step`` file.

    Returns:
        Loaded ``trimesh.Trimesh`` object for assembly composition and validation.
    """
    step_path = OUT_3D / f"{stem}.step"
    stl_path = OUT_3D / f"{stem}.stl"
    glb_path = OUT_3D / f"{stem}.glb"

    if export_step_flag:
        export_step(part, str(step_path))
    export_stl(part, str(stl_path), tolerance=0.05)

    mesh = trimesh.load(stl_path, force="mesh")
    mesh.visual.face_colors = np.tile(rgba, (len(mesh.faces), 1))
    mesh.export(glb_path)
    return mesh


def main():
    """Generates all IU-MIC_ORIGIN 3D parts, assemblies, and JLCPCB STL archives."""
    body = build_body_main()
    nose = build_nose_cone()
    cap = build_rear_cap()
    serig = build_serigraphy()
    xlr_hw = build_xlr_hardware()
    main_pcb = build_main_pcb_3d()
    tip_pcb = build_mems_tip_pcb_3d()

    parts = [
        ("IU-MIC_ORIGIN_body_main", body, [44, 48, 56, 255], True),
        ("IU-MIC_ORIGIN_nose_cone", nose, [52, 58, 68, 255], True),
        ("IU-MIC_ORIGIN_rear_cap", cap, [35, 39, 46, 255], True),
        ("IU-MIC_ORIGIN_serigraphy", serig, [226, 232, 240, 255], False),
        ("IU-MIC_ORIGIN_xlr_hardware", xlr_hw, [212, 175, 55, 255], False),
        ("IU-MIC_ORIGIN_main_pcb", main_pcb, [15, 118, 110, 255], False),
        ("IU-MIC_ORIGIN_mems_tip_pcb", tip_pcb, [20, 184, 166, 255], False),
    ]

    scene = trimesh.Scene()
    summary = {}
    for stem, part, rgba, do_step in parts:
        mesh = export_part_all(part, stem, rgba, do_step)
        scene.add_geometry(mesh, node_name=stem, geom_name=stem)
        summary[stem] = {
            "watertight": bool(mesh.is_watertight),
            "extents_mm": [round(float(v), 2) for v in mesh.extents],
            "volume_mm3": round(float(mesh.volume), 1),
        }

    # Export full colored assembly GLB + full B-rep assembly STEP
    scene.export(OUT_3D / "IU-MIC_ORIGIN_assembly.glb")
    assembly_compound = Compound(children=[body, nose, cap, serig, xlr_hw, main_pcb, tip_pcb])
    export_step(assembly_compound, str(OUT_3D / "IU-MIC_ORIGIN_assembly.step"))

    # JLCPCB 3D Printing Compliant ZIP: ONLY the 3 printable enclosure STL parts
    # (STL Recommended, Wall thickness > 1.2mm, Thinnest feature >= 0.8mm, Watertight, zero macOS ._ files)
    printable_stls = [
        "IU-MIC_ORIGIN_body_main.stl",
        "IU-MIC_ORIGIN_nose_cone.stl",
        "IU-MIC_ORIGIN_rear_cap.stl",
    ]
    zip_path = OUT_3D / "IU-MIC_ORIGIN_JLCPCB_3DPrint_STL.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in printable_stls:
            p = OUT_3D / fname
            if p.is_file():
                zf.write(p, p.name)

    cap_s1 = build_rear_cap_stage1()
    export_part_all(cap_s1, "IU-MIC_ORIGIN_rear_cap_stage1", [35, 39, 46, 255], True)

    # JLCPCB 3D Printing Compliant ZIP (Stadio 1): ONLY the 3 printable Stadio-1 STL parts (RJ45-only rear cap!)
    zip_s1 = OUT_3D / "IU-MIC_ORIGIN_Stage1_JLCPCB_3DPrint_STL.zip"
    with zipfile.ZipFile(zip_s1, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ("IU-MIC_ORIGIN_body_main.stl", "IU-MIC_ORIGIN_nose_cone.stl", "IU-MIC_ORIGIN_rear_cap_stage1.stl"):
            p = OUT_3D / fname
            if p.is_file():
                zf.write(p, p.name)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
