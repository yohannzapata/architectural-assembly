# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Small 3D vector helpers on plain tuples.

``core`` avoids ``mathutils`` on purpose so it runs, and is tested, on a
stock Python interpreter outside Blender.
"""

import math

EPS = 1e-12


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a):
    return math.sqrt(dot(a, a))


def normalize(a):
    n = length(a)
    if n < EPS:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def polygon_normal(points):
    """Unnormalised Newell normal; its length is twice the polygon area."""
    nx = ny = nz = 0.0
    count = len(points)
    for i in range(count):
        x0, y0, z0 = points[i]
        x1, y1, z1 = points[(i + 1) % count]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return (nx, ny, nz)


def solve3(m, b):
    """Solve the 3x3 system ``m @ x = b`` (``m`` as rows). None if singular."""
    (a11, a12, a13), (a21, a22, a23), (a31, a32, a33) = m
    det = (a11 * (a22 * a33 - a23 * a32)
           - a12 * (a21 * a33 - a23 * a31)
           + a13 * (a21 * a32 - a22 * a31))
    if abs(det) < 1e-18:
        return None
    b1, b2, b3 = b
    x = (b1 * (a22 * a33 - a23 * a32)
         - a12 * (b2 * a33 - a23 * b3)
         + a13 * (b2 * a32 - a22 * b3)) / det
    y = (a11 * (b2 * a33 - a23 * b3)
         - b1 * (a21 * a33 - a23 * a31)
         + a13 * (a21 * b3 - b2 * a31)) / det
    z = (a11 * (a22 * b3 - b2 * a32)
         - a12 * (a21 * b3 - b2 * a31)
         + b1 * (a21 * a32 - a22 * a31)) / det
    return (x, y, z)
