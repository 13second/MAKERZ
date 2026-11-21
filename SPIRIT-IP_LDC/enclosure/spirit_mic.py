#!/usr/bin/env python3
"""Parametric 3D mechanical enclosure generator for SPIRIT-IP_LDC v1.2.1.

Builds all printable enclosure parts and internal reference models using
``build123d`` from the shared ``dimensions.json`` single-source-of-truth file,
validates mesh watertightness and single-shell integrity via ``trimesh``, and
exports STEP, STL, GLB, and a JLC3DP-ready STL archive.

Revision v1.2.1 DFM & tolerance summary:
    * TPU shock-mount: 12.6 mm width (1.3 mm retaining lips), dedicated
      5.0 x 7.0 mm wire pass-through slot (2.8 mm side bridges), and three
      5.0 mm damping pads at -22/0/+22 deg with 0.3 mm radial preload.
    * Clear 8001 body / 316L metal grille interface: shoulder R = 25.30 mm,
      collar ID R = 25.55 mm (0.25 mm radial clearance per side).
    * Headamp centering lips: 1.40 mm radial thickness (R = 18.2..19.6 mm).
"""

import json
import math
import zipfile
from pathlib import Path
from typing import Any

import trimesh
from build123d import Box, Compound, Cylinder, Pos, Rot, export_step, export_stl

ROOT = Path(__file__).resolve().parent.parent
DIM = json.loads((ROOT / "dimensions.json").read_text(encoding="utf-8"))
OUT_3D = ROOT / "exports" / "3d"
OUT_3D.mkdir(parents=True, exist_ok=True)

ENC = DIM["enclosure"]
SAD = ENC["saddle"]
RAIL = ENC["rails"]
TPU = ENC["tpu"]

R_OUT = ENC["outer_diameter_mm"] / 2.0
WALL = ENC["wall_thickness_mm"]
R_IN = R_OUT - WALL
H_BODY = ENC["body_height_mm"]
H_GRILLE = ENC["grille_height_mm"]
H_CAP = ENC["bottom_cap_height_mm"]
R_SHOULDER = ENC["body_shoulder_radius_mm"]                  # 25.30 mm
R_COLLAR_IN = ENC["grille_collar_inner_radius_mm"]           # 25.55 mm
LIP_RADIAL = ENC["headamp_lip_radial_mm"]                    # 1.40 mm

Z_CAPSULE = DIM["capsule"]["capsule_center_z_mm"]            # 146.0 mm
Z_BASE0, Z_BASE1 = SAD["base_z_mm"]                          # 116.5 / 120.5 mm
R_SADDLE = SAD["base_radius_mm"]                             # 23.85 mm
R_ARC = SAD["cradle_arc_radius_mm"]                          # 18.5 mm
Z_HORN = SAD["cradle_horn_top_z_mm"]                         # 149.5 mm
R_CAPSULE = DIM["capsule"]["diameter_mm"] / 2.0              # 17.0 mm
T_CAPSULE = DIM["capsule"]["thickness_mm"]                   # 10.0 mm
Z_HP0, Z_HP1 = DIM["pcbs"]["headamp_2l"]["z_mm"]             # 110.2 / 111.8 mm
H_SH1 = DIM["pcbs"]["headamp_2l"]["shield_can_height_mm"]    # 3.6 mm
SLOT_X, SLOT_Y = SAD["wire_slot_xy_mm"]
SLOT_W, SLOT_L = SAD["wire_slot_wh_mm"]                      # 6.0 x 9.0 mm
TPU_THICK = SAD["shockmount_tpu_thickness_mm"]               # 1.5 mm
TPU_W = TPU["width_mm"]                                      # 12.6 mm
TPU_LIP = TPU["lip_mm"]                                      # 1.3 mm
TPU_WIN_W, TPU_WIN_L = TPU["window_wh_mm"]                   # 5.0 x 7.0 mm
TPU_PADS_DEG = TPU["pads_deg"]                               # [-22, 0, 22]
TPU_PAD_W = TPU["pad_width_mm"]                              # 5.0 mm
TPU_PRELOAD = TPU["preload_mm"]                              # 0.3 mm


