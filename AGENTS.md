## Project: chunitools v0.2.13

A high-performance CHUNITHM (SEGA arcade rhythm game) chart parser, viewer, and editor built with Python 3.10+ and PySide6 (Qt6).

### What it does

- Parses `.c2s` chart files (tab-delimited format) into an internal domain model
- Renders charts as a 2D/3D playfield with note visualisation, air notes, slides, holds, etc.
- Provides a full-featured desktop GUI for browsing, editing, validating, and exporting charts
- Plays chart audio (music + hitsounds) using Qt multimedia
- Supports CHUNITHM game data extraction: `.acb`/`.awb` cue files, `.hca`/`.afs2` audio codecs
- Exports charts to image files (PNG) via CLI

### Technology stack

- **Language:** Python ≥3.10
- **GUI:** PySide6 (Qt 6.6+ bindings)
- **Build:** Hatchling build backend; PyInstaller for standalone executables
- **Linting/formatting:** Ruff (strict ruleset: F, E, W, I, N, UP, B, C4, SIM, RET, TCH, PL)
- **Type checking:** basedpyright (basic mode)
- **Testing:** pytest
- **Other tooling:** radon (complexity gate), vulture (dead code)
- **Dependency management:** uv

### Project structure

```
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point (run_app → bootstrap.run)
│   ├── bootstrap.py            # QApplication setup, logging config
│   ├── cli.py                  # CLI chart → PNG export
│   ├── core/
│   │   ├── __init__.py         # Domain package (models, enums, notes)
│   │   ├── const.py            # NoteType, Command, AnimationType, AirColor, etc.
│   │   ├── models.py           # ChartMetadata, Chart, BpmEntry, SofLan*, etc.
│   │   ├── config.py           # User settings, config file I/O (YAML)
│   │   ├── enums.py            # Compatibility reexports from const
│   │   ├── read.py             # Chart discovery, parsing, library scanning
│   │   ├── write.py            # .c2s serializer, music.xml writer
│   │   ├── editor.py           # Mutation helpers (add/move/remove notes, snap)
│   │   ├── editor_metadata.py  # Editor metadata load/save
│   │   ├── metadata.py         # Fast metadata extraction
│   │   ├── library_models.py   # SongInfo, FumenInfo, MetadataPreview, etc.
│   │   ├── library_scanner.py  # Game data directory scanning
│   │   ├── images.py           # Image processing (jacket art)
│   │   ├── audio_assets.py     # .acb/.awb cue audio resolution
│   │   └── option_export.py    # Export options model
│   ├── notes/
│   │   ├── __init__.py         # Exports all Note subclasses
│   │   ├── base.py             # Abstract Note dataclass (serialize, get_extra_parts)
│   │   ├── tap.py              # Tap, ExTap, Mine
│   │   ├── hold.py             # Hold
│   │   ├── slide.py            # Slide, SlideTo
│   │   ├── flick.py            # Flick
│   │   ├── air.py              # Air, AirHold, AirHoldStart, AirSlide, AirSlideStart, AirSlidePattern
│   │   ├── effects.py          # AirSolid, HeavenHold
│   │   ├── geometry.py         # note_duration, note_end_cell, steps helpers
│   │   ├── factory.py          # Parser + editor note construction, dispatch
│   │   └── schema.py           # Per-NoteType field schemas for parsing
│   ├── engine/
│   │   ├── __init__.py         # Timeline and playback engine
│   │   ├── timeline.py         # ChartTimeline — temporal/spatial queries, BPM/time mapping
│   │   ├── playback.py         # PlaybackController — timing, hitsound triggering
│   │   ├── hitsounds.py        # AudibleEvent model
│   │   └── soflan.py           # SofLan evaluation
│   ├── audio/
│   │   ├── __init__.py         # Exports AudioEngine
│   │   ├── engine.py           # QSoundEffect pool for low-latency hitsounds
│   │   ├── music.py            # MusicStreamPlayer for background music
│   │   └── codecs/
│   │       ├── acb.py          # .acb cue file parser
│   │       ├── afs2.py         # .afs2 archive parser
│   │       └── hca.py          # .hca audio decoder
│   ├── services/
│   │   ├── __init__.py         # Exports ChartIndex, build_index
│   │   ├── indexing.py         # ChartIndex service for data dir scanning
│   │   └── playback.py         # PlaybackCoordinator — controller + audio engine glue
│   └── ui/
│       ├── theme/
│       │   ├── color_profile.py  # CHUNITHM-inspired color palette
│       │   ├── notes.py          # Note-specific theme colors
│       │   ├── styles.py         # Qt stylesheet generation
│       │   └── ui.py             # UI-level theme tokens
│       ├── components/
│       │   ├── play_view/              # 3D playfield package
│       │   │   ├── __init__.py         # Exports PlayView3D
│       │   │   ├── view.py             # 3D QWidget shell, playback state, paint orchestration
│       │   │   ├── playfield.py        # 3D lane field, judge lines, scrubber
│       │   │   ├── geometry.py         # 3D projection/depth/clipping helpers
│       │   │   └── notes/
│       │   │       ├── __init__.py     # Exports PlayViewNotesMixin
│       │   │       ├── air.py, damage.py, flick.py
│       │   │       └── hold.py, slide.py, support.py
│       │   ├── timeline_view/          # 2D timeline/chart viewport package
│       │   │   ├── __init__.py         # Exports ChartViewport, DEFAULT_VIEW_LANE_WIDTH
│       │   │   ├── constants.py        # Timeline viewport sizing/scroll constants
│       │   │   ├── view.py             # ChartViewport shell, state, public config
│       │   │   ├── render.py           # 2D paint/export/render-segment orchestration
│       │   │   ├── interaction.py      # Mouse, wheel, resize interaction
│       │   │   ├── selection.py        # Note picking, selection, placement previews
│       │   │   ├── scroll.py           # Scrollbar, zoom, jump/select measure helpers
│       │   │   └── notes/              # 2D per-note-type renderer mixins
│       │   │       ├── air.py, damage.py, flick.py
│       │   │       ├── hold.py, slide.py, support.py
│       │   │       └── __init__.py
│       │   ├── picker.py               # Chart browser/selector
│       │   ├── picker_model.py         # Chart list model
│       │   ├── picker_delegate.py      # Chart list delegate
│       │   ├── radar.py                # Note density radar chart
│       │   ├── fps_overlay.py          # FPS counter overlay
│       │   ├── note_debug_overlay.py   # 2D debug overlay for notes
│       │   └── note_debug_overlay_3d.py # 3D debug overlay for notes
│       ├── view/
│       │   ├── chart_renderer.py   # 2D chart rendering
│       │   ├── projection.py       # ViewProjection — coordinate mapping
│       │   ├── timeline_widget.py  # Timeline widget
│       │   ├── timeline_compat.py  # Timeline backward compat
│       │   ├── export.py           # Chart → image export
│       │   └── renderer/
│       │       └── base.py
│       └── window/
│           ├── window.py            # MainWindow — top-level app
│           ├── menus.py             # Menu bar, cursor filter
│           ├── key_handler.py       # Keyboard shortcuts
│           ├── file_handler.py      # File open/save dialogs
│           ├── editor_actions.py    # NoteEditor — editing interactions
│           ├── inspectors.py        # Note inspector panels
│           ├── export.py            # Export dialog operations
│           ├── widgets.py           # Shared widgets
│           ├── combo_box.py         # Custom combo box
│           ├── metadata_editor.py   # Chart metadata editing
│           ├── settings_handler.py  # Settings dialog
│           ├── overlay_manager.py   # Debug overlay manager
│           ├── status_widgets.py    # Status bar components
│           ├── slide_editor.py      # Slide-specific editor
│           ├── note_history.py      # Undo/redo history
│           └── source_opener.py     # Open source file location
├── vendor/vgmstream/              # Bundled vgmstream binaries for audio decode
├── builds/                        # PyInstaller build artifacts
├── scratch/                       # Scratch/vendor build assets (vgmstream source)
├── pyproject.toml                 # Project config, deps, tool settings
├── build.py                       # PyInstaller build script
├── chunitools.spec                # PyInstaller spec
└── AGENTS.md
```

