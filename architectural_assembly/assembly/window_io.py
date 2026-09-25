# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads window objects into ``core.WindowSpec`` objects."""

import bmesh
import bpy

from ..core import WindowSettings, WindowSpec


def is_window(obj):
    return obj is not None and obj.type == "MESH" and obj.aa_window.is_window


def all_windows():
    """Every window object that is still in a scene."""
    return [o for o in bpy.data.objects if is_window(o) and o.users_collection]


def settings_of(win):
    data = win.aa_window
    return WindowSettings(
        frame_width=data.frame_width, frame_depth=data.frame_depth,
        mullion_width=data.mullion_width, glass_thickness=data.glass_thickness)


def read_spec(win, matrix=None):
    """The window's panes with ``matrix`` applied to its world-space corners (None = world)."""
    mesh = win.data
    m = win.matrix_world if matrix is None else matrix @ win.matrix_world
    if mesh.is_editmode:
        bm = bmesh.from_edit_mesh(mesh)
        polys = [[tuple(m @ v.co) for v in f.verts] for f in bm.faces]
    else:
        co = [m @ v.co for v in mesh.vertices]
        polys = [[tuple(co[mesh.loops[i].vertex_index])
                  for i in range(p.loop_start, p.loop_start + p.loop_total)]
                 for p in mesh.polygons]
    return WindowSpec(polys, settings_of(win))


def read_openings(target):
    """Every window, in the local space of ``target`` (a wall object): windows cut all walls they lie on."""
    to_local = target.matrix_world.inverted_safe()
    return [read_spec(win, to_local) for win in all_windows()]


def signature(specs, quantum=1e-6):
    return tuple(
        (tuple(tuple(round(c / quantum) for c in p) for poly in s.polygons for p in poly),
         tuple(len(poly) for poly in s.polygons),
         tuple(round(getattr(s.settings, k) / quantum) for k in
               ("frame_width", "frame_depth", "mullion_width", "glass_thickness")))
        for s in specs)