def box(sx: float, sy: float, sz: float, x: float, y: float, z: float, rz: float = 0.0) -> Any:
    """Creates a positioned and Z-rotated box primitive.

    Args:
        sx: Box size along X in millimeters.
        sy: Box size along Y in millimeters.
        sz: Box size along Z in millimeters.
        x: Center X coordinate in millimeters.
        y: Center Y coordinate in millimeters.
        z: Center Z coordinate in millimeters.
        rz: Rotation around the Z axis in degrees.

    Returns:
        Positioned ``build123d`` solid box.
    """
    return Pos(x, y, z) * Rot(0, 0, rz) * Box(sx, sy, sz)


def polar_box(
    radial: float, tang: float, h: float, r_center: float, ang_deg: float, z_center: float
) -> Any:
    """Creates a box positioned in cylindrical polar coordinates.

    Args:
        radial: Radial thickness in millimeters.
        tang: Tangential width in millimeters.
        h: Axial height along Z in millimeters.
        r_center: Radial distance from the Z axis in millimeters.
        ang_deg: Azimuthal angle around the Z axis in degrees.
        z_center: Axial center Z coordinate in millimeters.

    Returns:
        Positioned and radially oriented ``build123d`` solid box.
    """
    a = math.radians(ang_deg)
    return Pos(r_center * math.cos(a), r_center * math.sin(a), z_center) * Rot(0, 0, ang_deg) * Box(radial, tang, h)


def wire_slot(h: float, z_center: float, w: float = SLOT_W, l: float = SLOT_L) -> Any:
    """Builds a stadium-shaped wire pass-through slot centered over J_CAP.

    Args:
        h: Extrusion height along Z in millimeters.
        z_center: Center Z coordinate in millimeters.
        w: Slot width along X in millimeters.
        l: Total slot length along Y in millimeters.

    Returns:
        Solid stadium geometry suitable for boolean subtraction.
    """
    straight = l - w
    s = Pos(SLOT_X, SLOT_Y, z_center) * Box(w, straight, h)
    for sy in (-straight / 2.0, straight / 2.0):
        s = s + Pos(SLOT_X, SLOT_Y + sy, z_center) * Cylinder(radius=w / 2.0, height=h)
    return s


def make_body_clear() -> Any:
    """Constructs the translucent 8001 resin main cylindrical microphone body.

    Includes the upper grille mating shoulder, internal capsule-saddle seating
    step with three asymmetric anti-rotation keys, dual Main PCB guide rails,
    four Headamp support shelves with centering lips, and three front switch
    recess cutouts.

    Returns:
        ``build123d`` solid representing the clear main body.
    """
    z0, z1 = H_CAP, H_BODY
    body = Pos(0, 0, (z0 + z1) / 2) * Cylinder(radius=R_OUT, height=z1 - z0)
    body = body - Pos(0, 0, (z0 + z1) / 2) * Cylinder(radius=R_IN, height=z1 - z0 + 2.0)

    # Upper mating shoulder for the 316L grille (R_IN -> R_SHOULDER = 25.30 mm, 1.30 mm wall)
    shoulder = Pos(0, 0, H_BODY + 2.5) * Cylinder(radius=R_SHOULDER, height=5.0)
    shoulder = shoulder - Pos(0, 0, H_BODY + 2.5) * Cylinder(radius=R_IN, height=6.0)
    body = body + shoulder

    # Internal saddle seating step (top Z = 116.5 mm, inner R = 21.5 mm) fused into the wall
    z_step0, z_step1 = H_BODY - 1.0, SAD["step_top_z_mm"]
    step = Pos(0, 0, (z_step0 + z_step1) / 2) * Cylinder(radius=R_IN + 1.0, height=z_step1 - z_step0)
    step = step - Pos(0, 0, (z_step0 + z_step1) / 2) * Cylinder(
        radius=SAD["step_inner_radius_mm"], height=z_step1 - z_step0 + 1.0
    )
    body = body + step

    # Three asymmetric anti-rotation keys rising from the saddle step
    for ang in SAD["keys_deg"]:
        body = body + polar_box(2.4, 3.0, 3.5, R_IN - 1.0, ang, SAD["step_top_z_mm"] + 1.75)

    # Main PCB guide rails fused into the inner wall with inward-facing grooves
    rz0, rz1 = RAIL["z_range_mm"]
    rx0, rx1 = RAIL["x_range_mm"]
    gx0, gx1 = RAIL["groove_x_mm"]
    for s in (-1, 1):
        rail = box(rx1 - rx0, RAIL["y_width_mm"], rz1 - rz0, s * (rx0 + rx1) / 2, 0, (rz0 + rz1) / 2)
        groove = box(
            (gx1 - gx0) + 0.5,
            RAIL["groove_y_mm"],
            rz1 - rz0 + 2.0,
            s * ((gx0 - 0.5 + gx1) / 2),
            0,
            (rz0 + rz1) / 2,
        )
        body = body + rail
        body = body - groove

    # Four Headamp support shelves + radial centering lips (inner R = 18.2 mm, thickness = 1.40 mm)
    for ang in SAD["feet_deg"]:
        body = body + polar_box(R_IN + 0.6 - 16.4, 4.0, 2.5, (16.4 + R_IN + 0.6) / 2, ang, Z_HP0 - 1.25)
        body = body + polar_box(LIP_RADIAL, 5.0, 1.4, SAD["shelf_lip_radius_mm"] + LIP_RADIAL / 2.0, ang, Z_HP0 + 0.7)

    # Three Aston-style recessed switch cutouts on the +Y face
    for sw in ENC["switch_slots"]:
        body = body - Pos(0, R_OUT - 1.0, sw["z_mm"]) * Box(sw["w_mm"], 8.0, sw["h_mm"])
    return body


