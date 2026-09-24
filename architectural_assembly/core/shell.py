# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the thick shell from a sheet and its topology.

0. Conform the input so faces that touch share topology (see conform.py).
1. Place one vertex per cell. Each face side in the cell defines an offset
   plane. The vertex is the least-squares point on all of them that is
   closest to the source vertex. One plane gives a plain offset, two give
   a clean miter, three or more give a corner or junction. Nearly parallel
   planes are clamped by the miter limit.
2. Emit, per source face, a FRONT and a BACK polygon.
3. Close every open edge with a rim quad, classified TOP/BOTTOM/EDGE by
   its direction.
4. Where three or more rims meet around one source vertex (the top of a
   T-junction, for example), close the remaining hole with a cap polygon.

Faces are tagged with surface, source face and material slot, which is
all the Blender side needs.
"""

from dataclasses import dataclass, field

from . import vec3 as v3
from .conform import conform
from .sheet import SolidifySettings
from .surfaces import Surface
from .topology import BACK, FRONT, analyse, face_side
from .uv import world_uvs

_REGULARISE = 1e-9
_UP_THRESHOLD = 0.7


@dataclass
class ShellMesh:
    vertices: list = field(default_factory=list)       # [(x, y, z)]
    faces: list = field(default_factory=list)          # [(i, j, k, ...)]
    face_surface: list = field(default_factory=list)   # Surface per face
    face_source: list = field(default_factory=list)    # source face index per face
    face_uid: list = field(default_factory=list)       # source face uid per face
    face_material: list = field(default_factory=list)  # material slot per face
    face_uvs: list = field(default_factory=list)       # [[(u, v)] per corner] per face


def side_offsets(sheet, settings, f):
    """Signed distances of the FRONT and BACK planes of face ``f``."""
    t = sheet.thickness(f, settings.thickness)
    o = max(-1.0, min(1.0, settings.offset))
    return t * (1.0 + o) * 0.5, -t * (1.0 - o) * 0.5


def _place_cells(sheet, settings, topo):
    members = {}
    for (v, fs), cell in topo.cells.items():
        members.setdefault(cell, (v, []))[1].append(fs)

    offsets = {}
    positions = {}
    for cell, (v, sides) in members.items():
        m = [[_REGULARISE, 0.0, 0.0], [0.0, _REGULARISE, 0.0], [0.0, 0.0, _REGULARISE]]
        rhs = [0.0, 0.0, 0.0]
        reach = 0.0
        for fs in sides:
            f, side = divmod(fs, 2)
            if f not in offsets:
                offsets[f] = side_offsets(sheet, settings, f)
            d = offsets[f][side]
            n = topo.normals[f]
            for r in range(3):
                rhs[r] += n[r] * d
                for c in range(3):
                    m[r][c] += n[r] * n[c]
            reach = max(reach, sheet.thickness(f, settings.thickness))
        y = v3.solve3(m, rhs) or (0.0, 0.0, 0.0)
        limit = settings.miter_limit * reach
        dist = v3.length(y)
        if dist > limit > 0.0:
            y = v3.scale(y, limit / dist)
        positions[cell] = v3.add(sheet.positions[v], y)
    return positions


class _Emitter:
    def __init__(self, sheet, topo, cell_positions):
        self.sheet = sheet
        self.topo = topo
        self.cell_positions = cell_positions
        self.mesh = ShellMesh()
        self._index = {}

    def vert(self, cell):
        idx = self._index.get(cell)
        if idx is None:
            idx = len(self.mesh.vertices)
            self.mesh.vertices.append(self.cell_positions[cell])
            self._index[cell] = idx
        return idx

    def cell(self, v, f, side):
        return self.topo.cells[(v, face_side(f, side))]

    def emit(self, cells, surface, source):
        # Collapse repeated corners (e.g. zero-thickness sides meeting).
        cleaned = []
        for c in cells:
            if not cleaned or cleaned[-1] != c:
                cleaned.append(c)
        while len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
            cleaned.pop()
        if len(set(cleaned)) < 3:
            return
        pts = [self.cell_positions[c] for c in cleaned]
        normal = v3.normalize(v3.polygon_normal(pts))
        if surface is None:
            surface = _classify(normal)
        m = self.mesh
        m.faces.append(tuple(self.vert(c) for c in cleaned))
        m.face_surface.append(int(surface))
        m.face_source.append(source)
        m.face_uid.append(self.sheet.uid(source))
        m.face_material.append(self.sheet.material(source, surface))
        m.face_uvs.append(world_uvs(pts, normal))


def _classify(normal):
    if normal[2] > _UP_THRESHOLD:
        return Surface.TOP
    if normal[2] < -_UP_THRESHOLD:
        return Surface.BOTTOM
    return Surface.EDGE


def build_shell(sheet, settings=None, conform_input=True):
    settings = settings or SolidifySettings()
    if conform_input:
        sheet = conform(sheet)
    topo = analyse(sheet)
    em = _Emitter(sheet, topo, _place_cells(sheet, settings, topo))

    # Sides.
    for f, face in enumerate(sheet.faces):
        if not topo.valid[f]:
            continue
        em.emit([em.cell(v, f, FRONT) for v in face], Surface.FRONT, f)
        em.emit([em.cell(v, f, BACK) for v in reversed(face)], Surface.BACK, f)

    # Rims on open edges. Also collect the half-edges each rim leaves open
    # around its end vertices, reversed, so the caps are wound to match.
    open_around = {}
    for (a, b), incident in topo.edge_faces.items():
        if len(incident) != 1:
            continue
        f, forward = incident[0]
        va, vb = (a, b) if forward else (b, a)
        fa, ba = em.cell(va, f, FRONT), em.cell(va, f, BACK)
        fb, bb = em.cell(vb, f, FRONT), em.cell(vb, f, BACK)
        em.emit([fa, ba, bb, fb], None, f)
        open_around.setdefault(va, []).append((ba, fa, f))
        open_around.setdefault(vb, []).append((fb, bb, f))

    # Caps where 3+ rims meet around one source vertex.
    for half_edges in open_around.values():
        for loop, source in _cycles(half_edges):
            if len(loop) >= 3:
                em.emit(loop, None, source)

    return em.mesh


def _cycles(half_edges):
    """Chain directed edges (start, end, source) into closed loops."""
    outgoing = {}
    for start, end, source in half_edges:
        outgoing.setdefault(start, []).append((end, source))
    loops = []
    for start in list(outgoing):
        while outgoing.get(start):
            loop, source = [start], outgoing[start][0][1]
            current = start
            while True:
                nxt = outgoing.get(current)
                if not nxt:
                    loop = None   # Open chain: nothing to cap.
                    break
                current, _ = nxt.pop()
                if current == start:
                    break
                loop.append(current)
            if loop:
                loops.append((loop, source))
    return loops
