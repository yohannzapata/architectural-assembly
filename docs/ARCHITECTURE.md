# Architecture

## Principles

1. **The user owns the shape.** Architectural Assembly never decides what a
   wall is. It thickens whatever faces it's given.
2. **One-way data flow.** Source faces + settings → generated shell. The
   shell is disposable and never edited by hand, so regenerating it can't
   lose work.
3. **Stable identity.** Everything a user attaches (paint now, doors and
   trims later) is keyed to *source faces*, never to generated polygons.
4. **Pure core.** All geometry lives in `core/` with no `bpy` import. It is
   unit-tested on a plain Python interpreter, and CI runs it on every push.

## Data flow

```
Source mesh (the user's faces)             ← edited normally, in Edit Mode or with modifiers above
  │  assembly.source_io.read_sheet()       object mode: Mesh arrays, edit mode: BMesh
  ▼
core.SheetMesh + core.SolidifySettings     settings are read from the modifier inputs
  │  core.build_shell()
  │    conform   → weld vertices, split T-vertices
  │    topology  → wedge cells (union-find over face sides around each edge)
  │    shell     → cell positions, sides, rims, caps, tags, UVs
  ▼
core.ShellMesh
  │  assembly.sync.write_shell()
  ▼
"<object>.shell" (hidden, in no collection)
  │  Object Info inside the "Architectural Assembly" node group
  ▼
Evaluated object: what you see, render, raycast and export
```

`assembly.sync` runs on `depsgraph_update_post`. A signature of every input
(positions, faces, per-face data, modifier settings, material slots) skips
work when nothing relevant changed.

## The solidify algorithm

**Face sides.** Each source face `f` has two sides, `2f` (FRONT, along its
normal) and `2f + 1` (BACK). With offset `o` and thickness `t`, their
offset planes sit at `+t(1+o)/2` and `−t(1−o)/2` along the normal.

**Wedge cells.** Around every edge shared by two or more faces, the faces
are sorted by the angle at which they leave the edge. Consecutive faces
enclose a wedge. The side of each that faces into the wedge is joined with
union-find at both ends of the edge. The resulting components per source
vertex are the *cells*, and each cell becomes one output vertex. Because the
rule is geometric:

- 2 faces on an edge → 2 wedges (inside and outside of a corner),
- 3 or more faces → 3 or more wedges (T-junction, crossing),
- inconsistent normals are handled (the wedge decides, not the normal).

**Placement.** A cell's vertex minimises the squared distance to all its
offset planes, plus a tiny pull towards the source vertex. One plane gives
a plain offset, two give a miter, three give a corner. The displacement is
clamped to `miter_limit × thickness`.

**Closing.** An edge with one face gets a rim quad between its front and back
cells. Rims are classified by their normal: TOP, BOTTOM or EDGE. Around a
source vertex, the rims' half-edges are chained into loops, and loops of
three or more get a cap (for example, the top of a T-junction).

**Conform.** Before any of this, vertices within `1e-4` are welded and edges
are split where another face's vertex lies on them. Faces that touch always
join, whatever their subdivision.

## Stable names (saved in .blend files; append-only)

| Where | Name | Type | Meaning |
|---|---|---|---|
| source face | `aa_thickness` | FLOAT | per-face thickness, ≤ 0 = modifier default |
| source face | `aa_paint_front` … `aa_paint_edge` | INT | material slot + 1 per surface, 0 = unpainted |
| source face | `aa_uid` | INT | persistent face id (automatic) |
| shell face | `aa_surface` | INT | `core.Surface`: FRONT 0, BACK 1, TOP 2, BOTTOM 3, EDGE 4 |
| shell face | `aa_source_face` | INT | index of the source face |
| shell face | `aa_uid` | INT | persistent id of the source face |
| shell corner | `UVMap` | FLOAT2 | world-scale UVs, 1 unit = 1 m |
| node group | `Architectural Assembly` | GN | the modifier; inputs *Thickness*, *Offset*, *Miter Limit*, *Shell* |

## Materials and paint

Material indices on the shell refer to the **source object's own material
slots**, so everything stays standard Blender: assign a material to a face in
Edit Mode and all its surfaces use it. Paint overrides that per surface. The
paint tool adds the chosen material to the object's slots if needed and
writes `slot + 1` into `aa_paint_<surface>` of the affected source faces.

A click paints one surface: one `(source face, Surface)` pair. Shift-click
floods through shell polygons that share an edge and have the same surface
type and orientation (`core.regions`). The rims between a sheet's two sides
stop the fill, so painting inside a room never reaches the outside.

## Extension points

- **Doors, windows, attachments.** Store a `core.SurfaceAnchor` (face uid, u,
  v, side, depth) and resolve it after each rebuild with
  `core.resolve_anchor()`. A component then stays on the same face,
  flush with its surface, whatever the user edits.
- **Openings with frames.** Cut by removing source faces (works today), or
  let a component generate the hole and frame from its anchor.
- **Trims.** Generate from shell rims (`aa_surface` = TOP/BOTTOM/EDGE), or
  add a node stage after the modifier.
- **Colour tint.** Add `aa_tint_<surface>` colour attributes next to paint and
  read them in materials through an Attribute node.

## Known limitations

- Modifiers *above* Architectural Assembly are ignored (it reads the
  original mesh). Keep it first; modifiers below it (Mirror, Array, Bevel)
  work normally.
- Faces that intersect without touching at vertices or edges are not merged.
- Generation is pure Python. Meshes with many thousands of faces update
  noticeably slower than native modifiers.
- Flipping a face's normal swaps its Front and Back, including their paint.
- Painting works in Object Mode only.

## Windows

A window is a mesh object whose faces are its panes (`Object.aa_window`).
It draws itself: like a wall, it has a Geometry Nodes modifier
(*Architectural Window*) that shows a hidden shell object, so it can be
clicked, edited and transformed like any object and has its own materials
(slot 0 frame, slot 1 glass).

`core.windows` does, in world space:

1. **Cut.** `build_assembly()` subtracts each window's outline (the convex hull
   of its panes) from every wall face parallel to it and within one
   thickness of it. This applies to *every* assembly object, so a window can
   span or move between separate walls. The convex hole is removed one edge
   at a time, which leaves convex pieces that inherit the parent's
   thickness, material, paint and uid. `face_source` is mapped back to the
   original face, so painting treats the pieces as one face.
2. **Frame and glass.** `build_window_shell()`: every pane edge with no pane
   on the other side is inset by the frame width, edges shared with another
   pane by half the mullion width (both sides together make one bar). The
   strips between each pane and its inset outline form a sheet thickened by
   the frame depth. The inset outlines, grown by a small rebate, form a thin
   glass sheet. A pane too small for its bars becomes solid frame.

The result is generated in world metres and stored in the window's local
space, so bar widths stay true when the window object is scaled.
`sync.rebuild_window()` does that; walls read all windows into their signature.

Limits: panes must be convex (skewed quads, trapezoids and triangles are
fine), wall faces must be convex, the wall opening follows the convex hull of
all panes, and a window only cuts walls parallel to it (within about 2.5
degrees).
