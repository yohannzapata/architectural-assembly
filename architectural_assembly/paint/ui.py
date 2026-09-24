# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import bpy


class AA_PT_paint(bpy.types.Panel):
    bl_label = "Paint"
    bl_idname = "AA_PT_paint"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assembly"

    def draw(self, context):
        layout = self.layout
        paint = context.scene.aa_paint

        row = layout.row()
        row.scale_y = 1.4
        row.operator("architectural_assembly.paint", icon="BRUSH_DATA")

        row = layout.row()
        row.template_list("AA_UL_palette", "", paint, "palette", paint, "active_index",
                          type="GRID", columns=4, rows=2)
        col = row.column(align=True)
        col.operator("architectural_assembly.palette_add", icon="ADD", text="")
        col.operator("architectural_assembly.palette_remove", icon="REMOVE", text="")
        col.separator()
        col.menu("AA_MT_palette_extras", icon="DOWNARROW_HLT", text="")

        if not paint.palette:
            layout.operator("architectural_assembly.palette_starter", icon="COLOR")
            return
        mat = paint.active_material()
        if mat is not None:
            box = layout.box()
            box.template_ID(paint.palette[paint.active_index], "material")
            box.prop(paint, "color")
        else:
            layout.prop(paint.palette[paint.active_index], "material")


class AA_MT_palette_extras(bpy.types.Menu):
    bl_label = "Palette"
    bl_idname = "AA_MT_palette_extras"

    def draw(self, _context):
        layout = self.layout
        layout.operator("architectural_assembly.palette_starter", icon="COLOR")
        layout.operator("architectural_assembly.palette_import", icon="MATERIAL")


classes = (AA_MT_palette_extras, AA_PT_paint)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
