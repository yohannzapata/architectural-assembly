# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers: build test sheets and check mesh invariants."""

import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SheetBuilder:
    """Builds a SheetMesh with welded vertices from panels and polygons."""

    def __init__(self):
        self.positions = []
        self.faces = []
        self._lookup = {}

    def vert(self, p):
        key = tuple(round(c, 9) for c in p)
        idx = self._lookup.get(key)
        if idx is None:
            idx = len(self.positions)
            self.positions.append(tuple(float(c) for c in p))
            self._lookup[key] = idx
        return idx

    def poly(self, points):
        self.faces.append([self.vert(p) for p in points])
        return len(self.faces) - 1

    def panel(self, p0, p1, height, z0=0.0):
        """Vertical wall panel standing on the segment p0 -> p1."""
        (x0, y0), (x1, y1) = p0, p1
        return self.poly([(x0, y0, z0), (x1, y1, z0), (x1, y1, z0 + height), (x0, y0, z0 + height)])

    def sheet(self, **kw):
        from architectural_assembly.core import SheetMesh
        return SheetMesh(positions=self.positions, faces=self.faces, **kw)


def signed_volume(mesh):
    vol = 0.0
    for face in mesh.faces:
        p0 = mesh.vertices[face[0]]
        for i in range(1, len(face) - 1):
            p1, p2 = mesh.vertices[face[i]], mesh.vertices[face[i + 1]]
            vol += (p0[0] * (p1[1] * p2[2] - p1[2] * p2[1])
                    - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
                    + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0]))
    return vol / 6.0


def half_edges(mesh):
    return Counter((f[i], f[(i + 1) % len(f)]) for f in mesh.faces for i in range(len(f)))


def euler_characteristic(mesh):
    return len(mesh.vertices) - len(half_edges(mesh)) // 2 + len(mesh.faces)


class MeshAssertions:
    def assertClosedManifold(self, mesh):
        he = half_edges(mesh)
        dup = [e for e, c in he.items() if c > 1]
        self.assertFalse(dup, f"non-manifold or inconsistently wound half-edges: {dup[:5]}")
        open_edges = [e for e in he if (e[1], e[0]) not in he]
        self.assertFalse(open_edges, f"open boundary: {open_edges[:5]}")

    def assertConsistentArrays(self, mesh):
        n = len(mesh.faces)
        for name in ("face_surface", "face_source", "face_uid", "face_material"):
            self.assertEqual(len(getattr(mesh, name)), n, name)
        self.assertEqual([len(u) for u in mesh.face_uvs], [len(f) for f in mesh.faces])
