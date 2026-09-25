# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""Keeps each assembly's generated shell in sync with its source mesh.

Data only flows one way: source mesh + modifier settings -> core -> shell.
The shell is never edited by hand, so regenerating it is always safe.
A cheap signature of the inputs skips rebuilds when nothing relevant
changed, so the depsgraph handler can run on every update.

Removing or applying the modifier ends the assembly. The object goes
back to being a plain mesh, just like any other modifier.
"""

import bpy
from mathutils import Vector
from bpy.app.handlers import persistent

from .. import core
from . import display, source_io, window_io
from .constants import OUT_SOURCE_FACE, OUT_SURFACE, OUT_UID, OUT_UV_MAP

_signatures = {}   # source session_uid -> signature of the last build
_busy = False


def is_assembly(obj):
    return obj is not None and obj.type == "MESH" and obj.aa_assembly.is_source


# -- shell object ------------------------------------------------------------

def _sources_using(shell):
    return [o for o in bpy.data.objects if is_assembly(o) and o.aa_assembly.shell == shell]


def _shell_taken(obj, shell):
    """True if another source (e.g. a Shift+D copy) has the better claim."""
    users = _sources_using(shell)
    if len(users) <= 1:
        return False
    owner = next((o for o in users if o.name == shell.aa_assembly.owner_name), None)
    return (owner or min(users, key=lambda o: o.name)) != obj


def ensure_shell(obj):
    data = obj.aa_assembly
    shell = data.shell
    if shell is not None and (shell.type != "MESH" or _shell_taken(obj, shell)):
        shell = None
    if shell is None:
        name = f"{obj.name}.shell"
        # Not linked to any collection: the modifier pulls it into the
        # depsgraph, and it can't be selected or edited by accident.
        shell = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        data.shell = shell
    if shell.aa_assembly.owner_name != obj.name:
        shell.aa_assembly.owner_name = obj.name
    return shell


def detach(obj):
    """Turn an assembly back into a plain mesh (keeps paint data)."""
    data = obj.aa_assembly
    shell = data.shell
    data.is_source = False
    data.shell = None
    _signatures.pop(obj.session_uid, None)
    if shell is not None and not _sources_using(shell):
        mesh = shell.data
        bpy.data.objects.remove(shell)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


# -- writing -----------------------------------------------------------------

def _set_face_ints(mesh, name, values):
    attr = mesh.attributes.get(name) or mesh.attributes.new(name, "INT", "FACE")
    attr.data.foreach_set("value", values)


def _source_materials(obj):
    return [slot.material for slot in obj.material_slots]


def write_shell(mesh, shell, materials):
    mesh.clear_geometry()
    try:
        mesh.from_pydata(shell.vertices, [], shell.faces, shade_flat=True)
    except TypeError:   # Blender < 4.1
        mesh.from_pydata(shell.vertices, [], shell.faces)

    # Mirror the source's material slots so material indices line up.
    mats = mesh.materials
    while len(mats) > len(materials):
        mats.pop()
    for i, mat in enumerate(materials):
        if i < len(mats):
            if mats[i] != mat:
                mats[i] = mat
        else:
            mats.append(mat)

    if shell.faces:
        mesh.polygons.foreach_set("material_index", shell.face_material)
        _set_face_ints(mesh, OUT_SURFACE, shell.face_surface)
        _set_face_ints(mesh, OUT_SOURCE_FACE, shell.face_source)
        _set_face_ints(mesh, OUT_UID, shell.face_uid)
        uv = mesh.uv_layers.get(OUT_UV_MAP) or mesh.uv_layers.new(name=OUT_UV_MAP)
        uv.data.foreach_set("uv", [c for uvs in shell.face_uvs for uv_co in uvs for c in uv_co])
    mesh.update()


def _signature(sheet, settings, materials, windows=()):
    q = 1e-6
    return hash((
        tuple(round(c / q) for p in sheet.positions for c in p),
        tuple(tuple(f) for f in sheet.faces),
        tuple(round(t / q) for t in sheet.face_thickness),
        tuple(sheet.face_material),
        tuple(sheet.face_paint),
        tuple(sheet.face_uids),
        round(settings.thickness / q), round(settings.offset / q), round(settings.miter_limit / q),
        tuple(m.session_uid if m else 0 for m in materials),
        window_io.signature(windows),
    ))


# -- rebuild -----------------------------------------------------------------

def rebuild(obj, force=False):
    """Regenerate ``obj``'s shell if its inputs changed. Returns True if rebuilt."""
    global _busy
    if _busy or not is_assembly(obj):
        return False
    _busy = True
    try:
        mod = display.find_modifier(obj)
        if mod is None:
            # The modifier was removed or applied: the assembly is finished.
            detach(obj)
            return False

        settings = display.read_settings(mod)
        sheet = source_io.read_sheet(obj)
        if not obj.data.is_editmode:
            source_io.assign_uids(obj, sheet)
        materials = _source_materials(obj)

        key = obj.session_uid
        windows = window_io.read_openings(obj)
        sig = _signature(sheet, settings, materials, windows)
        shell = obj.aa_assembly.shell
        if (not force and _signatures.get(key) == sig and shell is not None
                and display.shell_linked(mod, shell) and not _shell_taken(obj, shell)):
            return False

        shell = ensure_shell(obj)
        display.link_shell(mod, shell)
        write_shell(shell.data, core.build_assembly(sheet, settings, windows), materials)
        _signatures[key] = sig
        return True
    finally:
        _busy = False


