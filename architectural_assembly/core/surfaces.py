# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable identifiers for the parts of a generated shell.

Every generated face is tagged with a ``Surface``. It is also the paint
channel: each source face stores one paint value per surface, so its
front, back, top, bottom and edges can each be painted separately.

The values are stored in .blend files. Only ever append; never renumber.
"""

from enum import IntEnum


class Surface(IntEnum):
    FRONT = 0    # Offset copy on the source face's normal side.
    BACK = 1     # Offset copy on the opposite side.
    TOP = 2      # Rim/cap facing up (wall tops, window sills).
    BOTTOM = 3   # Rim/cap facing down (wall bases, lintel undersides).
    EDGE = 4     # Rim/cap facing sideways (wall ends, door/window jambs, slab edges).


SURFACE_LABELS = {
    Surface.FRONT: "Front",
    Surface.BACK: "Back",
    Surface.TOP: "Top",
    Surface.BOTTOM: "Bottom",
    Surface.EDGE: "Edge",
}

SIDE_SURFACES = (Surface.FRONT, Surface.BACK)
