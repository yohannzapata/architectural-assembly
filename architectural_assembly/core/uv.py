# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""World-scale UVs: 1 UV unit = 1 metre, so tiling textures line up
across every part of an assembly without unwrapping."""

from . import vec3 as v3

_FLAT_THRESHOLD = 0.7


def world_uvs(points, normal):
    nz = normal[2]
    if nz >= _FLAT_THRESHOLD:       # Faces up: plan view.
        return [(p[0], p[1]) for p in points]
    if nz <= -_FLAT_THRESHOLD:      # Faces down: mirrored so it reads correctly from below.
        return [(p[0], -p[1]) for p in points]
    # Wall-like: u runs to the viewer's right when looking at the face, v is height.
    right = v3.normalize((-normal[1], normal[0], 0.0))
    return [(p[0] * right[0] + p[1] * right[1], p[2]) for p in points]
