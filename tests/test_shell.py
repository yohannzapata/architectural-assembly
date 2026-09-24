# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import math
import unittest
from collections import Counter

from architectural_assembly.core import SolidifySettings, Surface, build_shell
from helpers import MeshAssertions, SheetBuilder, euler_characteristic, signed_volume

H = 3.0
T = 0.2
SETTINGS = SolidifySettings(thickness=T)


class TestPanels(unittest.TestCase, MeshAssertions):
    def test_single_panel_is_a_closed_box(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertEqual(len(mesh.vertices), 8)
        self.assertClosedManifold(mesh)
        self.assertConsistentArrays(mesh)
        self.assertAlmostEqual(signed_volume(mesh), 4 * H * T, places=6)
        self.assertEqual(Counter(mesh.face_surface), {
            Surface.FRONT: 1, Surface.BACK: 1, Surface.TOP: 1, Surface.BOTTOM: 1, Surface.EDGE: 2})

    def test_front_follows_face_normal(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)   # Winding gives normal -Y.
        mesh = build_shell(b.sheet(), SETTINGS)
        for face, surf in zip(mesh.faces, mesh.face_surface):
            ys = {round(mesh.vertices[i][1], 6) for i in face}
            if surf == Surface.FRONT:
                self.assertEqual(ys, {-T / 2})
            elif surf == Surface.BACK:
                self.assertEqual(ys, {T / 2})

    def test_offset_moves_thickness_to_one_side(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        mesh = build_shell(b.sheet(), SolidifySettings(thickness=T, offset=1.0))
        ys = sorted({round(v[1], 6) for v in mesh.vertices})
        self.assertEqual(ys, [-T, 0.0])   # Grows along the normal (-Y) only.

    def test_panel_with_window_opening(self):
        # 3 x 3 grid panel with the middle cell removed.
        b = SheetBuilder()
        xs, zs = [0, 1, 2, 3], [0, 1, 2, 3]
        for i in range(3):
            for j in range(3):
                if (i, j) == (1, 1):
                    continue
                x0, x1, z0, z1 = xs[i], xs[i + 1], zs[j], zs[j + 1]
                b.poly([(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)])
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertEqual(euler_characteristic(mesh), 0)   # A frame: genus 1.
        self.assertAlmostEqual(signed_volume(mesh), (9 - 1) * T, places=6)
        # Opening rims: sill faces up, lintel faces down, two jambs.
        inner = [s for f, s in zip(mesh.faces, mesh.face_surface)
                 if s in (Surface.TOP, Surface.BOTTOM, Surface.EDGE)
                 and all(1 - 1e-6 <= mesh.vertices[i][0] <= 2 + 1e-6 and
                         1 - 1e-6 <= mesh.vertices[i][2] <= 2 + 1e-6 for i in f)]
        self.assertEqual(Counter(inner), {Surface.TOP: 1, Surface.BOTTOM: 1, Surface.EDGE: 2})

    def test_gable_panel(self):
        b = SheetBuilder()
        b.poly([(0, 0, 0), (4, 0, 0), (4, 0, 2.5), (2, 0, 4.5), (0, 0, 2.5)])
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        area = 4 * 2.5 + 0.5 * 4 * 2
        self.assertAlmostEqual(signed_volume(mesh), area * T, places=6)


class TestJunctions(unittest.TestCase, MeshAssertions):
    def test_l_corner(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        b.panel((0, 3), (0, 0), H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        h = T / 2
        area = (4 + h) * T + T * (3 + h) - T * T
        self.assertAlmostEqual(signed_volume(mesh), area * H, places=6)

    def test_t_junction_gets_caps(self):
        b = SheetBuilder()
        b.panel((-3, 0), (0, 0), H)
        b.panel((0, 0), (3, 0), H)
        b.panel((0, 0), (0, 2), H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        area = 6 * T + T * (2 - T / 2)
        self.assertAlmostEqual(signed_volume(mesh), area * H, places=6)

    def test_crossing(self):
        b = SheetBuilder()
        for end in ((2, 0), (0, 2), (-2, 0), (0, -2)):
            b.panel((0, 0), end, H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertAlmostEqual(signed_volume(mesh), (8 * T - T * T) * H, places=6)

    def test_room_ring(self):
        b = SheetBuilder()
        pts = [(0, 0), (6, 0), (6, 4), (0, 4)]
        for i in range(4):
            b.panel(pts[i], pts[(i + 1) % 4], H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertEqual(euler_characteristic(mesh), 0)
        outer = (6 + T) * (4 + T) - (6 - T) * (4 - T)
        self.assertAlmostEqual(signed_volume(mesh), outer * H, places=6)

    def test_room_with_partition(self):
        b = SheetBuilder()
        loop = [(0, 0), (2, 0), (6, 0), (6, 4), (2, 4), (0, 4)]
        for i in range(6):
            b.panel(loop[i], loop[(i + 1) % 6], H)
        b.panel((2, 0), (2, 4), H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertEqual(euler_characteristic(mesh), -2)
        outer = (6 + T) * (4 + T) - (6 - T) * (4 - T)
        self.assertAlmostEqual(signed_volume(mesh), (outer + T * (4 - T)) * H, places=6)

    def test_inconsistent_normals_still_join(self):
        b = SheetBuilder()
        pts = [(0, 0), (6, 0), (6, 4), (0, 4)]
        for i in range(4):
            if i == 2:
                b.panel(pts[(i + 1) % 4], pts[i], H)   # Reversed winding.
            else:
                b.panel(pts[i], pts[(i + 1) % 4], H)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        outer = (6 + T) * (4 + T) - (6 - T) * (4 - T)
        self.assertAlmostEqual(abs(signed_volume(mesh)), outer * H, places=6)

    def test_floor_meets_wall(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        b.poly([(0, 0, 0), (0, 3, 0), (4, 3, 0), (4, 0, 0)])   # Floor slab behind the wall.
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)

    def test_mixed_thickness(self):
        b = SheetBuilder()
        b.panel((-3, 0), (0, 0), H)
        b.panel((0, 0), (3, 0), H)
        b.panel((0, 0), (0, 2), H)
        mesh = build_shell(b.sheet(face_thickness=[0, 0, 0.4]), SETTINGS)
        self.assertClosedManifold(mesh)

    def test_sharp_angle_respects_miter_limit(self):
        ang = math.radians(8)
        b = SheetBuilder()
        b.panel((3, 0), (0, 0), H)
        b.panel((0, 0), (3 * math.cos(ang), 3 * math.sin(ang)), H)
        mesh = build_shell(b.sheet(), SolidifySettings(thickness=T, miter_limit=3.0))
        self.assertClosedManifold(mesh)
        for x, y, _ in mesh.vertices:
            self.assertLessEqual(min(math.hypot(x, y), math.hypot(x - 3, y)), 3.0 * T + 1e-9)


class TestConform(unittest.TestCase, MeshAssertions):
    def test_corner_with_mismatched_splits_still_joins(self):
        # Front wall split at 2.1 (door height), side wall split at 1 and 2 (window):
        # the shared corner edge is subdivided differently on each side.
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), 2.1)
        b.panel((0, 0), (4, 0), 0.7, z0=2.1)
        b.panel((4, 0), (4, 3), 1.0)
        b.panel((4, 0), (4, 3), 1.0, z0=1.0)
        b.panel((4, 0), (4, 3), 0.8, z0=2.0)
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        h = T / 2
        area = (4 + h) * T + T * (3 + h) - T * T
        self.assertAlmostEqual(signed_volume(mesh), area * 2.8, places=6)

    def test_duplicate_vertices_are_welded(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        # Second panel built from its own, unmerged copies of the corner vertices.
        n = len(b.positions)
        b.positions += [(4, 0, 0), (4, 3, 0), (4, 3, H), (4, 0, H)]
        b.faces.append([n, n + 1, n + 2, n + 3])
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertEqual(Counter(mesh.face_surface)[Surface.EDGE], 2)   # joined: only 2 free ends

    def test_conform_can_be_disabled(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        n = len(b.positions)
        b.positions += [(4, 0, 0), (4, 3, 0), (4, 3, H), (4, 0, H)]
        b.faces.append([n, n + 1, n + 2, n + 3])
        mesh = build_shell(b.sheet(), SETTINGS, conform_input=False)
        self.assertEqual(Counter(mesh.face_surface)[Surface.EDGE], 4)   # two separate boxes


class TestMaterialsAndTags(unittest.TestCase, MeshAssertions):
    def test_paint_overrides_face_material_per_surface(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        # paint per surface: front, back, top, bottom, edge (slot + 1, 0 = unpainted)
        sheet = b.sheet(face_material=[2], face_paint=[(5, 0, 7, 0, 8)], face_uids=[42])
        mesh = build_shell(sheet, SETTINGS)
        by_surface = dict(zip(mesh.face_surface, mesh.face_material))
        self.assertEqual(by_surface[Surface.FRONT], 4)    # painted
        self.assertEqual(by_surface[Surface.BACK], 2)     # falls back to the face's material
        self.assertEqual(by_surface[Surface.TOP], 6)
        self.assertEqual(by_surface[Surface.BOTTOM], 2)
        self.assertEqual(by_surface[Surface.EDGE], 7)
        self.assertEqual(set(mesh.face_uid), {42})

    def test_degenerate_faces_are_ignored(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), H)
        b.faces.append([0, 1])        # Not a polygon.
        b.faces.append([0, 1, 1])     # Collapsed.
        mesh = build_shell(b.sheet(), SETTINGS)
        self.assertClosedManifold(mesh)
        self.assertEqual(set(mesh.face_source), {0})


if __name__ == "__main__":
    unittest.main()
