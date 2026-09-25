# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows: add one, slide it around on the walls, divide it into panes.

A window is a mesh object whose faces are the panes. It draws its own frame,
mullions and glass (a modifier, like the walls), so you click it, Tab into it
and transform it like any object. It has no size fields: scale it, or edit its
faces (loop cut, extrude, slide edges). Every wall it lies on gets an opening.
``core.windows`` does the geometry, ``sync`` keeps the shells up to date.
"""

import bpy
from bpy.props import FloatProperty, IntProperty
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector, geometry

from . import display, sync, window_io
from .constants import OUT_SOURCE_FACE, SRC_THICKNESS

_PASS_THROUGH = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
                 "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSESMARTZOOM", "NDOF_MOTION"}
_FRAME_MATERIAL = "AA Window Frame"
_GLASS_MATERIAL = "AA Window Glass"
_SIZE = 1.2
_GRID = 0.1   # Grid step (metres) when Ctrl is held while sliding.


# -- materials ------------------------------------------------------------------

def _window_material(name, color, glass):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    try:
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = color
            if glass:
                bsdf.inputs["Roughness"].default_value = 0.02
                bsdf.inputs["Alpha"].default_value = color[3]
    except (AttributeError, KeyError, RuntimeError):
        pass   # Node setup is cosmetic; the viewport colour still works.
    return mat


# -- window objects ---------------------------------------------------------------

def _grid_mesh(mesh, cols, rows, width, height, transom=0.0):
    """Rebuild ``mesh`` as a cols x rows grid of panes centred on the origin, in the XZ plane."""
    x0, z0 = -width / 2, -height / 2
    verts, faces = [], []

    def quad(xa, xb, za, zb):
        base = len(verts)
        verts.extend([(xa, 0.0, za), (xb, 0.0, za), (xb, 0.0, zb), (xa, 0.0, zb)])
        faces.append((base, base + 1, base + 2, base + 3))

    top_z = z0 + height
    lower_top = top_z - height * transom if transom > 0.0 else top_z
    for r in range(rows):
        za = z0 + (lower_top - z0) * r / rows
        zb = z0 + (lower_top - z0) * (r + 1) / rows
        for c in range(cols):
            quad(x0 + width * c / cols, x0 + width * (c + 1) / cols, za, zb)
    if transom > 0.0:
        quad(x0, x0 + width, lower_top, top_z)

    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)
    mesh.update()


def new_window(context, parent=None, name="Window"):
    mesh = bpy.data.meshes.new(name)
    _grid_mesh(mesh, 1, 1, _SIZE, _SIZE)
    mesh.materials.append(_window_material(_FRAME_MATERIAL, (0.92, 0.92, 0.9, 1.0), False))
    mesh.materials.append(_window_material(_GLASS_MATERIAL, (0.6, 0.8, 0.95, 0.3), True))
    win = bpy.data.objects.new(name, mesh)
    context.collection.objects.link(win)
    win.aa_window.is_window = True
    display.add_window_modifier(win)
    _set_parent(win, parent)
    return win


def _basis(normal):
    """Rotation whose X runs along the wall, Z up it, and Y points into the wall."""
    u = Vector((0.0, 0.0, 1.0)).cross(normal)
    u = Vector((1.0, 0.0, 0.0)) if u.length < 1e-6 else u.normalized()
    v = normal.cross(u)
    return Matrix((u, -normal, v)).transposed().to_4x4()   # Columns: X=u, Y=-n, Z=v.


def _pivot(win):
    """Centre of the window's panes in its local space (its origin may be elsewhere)."""
    co = [v.co for v in win.data.vertices]
    if not co:
        return Vector()
    return Vector([(min(c[i] for c in co) + max(c[i] for c in co)) / 2 for i in range(3)])


def place(win, location, normal, scale=(1.0, 1.0, 1.0), pivot=(0.0, 0.0, 0.0)):
    """Put ``win`` flush on the plane through ``location``, its ``pivot`` (local) point there."""
    matrix = Matrix.Translation(location) @ _basis(normal) @ Matrix.Diagonal((*scale, 1.0))
    win.matrix_world = matrix @ Matrix.Translation(-Vector(pivot))


def _set_parent(win, wall):
    """Parent the window to the wall it sits on, so it moves with it."""
    if wall is not None and win.parent != wall:
        win.parent = wall
        win.matrix_parent_inverse = wall.matrix_world.inverted_safe()


# -- finding the wall under the mouse -----------------------------------------------

def _cursor_ray(context, coord):
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return None
    return (view3d_utils.region_2d_to_origin_3d(region, rv3d, coord),
            view3d_utils.region_2d_to_vector_3d(region, rv3d, coord))


def _wall_settings(wall):
    mod = display.find_modifier(wall)
    return display.read_settings(mod) if mod is not None else None


