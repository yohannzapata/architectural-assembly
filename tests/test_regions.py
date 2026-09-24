# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from architectural_assembly.core import SolidifySettings, Surface, build_shell, regions
from architectural_assembly.core import vec3 as v3
from helpers import SheetBuilder


def room_shell():
    """Closed 6 x 4 room; winding makes every wall's FRONT face the inside."""
    b = SheetBuilder()
    pts = [(0, 0), (0, 4), (6, 4), (6, 0)]   # clockwise from above -> normals point inward
    for i in range(4):
        b.panel(pts[i], pts[(i + 1) % 4], 3.0)
    return build_shell(b.sheet(), SolidifySettings(thickness=0.2))


def arrays(mesh):
    nz = [v3.normalize(v3.polygon_normal([mesh.vertices[i] for i in f]))[2] for f in mesh.faces]
    neighbours = regions.face_adjacency(regions.edges_of_faces(mesh.faces))
    return mesh.face_source, mesh.face_surface, nz, neighbours


def is_inside(mesh, poly):
    return all(0.0 < mesh.vertices[i][0] < 6.0 and 0.0 < mesh.vertices[i][1] < 4.0
               for i in mesh.faces[poly])


class TestRegions(unittest.TestCase):
    def test_single_click_paints_one_surface(self):
        mesh = room_shell()
        hit = mesh.face_surface.index(Surface.FRONT)
        polys, targets = regions.surface_region(hit, mesh.face_source, mesh.face_surface)
        self.assertEqual(targets, {(mesh.face_source[hit], Surface.FRONT)})
        self.assertEqual(polys, [hit])

    def test_flood_fills_room_inside_only(self):
        mesh = room_shell()
        source, surface, nz, neighbours = arrays(mesh)
        hit = next(i for i, s in enumerate(surface) if s == Surface.FRONT and is_inside(mesh, i))
        polys, targets = regions.flood_region(hit, source, surface, nz, neighbours)
        self.assertEqual(len(targets), 4)                         # all four walls...
        self.assertTrue(all(surf == Surface.FRONT for _, surf in targets))
        self.assertTrue(all(is_inside(mesh, p) for p in polys))   # ...inside only

    def test_flood_on_outside_stays_outside(self):
        mesh = room_shell()
        source, surface, nz, neighbours = arrays(mesh)
        hit = next(i for i, s in enumerate(surface) if s == Surface.BACK)
        polys, targets = regions.flood_region(hit, source, surface, nz, neighbours)
        self.assertEqual(len(targets), 4)
        self.assertFalse(any(is_inside(mesh, p) for p in polys))

    def test_flood_on_top_rim_stays_on_tops(self):
        mesh = room_shell()
        source, surface, nz, neighbours = arrays(mesh)
        hit = surface.index(Surface.TOP)
        polys, _ = regions.flood_region(hit, source, surface, nz, neighbours)
        self.assertTrue(all(surface[p] == Surface.TOP for p in polys))
        self.assertEqual(len(polys), 4)


if __name__ == "__main__":
    unittest.main()
