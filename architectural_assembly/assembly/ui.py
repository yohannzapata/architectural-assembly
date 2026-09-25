# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import display, sync, window_io
from .constants import IN_MITER, IN_OFFSET, IN_THICKNESS


class AA_PT_assembly(bpy.types.Panel):
    bl_label = "Architectural Assembly"
    bl_idname = "AA_PT_assembly"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assembly"

    @classmethod
    def poll(cls, context):
        return not window_io.is_window(context.active_object)

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


class AA_PT_windows(bpy.types.Panel):
    bl_label = "Windows"
    bl_idname = "AA_PT_windows"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assembly"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == "OBJECT" and (sync.is_assembly(obj) or window_io.is_window(obj))

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        layout.operator("architectural_assembly.add_window", icon="MOD_LATTICE")
        if not window_io.is_window(obj):
            layout.label(text="Click a wall to drop a window. Click a window to edit it")
            return
        row = layout.row(align=True)
        row.operator("architectural_assembly.move_window", icon="CON_LOCLIKE")
        row.operator("architectural_assembly.divide_window", icon="GRID")
        layout.label(text="V slide on walls (Ctrl: grid)  •  S resize  •  Tab panes")
        data = obj.aa_window
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column(align=True)
        col.prop(data, "frame_width")
        col.prop(data, "mullion_width")
        col.prop(data, "frame_depth")
        col.prop(data, "glass_thickness")


classes = (AA_PT_assembly, AA_PT_assembly_faces, AA_PT_windows)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