def _mid_plane(wall, poly, settings):
    """The plane through the middle of the wall's thickness at ``poly``: (point, normal), world space.

    The normal is the source face's own normal. The thickness grows from the source
    face by ``t * (1 + offset) / 2`` in front and ``t * (1 - offset) / 2`` behind,
    so the middle is ``t * offset / 2`` along the normal.
    """
    thickness = settings.thickness if settings else 0.0
    layer = wall.data.attributes.get(SRC_THICKNESS)
    if layer is not None and layer.data[poly.index].value > 0.0:
        thickness = layer.data[poly.index].value
    shift = thickness * (settings.offset if settings else 0.0) / 2.0
    mw = wall.matrix_world
    normal = (mw.to_3x3() @ poly.normal).normalized()
    return mw @ poly.center + normal * shift, normal


def _grid_snap(point, normal, step):
    """Snap ``point`` to a grid inside its wall plane: along the wall and up it, from the world origin."""
    u = Vector((0.0, 0.0, 1.0)).cross(normal)
    u = Vector((1.0, 0.0, 0.0)) if u.length < 1e-6 else u.normalized()
    v = normal.cross(u)
    a, b = point.dot(u), point.dot(v)
    return point + u * (round(a / step) * step - a) + v * (round(b / step) * step - b)


def _on_plane(origin, direction, plane_point, plane_normal):
    """Where the cursor ray meets the plane, and the plane's normal turned towards the viewer."""
    point = geometry.intersect_line_plane(origin, origin + direction, plane_point, plane_normal)
    if point is None:
        return None
    return point, (-plane_normal if plane_normal.dot(direction) > 0.0 else plane_normal)


def _probe(context, event, last=None, moving=None):
    """Find the wall under the cursor, ignoring windows.

    Returns ``(host, point, normal, plane)``: ``point`` is where the cursor ray meets the
    middle of the wall's thickness. ``plane`` is ``(point, normal)`` of that middle plane, to
    pass back as ``last``: when the ray finds no wall (the cursor is over the window's own
    opening, say) the window then keeps following the cursor on the last plane, not jumping off.
    A ray that goes through the ``moving`` window itself doesn't count walls behind it either:
    it would hit the wall behind the opening, move the window there, and flip back and forth.
    """
    ray = _cursor_ray(context, (event.mouse_region_x, event.mouse_region_y))
    if ray is None:
        return None
    origin, direction = ray
    depsgraph = context.evaluated_depsgraph_get()
    for _ in range(12):
        hit, loc, _normal, index, obj, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
        if not hit:
            break
        original = obj.original
        if original == moving and last is not None:
            break   # Through the window being moved: stay on the wall it is on.
        if sync.is_assembly(original) and not original.data.is_editmode:
            # The face tags live on the evaluated mesh, not on the object the ray returns.
            attr = original.evaluated_get(depsgraph).data.attributes.get(OUT_SOURCE_FACE)
            source = attr.data[index].value if attr is not None else -1
            if 0 <= source < len(original.data.polygons):
                plane = _mid_plane(original, original.data.polygons[source], _wall_settings(original))
                placed = _on_plane(ray[0], direction, *plane)
                if placed is not None:
                    return original, placed[0], placed[1], plane
        origin = loc + direction * 1e-4   # A window or something else: look through it.
    if last is not None:
        host, plane = last
        placed = _on_plane(ray[0], direction, *plane)
        if placed is not None:
            return host, placed[0], placed[1], plane
    return None


# -- operators ----------------------------------------------------------------------

class _WallSlide:
    """Modal base: the window follows the wall under the cursor."""
    _plane = None   # (wall, (point, normal)) of the last wall plane it snapped to.
    bl_options = {"REGISTER", "UNDO", "BLOCKING"}

    def _confirms(self, event):
        return event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"} and event.value == "PRESS"

    def _slide(self, context, event):
        # Follows the wall under the cursor. Ctrl also snaps its centre to a grid on the wall.
        found = _probe(context, event, self._plane, self.window)
        win = self.window
        if found is None:
            # No wall to follow: move freely, keeping orientation and size.
            pivot = _pivot(win)
            coord = (event.mouse_region_x, event.mouse_region_y)
            free = view3d_utils.region_2d_to_location_3d(
                context.region, context.region_data, coord, win.matrix_world @ pivot)
            matrix = win.matrix_world.copy()
            matrix.translation = free - matrix.to_3x3() @ pivot
            win.matrix_world = matrix
            state = "no wall under the cursor"
        else:
            host, location, normal, plane = found
            self._plane = (host, plane)
            state = f"on {host.name}"
            if event.ctrl:
                location = _grid_snap(location, normal, _GRID)
                state += f", grid {_GRID:g} m"
            _set_parent(win, host)
            place(win, location, normal, win.matrix_world.to_scale(), _pivot(win))
        context.area.header_text_set(f"{self.hint}  •  {state}")

    def _finish(self, context):
        context.area.header_text_set(None)

    def modal(self, context, event):
        if event.type in _PASS_THROUGH:
            return {"PASS_THROUGH"}
        if event.type in {"MOUSEMOVE", "LEFT_CTRL", "RIGHT_CTRL"}:
            self._slide(context, event)
        elif self._confirms(event):
            self._finish(context)
            return {"FINISHED"}
        elif event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._cancel(context)
            self._finish(context)
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}


