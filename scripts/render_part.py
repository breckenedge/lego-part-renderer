"""
Render an LDraw part as an SVG line drawing using Blender Freestyle.

Usage:
    blender --background --python render_part.py -- <input.dat> <output.svg> [ldraw_path] [thickness] \
        [fill_color] [camera_lat] [camera_lon] [res_x] [res_y] [padding] [crease_angle] [edge_types] \
        [fill_opacity]

Arguments:
    input.dat      Path to the LDraw .dat part file
    output.svg     Path for the output SVG file
    ldraw_path     Path to LDraw library root (default: /usr/share/ldraw/ldraw)
    thickness      Line thickness in pixels (default: 2.0)
    fill_color     Fill color for object shapes (default: currentColor)
    camera_lat     Camera latitude in degrees (default: 30)
    camera_lon     Camera longitude in degrees (default: 45)
    res_x          Render resolution width (default: 1024)
    res_y          Render resolution height (default: 1024)
    padding        Camera framing padding factor (default: 0.03)
    crease_angle   Freestyle crease angle in degrees (default: 135)
    edge_types     Comma-separated edge types (default: silhouette,crease,border)
    fill_opacity   Fill opacity 0.0-1.0 (default: 1.0); <1.0 enables hidden edge rendering
"""

import bpy
import addon_utils
import sys
import os
import re
import mathutils
import xml.etree.ElementTree as ET
from math import radians, atan, sqrt


def parse_args():
    argv = sys.argv
    if "--" not in argv:
        print("Usage: blender --background --python render_part.py -- <input.dat> <output.svg> [ldraw_path] [thickness] [fill_color] ...")
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
        "fill_color": argv[4] if len(argv) > 4 else "currentColor",
        "camera_lat": float(argv[5]) if len(argv) > 5 else 30.0,
        "camera_lon": float(argv[6]) if len(argv) > 6 else 45.0,
        "resolution_x": int(argv[7]) if len(argv) > 7 else 1024,
        "resolution_y": int(argv[8]) if len(argv) > 8 else 1024,
        "padding": float(argv[9]) if len(argv) > 9 else 0.03,
        "crease_angle": float(argv[10]) if len(argv) > 10 else 135.0,
        "edge_types": argv[11] if len(argv) > 11 else "silhouette,crease,border",
        "fill_opacity": float(argv[12]) if len(argv) > 12 else 1.0,
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


def setup_camera(scene, padding=0.03, camera_lat=30.0, camera_lon=45.0):
    """Create an orthographic camera at a given angle, framed to fit all objects."""
    cam_data = bpy.data.cameras.new("IsoCam")
    cam_data.type = 'ORTHO'
    cam_data.clip_start = 0.0001  # Tiny clip_start for small LDraw parts
    cam_data.clip_end = 100000

    cam_obj = bpy.data.objects.new("IsoCam", cam_data)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    lat = radians(camera_lat)
    lon = radians(camera_lon)

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


def setup_freestyle(scene, thickness, crease_angle=135.0, edge_types="silhouette,crease,border", fill_opacity=1.0):
    """Configure Freestyle for clean line drawing output."""
    scene.render.use_freestyle = True

    view_layer = bpy.context.view_layer
    fs_settings = view_layer.freestyle_settings
    fs_settings.mode = 'EDITOR'
    fs_settings.crease_angle = radians(crease_angle)

    # Clear existing linesets
    while len(fs_settings.linesets) > 0:
        fs_settings.linesets.remove(fs_settings.linesets[0])

    # Create lineset with edge types from configuration
    enabled = set(edge_types.split(",")) if edge_types != "none" else set()
    lineset = fs_settings.linesets.new("Edges")
    lineset.select_silhouette = "silhouette" in enabled
    lineset.select_crease = "crease" in enabled
    lineset.select_border = "border" in enabled
    lineset.select_contour = "contour" in enabled
    lineset.select_external_contour = "external_contour" in enabled
    lineset.select_edge_mark = "edge_mark" in enabled
    lineset.select_material_boundary = "material_boundary" in enabled
    lineset.select_by_visibility = True
    lineset.visibility = 'VISIBLE'
    lineset.edge_type_combination = 'OR'
    lineset.edge_type_negation = 'INCLUSIVE'

    # Line style: black lines at specified thickness
    ls = lineset.linestyle
    ls.thickness = thickness
    ls.color = (0.0, 0.0, 0.0)
    ls.alpha = 1.0
    ls.thickness_position = 'CENTER'

    # For transparent/translucent parts, add a second lineset for hidden (occluded) edges.
    # Hidden edges are dimmed proportionally to fill_opacity (seen through the material).
    # For fully transparent parts (fill_opacity=0), hidden edges are shown at full opacity.
    if fill_opacity < 1.0:
        hidden_lineset = fs_settings.linesets.new("HiddenEdges")
        hidden_lineset.select_silhouette = "silhouette" in enabled
        hidden_lineset.select_crease = "crease" in enabled
        hidden_lineset.select_border = "border" in enabled
        hidden_lineset.select_contour = "contour" in enabled
        hidden_lineset.select_external_contour = "external_contour" in enabled
        hidden_lineset.select_edge_mark = "edge_mark" in enabled
        hidden_lineset.select_material_boundary = "material_boundary" in enabled
        hidden_lineset.select_by_visibility = True
        hidden_lineset.visibility = 'HIDDEN'
        hidden_lineset.edge_type_combination = 'OR'
        hidden_lineset.edge_type_negation = 'INCLUSIVE'

        hls = hidden_lineset.linestyle
        hls.thickness = thickness
        hls.color = (0.0, 0.0, 0.0)
        # Fully transparent parts show hidden edges at full opacity;
        # translucent parts dim hidden edges to match the material's opacity.
        hls.alpha = 1.0 if fill_opacity == 0.0 else fill_opacity
        hls.thickness_position = 'CENTER'
        hls.use_export_strokes = True
        hls.use_export_fills = False