### Domain model

**NoteType enum** (in `src/core/const.py`):
- Ground: `TAP`, `CHR` (ExTap), `FLK` (Flick), `MNE` (Mine)
- Holds: `HLD`, `HXD` (ExTap head hold)
- Slides: `SLD`, `SLC` (control point), `SXD` (ExTap head slide), `SXC` (ExTap control point)
- Air: `AIR`, `AUR`, `AUL`, `ADW`, `ADR`, `ADL` (arrows), `AHD` (hold), `AHX` (purple action on hold)
- Air effects: `ALD` (air slide pattern/effect carrier; `NON` = AIR-ACTION), `ASD`/`ASC` (air slide wrapper/control), `ASX` (air slide action), `ASO` (air solid)
- Heaven: `HHD`, `HHX`

**Key models** (in `src/core/models.py`):
- `Chart` — full parsed chart with metadata, notes, bpms, signatures, soflan areas/patterns, scroll speeds, stops, decelerations, clicks
- `ChartMetadata` — header metadata (title, artist, difficulty, level, BPM, etc.)
- `SofLanArea`/`SofLanPattern` — lane-local scroll (SLA/SLP)
- `ScrollSpeed` — SFL/SFE global scroll speed
- `Stop` — STP note halts
- `Deceleration` — DCM deceleration

