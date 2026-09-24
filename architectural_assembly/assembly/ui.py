# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import display, sync
from .constants import IN_MITER, IN_OFFSET, IN_THICKNESS


class AA_PT_assembly(bpy.types.Panel):
    bl_label = "Architectural Assembly"
    bl_idname = "AA_PT_assembly"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assembly"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select a mesh to thicken", icon="INFO")
            return
        if not sync.is_assembly(obj):
            row = layout.row()
            row.scale_y = 1.4
            row.operator("architectural_assembly.add", text="Add Architectural Assembly",
                         icon="MOD_SOLIDIFY")
            layout.label(text="Model any shape from faces. Assembly gives it thickness.")
            return

        mod = display.find_modifier(obj)
        if mod is None:
            return
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        display.draw_input(col, mod, IN_THICKNESS)
        display.draw_input(col, mod, IN_OFFSET, slider=True)
        display.draw_input(layout, mod, IN_MITER)

        row = layout.row(align=True)
        row.operator("architectural_assembly.rebuild", icon="FILE_REFRESH")
        row.operator("architectural_assembly.remove", icon="X", text="Remove")


class AA_PT_assembly_faces(bpy.types.Panel):
    bl_label = "Selected Faces"
    bl_parent_id = "AA_PT_assembly"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assembly"

    @classmethod
    def poll(cls, context):
        return sync.is_assembly(context.edit_object)

    def draw(self, _context):
        col = self.layout.column(align=True)
        col.operator("architectural_assembly.set_face_thickness", icon="MOD_SOLIDIFY")
        col.operator("architectural_assembly.clear_face_thickness", icon="LOOP_BACK")
        col.operator("architectural_assembly.clear_face_paint", icon="BRUSH_DATA")


classes = (AA_PT_assembly, AA_PT_assembly_faces)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