def make_grille_316l() -> Any:
    """Constructs the 316L stainless steel protective headbasket grille.

    Vertical ribs start above the base collar (Z = 120 mm) to avoid interfering
    with the clear body shoulder.

    Returns:
        ``build123d`` solid representing the 316L metal grille.
    """
    z_top = H_BODY + H_GRILLE - 4.0
    g = Pos(0, 0, H_BODY + 3.0) * Cylinder(radius=R_OUT, height=6.0)
    g = g - Pos(0, 0, H_BODY + 3.0) * Cylinder(radius=R_COLLAR_IN, height=7.0)
    crown = Pos(0, 0, z_top) * Cylinder(radius=R_OUT - 1.5, height=6.0)
    crown = crown - Pos(0, 0, z_top) * Cylinder(radius=R_IN - 2.5, height=7.0)
    g = g + crown
    for ang in (0, 45, 90, 135):
        g = g + Pos(0, 0, z_top + 1.5) * Rot(0, 0, ang) * Box(R_OUT * 1.85, 2.4, 2.4)

    # Vertical ribs start above the collar (Z = 120 mm) to clear the body shoulder
    rib_z0, rib_z1 = H_BODY + 6.0, z_top + 1.0
    for k in range(12):
        a = 360.0 * k / 12
        g = g + polar_box(2.4, 2.2, rib_z1 - rib_z0, R_OUT - 1.4, a, (rib_z0 + rib_z1) / 2.0)

    # Three horizontal stiffening rings
    for z_ring in (H_BODY + 18.0, H_BODY + 34.0, H_BODY + 50.0):
        ring = Pos(0, 0, z_ring) * Cylinder(radius=R_OUT - 0.3, height=2.6)
        ring = ring - Pos(0, 0, z_ring) * Cylinder(radius=R_OUT - 2.6, height=3.2)
        g = g + ring
    return g


def make_bottom_cap() -> Any:
    """Constructs the dual-port bottom cap with RJ45, USB-C, and 5/8"-27 mount cutouts.

    Returns:
        ``build123d`` solid representing the bottom end cap.
    """
    ports = ENC["bottom_ports"]
    cap = Pos(0, 0, H_CAP / 2.0) * Cylinder(radius=R_OUT, height=H_CAP)
    lip = Pos(0, 0, H_CAP + 2.5) * Cylinder(radius=R_IN - 0.15, height=5.0)
    lip = lip - Pos(0, 0, H_CAP + 2.5) * Cylinder(radius=R_IN - 3.0, height=6.0)
    cap = cap + lip
    cap = cap - Pos(0, 0, 3.5 + (H_CAP - 3.5) / 2.0) * Cylinder(radius=R_IN - 3.0, height=H_CAP - 3.0)

    tx, ty = ports["thread_insert_5_8_offset_xy_mm"]
    cap = cap - Pos(tx, ty, H_CAP / 2.0) * Cylinder(
        radius=ports["thread_insert_5_8_diameter_mm"] / 2.0, height=H_CAP + 8.0
    )
    rx, ry = ports["rj45_offset_xy_mm"]
    rw, rh = ports["rj45_cutout_wh_mm"]
    cap = cap - Pos(rx, ry, H_CAP / 2.0) * Box(rw, rh, H_CAP + 8.0)

    ux, uy = ports["usbc_offset_xy_mm"]
    uw, uh = ports["usbc_cutout_wh_mm"]
    cap = cap - Pos(ux, uy, H_CAP / 2.0) * Box(uw, uh, H_CAP + 8.0)
    return cap


