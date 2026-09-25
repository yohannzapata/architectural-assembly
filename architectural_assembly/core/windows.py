# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows: a sheet of pane faces that cuts a wall and grows its own frame.

A window is modelled like everything else here, as plain faces. Each face
of the window sheet is one pane, and it can be any convex shape: a skewed
quad, a trapezoid, a triangle. Move, scale or reshape the sheet and the wall
opening, frame, mullions and glass follow:

- The wall faces it lies on are cut by the window's outline.
- Every pane edge that has no pane on the other side gets a frame of
  ``frame_width``. Edges shared with another pane get half a
  ``mullion_width`` from each side, so together they make one mullion.
- The frame is a thick sheet of strips around every pane, the glass is a
  thin sheet inside them, both thickened by the normal solidify engine.

The cut follows the convex hull of the panes. Concave panes are not supported.
"""

import math
from dataclasses import dataclass, field

from . import vec3 as v3
from .anchors import face_frame
from .sheet import SheetMesh, SolidifySettings
from .shell import ShellMesh, build_shell

_EPS = 1e-9
_MIN_AREA = 1e-8
_EDGE_TOL = 1e-4
_MITER_LIMIT = 4.0


@dataclass
class WindowSettings:
    frame_width: float = 0.06
    frame_depth: float = 0.08
    mullion_width: float = 0.03
    glass_thickness: float = 0.01
    rebate: float = 0.01      # How far the glass tucks into the frame.


@dataclass
class WindowSpec:
    """A window in the space of the sheet it belongs to (the host's local space)."""
    polygons: list                      # pane faces, [[(x, y, z)]]
    settings: WindowSettings = field(default_factory=WindowSettings)


class WindowPlane:
    """The plane shared by a window's panes, with the panes as 2D polygons on it."""

    def __init__(self, origin, u, v, n, panes):
        self.origin, self.u, self.v, self.n = origin, u, v, n
        self.panes = panes   # [[(a, b)]], each counter-clockwise seen from +n

    def point(self, a, b, d=0.0):
        p = v3.add(self.origin, v3.add(v3.scale(self.u, a), v3.scale(self.v, b)))
        return v3.add(p, v3.scale(self.n, d))

    def outline(self):
        """The convex hull of all panes, counter-clockwise, in plane coordinates."""
        return _hull([p for pane in self.panes for p in pane])


def analyse(spec):
    """Fit a ``WindowPlane`` to the panes. None if the window is degenerate."""
    polys = [p for p in spec.polygons if len(p) >= 3]
    if not polys:
        return None
    normal = (0.0, 0.0, 0.0)
    for p in polys:
        pn = v3.polygon_normal(p)
        if v3.dot(pn, normal) < 0.0:
            pn = v3.scale(pn, -1.0)
        normal = v3.add(normal, pn)
    n = v3.normalize(normal)
    if v3.length(n) < 0.5:
        return None
    pts = [q for p in polys for q in p]
    origin = v3.scale(_sum(pts), 1.0 / len(pts))
    u = v3.cross((0.0, 0.0, 1.0), n)
    if v3.length(u) < 1e-6:
        u = (1.0, 0.0, 0.0)
    u = v3.normalize(u)
    v = v3.cross(n, u)
    panes = []
    for p in polys:
        pane = [(v3.dot(v3.sub(q, origin), u), v3.dot(v3.sub(q, origin), v)) for q in p]
        area = _area2(pane)
        if abs(area) < _MIN_AREA:
            continue
        panes.append(pane if area > 0.0 else pane[::-1])
    if not panes:
        return None
    return WindowPlane(origin, u, v, n, panes)


def _sum(points):
    x = y = z = 0.0
    for p in points:
        x += p[0]
        y += p[1]
        z += p[2]
    return (x, y, z)


# -- 2D helpers ---------------------------------------------------------------------

def _area2(poly):
    """Signed area of a 2D polygon (positive when counter-clockwise)."""
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))


