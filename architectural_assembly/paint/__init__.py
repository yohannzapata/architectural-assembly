# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bloxburg-style surface painting.

    palette  scene-wide paint materials (Scene.aa_paint)
    tool     modal click-to-paint operator with hover highlight
    ui       sidebar panel (View3D > Sidebar > Assembly > Paint)
"""

from . import palette, tool, ui

_modules = (palette, tool, ui)


def register():
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