def make_capsule_saddle() -> Any:
    """Constructs the rigid 34 mm capsule saddle.

    Combines a solid base plate (Z = 116.5..120.5 mm) with anti-rotation keyways,
    a rigid cradle arc (R = 18.5 mm centered at Z = 146 mm), four lower Headamp
    clamping feet, and a post-union J_CAP wire pass-through slot.

    Returns:
        ``build123d`` solid representing the capsule saddle.
    """
    zb = (Z_BASE0 + Z_BASE1) / 2.0
    s = Pos(0, 0, zb) * Cylinder(radius=R_SADDLE, height=Z_BASE1 - Z_BASE0)

    # Three outward-facing keyways mating with the body anti-rotation keys
    for ang in SAD["keys_deg"]:
        s = s - polar_box(2.9 + 1.0, 3.5, Z_BASE1 - Z_BASE0 + 1.0, R_IN - 1.0 + 0.5, ang, zb)

    # Cradle block spanning X = +-22 mm, Y = +-7 mm, carved with R = 18.5 mm Y-axis cylinder
    zc0, zc1 = Z_BASE1 - 0.5, Z_HORN
    cradle = Pos(0, 0, (zc0 + zc1) / 2) * Box(44.0, 14.0, zc1 - zc0)
    s = s + cradle
    s = s - Pos(0, 0, Z_CAPSULE) * Rot(90, 0, 0) * Cylinder(radius=R_ARC, height=20.0)

    # Four lower feet clamping the Headamp PCB (Z = 116.5 -> 112.0 mm)
    f0, f1 = SAD["feet_z_mm"]
    fr0, fr1 = SAD["feet_radius_mm"]
    for ang in SAD["feet_deg"]:
        s = s + polar_box(fr1 - fr0, 3.0, f1 - f0 + 0.5, (fr0 + fr1) / 2, ang, (f0 + f1) / 2 + 0.25)

    # Cut wire slot after cradle union to ensure an unobstructed passage
    s = s - wire_slot(Z_HORN - f0 + 6.0, (Z_HORN + f0) / 2)
    return s


def make_capsule_shockmount_tpu() -> Any:
    """Constructs the 1.5 mm TPU/silicone capsule shock-mount liner.

    Features a 12.6 mm total width (1.3 mm retaining lips), three 5.0 mm damping
    pads at -22/0/+22 deg with 0.3 mm radial preload, and a dedicated 5.0 x 7.0 mm
    wire pass-through window.

    Returns:
        ``build123d`` solid representing the flexible shock-mount insert.
    """
    r_i = R_ARC - TPU_THICK
    zc = Z_CAPSULE
    ring = Pos(0, 0, zc) * Rot(90, 0, 0) * Cylinder(radius=R_ARC, height=TPU_W)
    ring = ring - Pos(0, 0, zc) * Rot(90, 0, 0) * Cylinder(radius=r_i, height=T_CAPSULE)          # Core +-5.0 mm
    ring = ring - Pos(0, 0, zc) * Rot(90, 0, 0) * Cylinder(radius=r_i - 1.2, height=TPU_W + 4.0)  # Retaining lips R 15.8..18.5 mm

    # Three damping pads (5.0 mm tangential width, 0.3 mm radial preload toward capsule)
    pad_radial = 2.0 * TPU_PRELOAD
    for th in TPU_PADS_DEG:
        a = math.radians(th)
        px = r_i * math.sin(a)
        pz = zc - r_i * math.cos(a)
        ring = ring + Pos(px, 0, pz) * Rot(0, -th, 0) * Box(TPU_PAD_W, 8.0, pad_radial)

    # Trim above the saddle cradle horns
    ring = ring - Pos(0, 0, Z_HORN + 10.0) * Box(60.0, 20.0, 20.0)

    # Dedicated 5.0 x 7.0 mm wire window (2.8 mm side bridges)
    ring = ring - wire_slot(40.0, zc - 12.0, w=TPU_WIN_W, l=TPU_WIN_L)
    return ring


