# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Paint regions: which generated faces one click paints.

The unit of paint is a *surface*, never a single polygon: one surface
(front, back, top, bottom or edge) of one source face. A click on any
polygon of it paints all of it.

Flood fill ("paint the whole room") spreads across edges to
neighbouring polygons with the same surface type and orientation (walls
stay walls, floors stay floors). Rims separate the two sides of a sheet,
so filling the inside of a room never leaks outside.

Pure Python: the Blender side passes in plain arrays.
"""

from collections import deque

_FLAT = 0.7


def orientation(nz):
    if nz >= _FLAT:
        return 1
    if nz <= -_FLAT:
        return -1
    return 0


def _polys_of(targets, face_source, face_surface):
    return [i for i, key in enumerate(zip(face_source, face_surface)) if key in targets]


def surface_region(hit, face_source, face_surface):
    """Polygons and paint targets ``{(source face, surface)}`` of the surface under ``hit``."""
    targets = {(face_source[hit], face_surface[hit])}
    return _polys_of(targets, face_source, face_surface), targets


def face_adjacency(face_edges):
    """Neighbour sets from per-face edge ids (faces sharing an edge)."""
    by_edge = {}
    for f, edges in enumerate(face_edges):
        for e in edges:
            by_edge.setdefault(e, []).append(f)
    neighbours = [set() for _ in face_edges]
    for faces in by_edge.values():
        for f in faces:
            neighbours[f].update(g for g in faces if g != f)
    return neighbours


def flood_region(hit, face_source, face_surface, face_nz, neighbours):
    """Polygons and paint targets reachable from ``hit`` through similar surfaces."""
    def kind(f):
        return face_surface[f], orientation(face_nz[f])

    start = kind(hit)
    seen = {hit}
    queue = deque([hit])
    while queue:
        f = queue.popleft()
        for g in neighbours[f]:
            if g not in seen and kind(g) == start:
                seen.add(g)
                queue.append(g)
    targets = {(face_source[f], face_surface[f]) for f in seen}
    return _polys_of(targets, face_source, face_surface), targets


def edges_of_faces(faces):
    """Per-face undirected edge keys, for meshes given as vertex loops."""
    return [[(min(a, b), max(a, b)) for a, b in zip(face, face[1:] + face[:1])]
            for face in (list(f) for f in faces)]
