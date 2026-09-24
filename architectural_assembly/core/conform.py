# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Makes touching faces share topology before thickening.

Builders model freely. Two walls may meet at a corner with different
subdivisions (one split for a door, the other for a window), or have
duplicate vertices at a joint that were never merged. Geometrically they
touch, but topologically they don't, so they would thicken into
overlapping boxes instead of one clean joint.

``conform`` fixes that without changing the source object:

1. Weld: vertices at the same position (within ``tolerance``) become one.
2. Split: a vertex lying on another face's edge is inserted into that
   face's loop ("T-vertex" repair), so both faces share the edge pieces.

Face indices are preserved, so paint and ids keep pointing at the right
source faces.
"""

import math

from . import vec3 as v3


def conform(sheet, tolerance=1e-4):
    positions, remap = _weld(sheet.positions, tolerance)
    faces = [_dedupe_loop([remap[v] for v in face]) for face in sheet.faces]
    faces = _split_t_vertices(positions, faces, tolerance)
    return sheet.__class__(
        positions=positions,
        faces=faces,
        face_thickness=sheet.face_thickness,
        face_material=sheet.face_material,
        face_paint=sheet.face_paint,
        face_uids=sheet.face_uids,
    )


def _weld(positions, tol):
    inv = 1.0 / tol
    grid = {}
    out, remap = [], []
    for p in positions:
        key = (math.floor(p[0] * inv), math.floor(p[1] * inv), math.floor(p[2] * inv))
        found = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for idx in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if v3.length(v3.sub(out[idx], p)) <= tol:
                            found = idx
                            break
                    if found is not None:
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            found = len(out)
            out.append(tuple(p))
            grid.setdefault(key, []).append(found)
        remap.append(found)
    return out, remap


def _dedupe_loop(loop):
    cleaned = []
    for v in loop:
        if not cleaned or cleaned[-1] != v:
            cleaned.append(v)
    while len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def _split_t_vertices(positions, faces, tol):
    used = sorted({v for face in faces for v in face})
    if not used:
        return faces
    # Spatial hash sized from the typical edge length.
    lengths = sorted(
        v3.length(v3.sub(positions[a], positions[b]))
        for face in faces for a, b in zip(face, face[1:] + face[:1]) if a != b)
    cell = max(lengths[len(lengths) // 2] if lengths else 1.0, tol * 10)
    grid = {}
    for v in used:
        key = tuple(math.floor(c / cell) for c in positions[v])
        grid.setdefault(key, []).append(v)

    splits_cache = {}

    def splits(a, b):
        key = (a, b) if a < b else (b, a)
        if key not in splits_cache:
            splits_cache[key] = _points_on_segment(positions, grid, cell, key[0], key[1], tol)
        found = splits_cache[key]   # sorted from key[0] to key[1]
        return found if key[0] == a else list(reversed(found))

    result = []
    for face in faces:
        if len(face) < 3:
            result.append(face)
            continue
        new_loop = []
        for a, b in zip(face, face[1:] + face[:1]):
            new_loop.append(a)
            new_loop.extend(v for v in splits(a, b) if v not in face)
        result.append(new_loop)
    return result


def _points_on_segment(positions, grid, cell, a, b, tol):
    pa, pb = positions[a], positions[b]
    d = v3.sub(pb, pa)
    seg_len = v3.length(d)
    if seg_len <= tol:
        return []
    u = v3.scale(d, 1.0 / seg_len)
    lo = [math.floor((min(pa[i], pb[i]) - tol) / cell) for i in range(3)]
    hi = [math.floor((max(pa[i], pb[i]) + tol) / cell) for i in range(3)]
    hits = []
    for x in range(lo[0], hi[0] + 1):
        for y in range(lo[1], hi[1] + 1):
            for z in range(lo[2], hi[2] + 1):
                for v in grid.get((x, y, z), ()):
                    if v in (a, b):
                        continue
                    rel = v3.sub(positions[v], pa)
                    t = v3.dot(rel, u)
                    if tol < t < seg_len - tol:
                        off = v3.sub(rel, v3.scale(u, t))
                        if v3.length(off) <= tol:
                            hits.append((t, v))
    hits.sort()
    return [v for _, v in hits]
