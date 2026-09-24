# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import bmesh
import bpy
from bpy.props import FloatProperty

from . import display, source_io, sync
from .constants import SRC_PAINT_ATTRS, SRC_THICKNESS


class AA_OT_add_assembly(bpy.types.Operator):
    """Thicken the selected meshes' faces into architectural shells"""
    bl_idname = "architectural_assembly.add"
    bl_label = "Architectural Assembly"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(
            o.type == "MESH" and not sync.is_assembly(o) for o in _targets(context))

    def execute(self, context):
        added = 0
        for obj in _targets(context):
            if obj.type != "MESH" or sync.is_assembly(obj):
                continue
            source_io.ensure_attributes(obj.data)
            if display.find_modifier(obj) is None:
                display.add_modifier(obj)
            obj.aa_assembly.is_source = True
            sync.rebuild(obj, force=True)
            added += 1
        self.report({"INFO"}, f"Architectural Assembly added to {added} object(s)")
        return {"FINISHED"}


class AA_OT_remove_assembly(bpy.types.Operator):
    """Remove Architectural Assembly and keep the original faces"""
    bl_idname = "architectural_assembly.remove"
    bl_label = "Remove Assembly"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(sync.is_assembly(o) for o in _targets(context))

    def execute(self, context):
        for obj in _targets(context):
            if sync.is_assembly(obj):
                mod = display.find_modifier(obj)
                if mod is not None:
                    obj.modifiers.remove(mod)
                sync.detach(obj)
        return {"FINISHED"}


class AA_OT_rebuild(bpy.types.Operator):
    """Regenerate the selected assemblies"""
    bl_idname = "architectural_assembly.rebuild"
    bl_label = "Rebuild"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(sync.is_assembly(o) for o in _targets(context))

    def execute(self, context):
        for obj in _targets(context):
            sync.rebuild(obj, force=True)
        return {"FINISHED"}


class _SelectedFacesOperator:
    """Base for edit-mode operators acting on the selected source faces."""
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return sync.is_assembly(context.edit_object)

    def execute(self, context):
        obj = context.edit_object
        bm = bmesh.from_edit_mesh(obj.data)
        faces = [f for f in bm.faces if f.select]
        if not faces:
            self.report({"WARNING"}, "Select one or more faces")
            return {"CANCELLED"}
        self.apply(bm, faces)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return {"FINISHED"}


class AA_OT_set_face_thickness(_SelectedFacesOperator, bpy.types.Operator):
    """Give the selected faces their own thickness (0 = use the modifier's)"""
    bl_idname = "architectural_assembly.set_face_thickness"
    bl_label = "Set Face Thickness"

    thickness: FloatProperty(name="Thickness", default=0.3, min=0.0, soft_max=2.0,
                             subtype="DISTANCE", unit="LENGTH")

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def apply(self, bm, faces):
        layer = bm.faces.layers.float.get(SRC_THICKNESS) or bm.faces.layers.float.new(SRC_THICKNESS)
        for f in faces:
            f[layer] = self.thickness


class AA_OT_clear_face_thickness(_SelectedFacesOperator, bpy.types.Operator):
    """Make the selected faces use the modifier's thickness again"""
    bl_idname = "architectural_assembly.clear_face_thickness"
    bl_label = "Use Default Thickness"

    def apply(self, bm, faces):
        layer = bm.faces.layers.float.get(SRC_THICKNESS)
        if layer:
            for f in faces:
                f[layer] = 0.0


class AA_OT_clear_face_paint(_SelectedFacesOperator, bpy.types.Operator):
    """Remove paint from the selected faces (all sides)"""
    bl_idname = "architectural_assembly.clear_face_paint"
    bl_label = "Clear Paint"

    def apply(self, bm, faces):
        for name in SRC_PAINT_ATTRS:
            layer = bm.faces.layers.int.get(name)
            if layer:
                for f in faces:
                    f[layer] = 0


def _targets(context):
    objs = list(context.selected_objects)
    if context.active_object is not None and context.active_object not in objs:
        objs.append(context.active_object)
    return objs


def _menu_modifier_add(self, _context):
    self.layout.operator(AA_OT_add_assembly.bl_idname, icon="MOD_SOLIDIFY")


classes = (
    AA_OT_add_assembly,
    AA_OT_remove_assembly,
    AA_OT_rebuild,
    AA_OT_set_face_thickness,
    AA_OT_clear_face_thickness,
    AA_OT_clear_face_paint,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    menu = getattr(bpy.types, "OBJECT_MT_modifier_add", None)
    if menu is not None:
        menu.append(_menu_modifier_add)


def unregister():
    menu = getattr(bpy.types, "OBJECT_MT_modifier_add", None)
    if menu is not None:
        menu.remove(_menu_modifier_add)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
