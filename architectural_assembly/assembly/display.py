# SPDX-FileCopyrightText: 2026 Yohann Joachim Zapata
# SPDX-License-Identifier: GPL-3.0-or-later
"""The "Architectural Assembly" modifier: the user-facing control surface.

It is a Geometry Nodes modifier, so it lives in the modifier stack like
Solidify. Thickness, Offset and Miter Limit are its inputs, so they can be
keyframed, driven and undone. It can be moved, disabled or applied like
any other modifier.

The geometry is computed in Python (``core``) and written to a hidden
shell object. The node group just swaps that shell in with Object Info.
Applying the modifier bakes the shell into the object.
"""

import bpy

from .constants import IN_MITER, IN_OFFSET, IN_SHELL, IN_THICKNESS, MODIFIER, NODE_GROUP

# (name, socket type, default, min, max, subtype, description)
_INPUTS = (
    (IN_THICKNESS, "NodeSocketFloat", 0.2, 0.0, 10.0, "DISTANCE",
     "Default thickness. Faces can override it"),
    (IN_OFFSET, "NodeSocketFloat", 0.0, -1.0, 1.0, "FACTOR",
     "Where the thickness goes: -1 behind the face, 0 centred, +1 in front"),
    (IN_MITER, "NodeSocketFloat", 4.0, 1.0, 100.0, "NONE",
     "How far sharp corners may reach, in multiples of the thickness"),
)
_VERSION = 1   # Bump to rebuild the node group in existing files.


def _find_socket(group, name):
    for item in group.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            return item
    return None


def ensure_node_group():
    group = bpy.data.node_groups.get(NODE_GROUP)
    if group is not None and group.get("aa_version") == _VERSION:
        return group
    if group is None:
        group = bpy.data.node_groups.new(NODE_GROUP, "GeometryNodeTree")
    group.interface.clear()
    group.nodes.clear()
    if hasattr(group, "is_modifier"):
        group.is_modifier = True
    group.description = "Thickens this object's faces (Architectural Assembly add-on)"

    iface = group.interface
    iface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name, sock_type, default, lo, hi, subtype, desc in _INPUTS:
        sock = iface.new_socket(name, in_out="INPUT", socket_type=sock_type)
        sock.default_value, sock.min_value, sock.max_value = default, lo, hi
        sock.description = desc
        try:
            sock.subtype = subtype
        except (AttributeError, TypeError):
            pass
    shell = iface.new_socket(IN_SHELL, in_out="INPUT", socket_type="NodeSocketObject")
    shell.description = "Generated geometry (managed automatically)"
    iface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes, links = group.nodes, group.links
    g_in = nodes.new("NodeGroupInput")
    g_in.location = (-700, 0)
    info = nodes.new("GeometryNodeObjectInfo")
    info.transform_space = "ORIGINAL"   # Shell is generated in the source's local space.
    info.location = (-400, 150)
    links.new(g_in.outputs[IN_SHELL], info.inputs["Object"])

    # The settings are read by Python. Route them into a no-op (selection
    # is False) so Blender treats them as used and doesn't grey them out.
    combine = nodes.new("ShaderNodeCombineXYZ")
    combine.location = (-400, -150)
    links.new(g_in.outputs[IN_THICKNESS], combine.inputs[0])
    links.new(g_in.outputs[IN_OFFSET], combine.inputs[1])
    links.new(g_in.outputs[IN_MITER], combine.inputs[2])
    keep = nodes.new("GeometryNodeSetPosition")
    keep.label = "Keeps settings active (no-op)"
    keep.location = (-150, 0)
    keep.inputs["Selection"].default_value = False
    links.new(info.outputs["Geometry"], keep.inputs["Geometry"])
    links.new(combine.outputs[0], keep.inputs["Offset"])

    g_out = nodes.new("NodeGroupOutput")
    g_out.location = (100, 0)
    links.new(keep.outputs["Geometry"], g_out.inputs["Geometry"])
    group["aa_version"] = _VERSION
    return group


# -- modifier inputs (API differs between Blender versions) ---------------

def _input_get(mod, identifier):
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):   # Blender 5.2+
        return getattr(props.inputs, identifier).value
    return mod.get(identifier)


def _input_set(mod, identifier, value):
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        getattr(props.inputs, identifier).value = value
    else:
        mod[identifier] = value


def draw_input(layout, mod, name, **kw):
    """Draw a modifier input in a custom panel."""
    sock = _find_socket(mod.node_group, name)
    if sock is None:
        return
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        layout.prop(getattr(props.inputs, sock.identifier), "value", text=name, **kw)
    else:
        layout.prop(mod, f'["{sock.identifier}"]', text=name, **kw)


def find_modifier(obj):
    for mod in obj.modifiers:
        if mod.type == "NODES" and mod.node_group is not None and mod.node_group.name == NODE_GROUP:
            return mod
    return None


def read_settings(mod):
    from ..core import SolidifySettings
    values = {}
    for name, *_ in _INPUTS:
        sock = _find_socket(mod.node_group, name)
        values[name] = float(_input_get(mod, sock.identifier)) if sock else None
    return SolidifySettings(
        thickness=values[IN_THICKNESS] if values[IN_THICKNESS] is not None else 0.2,
        offset=values[IN_OFFSET] if values[IN_OFFSET] is not None else 0.0,
        miter_limit=values[IN_MITER] if values[IN_MITER] is not None else 4.0,
    )


def add_modifier(obj):
    group = ensure_node_group()
    mod = obj.modifiers.new(MODIFIER, "NODES")
    mod.node_group = group
    mod.show_in_editmode = True
    mod.show_on_cage = False
    # Solidify-like tools belong first in the stack.
    index = list(obj.modifiers).index(mod)
    if index > 0:
        obj.modifiers.move(index, 0)
    return mod


def link_shell(mod, shell):
    sock = _find_socket(mod.node_group, IN_SHELL)
    if sock is not None and _input_get(mod, sock.identifier) != shell:
        _input_set(mod, sock.identifier, shell)


def shell_linked(mod, shell):
    sock = _find_socket(mod.node_group, IN_SHELL)
    return sock is not None and _input_get(mod, sock.identifier) == shell
