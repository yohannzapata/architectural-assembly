# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from architectural_assembly.core import (
    SolidifySettings, WindowSettings, WindowSpec, build_assembly, build_window_shell, cut_openings)
from helpers import MeshAssertions, SheetBuilder, euler_characteristic, signed_volume

T = 0.2
SETTINGS = SolidifySettings(thickness=T)


def pane(x0, x1, z0, z1, y=0.0):
    return [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]


def wall():
    b = SheetBuilder()
    b.panel((0, 0), (4, 0), 3.0)
    return b.sheet()


class TestCutOpenings(unittest.TestCase, MeshAssertions):
    def test_window_cuts_a_hole_and_keeps_the_area(self):
        spec = WindowSpec([pane(1, 2, 1, 2)])
        sheet, origin = cut_openings(wall(), [spec], SETTINGS)
        self.assertEqual(set(origin), {0})
        self.assertEqual(len(sheet.faces), 4)
        mesh = build_assembly(wall(), SETTINGS, [WindowSpec([pane(1, 2, 1, 2)], WindowSettings())])
        cut_only = build_assembly_wall_only(spec)
        self.assertClosedManifold(cut_only)
        self.assertEqual(euler_characteristic(cut_only), 0)
        self.assertAlmostEqual(signed_volume(cut_only), (12 - 1) * T, places=6)
        self.assertTrue(mesh.faces)

    def test_window_on_the_edge_makes_a_notch(self):
        spec = WindowSpec([pane(-0.5, 1, 1, 2)])
        mesh = build_assembly_wall_only(spec)
        self.assertClosedManifold(mesh)
        self.assertAlmostEqual(signed_volume(mesh), (12 - 1 * 1) * T, places=6)

    def test_window_off_the_wall_plane_is_ignored(self):
        sheet, origin = cut_openings(wall(), [WindowSpec([pane(1, 2, 1, 2, y=2.0)])], SETTINGS)
        self.assertEqual(len(sheet.faces), 1)

    def test_window_far_from_wall_extent_is_ignored(self):
        sheet, _ = cut_openings(wall(), [WindowSpec([pane(10, 11, 1, 2)])], SETTINGS)
        self.assertEqual(len(sheet.faces), 1)

    def test_two_windows_on_one_wall(self):
        specs = [WindowSpec([pane(0.5, 1.5, 1, 2)]), WindowSpec([pane(2.5, 3.5, 1, 2)])]
        sheet, origin = cut_openings(wall(), specs, SETTINGS)
        mesh = build_assembly_wall_only(*specs)
        self.assertClosedManifold(mesh)
        self.assertAlmostEqual(signed_volume(mesh), (12 - 2) * T, places=6)

    def test_pieces_keep_face_data(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), 3.0)
        sheet = b.sheet(face_thickness=[0.3], face_material=[2], face_paint=[(1, 0, 0, 0, 0)],
                        face_uids=[7])
        cut, origin = cut_openings(sheet, [WindowSpec([pane(1, 2, 1, 2)])], SETTINGS)
        self.assertTrue(all(m == 2 for m in cut.face_material))
        self.assertTrue(all(t == 0.3 for t in cut.face_thickness))
        self.assertTrue(all(u == 7 for u in cut.face_uids))

    def test_shell_source_points_at_original_faces(self):
        mesh = build_assembly(wall(), SETTINGS, [WindowSpec([pane(1, 2, 1, 2)])])
        wall_faces = list(mesh.face_source)
        self.assertEqual(set(wall_faces), {0})
        self.assertNotIn(-1, mesh.face_source)   # Windows draw themselves.


def build_assembly_wall_only(*specs):
    """The wall with its openings, without the windows' own geometry."""
    from architectural_assembly.core import build_shell
    cut, origin = cut_openings(wall(), list(specs), SETTINGS)
    return build_shell(cut, SETTINGS)