def make_ref_parts() -> tuple[Any, Any, Any, Any]:
    """Creates non-printable reference solids for interference checks and 3D preview.

    Returns:
        Tuple of ``(capsule, main_pcb, headamp_pcb, shield_can_sh1)`` solids.
    """
    cap = Pos(0, 0, Z_CAPSULE) * Rot(90, 0, 0) * Cylinder(radius=R_CAPSULE, height=T_CAPSULE)
    mpcb = Pos(0, 0, 14.0 + 47.0) * Box(38.0, 1.6, 94.0)
    hpcb = Pos(0, 0, (Z_HP0 + Z_HP1) / 2) * Cylinder(radius=18.0, height=Z_HP1 - Z_HP0)
    sh1 = Pos(0, 0, Z_HP1 + H_SH1 / 2) * Box(16.5, 16.5, H_SH1)
    return cap, mpcb, hpcb, sh1


def save_part(part: Any, stem: str, check_watertight: bool = True) -> Path:
    """Exports a single CAD part to STL, STEP, and GLB and checks mesh quality.

    Args:
        part: ``build123d`` solid to export.
        stem: Base filename without extension.
        check_watertight: When True, asserts that the STL mesh is watertight and
            consists of exactly one connected shell.

    Returns:
        Path to the exported STL file.
    """
    stl_p = OUT_3D / f"{stem}.stl"
    export_stl(part, str(stl_p))
    export_step(part, str(OUT_3D / f"{stem}.step"))
    mesh = trimesh.load(str(stl_p), force="mesh")
    mesh.export(str(OUT_3D / f"{stem}.glb"))
    ncomp = len(mesh.split(only_watertight=False))
    if check_watertight:
        assert mesh.is_watertight, f"{stl_p.name} is NOT watertight"
        assert ncomp == 1, f"{stl_p.name} has {ncomp} disconnected shells"
    print(f"  [OK] {stem}: watertight={mesh.is_watertight} comps={ncomp} vol={mesh.volume / 1000:.2f} cm3")
    return stl_p


def main() -> dict[str, Any]:
    """Generates all SPIRIT-IP_LDC enclosure parts, assemblies, and JLC3DP ZIP.

    Returns:
        Dictionary mapping part names to their generated ``build123d`` solids.
    """
    print("=== SPIRIT-IP_LDC v1.2.1 enclosure ===")
    body, grille, cap = make_body_clear(), make_grille_316l(), make_bottom_cap()
    saddle, tpu = make_capsule_saddle(), make_capsule_shockmount_tpu()
    cap_ref, mpcb_ref, hpcb_ref, sh1_ref = make_ref_parts()

    printed = []
    for part, stem, wt in [
        (body, "SPIRIT-IP_body_clear_8001", True),
        (grille, "SPIRIT-IP_grille_316L_metal", True),
        (cap, "SPIRIT-IP_bottom_cap_triple_port", True),
        (saddle, "SPIRIT-IP_capsule_saddle", True),
        (tpu, "SPIRIT-IP_capsule_shockmount_TPU", True),
        (cap_ref, "SPIRIT-IP_capsule_34mm", False),
        (mpcb_ref, "SPIRIT-IP_main_pcb", False),
        (hpcb_ref, "SPIRIT-IP_headamp_pcb", False),
        (sh1_ref, "SPIRIT-IP_headamp_shield_SH1", False),
    ]:
        p = save_part(part, stem, wt)
        if wt and "TPU" not in stem:
            printed.append(p)

    parts = [body, grille, cap, saddle, tpu, cap_ref, mpcb_ref, hpcb_ref, sh1_ref]
    asm = Compound(children=parts)
    export_step(asm, str(OUT_3D / "SPIRIT-IP_assembly.step"))
    export_stl(asm, str(OUT_3D / "SPIRIT-IP_assembly.stl"))
    trimesh.load(str(OUT_3D / "SPIRIT-IP_assembly.stl"), force="mesh").export(str(OUT_3D / "SPIRIT-IP_assembly.glb"))

    with zipfile.ZipFile(OUT_3D / "SPIRIT-IP_JLC3DP_3DPrint_STL.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        for p in printed:
            zf.write(p, p.name)
    print("JLC3DP ZIP updated (4 rigid parts; TPU shock-mount is shipped as a separate STL)")
    return dict(
        body=body,
        grille=grille,
        cap=cap,
        saddle=saddle,
        tpu=tpu,
        capsule=cap_ref,
        mpcb=mpcb_ref,
        hpcb=hpcb_ref,
        sh1=sh1_ref,
    )


if __name__ == "__main__":
    main()
