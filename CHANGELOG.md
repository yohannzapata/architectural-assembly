# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Architectural solidify engine: thickens any faces with proper L, T, X and
  any-angle joints, a miter limit, rims, junction caps and world-scale UVs.
- Conform pass that joins faces that touch but don't share topology
  (unmerged vertices, differently split edges).
- *Architectural Assembly* Geometry Nodes modifier with Thickness, Offset and
  Miter Limit; live update in Edit Mode; apply or remove like any modifier.
- Per-face thickness overrides.
- Click-to-paint tool: click, Shift-click fill, Ctrl-click erase,
  Alt-click pick, hover highlight, scene-wide palette with starter paints.
- Surface tags (`aa_surface`, `aa_source_face`, `aa_uid`) on the generated
  mesh for other tools.
- Surface anchors (`core.anchors`) as the foundation for doors, windows and
  attachments.
