# bambustudio-agent-harness

Agent-native Python CLI for [BambuStudio](https://bambulab.com/en/download/studio) 3D printing slicer.

**v2.0.0** | Python 3.10+ | 81 tests passing

Wraps the BambuStudio binary with structured JSON output, profile discovery, workflow orchestration, and an interactive REPL. Designed for AI agent integration and automation.

## Quick Start

```bash
# Install
cd agent-harness && pip install -e .

# Verify
cli-anything-bambustudio --help

# Full auto workflow: STL → sliced 3MF
cli-anything-bambustudio --json workflow auto \
  --stl model.stl --printer "Bambu Lab A1" --material PLA --quality standard

# Discover available printers
cli-anything-bambustudio --json profiles list-printers
```

## Prerequisites

BambuStudio must be installed. This CLI wraps the real BambuStudio binary — it does not reimplement the slicing engine.

| Platform | Install |
|----------|---------|
| **macOS** | Download `.dmg` from [bambulab.com/en/download/studio](https://bambulab.com/en/download/studio) |
| **Linux** | `sudo apt install bambu-studio` or Flatpak / Snap |
| **Windows** | Download installer from [bambulab.com/en/download/studio](https://bambulab.com/en/download/studio) |

Binary auto-detection paths:

- **macOS:** `/Applications/BambuStudio.app/Contents/MacOS/BambuStudio`
- **Linux:** `bambu-studio` in PATH, `/usr/bin/bambu-studio`, Snap, Flatpak
- **Windows:** `%PROGRAMFILES%\BambuStudio\bambu-studio.exe`

Override with `BAMBUSTUDIO_BIN=/path/to/binary`.

## Installation

```bash
git clone https://github.com/lumeleopard001/bambustudio-agent-harness.git
cd bambustudio-agent-harness
pip install -e .
```

Verify installation:

```bash
cli-anything-bambustudio --help
```

## Workflow Commands

The `workflow` group provides high-level, agent-native commands that orchestrate the full 3D printing pipeline.

### workflow auto

Full auto pipeline: STL → sliced 3MF project with print time and filament estimates.

```bash
cli-anything-bambustudio --json workflow auto \
  --stl cube.stl \
  --printer "Bambu Lab A1" \
  --material PLA \
  --quality standard \
  -o output.3mf
```

Pipeline steps: suggest presets → create project → import STL → orient → arrange → slice → parse estimates.

**Options:**

| Flag | Required | Description |
|------|----------|-------------|
| `--stl` | Yes | Input STL file path |
| `--printer` | Yes | Printer name (e.g. `"Bambu Lab A1"`) |
| `--material` | Yes | Material type: PLA, ABS, PETG, TPU, ASA, ... |
| `--quality` | No | `draft`, `standard` (default), `fine`, `extra-fine` |
| `-o, --output` | No | Output 3MF path (auto-generated if omitted) |

### workflow guided

Multi-step API for interactive selection. The agent presents options at each step and the user makes choices.

```bash
# Step 1: Start — returns available printers
RESULT=$(cli-anything-bambustudio --json workflow guided-start --stl cube.stl)
SESSION=$(echo $RESULT | jq -r '.data.session_file')

# Step 2: Select printer
cli-anything-bambustudio --json workflow guided-select \
  --session-file "$SESSION" --step printer --value "Bambu Lab A1"

# Step 3: Select material
cli-anything-bambustudio --json workflow guided-select \
  --session-file "$SESSION" --step material --value PLA

# Step 4: Select quality
cli-anything-bambustudio --json workflow guided-select \
  --session-file "$SESSION" --step quality --value standard

# Step 5: Execute
cli-anything-bambustudio --json workflow guided-execute --session-file "$SESSION"
```

Steps: `printer` → `material` → `quality` → `confirm` → execute. Each step returns available options and a recommendation.

### workflow review

Analyze an existing 3MF project and get improvement suggestions with severity levels.

```bash
cli-anything-bambustudio --json workflow review --project existing.3mf
```

Returns: current settings, recommendations (with severity: `error`, `warning`, `info`), and overall score (`good`, `needs-attention`, `problematic`).

## Profile Discovery

The `profiles` group discovers printers, filaments, and process presets from BambuStudio's bundled profile database.

### profiles list-printers

```bash
cli-anything-bambustudio --json profiles list-printers
```

Returns all available Bambu Lab printers with nozzle options, bed type, and tech info.

### profiles list-filaments

```bash
cli-anything-bambustudio --json profiles list-filaments \
  --printer "Bambu Lab A1" --nozzle 0.4
```

Returns filaments compatible with the specified printer and nozzle diameter.

### profiles list-processes

```bash
cli-anything-bambustudio --json profiles list-processes \
  --printer "Bambu Lab A1" --nozzle 0.4
```

Returns print quality presets (layer heights) for the printer.

### profiles suggest

```bash
cli-anything-bambustudio --json profiles suggest \
  --printer "Bambu Lab A1" --material PLA --quality standard
```

Recommends a complete preset triple: machine + filament + process files.

### profiles validate

```bash
cli-anything-bambustudio --json profiles validate \
  --machine "Bambu Lab A1 0.4 nozzle" \
  --filament "Bambu PLA Basic @BBL A1" \
  --process "0.20mm Standard @BBL A1"
```

Checks preset compatibility and returns `{valid, warnings, errors}`.

## Low-Level Commands

### project

```bash
project new --printer PRESET -o PATH        # Create empty 3MF
project info [PATH]                         # Show project metadata
project list-plates [PATH]                  # List build plates
project list-objects [PATH]                 # List 3D objects with geometry info
```

### model

```bash
model import FILE --project PATH                    # Import STL/OBJ/STEP
model transform --rotate-z DEG --scale F --project PATH  # Rotate, scale
model arrange --project PATH                        # Auto-arrange on plate
model orient --project PATH                         # Auto-orient for printing
model delete --object-id ID --project PATH          # Remove object
model list --project PATH                           # List all objects
```

### plate

```bash
plate list --project PATH               # List all plates
plate add --project PATH                 # Add new plate
plate remove --plate N --project PATH    # Remove plate by number
plate info --plate N --project PATH      # Show plate details
```

### slice

```bash
slice run [--plate N] [--no-check] --project PATH    # Slice (0=all plates)
slice estimate [--plate N] --project PATH             # Time/material estimate
```

### export

```bash
export 3mf -o PATH --project PATH [--min-save]     # Export as 3MF
export stl -o PATH --project PATH                   # Export as STL
export gcode -o DIR --project PATH [--plate N]      # Export G-code
export png -o PATH --project PATH [--plate N]       # Export plate preview PNG
export settings -o PATH --project PATH              # Export settings JSON
```

### config

```bash
config get KEY --project PATH                         # Read a setting value
config set KEY VALUE --project PATH [-o OUTPUT]       # Write a setting value
config profiles-list [--type machine|filament|process] # List presets
config profiles-show NAME                              # Show preset details
```

### session (REPL mode)

```bash
session status     # Current session info
session undo       # Undo last change
session redo       # Redo last undone change
session history    # Show command history
```

## JSON Output Format

All commands support `--json` for structured, machine-readable output. Every response follows this envelope:

```json
{
  "ok": true,
  "command": "workflow.auto",
  "data": { "..." },
  "error": null,
  "timestamp": "2026-03-15T10:30:00+00:00",
  "duration_ms": 12500
}
```

On error:

```json
{
  "ok": false,
  "command": "workflow.auto",
  "data": null,
  "error": "BambuStudio binary not found",
  "timestamp": "2026-03-15T10:30:00+00:00",
  "duration_ms": 5
}
```

Without `--json`, output is human-readable key-value text.

## Architecture

```
bambustudio-agent-harness
│
├── CLI Layer (Click)
│   bambustudio_cli.py         ← Entry point, Click groups + REPL
│
├── Core Layer
│   core/
│   ├── workflow.py            ← auto / guided / review orchestration
│   ├── config.py              ← Profile discovery, suggest, validate
│   ├── project.py             ← Project CRUD (3MF metadata)
│   ├── model.py               ← Model import, transform, arrange
│   ├── plate.py               ← Build plate management
│   ├── slicer.py              ← Slicing orchestration
│   ├── export.py              ← Export formats (3MF, STL, G-code, PNG)
│   └── session.py             ← Undo/redo, history tracking
│
├── Utils Layer
│   utils/
│   ├── bambustudio_backend.py ← Subprocess wrapper, binary discovery
│   ├── output.py              ← JSON/human output formatter
│   ├── threemf.py             ← 3MF (ZIP+XML) parser/writer
│   ├── settings_parser.py     ← INI config parser
│   └── repl_skin.py           ← prompt_toolkit REPL UI
│
└── BambuStudio Binary         ← Real C++ slicer (external dependency)
    Delegates: slicing, orient, arrange, export
    Reads: profiles/BBL/ (machine, filament, process presets)
```

The harness splits work between:
- **Python-side:** 3MF metadata manipulation (zipfile + XML), profile discovery, JSON formatting, session state
- **Binary-side:** Actual slicing, model orientation, arrangement, G-code generation (via subprocess)

## Project Structure

```
bambustudio-agent-harness/
├── README.md                          # This file
├── BAMBUSTUDIO.md                     # BambuStudio SOP (C++ binary reference)
├── setup.py                           # Package config (v2.0.0)
├── .gitignore
└── cli_anything/bambustudio/
    ├── __init__.py                    # Version: 2.0.0
    ├── __main__.py                    # python -m entry
    ├── bambustudio_cli.py             # CLI definition (Click groups)
    ├── AGENT_PROMPT.md                # System prompt for agent integration
    ├── core/
    │   ├── config.py                  # Profile discovery + validation
    │   ├── export.py                  # Export operations
    │   ├── model.py                   # Model manipulation
    │   ├── plate.py                   # Plate management
    │   ├── project.py                 # Project CRUD
    │   ├── session.py                 # Undo/redo stack
    │   ├── slicer.py                  # Slicing orchestration
    │   └── workflow.py                # auto/guided/review workflows
    ├── utils/
    │   ├── bambustudio_backend.py     # Binary subprocess wrapper
    │   ├── output.py                  # JSON envelope formatter
    │   ├── repl_skin.py               # REPL prompt_toolkit skin
    │   ├── settings_parser.py         # INI config parser
    │   └── threemf.py                 # 3MF ZIP+XML handler
    └── tests/
        ├── conftest.py                # Fixtures (minimal_3mf, mock_backend)
        ├── TEST.md                    # Test plan and results
        ├── test_core.py               # 35 unit tests
        ├── test_full_e2e.py           # 7 E2E + subprocess tests
        ├── test_profiles.py           # 17 profile discovery tests
        ├── test_workflow.py           # 13 workflow tests
        └── test_bugfix_regressions.py # 7 regression tests
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BAMBUSTUDIO_BIN` | Path to BambuStudio binary | Auto-detected per platform |
| `BAMBUSTUDIO_PROFILES` | Path to profiles/BBL/ directory | Auto-detected from binary location |
| `BAMBUSTUDIO_JSON` | Set to `1` to default to JSON output | `0` |
| `BAMBUSTUDIO_DEBUG` | Default debug level (0-5) | `1` |

The CLI also supports Click's auto-env-var prefix: any `--flag` can be set via `BAMBUSTUDIO_FLAG`.

## Running Tests

```bash
# All unit tests (no BambuStudio binary required)
pytest cli_anything/bambustudio/tests/ -v --ignore=cli_anything/bambustudio/tests/test_full_e2e.py

# Full test suite including E2E (requires BambuStudio binary)
pytest cli_anything/bambustudio/tests/ -v -s

# Individual test files
pytest cli_anything/bambustudio/tests/test_core.py -v          # 35 core tests
pytest cli_anything/bambustudio/tests/test_profiles.py -v      # 17 profile tests
pytest cli_anything/bambustudio/tests/test_workflow.py -v       # 13 workflow tests
pytest cli_anything/bambustudio/tests/test_bugfix_regressions.py -v  # 7 regression tests
pytest cli_anything/bambustudio/tests/test_full_e2e.py -v -s   # 7 E2E tests (binary required)

# With installed CLI entry point
CLI_ANYTHING_FORCE_INSTALLED=1 pytest cli_anything/bambustudio/tests/ -v -s
```

Current results: **81 tests, 100% pass rate** (v2.0.0, 2026-03-15).

## Agent Integration

For AI agents, see [`AGENT_PROMPT.md`](cli_anything/bambustudio/AGENT_PROMPT.md) — a ready-to-use system prompt with:

- Command reference tables
- Workflow recipes (auto, guided, review, discovery)
- Material, quality, and infill guides
- Error code reference with recommended agent actions
- Available printer list

Feed it as a system prompt or tool description to give your agent full 3D printing capability.

## Error Codes

The BambuStudio binary uses 51 error codes (0-49). Key codes:

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Proceed |
| 2 | Invalid parameters | Check preset compatibility |
| 3 | Input files not found | Verify file paths |
| 14 | Out of memory | Reduce mesh density or split model |
| 21 | Auto-arrange failed | Model too large for build plate |
| 25 | Empty plate / object outside bed | Re-arrange, check bed size |
| 36 | Filament incompatible with plate type | Change filament or plate type |
| 39 | Object collision | Reduce object count or re-arrange |
| 44 | Slicing failed | Review all settings, retry with `--no-check` |

Full mapping in `utils/bambustudio_backend.py`.

## License

GPL-3.0 — inherited from [BambuStudio](https://github.com/bambulab/BambuStudio) (PrusaSlicer fork).
