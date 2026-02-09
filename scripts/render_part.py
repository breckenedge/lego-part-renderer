"""
Render an LDraw part as an SVG line drawing using Blender Freestyle.

Usage:
    blender --background --python render_part.py -- <input.dat> <output.svg> [ldraw_path] [thickness]

Arguments:
    input.dat    Path to the LDraw .dat part file
    output.svg   Path for the output SVG file
    ldraw_path   Path to LDraw library root (default: /usr/share/ldraw/ldraw)
    thickness    Line thickness in pixels (default: 2.0)
"""

import bpy
import addon_utils
import sys
import os
import mathutils
from math import radians, atan, sqrt


def parse_args():
    argv = sys.argv
    if "--" not in argv:
        print("Usage: blender --background --python render_part.py -- <input.dat> <output.svg> [ldraw_path] [thickness]")
        sys.exit(1)

    argv = argv[argv.index("--") + 1:]
    if len(argv) < 2:
        print("Error: input and output paths required")
        sys.exit(1)

    return {
        "input_file": argv[0],
        "output_svg": argv[1],
        "ldraw_path": argv[2] if len(argv) > 2 else "/usr/share/ldraw/ldraw",
        "thickness": float(argv[3]) if len(argv) > 3 else 2.0,
    }


def clear_scene():
    """Remove all objects from the scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Also remove orphan data
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)
    for cam in bpy.data.cameras:
        bpy.data.cameras.remove(cam)


def import_ldraw_part(filepath, ldraw_path):
    """Import an LDraw part using the ImportLDraw addon."""
    bpy.ops.import_scene.importldraw(
        filepath=filepath,
        ldrawPath=ldraw_path,
        realScale=1.0,
        resPrims="Standard",
        smoothParts=True,
        look="normal",
        colourScheme="ldraw",
        addGaps=False,
        curvedWalls=True,
        importCameras=False,
        linkParts=True,
        positionOnGround=False,
        useUnofficialParts=True,
        useLogoStuds=False,
        bevelEdges=False,
        addEnvironment=False,
        positionCamera=False,
    )


def setup_camera(scene, padding=0.03):
    """Create an orthographic camera at an isometric angle, framed to fit all objects."""
    cam_data = bpy.data.cameras.new("IsoCam")
    cam_data.type = 'ORTHO'
    cam_data.clip_start = 0.0001  # Tiny clip_start for small LDraw parts
    cam_data.clip_end = 100000

    cam_obj = bpy.data.objects.new("IsoCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # Isometric rotation: 30 deg latitude, 45 deg longitude
    # (matching the existing three.js renderer angles)
    lat = radians(30)
    lon = radians(45)

    # Gather bounding box of all mesh objects
    all_corners = []
    for obj in scene.objects:
        if obj.type == 'MESH':
            for corner in obj.bound_box:
                all_corners.append(obj.matrix_world @ mathutils.Vector(corner))

    if not all_corners:
        print("Warning: no mesh objects found for camera framing")
        return

    xs = [c.x for c in all_corners]
    ys = [c.y for c in all_corners]
    zs = [c.z for c in all_corners]
    center = mathutils.Vector((
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        (min(zs) + max(zs)) / 2,
    ))
    size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    # Position camera along isometric direction
    import math
    dir_x = math.cos(lat) * math.sin(lon)
    dir_y = -math.cos(lat) * math.cos(lon)
    dir_z = math.sin(lat)
    direction = mathutils.Vector((dir_x, dir_y, dir_z)).normalized()
    distance = size * 5
    cam_obj.location = center + direction * distance

    # Point camera at center using track constraint
    track = cam_obj.constraints.new(type='TRACK_TO')
    # Create an empty at the center to track
    empty = bpy.data.objects.new("CamTarget", None)
    empty.location = center
    scene.collection.objects.link(empty)
    track.target = empty
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    # Update to apply constraint
    bpy.context.view_layer.update()

    # Now compute ortho_scale by projecting corners into camera view space
    cam_matrix_inv = cam_obj.matrix_world.inverted()
    min_vx = float('inf')
    max_vx = float('-inf')
    min_vy = float('inf')
    max_vy = float('-inf')
    for corner in all_corners:
        v = cam_matrix_inv @ corner
        min_vx = min(min_vx, v.x)
        max_vx = max(max_vx, v.x)
        min_vy = min(min_vy, v.y)
        max_vy = max(max_vy, v.y)

    ext_x = max_vx - min_vx
    ext_y = max_vy - min_vy

    aspect = scene.render.resolution_x / scene.render.resolution_y
    # ortho_scale controls vertical extent in Blender
    scale = max(ext_x / aspect, ext_y) / (1 - 2 * padding)
    cam_data.ortho_scale = scale

    # Shift camera to center the object in view
    # For ortho cameras: width = ortho_scale * aspect, height = ortho_scale
    center_vx = (min_vx + max_vx) / 2
    center_vy = (min_vy + max_vy) / 2
    cam_data.shift_x = -center_vx / (scale * aspect)
    cam_data.shift_y = -center_vy / scale


def setup_freestyle(scene, thickness):
    """Configure Freestyle for clean line drawing output."""
    scene.render.use_freestyle = True

    view_layer = bpy.context.view_layer
    fs_settings = view_layer.freestyle_settings
    fs_settings.mode = 'EDITOR'
    fs_settings.crease_angle = radians(135)

    # Clear existing linesets
    while len(fs_settings.linesets) > 0:
        fs_settings.linesets.remove(fs_settings.linesets[0])

    # Create lineset with edge types for clean technical drawing
    lineset = fs_settings.linesets.new("Edges")
    lineset.select_silhouette = True
    lineset.select_crease = True
    lineset.select_border = True
    lineset.select_contour = False
    lineset.select_external_contour = False
    lineset.select_edge_mark = False
    lineset.select_material_boundary = False
    lineset.visibility = 'VISIBLE'
    lineset.edge_type_combination = 'OR'
    lineset.edge_type_negation = 'INCLUSIVE'

    # Line style: black lines at specified thickness
    ls = lineset.linestyle
    ls.thickness = thickness
    ls.color = (0.0, 0.0, 0.0)
    ls.alpha = 1.0
    ls.thickness_position = 'CENTER'


def setup_svg_export(scene, lineset):
    """Configure the Freestyle SVG Exporter addon."""
    scene.svg_export.use_svg_export = True
    scene.svg_export.mode = 'FRAME'
    scene.svg_export.object_fill = False
    scene.svg_export.split_at_invisible = False
    scene.svg_export.line_join_type = 'ROUND'

    # Per-linestyle export settings
    ls = lineset.linestyle
    ls.use_export_strokes = True
    ls.use_export_fills = False


def main():
    args = parse_args()

    # Enable addons
    addon_utils.enable("ImportLDraw")
    addon_utils.enable("render_freestyle_svg", default_set=True, persistent=True)

    scene = bpy.context.scene

    # Clear default scene
    clear_scene()

    # Import LDraw part
    print(f"Importing {args['input_file']}...")
    import_ldraw_part(args["input_file"], args["ldraw_path"])

    # Make any collection instances into real geometry, join all meshes,
    # and recalculate normals — required for Freestyle to detect edges
    # on all ImportLDraw-imported parts.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.duplicates_make_real()
    bpy.ops.object.select_all(action='DESELECT')
    meshes = [o for o in scene.objects if o.type == 'MESH']
    for o in meshes:
        o.select_set(True)
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
        if len(meshes) > 1:
            bpy.ops.object.join()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')

    obj = bpy.context.active_object
    if obj and obj.type == 'MESH':
        print(f"Mesh: {len(obj.data.vertices)} verts, {len(obj.data.polygons)} faces")

    # Set all materials to white for line-drawing look
    for obj in scene.objects:
        if obj.type == 'MESH':
            for slot in obj.material_slots:
                if slot.material:
                    slot.material.diffuse_color = (1.0, 1.0, 1.0, 1.0)

    # Configure render settings
    # Use Cycles (CPU) — EEVEE requires OpenGL which isn't available in WSL2 headless
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 1  # Minimal samples since we only need Freestyle lines
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.film_transparent = True

    # Setup camera
    setup_camera(scene)

    # Setup Freestyle
    setup_freestyle(scene, args["thickness"])

    # Setup SVG export
    fs_settings = bpy.context.view_layer.freestyle_settings
    lineset = fs_settings.linesets["Edges"]
    setup_svg_export(scene, lineset)

    # Set output path - SVG exporter derives from render.filepath
    output_svg = os.path.abspath(args["output_svg"])
    output_dir = os.path.dirname(output_svg)
    output_base = os.path.splitext(os.path.basename(output_svg))[0]
    os.makedirs(output_dir, exist_ok=True)

    scene.render.filepath = os.path.join(output_dir, output_base)

    # Render (triggers SVG export as side-effect)
    print("Rendering...")
    bpy.ops.render.render(write_still=False)

    # SVG exporter writes to <filepath>0001.svg
    expected_svg = os.path.join(output_dir, f"{output_base}0001.svg")
    if os.path.exists(expected_svg):
        if expected_svg != output_svg:
            os.rename(expected_svg, output_svg)
        print(f"SVG written to: {output_svg}")
    else:
        print(f"Error: expected SVG not found at {expected_svg}")
        # List files in output dir for debugging
        for f in os.listdir(output_dir):
            print(f"  {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
