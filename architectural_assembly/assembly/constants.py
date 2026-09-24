# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Names stored in .blend files. Renaming any of these breaks saved scenes."""

# Face attributes on the source mesh (inputs, editable by the user and tools).
SRC_THICKNESS = "aa_thickness"      # FLOAT: per-face thickness, <= 0 means modifier default
SRC_UID = "aa_uid"                  # INT: persistent face id (managed automatically)

# INT per surface: material slot + 1 painted on that surface, 0 = not painted.
# Indexed by core.Surface; append-only like Surface itself.
SRC_PAINT_ATTRS = (
    "aa_paint_front",
    "aa_paint_back",
    "aa_paint_top",
    "aa_paint_bottom",
    "aa_paint_edge",
)

# Face attributes on the generated shell (outputs, read by tools).
OUT_SURFACE = "aa_surface"          # core.Surface
OUT_SOURCE_FACE = "aa_source_face"  # index of the source face
OUT_UID = "aa_uid"                  # persistent id of the source face
OUT_UV_MAP = "UVMap"                # world-scale UVs (1 unit = 1 m)

# Display modifier.
NODE_GROUP = "Architectural Assembly"
MODIFIER = "Architectural Assembly"
IN_SHELL = "Shell"
IN_THICKNESS = "Thickness"
IN_OFFSET = "Offset"
IN_MITER = "Miter Limit"
