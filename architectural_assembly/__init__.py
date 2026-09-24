# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Architectural Assembly: architectural solidify and Bloxburg-style painting for Blender.

Packages:
    core      pure-Python geometry (no bpy): sheet -> thick shell
    assembly  Blender integration: data, live sync, modifier display, operators, UI
    paint     click-to-paint tool with a material palette

Blender modules are imported inside ``register()`` so that ``core`` can be
imported and tested outside Blender.
"""

_modules = []


def register():
    from . import assembly, paint

    _modules[:] = [assembly, paint]
    for mod in _modules:
        mod.register()


def unregister():
    for mod in reversed(_modules):
        mod.unregister()
    _modules.clear()
