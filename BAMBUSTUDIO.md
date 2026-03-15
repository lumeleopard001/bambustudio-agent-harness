# BambuStudio — CLI Anything SOP

## Software Overview

**BambuStudio** is a 3D printing slicer (GUI application) by Bambu Lab. Fork of PrusaSlicer.
Converts 3D models (STL/OBJ/STEP) into G-code for FDM 3D printers.

- **Source:** https://github.com/bambulab/BambuStudio
- **Language:** C++ (~700K LOC, 1146 .cpp files, 1034 .h files)
- **GUI Framework:** wxWidgets
- **Core Engine:** libslic3r (pure C++ slicing library)
- **Project Format:** 3MF (ZIP + XML + INI configs + G-code + thumbnails)
- **Binary:** `BambuStudio` (macOS .app bundle), `bambu-studio` (Linux)

## Architecture

```
BambuStudio
├── libslic3r/           # Core slicing engine (pure C++, no GUI)
│   ├── Model.*          # Model, ModelObject, ModelVolume, ModelInstance
│   ├── Print.*          # Print orchestrator, PrintObject, PrintRegion
│   ├── Layer.*          # Layer, LayerRegion (2D slice data)
│   ├── GCode.*          # G-code generator
│   ├── TriangleMeshSlicer.*  # Core mesh → 2D polygon slicing
│   ├── PrintConfig.*    # ~300+ config options
│   └── Format/
│       ├── bbs_3mf.*    # BBS-variant 3MF format (ZIP+XML)
│       ├── STL.*        # STL import
│       ├── OBJ.*        # OBJ import
│       └── STEP.*       # STEP import (OpenCASCADE)
└── slic3r/GUI/          # wxWidgets GUI (407 files)
    ├── Plater.*         # Main UI panel
    └── BackgroundSlicingProcess.*  # GUI↔engine bridge
```

### Slicing Pipeline
```
Model → Print.apply() → PrintObject steps:
  posSlice → posPerimeters → posPrepareInfill → posInfill
  → posIroning → posSupportMaterial → GCodeExport
```

## Existing CLI

Binary: `bambu-studio [OPTIONS] [file.3mf/file.stl ...]`

### Actions
- `--slice <0|i>` — Slice (0=all, i=plate#)
- `--export-3mf <path>` — Export 3MF
- `--export-stl` / `--export-stls <dir>` — Export STL
- `--export-png <0|i>` — Export plate PNG
- `--export-settings <json>` — Export settings
- `--export-slicedata <dir>` — Export slice cache
- `--info` — Model information

### Transforms
- `--arrange <0|1>` / `--orient <0|1>` — Auto-layout
- `--rotate <deg>` / `--rotate-x` / `--rotate-y` — Rotation
- `--scale <factor>` — Scaling

### Settings
- `--load-settings "s1.json;s2.json"` — Load print/machine settings
- `--load-filaments "f1.json;f2.json"` — Load filaments
- `--load-filament-ids "1,2,3"` — Filament mapping

### Output
- `--outputdir <dir>` — Output directory
- `--debug <0-5>` — Log level
- `result.json` — Written after slice (return_code, plates[], filaments[])

## 3MF Format (BBS Variant)

```
project.3mf (ZIP)
  3D/3dmodel.model                # OPC 3D model XML
  Metadata/print_profile.config   # Print settings (INI: key = value)
  Metadata/project_settings.config
  Metadata/model_settings.config  # Per-object settings (XML)
  Metadata/plate_N.gcode          # G-code per plate
  Metadata/plate_N.png            # Thumbnail 128x128
  Metadata/plate_N.json           # Pattern config
```

## CLI Error Codes

51 error codes (0-49), mapped from `cli_errors` in BambuStudio.cpp:
- 0: Success
- 2: Invalid parameters
- 3: Input files not found
- 6: Model file cannot be parsed
- 14: Out of memory
- 21: Auto-arrange failed
- 22: Auto-orient failed
- 33: Slicing time exceeds limit
- 34: Triangle count exceeds limit
- 44: Slicing failed
- 45: G-code conflicts

## CLI Harness Design

The Python CLI harness:
1. **Delegates** slicing/export/transform to the real BambuStudio binary
2. **Manipulates** 3MF metadata directly (Python zipfile + XML)
3. **Adds** `--json` output envelope for agent consumption
4. **Adds** REPL mode for interactive use
5. **Adds** session management with undo/redo

## Profiles

Located in `resources/profiles/BBL/`:
- `machine/` — Printer presets (A1, A1 mini, X1C, P1S, etc.)
- `filament/` — Filament presets (PLA, ABS, PETG, etc.)
- `process/` — Print presets (0.08mm, 0.12mm, 0.20mm, etc.)
- `cli_config.json` — CLI-specific limits per printer
