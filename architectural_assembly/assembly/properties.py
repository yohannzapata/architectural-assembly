# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bookkeeping stored on objects. User-facing settings live on the modifier."""

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup


class AA_AssemblyData(PropertyGroup):
    is_source: BoolProperty(
        name="Architectural Assembly",
        description="This object's faces are thickened by Architectural Assembly",
        default=False,
    )
    shell: PointerProperty(
        name="Shell",
        type=bpy.types.Object,
        description="Hidden object that holds the generated geometry",
    )
    owner_name: StringProperty(
        description="On a shell object: name of the source object that owns it",
    )
    next_uid: IntProperty(default=1, min=1)


def _touch(self, _context):
    """Nudge the depsgraph so walls and the window rebuild when a setting changes."""
    if self.id_data is not None:
        self.id_data.update_tag()


class AA_WindowData(PropertyGroup):
    is_window: BoolProperty(
        name="Window",
        description="The faces of this object are the panes of a window",
        default=False,
    )
    shell: PointerProperty(
        name="Shell",
        type=bpy.types.Object,
        description="Hidden object that holds the generated frame and glass",
    )
    frame_width: FloatProperty(
        name="Frame Width", description="Width of the outer frame",
        default=0.06, min=0.001, soft_max=0.3, subtype="DISTANCE", unit="LENGTH", update=_touch)
    mullion_width: FloatProperty(
        name="Mullion Width", description="Width of the bars between panes",
        default=0.03, min=0.001, soft_max=0.2, subtype="DISTANCE", unit="LENGTH", update=_touch)
    frame_depth: FloatProperty(
        name="Frame Depth", description="How deep the frame and mullions are",
        default=0.08, min=0.001, soft_max=0.5, subtype="DISTANCE", unit="LENGTH", update=_touch)
    glass_thickness: FloatProperty(
        name="Glass", description="Thickness of the glass",
        default=0.01, min=0.001, soft_max=0.05, subtype="DISTANCE", unit="LENGTH", update=_touch)


classes = (AA_AssemblyData, AA_WindowData)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.aa_assembly = PointerProperty(type=AA_AssemblyData)
    bpy.types.Object.aa_window = PointerProperty(type=AA_WindowData)



def unregister():
    del bpy.types.Object.aa_window
    del bpy.types.Object.aa_assembly
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
