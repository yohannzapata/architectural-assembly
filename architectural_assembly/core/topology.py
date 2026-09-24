# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Topology analysis: which face sides share a generated vertex.

Every source face has two sides: FRONT (along its normal) and BACK. Around
each source edge shared by two or more faces, the faces are sorted by the
angle at which they leave the edge. Neighbouring faces enclose a wedge of
space. The two sides facing into the same wedge belong together, so at both
ends of the edge they must use the same generated vertex.

Doing this with union-find over all edges splits the face sides at each
source vertex into "cells". One cell becomes one output vertex. The rule
is purely geometric, so it works the same for:

  * flat panels and L-corners (2 faces per edge -> 2 wedges),
  * T-junctions and crossings (3+ faces per edge -> 3+ wedges),
  * faces with inconsistent normals (the wedge decides, not the normal).

Edges with a single face are open. Their two sides stay apart, and the
shell builder closes them with rim faces.
"""

import math
from dataclasses import dataclass

from . import vec3 as v3

FRONT = 0
BACK = 1


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        parent = self.parent
        root = parent.setdefault(x, x)
        while root != parent[root]:
            root = parent[root]
        while x != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


@dataclass
class Topology:
    normals: list      # unit normal per source face (zero for degenerate faces)
    valid: list        # per face: usable (>= 3 verts, non-zero area)
    edge_faces: dict   # (a, b) with a < b -> [(face, forward)]; forward: face runs a -> b
    cells: dict        # (vertex, face * 2 + side) -> cell id


def face_side(face, side):
    return face * 2 + side


def analyse(sheet):
    positions = sheet.positions
    normals, valid = [], []
    for face in sheet.faces:
        if len(face) < 3 or len(set(face)) < 3:
            normals.append((0.0, 0.0, 0.0))
            valid.append(False)
            continue
        n = v3.polygon_normal([positions[i] for i in face])
        ok = v3.length(n) > 1e-12
        normals.append(v3.normalize(n))
        valid.append(ok)

    edge_faces = {}
    for f, face in enumerate(sheet.faces):
        if not valid[f]:
            continue
        count = len(face)
        for i in range(count):
            a, b = face[i], face[(i + 1) % count]
            if a == b:
                continue
            key = (a, b) if a < b else (b, a)
            edge_faces.setdefault(key, []).append((f, a < b))

    uf = _UnionFind()
    for f, face in enumerate(sheet.faces):
        if valid[f]:
            for v in face:
                uf.find((v, face_side(f, FRONT)))
                uf.find((v, face_side(f, BACK)))

    for (a, b), incident in edge_faces.items():
        if len(incident) < 2:
            continue
        for fs_i, fs_j in _wedge_pairs(positions[a], positions[b], incident, normals):
            uf.union((a, fs_i), (a, fs_j))
            uf.union((b, fs_i), (b, fs_j))

    cells = {node: uf.find(node) for node in uf.parent}
    return Topology(normals=normals, valid=valid, edge_faces=edge_faces, cells=cells)


def _wedge_pairs(pa, pb, incident, normals):
    """Yield (face side, face side) pairs that face into the same wedge."""
    axis = v3.normalize(v3.sub(pb, pa))
    wings = []
    for f, forward in incident:
        n = normals[f]
        # Direction from the edge into the face, perpendicular to the edge.
        inward = v3.cross(n, axis) if forward else v3.cross(axis, n)
        inward = v3.normalize(v3.sub(inward, v3.scale(axis, v3.dot(inward, axis))))
        wings.append((f, inward, n))

    ref = wings[0][1]
    ref_perp = v3.cross(axis, ref)
    ordered = sorted(
        wings,
        key=lambda w: (math.atan2(v3.dot(w[1], ref_perp), v3.dot(w[1], ref)) % (2.0 * math.pi), w[0]),
    )
    count = len(ordered)
    for i in range(count):
        f_i, w_i, n_i = ordered[i]
        f_j, w_j, n_j = ordered[(i + 1) % count]
        # Side of f_i that faces the direction of increasing angle...
        side_i = FRONT if v3.dot(n_i, v3.cross(axis, w_i)) > 0.0 else BACK
        # ...and the side of the next face that looks back at it.
        side_j = FRONT if v3.dot(n_j, v3.cross(axis, w_j)) < 0.0 else BACK
        yield face_side(f_i, side_i), face_side(f_j, side_j)
