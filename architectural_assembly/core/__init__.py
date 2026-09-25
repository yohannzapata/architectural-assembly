# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender-independent geometry core of Architectural Assembly.

    SheetMesh + SolidifySettings --build_shell()--> ShellMesh

Nothing in this package imports ``bpy``. It can be unit-tested with a
regular Python interpreter.
"""

from . import regions
from .anchors import SurfaceAnchor, SurfaceFrame, face_frame, resolve_anchor
from .sheet import SheetMesh, SolidifySettings
from .shell import ShellMesh, build_shell, side_offsets
from .surfaces import SIDE_SURFACES, SURFACE_LABELS, Surface
from .windows import WindowSettings, WindowSpec, build_assembly, build_window_shell, cut_openings

__all__ = [
    "SIDE_SURFACES", "SURFACE_LABELS", "SheetMesh", "ShellMesh", "SolidifySettings",
    "Surface", "SurfaceAnchor", "SurfaceFrame", "WindowSettings", "WindowSpec",
    "build_assembly", "build_shell", "build_window_shell", "cut_openings", "face_frame",
    "regions", "resolve_anchor", "side_offsets",
]
