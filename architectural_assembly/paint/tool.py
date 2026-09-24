# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Click-to-paint tool for assemblies.

    LMB           paint the surface under the cursor
    Shift + LMB   fill: paint every connected surface of the same kind
    Ctrl + LMB    erase paint (back to the face's own material)
    Alt + LMB     pick the material under the cursor into the palette
    RMB / Esc     finish

The surface under the cursor is highlighted in the active paint's colour.
Navigation keeps working while the tool runs, and so does the sidebar,
so you can switch paints mid-session.

Paint is stored on the *source* faces (``aa_paint_*`` attributes), never on
the generated polygons, so it survives any regeneration.
"""

import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..assembly import source_io, sync
from ..assembly.constants import OUT_SOURCE_FACE, OUT_SURFACE, SRC_PAINT_ATTRS
from ..core import regions

_NAVIGATION = {
    "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE",
    "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSESMARTZOOM",
    "NDOF_MOTION", "NDOF_BUTTON_MENU", "NDOF_BUTTON_FIT",
    "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4", "NUMPAD_5",
    "NUMPAD_6", "NUMPAD_7", "NUMPAD_8", "NUMPAD_9", "NUMPAD_PERIOD",
    "NUMPAD_PLUS", "NUMPAD_MINUS", "HOME", "Z",
}
_MODIFIER_KEYS = {"LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL", "LEFT_ALT", "RIGHT_ALT"}
_HEADER = "Paint: LMB paint  •  Shift fill  •  Ctrl erase  •  Alt pick  •  RMB/Esc done"
_LIFT = 0.002   # Highlight offset from the surface, avoids z-fighting.


class _EvalMesh:
    """Arrays from an assembly's evaluated mesh, for hit lookup and drawing."""

    def __init__(self, obj, eval_obj):
        me = eval_obj.data
        n = len(me.polygons)
        self.obj_name = obj.name
        self.source = self._ints(me, OUT_SOURCE_FACE, n)
        self.surface = self._ints(me, OUT_SURFACE, n)
        normals = [0.0] * (n * 3)
        me.polygons.foreach_get("normal", normals)
        self.normals = [Vector(normals[i:i + 3]) for i in range(0, n * 3, 3)]
        self.nz = [nrm.z for nrm in self.normals]
        self.materials = [0] * n
        me.polygons.foreach_get("material_index", self.materials)
        self.valid = me.attributes.get(OUT_SOURCE_FACE) is not None

        co = [0.0] * (len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = eval_obj.matrix_world
        self.verts = [mw @ Vector(co[i:i + 3]) for i in range(0, len(co), 3)]
        self.normal_matrix = mw.to_3x3().inverted_safe().transposed()

        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        tri_verts, tri_poly = [0] * (nt * 3), [0] * nt
        me.loop_triangles.foreach_get("vertices", tri_verts)
        me.loop_triangles.foreach_get("polygon_index", tri_poly)
        self.tris_by_poly = {}
        for t in range(nt):
            self.tris_by_poly.setdefault(tri_poly[t], []).append(tri_verts[t * 3:t * 3 + 3])

        starts, totals = [0] * n, [0] * n
        me.polygons.foreach_get("loop_start", starts)
        me.polygons.foreach_get("loop_total", totals)
        loop_edges = [0] * len(me.loops)
        me.loops.foreach_get("edge_index", loop_edges)
        self._face_edges = [loop_edges[s:s + t] for s, t in zip(starts, totals)]
        self._neighbours = None

    @staticmethod
    def _ints(me, name, n):
        attr = me.attributes.get(name)
        values = [0] * n
        if attr is not None and attr.domain == "FACE" and len(attr.data) == n:
            attr.data.foreach_get("value", values)
        return values

    @property
    def neighbours(self):
        if self._neighbours is None:
            self._neighbours = regions.face_adjacency(self._face_edges)
        return self._neighbours

    def triangles(self, polys):
        coords = []
        for p in polys:
            lift = (self.normal_matrix @ self.normals[p]).normalized() * _LIFT
            for tri in self.tris_by_poly.get(p, ()):
                coords.extend(self.verts[i] + lift for i in tri)
        return coords


class AA_OT_paint(bpy.types.Operator):
    """Paint assembly surfaces with the active palette material. Click to paint, Shift-click to fill"""
    bl_idname = "architectural_assembly.paint"
    bl_label = "Paint Surfaces"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == "VIEW_3D"
                and context.mode == "OBJECT")

    # -- lifecycle -------------------------------------------------------------

    def invoke(self, context, _event):
        if not any(sync.is_assembly(o) for o in context.visible_objects):
            self.report({"WARNING"}, "No Architectural Assembly objects are visible")
            return {"CANCELLED"}
        self._region = context.region
        self._rv3d = context.region_data
        self._cache = None
        self._hover_key = None
        self._hover_tris = []
        self._hover_mode = "PAINT"
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_highlight, (self,), "WINDOW", "POST_VIEW")
        context.area.header_text_set(_HEADER)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
        if context.area is not None:
            context.area.header_text_set(None)
            context.area.tag_redraw()

    # -- events ----------------------------------------------------------------

    def modal(self, context, event):
        if context.area is None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
            return {"CANCELLED"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._finish(context)
            return {"FINISHED"}
        if event.type in _NAVIGATION:
            return {"PASS_THROUGH"}
        if not self._inside_region(event):
            # Let the sidebar, header and other areas work (e.g. pick another
            # paint, change thickness). Drop the cache: the mesh may change.
            self._set_hover(None, [])
            self._cache = None
            return {"PASS_THROUGH"}

        if event.type == "MOUSEMOVE" or event.type in _MODIFIER_KEYS:
            self._update_hover(context, event)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            hit = self._raycast(context, event)
            if hit is not None:
                obj, cache, poly = hit
                if event.alt:
                    self._pick(context, obj, cache, poly)
                else:
                    self._paint(context, obj, cache, poly, flood=event.shift, erase=event.ctrl)
                self._cache = None
            self._update_hover(context, event)
            return {"RUNNING_MODAL"}

        return {"RUNNING_MODAL"}

    def _inside_region(self, event):
        r = self._region
        return (r.x <= event.mouse_x < r.x + r.width) and (r.y <= event.mouse_y < r.y + r.height)

    # -- hit testing -----------------------------------------------------------

    def _raycast(self, context, event):
        region, rv3d = self._region, self._rv3d
        if rv3d is None:
            return None
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        depsgraph = context.evaluated_depsgraph_get()
        ok, _loc, _nrm, index, hit_obj, _mat = context.scene.ray_cast(depsgraph, origin, direction)
        if not ok or hit_obj is None:
            return None
        obj = hit_obj.original
        if not sync.is_assembly(obj):
            return None
        eval_obj = obj.evaluated_get(depsgraph)
        if self._cache is None or self._cache.obj_name != obj.name \
                or len(self._cache.source) != len(eval_obj.data.polygons):
            self._cache = _EvalMesh(obj, eval_obj)
        if not self._cache.valid or index >= len(self._cache.source):
            return None
        return obj, self._cache, index

    def _region_for(self, cache, poly, flood):
        if flood:
            return regions.flood_region(poly, cache.source, cache.surface, cache.nz, cache.neighbours)
        return regions.surface_region(poly, cache.source, cache.surface)

    def _update_hover(self, context, event):
        hit = self._raycast(context, event)
        if hit is None:
            self._set_hover(None, [])
            return
        obj, cache, poly = hit
        key = (obj.name, cache.source[poly], cache.surface[poly], event.shift, event.ctrl, event.alt)
        if key == self._hover_key:
            return
        if event.alt:
            polys = [poly]
        else:
            polys, _ = self._region_for(cache, poly, event.shift)
        self._hover_mode = "ERASE" if event.ctrl else "PICK" if event.alt else "PAINT"
        self._set_hover(key, cache.triangles(polys))

    def _set_hover(self, key, tris):
        if key == self._hover_key and (key is not None or not self._hover_tris):
            return
        self._hover_key = key
        self._hover_tris = tris
        if self._region is not None:
            self._region.tag_redraw()

    # -- actions ---------------------------------------------------------------

    def _paint(self, context, obj, cache, poly, flood, erase):
        paint = context.scene.aa_paint
        material = None if erase else paint.active_material()
        if not erase and material is None:
            self.report({"WARNING"}, "Pick a paint in the palette first")
            return
        _, targets = self._region_for(cache, poly, flood)
        apply_paint(obj, targets, material)
        verb = "Erase Paint" if erase else "Fill Paint" if flood else "Paint Surface"
        bpy.ed.undo_push(message=verb)

    def _pick(self, context, obj, cache, poly):
        slot = cache.materials[poly]
        if 0 <= slot < len(obj.material_slots) and obj.material_slots[slot].material:
            context.scene.aa_paint.select_material(obj.material_slots[slot].material)
            for area in context.screen.areas:
                area.tag_redraw()


def apply_paint(obj, targets, material):
    """Write paint to source faces. ``targets``: {(source face, Surface)}.

    ``material=None`` erases. Adds the material to the object's slots if needed.
    """
    mesh = obj.data
    value = 0
    if material is not None:
        slots = [s.material for s in obj.material_slots]
        if material in slots:
            value = slots.index(material) + 1
        else:
            mesh.materials.append(material)
            value = len(obj.material_slots)
    if any(mesh.attributes.get(name) is None for name in SRC_PAINT_ATTRS):
        source_io.ensure_attributes(mesh)
    n = len(mesh.polygons)
    for face, surface in targets:
        if 0 <= face < n:
            mesh.attributes[SRC_PAINT_ATTRS[surface]].data[face].value = value
    mesh.update()


def _draw_highlight(op):
    tris = getattr(op, "_hover_tris", None)
    if not tris:
        return
    mode = getattr(op, "_hover_mode", "PAINT")
    if mode == "ERASE":
        color = (1.0, 0.25, 0.25, 0.45)
    elif mode == "PICK":
        color = (1.0, 1.0, 1.0, 0.35)
    else:
        mat = bpy.context.scene.aa_paint.active_material()
        c = mat.diffuse_color if mat is not None else (1.0, 1.0, 1.0, 1.0)
        color = (c[0], c[1], c[2], 0.65)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "TRIS", {"pos": tris})
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.depth_test_set("NONE")
    gpu.state.blend_set("NONE")


classes = (AA_OT_paint,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