class TestWindowShell(unittest.TestCase, MeshAssertions):
    def test_single_pane_is_frame_and_glass(self):
        s = WindowSettings()
        mesh = build_window_shell(WindowSpec([pane(1, 2, 1, 2)], s), frame_material=1, glass_material=2)
        self.assertClosedManifold(mesh)
        self.assertConsistentArrays(mesh)
        self.assertEqual({1, 2}, set(mesh.face_material))
        w = 1.0 - 2 * s.frame_width
        glass = (w + 2 * s.rebate) ** 2 * s.glass_thickness
        frame = (1.0 - w * w) * s.frame_depth
        self.assertAlmostEqual(signed_volume(mesh), glass + frame, places=6)

    def test_mullions_between_panes(self):
        s = WindowSettings()
        one = build_window_shell(WindowSpec([pane(0, 2, 0, 1)], s))
        two = build_window_shell(WindowSpec([pane(0, 1, 0, 1), pane(1, 2, 0, 1)], s))
        self.assertClosedManifold(two)
        self.assertGreater(len(two.faces), len(one.faces))
        # The mullion adds frame volume and removes a little glass.
        self.assertGreater(signed_volume(two) - signed_volume(one), 0.0)

    def test_grid_of_panes(self):
        panes = [pane(x, x + 1, z, z + 1) for x in range(3) for z in range(2)]
        mesh = build_window_shell(WindowSpec(panes))
        self.assertClosedManifold(mesh)
        self.assertConsistentArrays(mesh)

    def test_window_tilted_to_face_any_way(self):
        y = [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)]   # In the YZ plane.
        mesh = build_window_shell(WindowSpec([y]))
        self.assertClosedManifold(mesh)

    def test_degenerate_window(self):
        self.assertIsNone(build_window_shell(WindowSpec([])))
        self.assertIsNone(build_window_shell(WindowSpec([[(0, 0, 0), (1, 0, 0), (2, 0, 0)]])))


def poly_area(points):
    """Area of a polygon in the y = 0 plane (x, z)."""
    xz = [(p[0], p[2]) for p in points]
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(xz, xz[1:] + xz[:1]))) / 2


class TestShapedPanes(unittest.TestCase, MeshAssertions):
    TRAPEZOID = [(1, 0, 1), (2.5, 0, 1), (2, 0, 2.2), (1.2, 0, 2.2)]
    TRIANGLE = [(1, 0, 1), (3, 0, 1), (2, 0, 2.5)]

    def test_opening_follows_the_outline(self):
        for shape in (self.TRAPEZOID, self.TRIANGLE):
            mesh = build_assembly_wall_only(WindowSpec([shape]))
            self.assertClosedManifold(mesh)
            self.assertEqual(euler_characteristic(mesh), 0)
            self.assertAlmostEqual(signed_volume(mesh), (12 - poly_area(shape)) * T, places=6)

    def test_window_shell_is_closed_for_any_convex_pane(self):
        for shape in (self.TRAPEZOID, self.TRIANGLE):
            mesh = build_window_shell(WindowSpec([shape]))
            self.assertClosedManifold(mesh)
            self.assertConsistentArrays(mesh)
            self.assertGreater(signed_volume(mesh), 0.0)

    def test_frame_covers_the_edges_and_glass_stays_inside(self):
        s = WindowSettings()
        mesh = build_window_shell(WindowSpec([self.TRAPEZOID], s), frame_material=1, glass_material=2)
        xs = [v[0] for v in mesh.vertices]
        zs = [v[2] for v in mesh.vertices]
        self.assertAlmostEqual(min(xs), 1.0, places=6)      # The frame reaches the pane's outline...
        self.assertAlmostEqual(max(xs), 2.5, places=6)
        self.assertAlmostEqual(min(zs), 1.0, places=6)
        self.assertAlmostEqual(max(zs), 2.2, places=6)
        glass = [f for f, m in zip(mesh.faces, mesh.face_material) if m == 2]
        self.assertTrue(glass)
        for f in glass:                                     # ...and the glass sits inside it.
            for i in f:
                x, _y, z = mesh.vertices[i]
                self.assertGreater(z, 1.0 + s.frame_width - s.rebate - 1e-6)

    def test_slanted_mullion_between_two_panes(self):
        left = [(1, 0, 1), (2, 0, 1), (2.4, 0, 2), (1, 0, 2)]
        right = [(2, 0, 1), (3, 0, 1), (3, 0, 2), (2.4, 0, 2)]
        s = WindowSettings()
        two = build_window_shell(WindowSpec([left, right], s))
        one = build_window_shell(WindowSpec([left[:2] + right[1:3] + left[2:]], s))   # Same outline, no bar.
        self.assertClosedManifold(two)
        self.assertGreater(signed_volume(two) - signed_volume(one), 0.0)

    def test_collapsed_pane_is_solid(self):
        tiny = [(0, 0, 0), (0.05, 0, 0), (0.05, 0, 0.05), (0, 0, 0.05)]   # Thinner than the frame.
        mesh = build_window_shell(WindowSpec([tiny]))
        self.assertClosedManifold(mesh)
        self.assertNotIn(1, mesh.face_material)   # No glass.


if __name__ == "__main__":
    unittest.main()
