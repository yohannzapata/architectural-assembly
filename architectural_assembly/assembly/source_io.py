# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads the user's source mesh (object or edit mode) into a ``core.SheetMesh``."""

import bmesh

from ..core import SheetMesh
from .constants import SRC_PAINT_ATTRS, SRC_THICKNESS, SRC_UID

_SOURCE_ATTRS = (
    (SRC_THICKNESS, "FLOAT"),
    *((name, "INT") for name in SRC_PAINT_ATTRS),
    (SRC_UID, "INT"),
)


def ensure_attributes(mesh):
    """Create the per-face input attributes (object mode only)."""
    for name, data_type in _SOURCE_ATTRS:
        attr = mesh.attributes.get(name)
        if attr is not None and (attr.domain != "FACE" or attr.data_type != data_type):
            mesh.attributes.remove(attr)
            attr = None
        if attr is None:
            mesh.attributes.new(name, data_type, "FACE")


def read_sheet(obj):
    mesh = obj.data
    if mesh.is_editmode:
        return _read_bmesh(bmesh.from_edit_mesh(mesh))
    return _read_mesh(mesh)


def _face_values(mesh, name, default):
    n = len(mesh.polygons)
    attr = mesh.attributes.get(name)
    if attr is None or attr.domain != "FACE" or len(attr.data) != n:
        return [default] * n
    values = [default] * n
    attr.data.foreach_get("value", values)
    return values


def _read_mesh(mesh):
    nv, nf, nl = len(mesh.vertices), len(mesh.polygons), len(mesh.loops)
    co = [0.0] * (nv * 3)
    mesh.vertices.foreach_get("co", co)
    starts, totals, corners = [0] * nf, [0] * nf, [0] * nl
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    mesh.loops.foreach_get("vertex_index", corners)
    materials = [0] * nf
    mesh.polygons.foreach_get("material_index", materials)
    paint = [_face_values(mesh, name, 0) for name in SRC_PAINT_ATTRS]
    return SheetMesh(
        positions=[(co[i], co[i + 1], co[i + 2]) for i in range(0, nv * 3, 3)],
        faces=[corners[s:s + t] for s, t in zip(starts, totals)],
        face_thickness=_face_values(mesh, SRC_THICKNESS, 0.0),
        face_material=materials,
        face_paint=list(zip(*paint)),
        face_uids=_face_values(mesh, SRC_UID, 0),
    )


def _read_bmesh(bm):
    bm.verts.index_update()
    layer_t = bm.faces.layers.float.get(SRC_THICKNESS)
    paint_layers = [bm.faces.layers.int.get(name) for name in SRC_PAINT_ATTRS]
    layer_u = bm.faces.layers.int.get(SRC_UID)
    faces, thickness, materials, paint, uids = [], [], [], [], []
    for f in bm.faces:
        faces.append([v.index for v in f.verts])
        thickness.append(f[layer_t] if layer_t else 0.0)
        materials.append(f.material_index)
        paint.append(tuple(f[layer] if layer else 0 for layer in paint_layers))
        uids.append(f[layer_u] if layer_u else 0)
    return SheetMesh(
        positions=[tuple(v.co) for v in bm.verts],
        faces=faces, face_thickness=thickness, face_material=materials,
        face_paint=paint, face_uids=uids,
    )


def assign_uids(obj, sheet):
    """Give every face a unique persistent id (object mode only).

    Faces created in edit mode start at 0 or copy their neighbour's id.
    The lowest face index keeps a duplicated id, since new faces are
    appended. Returns True when the mesh was modified.
    """
    data = obj.aa_assembly
    seen, changed = set(), False
    next_uid = max([data.next_uid] + [u + 1 for u in sheet.face_uids])
    for i, uid in enumerate(sheet.face_uids):
        if uid <= 0 or uid in seen:
            sheet.face_uids[i] = uid = next_uid
            next_uid += 1
            changed = True
        seen.add(uid)
    if data.next_uid != next_uid:
        data.next_uid = next_uid
    if changed:
        mesh = obj.data
        if mesh.attributes.get(SRC_UID) is None:
            ensure_attributes(mesh)
        mesh.attributes[SRC_UID].data.foreach_set("value", sheet.face_uids)
        mesh.update()
    return changed
