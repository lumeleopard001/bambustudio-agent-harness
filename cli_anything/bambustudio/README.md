# cli-anything-bambustudio

Agent-native CLI harness for [BambuStudio](https://bambulab.com/en/download/studio) 3D printing slicer.

## Prerequisites

**BambuStudio must be installed.** This CLI wraps the real BambuStudio binary — it does not reimplement the slicing engine.

- **macOS:** Download from [bambulab.com](https://bambulab.com/en/download/studio) or install via the `.dmg`
- **Linux:** `sudo apt install bambu-studio` or Flatpak/Snap
- **Windows:** Download installer from [bambulab.com](https://bambulab.com/en/download/studio)

## Installation

```bash
cd agent-harness
pip install -e .
```

Verify:

```bash
cli-anything-bambustudio --help
```

## Usage

### One-shot commands

```bash
# Project info
cli-anything-bambustudio --json project info my_model.3mf

# Slice all plates
cli-anything-bambustudio --json slice run --plate 0 my_model.3mf

# Export STL
cli-anything-bambustudio --json export stl -o output.stl --project my_model.3mf

# Get time/material estimate
cli-anything-bambustudio --json slice estimate --project my_model.3mf
```

### REPL mode

```bash
cli-anything-bambustudio
```

Launches an interactive session with command completion and history.

### JSON output

All commands support `--json` for machine-readable output:

```json
{
  "ok": true,
  "command": "slice.run",
  "data": {
    "return_code": 0,
    "plates": [
      {
        "id": 1,
        "sliced_time": 12500,
        "triangle_count": 48200,
        "filaments": [{"id": 0, "total_used_g": 15.2}]
      }
    ]
  },
  "error": null,
  "timestamp": "2026-03-15T10:30:00Z",
  "duration_ms": 12500
}
```

## Command Reference

### project
- `project new --printer PRESET -o PATH` — Create new 3MF
- `project info [PATH]` — Project metadata
- `project list-plates [PATH]` — List build plates
- `project list-objects [PATH]` — List 3D objects

### model
- `model import FILE` — Import STL/OBJ/STEP
- `model transform [--rotate-z DEG] [--scale F]` — Transform objects
- `model arrange` — Auto-arrange on plate
- `model orient` — Auto-orient for printing
- `model delete --object-id ID` — Remove object
- `model list` — List all objects

### plate
- `plate list` — List plates
- `plate add` — Add new plate
- `plate remove --plate N` — Remove plate
- `plate info --plate N` — Plate details

### slice
- `slice run [--plate N] [--no-check]` — Run slicing
- `slice estimate [--plate N]` — Time/material estimate

### export
- `export 3mf -o PATH` — Export as 3MF
- `export stl -o PATH` — Export as STL
- `export gcode -o DIR` — Export G-code
- `export png -o PATH [--camera-view VIEW]` — Export plate screenshot
- `export settings -o PATH` — Export settings JSON

### config
- `config get KEY` — Read setting
- `config set KEY VALUE` — Write setting
- `config profiles-list [--type machine|filament|process]` — List presets
- `config profiles-show NAME` — Preset details

### session (REPL only)
- `session status` — Session state
- `session undo` — Undo last change
- `session redo` — Redo
- `session history` — Change history

## Environment Variables

- `BAMBUSTUDIO_BIN` — Path to BambuStudio binary (overrides auto-detection)
- `BAMBUSTUDIO_JSON` — Set to `1` to default to JSON output
- `BAMBUSTUDIO_DEBUG` — Default debug level (0-5)

## Running Tests

```bash
# Unit tests (no binary required)
pytest cli_anything/bambustudio/tests/test_core.py -v

# E2E tests (requires BambuStudio binary)
pytest cli_anything/bambustudio/tests/test_full_e2e.py -v -s

# All tests with installed CLI
CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/bambustudio/tests/ -v -s
```