**ChartTimeline** (in `src/engine/timeline.py`) — the central spatial-temporal engine converting measure/tick positions to seconds and z-indices, handling BPM changes, time signatures, soflan areas, and note chain traversal.

### C2S chart format

- Tab-separated text format
- Header commands: `MET`, `MUSICID`, `TITLE`, `ARTIST`, `VERSION`, `DIFFICULT`, `LEVEL`, `CREATOR`, `RESOLUTION`, `BPM_DEF`, `MET_DEF`, `CLK_DEF`, `BPM`, `WENAME`, `WELEVEL`, `TUTORIAL`, `PROGJUDGE_BPM`, `PROGJUDGE_AER`
- Note lines: `NoteType\tMeasure\tOffset\tCell\tWidth\t[extra_fields...]`
- 16-lane playfield (cells 0-15)
- Resolution: 384 ticks per measure (standard)

### Parser and renderer seams

- **C2S parser:** `src/core/read.py` uses `C2sParser` with explicit `HEADER_TAGS`, `TIMING_TAGS`, and `METADATA_MAP`. Parsing is line-classification first, then note construction, slide/air-slide chaining, and air-anchor resolution.
- **Note construction:** `src/notes/schema.py` defines per-`NoteType` parse fields; `src/notes/factory.py` owns explicit parse/build dispatch. Keep note construction explicit; do not use `**base`, `**extras`, or `**kwargs` splatting.
- **Timeline renderer:** `src/ui/view/chart_renderer.py` orchestrates the 2D renderer stack. The interactive viewport and 2D note renderer mixins live in `src/ui/components/timeline_view/`, including `timeline_view/notes/`.
- **3D play renderer:** `src/ui/components/play_view/` is the 3D package. `view.py` owns the QWidget shell, `playfield.py` owns field/judge/scrubber drawing, `geometry.py` owns projection and clipping math, and `notes/` owns per-category 3D note rendering.
- **3D clipping rule:** sustain, slide, air hold, air slide, and ALD air slide pattern bodies must clip in chart-space before projection. Do not clamp depth alone; interpolate cell/width/height at the clipped depth to avoid folded/compressed slide bodies.
- **Air wrapped ground heads:** `AIR_WRAPPED_GROUND_TYPES` in `play_view/notes/air.py` is renderer terminology for ground-style heads drawn under air paths. It is not a separate C2S note category.

### Key architectural patterns