def _hull(points):
    """Convex hull (monotone chain), counter-clockwise, without collinear points."""
    pts = sorted(set((round(p[0], 9), round(p[1], 9)) for p in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _dist_to_segment(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    length2 = ab[0] * ab[0] + ab[1] * ab[1]
    if length2 < _EPS:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2))
    return math.hypot(p[0] - (a[0] + t * ab[0]), p[1] - (a[1] + t * ab[1]))


def _shared_edges(panes):
    """Per pane, per edge: True when another pane lies on the other side of it."""
    result = []
    for i, pane in enumerate(panes):
        flags = []
        for a, b in zip(pane, pane[1:] + pane[:1]):
            mid = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            flags.append(any(
                _dist_to_segment(mid, c, d) < _EDGE_TOL
                for j, other in enumerate(panes) if j != i
                for c, d in zip(other, other[1:] + other[:1])))
        result.append(flags)
    return result


def _inset(poly, dists):
    """Move every edge of a counter-clockwise polygon inwards by its own distance.

    Returns the new polygon, or None when it collapses (the bars are wider than the pane).
    """
    n = len(poly)
    lines = []   # Per edge: inward unit normal and a point on the moved edge.
    for k in range(n):
        a, b = poly[k], poly[(k + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < _EPS:
            return None
        nx, ny = -dy / length, dx / length
        lines.append(((nx, ny), (a[0] + nx * dists[k], a[1] + ny * dists[k])))
    out = []
    for k in range(n):
        (n0, p0), (n1, p1) = lines[k - 1], lines[k]
        det = n0[0] * n1[1] - n0[1] * n1[0]
        if abs(det) < 1e-9:   # Collinear edges: just offset the vertex.
            q = (poly[k][0] + n1[0] * dists[k], poly[k][1] + n1[1] * dists[k])
        else:
            c0 = n0[0] * p0[0] + n0[1] * p0[1]
            c1 = n1[0] * p1[0] + n1[1] * p1[1]
            q = ((c0 * n1[1] - c1 * n0[1]) / det, (n0[0] * c1 - n1[0] * c0) / det)
            reach = math.hypot(q[0] - poly[k][0], q[1] - poly[k][1])
            limit = _MITER_LIMIT * max(dists[k - 1], dists[k])
            if reach > limit > 0.0:
                s = limit / reach
                q = (poly[k][0] + (q[0] - poly[k][0]) * s, poly[k][1] + (q[1] - poly[k][1]) * s)
        out.append(q)
    if _area2(out) < _MIN_AREA:
        return None
    for k in range(n):   # An edge that turned around means the polygon inverted.
        a, b = poly[k], poly[(k + 1) % n]
        c, d = out[k], out[(k + 1) % n]
        if (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1]) <= 0.0:
            return None
    return out


# -- cutting openings in walls ---------------------------------------------------------

def _clip(poly, coord, c, below):
    """Sutherland-Hodgman clip of a convex 3D polygon against ``coord(p) <= c`` (or ``>=``)."""
    def inside(p):
        return coord(p) <= c + _EPS if below else coord(p) >= c - _EPS
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        ia, ib = inside(a), inside(b)
        if ia:
            out.append(a)
        if ia != ib:
            ca, cb = coord(a), coord(b)
            t = (c - ca) / (cb - ca)
            out.append(v3.add(a, v3.scale(v3.sub(b, a), t)))
    return out


def _area3(poly):
    return 0.5 * v3.length(v3.polygon_normal(poly)) if len(poly) >= 3 else 0.0


def _subtract_convex(poly, hole, cu, cv):
    """Cut the convex 2D polygon ``hole`` (counter-clockwise, in ``(cu, cv)`` coordinates) out
    of the convex 3D polygon ``poly``. Returns the convex pieces left over."""
    rest = poly
    pieces = []
    for a, b in zip(hole, hole[1:] + hole[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]

        def side(p, a=a, ex=ex, ey=ey):   # > 0 on the inside of this edge.
            return ex * (cv(p) - a[1]) - ey * (cu(p) - a[0])
        outside = _clip(rest, side, 0.0, True)
        if _area3(outside) > _MIN_AREA:
            pieces.append(outside)
        rest = _clip(rest, side, 0.0, False)
        if _area3(rest) <= _MIN_AREA:
            break
    if _area3(rest) <= _MIN_AREA:
        return [poly]   # The hole doesn't touch this polygon.
    return pieces


def cut_openings(sheet, windows, settings=None, reach=0.05):
    """Cut every window's outline out of the wall faces it lies on.

    Returns ``(sheet, origin)``: the new sheet and, per new face, the index of
    the face of the input it came from. Faces are cut only when they are
    parallel to the window and the window is within one thickness of them.
    Wall faces are expected to be convex.
    """
    settings = settings or SolidifySettings()
    planes = [w for w in (analyse(s) for s in windows) if w is not None]
    if not planes:
        return sheet, list(range(len(sheet.faces)))

    positions = list(sheet.positions)
    lookup = {}
    faces, origin = [], []
    for f, face in enumerate(sheet.faces):
        polys = [[sheet.positions[i] for i in face]]
        cuts = []
        if len(face) >= 3:
            o, t, b, n = face_frame(sheet, f)
            reach_f = sheet.thickness(f, settings.thickness) + reach
            cuts = _openings_on_face(planes, o, t, b, n, reach_f)
        if not cuts:
            faces.append(list(face))
            origin.append(f)
            continue
        for hole in cuts:
            def cu(p, o=o, t=t):
                return v3.dot(v3.sub(p, o), t)

            def cv(p, o=o, b=b):
                return v3.dot(v3.sub(p, o), b)
            polys = [q for p in polys for q in _subtract_convex(p, hole, cu, cv)]
        for p in polys:
            ids = []
            for q in p:
                key = tuple(round(c, 9) for c in q)
                if key not in lookup:
                    lookup[key] = len(positions)
                    positions.append(tuple(q))
                ids.append(lookup[key])
            faces.append(ids)
            origin.append(f)

    def pick(values, default):
        return [values[o] if o < len(values) else default for o in origin] if values else []

    cut = SheetMesh(
        positions=positions,
        faces=faces,
        face_thickness=pick(sheet.face_thickness, 0.0),
        face_material=pick(sheet.face_material, 0),
        face_paint=pick(sheet.face_paint, ()),
        face_uids=pick(sheet.face_uids, 0),
    )
    return cut, origin


def _openings_on_face(planes, o, t, b, n, reach):
    """Each window that lies on this wall face, as a hole polygon in the face's (t, b) coordinates."""
    holes = []
    for w in planes:
        if abs(v3.dot(w.n, n)) < 0.999:
            continue
        if abs(v3.dot(v3.sub(w.origin, o), n)) > reach:
            continue
        outline = w.outline()
        if len(outline) < 3:
            continue
        hole = []
        for a, c in outline:
            p = v3.sub(w.point(a, c), o)
            hole.append((v3.dot(p, t), v3.dot(p, b)))
        if _area2(hole) < 0.0:   # Mirrored when the window faces the other way.
            hole.reverse()
        holes.append(hole)
    return holes


# -- the window's own geometry ----------------------------------------------------------

def _poly_sheet(plane, polys, material):
    positions, faces, lookup = [], [], {}
    for poly in polys:
        ids = []
        for a, b in poly:
            key = (round(a, 9), round(b, 9))
            if key not in lookup:
                lookup[key] = len(positions)
                positions.append(plane.point(a, b))
            ids.append(lookup[key])
        faces.append(ids)
    return SheetMesh(positions=positions, faces=faces, face_material=[material] * len(faces))


def build_window_shell(spec, frame_material=0, glass_material=1):
    """Frame, mullions and glass for one window, as a ``ShellMesh`` (or None)."""
    plane = analyse(spec)
    if plane is None:
        return None
    s = spec.settings
    shared = _shared_edges(plane.panes)
    frame, glass = [], []
    for pane, flags in zip(plane.panes, shared):
        dists = [s.mullion_width * 0.5 if f else s.frame_width for f in flags]
        inner = _inset(pane, dists)
        if inner is None:
            frame.append(pane)   # Bars fill the whole pane: solid, no glass.
            continue
        for k in range(len(pane)):
            j = (k + 1) % len(pane)
            frame.append([pane[k], pane[j], inner[j], inner[k]])
        tucked = _inset(pane, [max(d - s.rebate, 1e-4) for d in dists])
        if tucked is not None:
            glass.append(tucked)
    out = ShellMesh()
    if frame:
        _append(out, build_shell(_poly_sheet(plane, frame, frame_material),
                                 SolidifySettings(thickness=s.frame_depth, offset=0.0)))
    if glass:
        _append(out, build_shell(_poly_sheet(plane, glass, glass_material),
                                 SolidifySettings(thickness=s.glass_thickness, offset=0.0)))
    return out


def _append(dst, src):
    base = len(dst.vertices)
    dst.vertices += src.vertices
    dst.faces += [tuple(i + base for i in f) for f in src.faces]
    dst.face_surface += src.face_surface
    dst.face_source += [-1] * len(src.faces)   # Not a source face: can't be painted.
    dst.face_uid += [0] * len(src.faces)
    dst.face_material += src.face_material
    dst.face_uvs += src.face_uvs


def build_assembly(sheet, settings, openings=()):
    """``build_shell`` with the openings of the given windows cut out of the walls.

    The windows draw themselves (``build_window_shell``), so the result only
    holds wall geometry. ``face_source`` keeps pointing at the faces of ``sheet``.
    """
    openings = list(openings)
    if not openings:
        return build_shell(sheet, settings)
    cut, origin = cut_openings(sheet, openings, settings)
    shell = build_shell(cut, settings)
    shell.face_source = [origin[s] for s in shell.face_source]
    return shell