def _window_shell_object(win):
    data = win.aa_window
    shell = data.shell
    if shell is not None:
        users = [o for o in window_io.all_windows() if o.aa_window.shell == shell]
        owner = next((o for o in users if o.name == shell.aa_assembly.owner_name), None)
        owner = owner or min(users, key=lambda o: o.name, default=win)
        if shell.type != "MESH" or (len(users) > 1 and owner != win):
            shell = None   # A copy of a window (Shift+D) gets a shell of its own.
    if shell is None:
        name = f"{win.name}.shell"
        shell = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        data.shell = shell
    if shell.aa_assembly.owner_name != win.name:
        shell.aa_assembly.owner_name = win.name
    return shell


def rebuild_window(win, force=False):
    """Regenerate a window's own frame and glass if its panes, size or settings changed."""
    global _busy
    if _busy or not window_io.is_window(win):
        return False
    mod = display.find_window_modifier(win)
    if mod is None:
        return False   # The modifier was removed or applied: the window is just its sheet.
    _busy = True
    try:
        spec = window_io.read_spec(win)
        materials = _source_materials(win)
        inverse = win.matrix_world.inverted_safe()
        q = 1e-6
        sig = hash((window_io.signature([spec]),
                    tuple(round(c / q) for row in win.matrix_world for c in row),
                    tuple(m.session_uid if m else 0 for m in materials)))
        key = win.session_uid
        shell = win.aa_window.shell
        if (not force and _signatures.get(key) == sig and shell is not None
                and display.shell_linked(mod, shell)):
            return False
        shell = _window_shell_object(win)
        display.link_shell(mod, shell)
        # Generated in world metres, stored in the window's local space: bar widths stay
        # true when the window object is scaled.
        result = core.build_window_shell(spec) or core.ShellMesh()
        result.vertices = [tuple(inverse @ Vector(v)) for v in result.vertices]
        write_shell(shell.data, result, materials)
        _signatures[key] = sig
        return True
    finally:
        _busy = False


def rebuild_all(force=False):
    for obj in bpy.data.objects:
        if is_assembly(obj):
            rebuild(obj, force=force)
        elif window_io.is_window(obj):
            rebuild_window(obj, force=force)


# -- handlers ----------------------------------------------------------------

@persistent
def aa_on_depsgraph_update(scene, depsgraph):
    if _busy:
        return
    if not any(isinstance(u.id, (bpy.types.Object, bpy.types.Mesh, bpy.types.NodeTree))
               for u in depsgraph.updates):
        return
    for obj in scene.objects:
        if is_assembly(obj):
            rebuild(obj)
        elif window_io.is_window(obj):
            rebuild_window(obj)


@persistent
def aa_on_undo_redo(*_args):
    _signatures.clear()


@persistent
def aa_on_load(*_args):
    _signatures.clear()
    rebuild_all()


_HANDLERS = (
    (bpy.app.handlers.depsgraph_update_post, aa_on_depsgraph_update),
    (bpy.app.handlers.undo_post, aa_on_undo_redo),
    (bpy.app.handlers.redo_post, aa_on_undo_redo),
    (bpy.app.handlers.load_post, aa_on_load),
)


def register():
    for handlers, fn in _HANDLERS:
        for h in [h for h in handlers if getattr(h, "__name__", "") == fn.__name__]:
            handlers.remove(h)
        handlers.append(fn)


def unregister():
    for handlers, fn in _HANDLERS:
        for h in [h for h in handlers if getattr(h, "__name__", "") == fn.__name__]:
            handlers.remove(h)
    _signatures.clear()
