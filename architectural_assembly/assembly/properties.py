# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bookkeeping stored on objects. User-facing settings live on the modifier."""

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty
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


classes = (AA_AssemblyData,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.aa_assembly = PointerProperty(type=AA_AssemblyData)


def unregister():
    del bpy.types.Object.aa_assembly
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
