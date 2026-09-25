# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender integration of the architectural solidify.

    properties  object bookkeeping (Object.aa_assembly)
    source_io   source mesh / edit BMesh -> core.SheetMesh
    display     the "Architectural Assembly" Geometry Nodes modifier
    sync        regenerates shells when sources change (depsgraph handler)
    operators   add/remove, rebuild, per-face thickness, clear paint
    windows     window objects: add, slide along walls, divide into panes
    window_io   reads windows into core.WindowSpec
    ui          sidebar panel (View3D > Sidebar > Assembly)
"""

import bpy

from . import operators, properties, sync, ui, windows

_modules = (properties, operators, windows, ui, sync)


def _initial_sync():
    sync.rebuild_all()
    return None   # Run once.


def register():
    for mod in _modules:
        mod.register()
    # bpy.data is restricted while add-ons register; sync once it's safe.
    bpy.app.timers.register(_initial_sync, first_interval=0.1)


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
