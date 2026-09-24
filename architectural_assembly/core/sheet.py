# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Input data: the user's source mesh ("sheet") and the solidify settings.

A sheet is any polygon mesh: wall panels, gables, floors, roofs, fences.
It does not have to be manifold. Edges shared by three or more faces
(T-junctions, crossings) are supported on purpose.
"""

from dataclasses import dataclass, field


@dataclass
class SolidifySettings:
    thickness: float = 0.2
    # -1: grow fully behind the face, 0: centred on it, +1: fully in front.
    offset: float = 0.0
    # Largest allowed corner displacement, in multiples of the local
    # thickness. Stops very sharp angles from producing spikes.
    miter_limit: float = 4.0


@dataclass
class SheetMesh:
    positions: list                                       # [(x, y, z)]
    faces: list                                           # [[v0, v1, ...]]
    face_thickness: list = field(default_factory=list)   # per face, <= 0 means default
    face_material: list = field(default_factory=list)    # per face, material slot index
    # Per face, one value per Surface: material slot + 1, or 0 when unpainted.
    face_paint: list = field(default_factory=list)
    face_uids: list = field(default_factory=list)        # per face, persistent id

    def thickness(self, f, default):
        if f < len(self.face_thickness) and self.face_thickness[f] > 0.0:
            return self.face_thickness[f]
        return default

    def material(self, f, surface):
        """Material slot for ``surface`` of face ``f``: paint wins, else the face's own slot."""
        if f < len(self.face_paint) and surface < len(self.face_paint[f]):
            painted = self.face_paint[f][surface]
            if painted > 0:
                return painted - 1
        return self.face_material[f] if f < len(self.face_material) else 0

    def uid(self, f):
        return self.face_uids[f] if f < len(self.face_uids) else 0
