# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Surface anchors: the placement hook for doors, windows and attachments.

A component attached to an assembly doesn't store a world position. It
stores a ``SurfaceAnchor``: which source face (persistent uid), where on it
(u, v in metres), and which side. After the user reshapes or re-thickens
the assembly, resolving the anchor again puts the component back on the
same surface, flush with it.

Face frame: ``u`` runs horizontally (for floors and ceilings, along world
X). ``v`` runs up the face, and the origin is the face's first vertex.
"""

from dataclasses import dataclass

from . import vec3 as v3
from .sheet import SolidifySettings
from .shell import side_offsets
from .surfaces import Surface


@dataclass
class SurfaceAnchor:
    uid: int
    u: float
    v: float
    side: Surface = Surface.FRONT   # FRONT or BACK
    depth: float = 0.0              # Extra push away from the surface.


@dataclass
class SurfaceFrame:
    position: tuple
    tangent: tuple   # +u
    bitangent: tuple  # +v
    normal: tuple    # outward from the chosen side


def face_frame(sheet, f):
    pts = [sheet.positions[i] for i in sheet.faces[f]]
    n = v3.normalize(v3.polygon_normal(pts))
    tangent = v3.cross((0.0, 0.0, 1.0), n)
    if v3.length(tangent) < 1e-6:          # Horizontal face.
        tangent = (1.0, 0.0, 0.0) if n[2] > 0 else (-1.0, 0.0, 0.0)
    tangent = v3.normalize(tangent)
    bitangent = v3.cross(n, tangent)
    return pts[0], tangent, bitangent, n


def resolve_anchor(sheet, anchor, settings=None):
    """Return the ``SurfaceFrame`` for ``anchor``, or None if its face is gone."""
    settings = settings or SolidifySettings()
    try:
        f = sheet.face_uids.index(anchor.uid)
    except ValueError:
        return None
    origin, t, b, n = face_frame(sheet, f)
    front, back = side_offsets(sheet, settings, f)
    if anchor.side == Surface.BACK:
        dist, out = back - anchor.depth, v3.scale(n, -1.0)
    else:
        dist, out = front + anchor.depth, n
    pos = v3.add(origin, v3.add(v3.scale(t, anchor.u), v3.scale(b, anchor.v)))
    return SurfaceFrame(position=v3.add(pos, v3.scale(n, dist)),
                        tangent=t, bitangent=b, normal=out)