class AA_OT_add_window(_WallSlide, bpy.types.Operator):
    """Add a window and place it on a wall: it follows the cursor, click to drop it"""
    bl_idname = "architectural_assembly.add_window"
    bl_label = "Add Window"
    hint = "Window: LMB place  •  RMB/Esc cancel  •  hold Ctrl for grid snap"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (context.mode == "OBJECT" and context.area is not None
                and context.area.type == "VIEW_3D"
                and (sync.is_assembly(obj) or window_io.is_window(obj)))

    def invoke(self, context, event):
        active = context.active_object
        parent = active if sync.is_assembly(active) else active.parent
        self.window = new_window(context, parent)
        for o in context.selected_objects:
            o.select_set(False)
        self.window.select_set(True)
        context.view_layer.objects.active = self.window
        self._slide(context, event)
        context.area.header_text_set(self.hint)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _cancel(self, _context):
        mesh = self.window.data
        bpy.data.objects.remove(self.window)
        bpy.data.meshes.remove(mesh)


class AA_OT_move_window(_WallSlide, bpy.types.Operator):
    """Slide the window over the walls: it stays flush with whichever wall is under the cursor"""
    bl_idname = "architectural_assembly.move_window"
    bl_label = "Slide Window on Wall (V)"
    hint = "Slide window: LMB drop  •  RMB/Esc cancel  •  hold Ctrl for grid snap"

    @classmethod
    def poll(cls, context):
        return (context.mode == "OBJECT" and context.area is not None
                and context.area.type == "VIEW_3D" and window_io.is_window(context.active_object))

    def invoke(self, context, _event):
        self.window = context.active_object
        self._start = (self.window.matrix_world.copy(), self.window.parent)
        # Start on the wall the window is on, so it doesn't hop to one behind it.
        near = _nearest_wall(self.window.matrix_world @ _pivot(self.window))
        if near is not None:
            self._plane = (near[0], (near[1], near[2]))
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set(self.hint)
        return {"RUNNING_MODAL"}

    def _cancel(self, _context):
        matrix, host = self._start
        _set_parent(self.window, host)
        self.window.matrix_world = matrix


class AA_OT_divide_window(bpy.types.Operator):
    """Divide the window into panes. Edit the faces for any other layout"""
    bl_idname = "architectural_assembly.divide_window"
    bl_label = "Divide Window"
    bl_options = {"REGISTER", "UNDO"}

    columns: IntProperty(name="Columns", default=2, min=1, max=20)
    rows: IntProperty(name="Rows", default=2, min=1, max=20)
    transom: FloatProperty(
        name="Top Light",
        description="Height of a full-width pane along the top, as a fraction of the window (0 = none)",
        default=0.0, min=0.0, max=0.6, subtype="FACTOR")

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and window_io.is_window(context.active_object)

    def execute(self, context):
        win = context.active_object
        xs = [v.co.x for v in win.data.vertices]
        zs = [v.co.z for v in win.data.vertices]
        width = (max(xs) - min(xs)) if xs else _SIZE
        height = (max(zs) - min(zs)) if zs else _SIZE
        cx = (max(xs) + min(xs)) / 2 if xs else 0.0
        cz = (max(zs) + min(zs)) / 2 if zs else 0.0
        if width < 1e-4 or height < 1e-4:
            width = height = _SIZE
        _grid_mesh(win.data, self.columns, self.rows, width, height, self.transom)
        win.data.transform(Matrix.Translation((cx, 0.0, cz)))
        return {"FINISHED"}


def _nearest_wall(centre):
    """The wall the window's centre (world) lies over, nearest first: (wall, point, normal).

    ``point`` is ``centre`` moved onto the middle of that wall's thickness.
    """
    best = None
    for wall in bpy.data.objects:
        if not sync.is_assembly(wall) or wall.data.is_editmode:
            continue
        to_local = wall.matrix_world.inverted_safe()
        settings = _wall_settings(wall)
        for poly in wall.data.polygons:
            plane_point, normal = _mid_plane(wall, poly, settings)
            d = (centre - plane_point).dot(normal)
            point = centre - normal * d
            local = to_local @ point
            local -= poly.normal * (local - poly.center).dot(poly.normal)   # In-plane test.
            verts = [wall.data.vertices[i].co for i in poly.vertices]
            inside = any(geometry.intersect_point_tri(local, verts[0], verts[i], verts[i + 1]) is not None
                         for i in range(1, len(verts) - 1))
            if inside and (best is None or abs(d) < best[0]):
                best = (abs(d), wall, point, normal)
    return best and best[1:]


classes = (AA_OT_add_window, AA_OT_move_window, AA_OT_divide_window)
_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc is None:
        return
    # Only act when a window is active. G, S and the rest stay exactly as in Blender.
    km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
    _keymaps.append((km, km.keymap_items.new(AA_OT_move_window.bl_idname, "V", "PRESS")))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
