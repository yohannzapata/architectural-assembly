# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-wide paint palette: the materials you paint surfaces with."""

import bpy
from bpy.props import CollectionProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup, UIList


def _bsdf(material):
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return None
    return next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def _get_color(self):
    mat = self.active_material()
    if mat is None:
        return (0.8, 0.8, 0.8, 1.0)
    bsdf = _bsdf(mat)
    if bsdf is not None:
        return tuple(bsdf.inputs["Base Color"].default_value)
    return tuple(mat.diffuse_color)


def _set_color(self, value):
    mat = self.active_material()
    if mat is None:
        return
    mat.diffuse_color = value          # Solid-mode colour.
    bsdf = _bsdf(mat)
    if bsdf is not None:               # Rendered / material preview colour.
        bsdf.inputs["Base Color"].default_value = value


class AA_PaletteItem(PropertyGroup):
    material: PointerProperty(name="Material", type=bpy.types.Material)


class AA_PaintSettings(PropertyGroup):
    palette: CollectionProperty(type=AA_PaletteItem)
    active_index: IntProperty(name="Active Paint", default=0)
    color: FloatVectorProperty(
        name="Color", subtype="COLOR", size=4, min=0.0, max=1.0,
        get=_get_color, set=_set_color,
        description="Colour of the active palette material",
    )

    def active_material(self):
        if 0 <= self.active_index < len(self.palette):
            return self.palette[self.active_index].material
        return None

    def select_material(self, material):
        """Make ``material`` the active paint, adding it to the palette if needed."""
        for i, item in enumerate(self.palette):
            if item.material == material:
                self.active_index = i
                return
        item = self.palette.add()
        item.material = material
        self.active_index = len(self.palette) - 1


def new_paint_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    bsdf = _bsdf(mat)
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.8
    return mat


# Starter swatches: (name, colour).
STARTER_PALETTE = (
    ("Plaster White", (0.90, 0.89, 0.85, 1.0)),
    ("Warm Beige", (0.80, 0.70, 0.55, 1.0)),
    ("Sage", (0.55, 0.63, 0.52, 1.0)),
    ("Dusty Blue", (0.45, 0.56, 0.68, 1.0)),
    ("Terracotta", (0.72, 0.40, 0.28, 1.0)),
    ("Charcoal", (0.14, 0.14, 0.15, 1.0)),
)


class AA_UL_palette(UIList):
    bl_idname = "AA_UL_palette"

    def draw_item(self, _context, layout, _data, item, _icon, _active_data, _active_prop, _index):
        mat = item.material
        icon = layout.icon(mat) if mat else 0
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text="", icon_value=icon)
        else:
            layout.prop(item, "material", text="", emboss=False, icon_value=icon)


class AA_OT_palette_add(Operator):
    """Add a new paint material to the palette"""
    bl_idname = "architectural_assembly.palette_add"
    bl_label = "New Paint"
    bl_options = {"REGISTER", "UNDO"}

    name: StringProperty(name="Name", default="Paint")
    color: FloatVectorProperty(name="Color", subtype="COLOR", size=4, min=0.0, max=1.0,
                               default=(0.8, 0.8, 0.8, 1.0))

    def invoke(self, context, _event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        context.scene.aa_paint.select_material(new_paint_material(self.name, self.color))
        return {"FINISHED"}


class AA_OT_palette_remove(Operator):
    """Remove the active material from the palette (the material itself is kept)"""
    bl_idname = "architectural_assembly.palette_remove"
    bl_label = "Remove Paint"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return len(context.scene.aa_paint.palette) > 0

    def execute(self, context):
        paint = context.scene.aa_paint
        paint.palette.remove(paint.active_index)
        paint.active_index = min(paint.active_index, len(paint.palette) - 1)
        return {"FINISHED"}


class AA_OT_palette_import(Operator):
    """Add every material in this file to the palette"""
    bl_idname = "architectural_assembly.palette_import"
    bl_label = "Add All Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        paint = context.scene.aa_paint
        present = {item.material for item in paint.palette}
        for mat in bpy.data.materials:
            if mat not in present and not getattr(mat, "is_grease_pencil", False):
                paint.palette.add().material = mat
        return {"FINISHED"}


class AA_OT_palette_starter(Operator):
    """Fill the palette with a few starter paints"""
    bl_idname = "architectural_assembly.palette_starter"
    bl_label = "Starter Paints"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        paint = context.scene.aa_paint
        for name, color in STARTER_PALETTE:
            mat = bpy.data.materials.get(name) or new_paint_material(name, color)
            paint.select_material(mat)
        paint.active_index = 0
        return {"FINISHED"}


classes = (
    AA_PaletteItem,
    AA_PaintSettings,
    AA_UL_palette,
    AA_OT_palette_add,
    AA_OT_palette_remove,
    AA_OT_palette_import,
    AA_OT_palette_starter,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aa_paint = PointerProperty(type=AA_PaintSettings)


def unregister():
    del bpy.types.Scene.aa_paint
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