def setup_svg_export(scene, lineset):
    """Configure the Freestyle SVG Exporter addon."""
    scene.svg_export.use_svg_export = True
    scene.svg_export.mode = 'FRAME'
    scene.svg_export.object_fill = True
    scene.svg_export.split_at_invisible = False
    scene.svg_export.line_join_type = 'ROUND'

    # Per-linestyle export settings for visible edges
    ls = lineset.linestyle
    ls.use_export_strokes = True
    ls.use_export_fills = True


def postprocess_svg(svg_path, fill_color, fill_opacity=1.0):
    """Replace Blender's hardcoded colors with configurable values."""
    with open(svg_path, "r") as f:
        content = f.read()

    # Replace Blender's white fill (from white material) with the requested fill color
    content = re.sub(r'fill="rgb\(255,\s*255,\s*255\)"', f'fill="{fill_color}"', content)

    # Replace black strokes with currentColor so SVGs adapt to CSS context
    content = re.sub(r'stroke="rgb\(0,\s*0,\s*0\)"', 'stroke="currentColor"', content)

    # Apply fill opacity for transparent/translucent parts
    if fill_opacity < 1.0:
        content = re.sub(r'fill-opacity="1\.0"', f'fill-opacity="{fill_opacity:.4f}"', content)

    with open(svg_path, "w") as f:
        f.write(content)

    # For translucent/transparent parts, reorder SVG groups so HiddenEdges appears
    # before Edges. SVG renders later elements on top, so hidden edge strokes must
    # come first to appear behind the semi-transparent fills.
    if fill_opacity < 1.0:
        _reorder_svg_hidden_edges(svg_path)


def _reorder_svg_hidden_edges(svg_path):
    """Move HiddenEdges lineset group before Edges group for correct z-ordering.

    Blender outputs HiddenEdges after Edges, which causes hidden edge strokes to
    render on top of fills. The correct render order is:
      1. HiddenEdges strokes (behind everything, seen dimly through the fill)
      2. Edges fills (semi-transparent)
      3. Edges strokes (on top)
    """
    SVG_NS = "http://www.w3.org/2000/svg"
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")

    tree = ET.parse(svg_path)
    root = tree.getroot()

    # Find HiddenEdges and Edges lineset groups by id attribute.
    # Check HiddenEdges first since "Edges" is a substring of "HiddenEdges".
    hidden_group = None
    edges_group = None
    for child in root:
        child_id = child.get("id", "")
        if "HiddenEdges" in child_id:
            hidden_group = child
        elif "Edges" in child_id:
            edges_group = child

    if hidden_group is None or edges_group is None:
        print("SVG group reordering skipped: HiddenEdges or Edges group not found")
        return

    children = list(root)
    hidden_idx = children.index(hidden_group)
    edges_idx = children.index(edges_group)

    if hidden_idx <= edges_idx:
        print("SVG group reordering skipped: HiddenEdges already before Edges")
        return

    # Remove HiddenEdges and reinsert before Edges
    root.remove(hidden_group)
    children = list(root)
    edges_idx = children.index(edges_group)
    root.insert(edges_idx, hidden_group)

    tree.write(svg_path, xml_declaration=True, encoding="unicode")
    print("Reordered SVG groups: HiddenEdges moved before Edges for correct z-ordering")


def add_svg_background(svg_path):
    """Insert a white background rect as the first child of the SVG root."""
    SVG_NS = "http://www.w3.org/2000/svg"
    ET.register_namespace("", SVG_NS)
    tree = ET.parse(svg_path)
    root = tree.getroot()
    bg = ET.Element("rect")
    bg.set("width", "100%")
    bg.set("height", "100%")
    bg.set("fill", "white")
    root.insert(0, bg)
    tree.write(svg_path, xml_declaration=True, encoding="unicode")
    print(f"Added white background to: {svg_path}")


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
    scene.render.resolution_x = args["resolution_x"]
    scene.render.resolution_y = args["resolution_y"]
    scene.render.film_transparent = True

    # Setup camera
    setup_camera(scene,
                 padding=args["padding"],
                 camera_lat=args["camera_lat"],
                 camera_lon=args["camera_lon"])

    # Setup Freestyle
    setup_freestyle(scene, args["thickness"],
                    crease_angle=args["crease_angle"],
                    edge_types=args["edge_types"],
                    fill_opacity=args["fill_opacity"])

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
        postprocess_svg(output_svg, args["fill_color"], args["fill_opacity"])
        print(f"SVG written to: {output_svg}")
    else:
        print(f"Error: expected SVG not found at {expected_svg}")
        # List files in output dir for debugging
        for f in os.listdir(output_dir):
            print(f"  {f}")
        sys.exit(1)

    # Post-process SVG: add white background for dark mode compatibility
    add_svg_background(output_svg)


if __name__ == "__main__":
    main()
