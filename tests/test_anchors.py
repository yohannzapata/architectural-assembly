# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from architectural_assembly.core import SolidifySettings, Surface, SurfaceAnchor, resolve_anchor
from helpers import SheetBuilder

T = 0.2


class TestAnchors(unittest.TestCase):
    def test_anchor_sits_on_surface_and_follows_edits(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), 3.0)                 # normal -Y
        sheet = b.sheet(face_uids=[7])
        settings = SolidifySettings(thickness=T)

        frame = resolve_anchor(sheet, SurfaceAnchor(uid=7, u=1.0, v=0.9), settings)
        self.assertAlmostEqual(frame.position[1], -T / 2)
        self.assertAlmostEqual(frame.position[2], 0.9)
        self.assertAlmostEqual(frame.normal[1], -1.0)

        back = resolve_anchor(sheet, SurfaceAnchor(uid=7, u=1.0, v=0.9, side=Surface.BACK), settings)
        self.assertAlmostEqual(back.position[1], T / 2)
        self.assertAlmostEqual(back.normal[1], 1.0)

        # Move the panel: the anchor follows it.
        sheet.positions = [(x + 10, y, z) for x, y, z in sheet.positions]
        moved = resolve_anchor(sheet, SurfaceAnchor(uid=7, u=1.0, v=0.9), settings)
        self.assertAlmostEqual(moved.position[0] - frame.position[0], 10.0)

    def test_missing_face_returns_none(self):
        b = SheetBuilder()
        b.panel((0, 0), (4, 0), 3.0)
        self.assertIsNone(resolve_anchor(b.sheet(face_uids=[1]), SurfaceAnchor(uid=99, u=0, v=0)))


if __name__ == "__main__":
    unittest.main()