- **Notes:** Frozen dataclasses inheriting from abstract `Note` base. Each subclass implements `get_extra_parts()` for serialization. Factory dispatch in `notes/factory.py` handles both parser and editor construction.
- **C2S parser:** `C2sParser` in `core/read.py` classifies lines into header/timing/note buckets before chaining slide segments and resolving air anchors. Keep parser terminology aligned with `NoteType` names and game-engine categories.
- **Render packages:** `ui/components/play_view/` is the 3D playfield; `ui/components/timeline_view/` is the 2D interactive timeline viewport and 2D note renderer package. Do not recreate old flat modules like `play_view.py`, `play_view_notes.py`, or `viewport.py`, and do not put timeline note renderers back under `ui/view/renderer/notes/`.
- **Editor mutations:** Immutable note copies via `dataclasses.replace()`. `add_note`/`remove_notes`/`move_note` in `core/editor.py` handle chart mutation with sorting and timeline cache invalidation.
- **Playback controller:** QTimer-driven with precise timing, hitsound trigger queue, audio sync offset slewing, and debounced seeking.
- **PlaybackCoordinator:** Glues PlaybackController (timing) → AudioEngine (hitsounds) → MusicStreamPlayer (background music) → audio asset resolution.
- **Bootstrap-only mode:** `CHUNITOOLS_BOOTSTRAP_ONLY=1` skips GUI for testing.
- **Config:** YAML config file at platformdirs `chunitools/config.yaml`. Settings includes scroll speed, volumes, visible note types, audio asset root, etc.

### Versioning

- **Always use SemVer** (semver.org). Current: 0.2.13. For 0.x, bump MINOR for breaking internal API changes, PATCH for bugfixes/refactors that don't change public interfaces. Tag every release with `v<VERSION>` (e.g., `v0.2.13`) and push tags to origin. Commit version bumps separately as `v<VERSION>`.

## Rules

- **Never push to git** unless explicitly told to. Do not push even after committing — wait for explicit instruction.
- Keep Python import blocks sorted and formatted with Ruff/isort conventions; do **not** leave Ruff I001 cleanup for the user.
- Keep imports at module top level. Do not sprinkle imports inside functions or methods unless there is a documented circular-import or heavyweight optional dependency reason; type-only imports belong under `if TYPE_CHECKING:`.
- Run `ruff check .` before committing changes to ensure lint passes.
- Use basedpyright for type checking (`basedpyright src/`).
- Do not add or write tests unless explicitly requested. Do not run render smoke checks unless explicitly requested. Prefer direct scripts, compile/import checks, Ruff, and basedpyright for routine verification.
- The `.c2s` format uses 1-indexed measures in BPM_DEF but 0-indexed in note files — be aware when parsing.

### Architecture & naming conventions

- **No backward compatibility.** This project is in active development. When code is renamed or restructured, old names are removed completely — no aliases, no deprecation shims, no `# legacy` comments. The codebase is cleaned up as if the old names never existed.
- **Never guess.** Implementation choices must be tied to explicit user requirements, parsed data, source code, documented behavior, or verified observations. If a value or behavior is uncertain, inspect the relevant source/artifact or state the uncertainty instead of inventing tuned constants or assumptions.
- **No fallback inference.** Do not silently guess note anchors, note types, paths, or renderer geometry from nearby notes, matching cells, filenames, or target strings. Use explicit parsed data and object links only; if data is missing or ambiguous, leave it unresolved and surface the issue.
- **No `**kwargs` or `**dict` splatting** in constructor/factory calls. Every keyword argument is explicitly named at every call site.
- **Note type groupings must match game-engine categories.** The game's internal classification is:
  - `GROUND` = TAP, MNE
  - `CRUSH` = CHR (ExTap / double-hit mechanic)
  - `FLICK` = FLK
  - `HOLD` = HLD, HXD
  - `SLIDE` = SLD, SLC, SXD, SXC
  - `AIR_ARROW` = AIR, AUR, AUL, ADW, ADR, ADL
  - `AIR_HOLD` = AHD, AHX
  - `AIR_SLIDE` = ASD, ASC, ASX
  - `AIR_SLIDE_PATTERN` = ALD (`NON` color renders AIR-ACTION)
  - `AIR_SOLID` = ASO
  - `HEAVEN` = HHD, HHX
- The Note dataclass at `notes/base.py` provides `serialize()` and the abstract `get_extra_parts()` contract. Construction logic lives in `notes/factory.py` with explicit per-type parse/build functions — no `**base`, no `**extras`.
- Render constants use game terminology: `HOLD_STROKE_WIDTH` (not `SUSTAIN_STROKE_WIDTH`), `AIR_PATH_WIDTH` (not `AIR_SUSTAIN_WIDTH`).
