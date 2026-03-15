# BambuStudio Agent Harness

Command-line tool that lets you (or Claude) slice 3D models and track filament usage from the terminal.

**v2.2.0** | Python 3.10+ | 130 tests passing

## What is this?

If you have a Bambu Lab 3D printer, you probably use BambuStudio to slice your models.
This tool wraps BambuStudio so you can do the same thing from the command line — or let
Claude do it for you. It also tracks how much filament is left on each spool.

## Why would I want this?

1. **Ask Claude to slice for you.** "Slice this STL for my A1 with PLA" — Claude calls the tool, tells you print time and filament usage.
2. **Track your filament.** Know exactly how much is left on each spool. Get warned when a spool is running low.
3. **Batch processing.** Slice 20 STL files with one script instead of clicking through the GUI 20 times.
4. **Compare settings.** Quickly see how print time changes between draft and fine quality.

## Installation

### Quick install (recommended)

```bash
git clone https://github.com/lumeleopard001/bambustudio-agent-harness.git
cd bambustudio-agent-harness
bash install.sh
```

The installer checks for Python and BambuStudio, creates a virtual environment, and adds the tool to your PATH.

### Manual install

```bash
git clone https://github.com/lumeleopard001/bambustudio-agent-harness.git
cd bambustudio-agent-harness
pip install -e .
cli-anything-bambustudio --help
```

### Requirements

- **Python 3.10+** — `brew install python@3.12` (macOS) or `apt install python3.12` (Linux)
- **BambuStudio** — [download from bambulab.com](https://bambulab.com/en/download/studio)

## Slice an STL file

```bash
cli-anything-bambustudio --json workflow auto \
  --stl phone_stand.stl \
  --printer "Bambu Lab A1" \
  --material PLA \
  --quality standard
```

Output:

```json
{
  "ok": true,
  "data": {
    "print_time_human": "45m 0s",
    "filament_used_g": 12.3,
    "output_3mf": "/tmp/bambustudio_auto_.../phone_stand_project.3mf",
    "sliced": true
  }
}
```

See [`examples/workflow_auto_output.json`](examples/workflow_auto_output.json) for complete output.

## Track your filament

Register your spools, load them into AMS slots, and the tool tracks usage automatically.

```bash
# Register spools
cli-anything-bambustudio spool add --id 1 --brand Bambu --material PLA --color white --slot AMS:1
cli-anything-bambustudio spool add --id 2 --brand Bambu --material PLA --color black --slot AMS:2
cli-anything-bambustudio spool add --id 3 --brand Sunlu --material PETG --color red

# Check what's loaded
cli-anything-bambustudio --json spool status

# Slice and auto-deduct filament
cli-anything-bambustudio --json workflow auto \
  --stl model.stl --printer "Bambu Lab A1" --material PLA \
  --track-usage

# Swap a spool
cli-anything-bambustudio spool unload --slot AMS:2
cli-anything-bambustudio spool load --id 3 --slot AMS:2

# Check usage history
cli-anything-bambustudio --json spool history --id 1
```

Spools are persistent — the tool remembers remaining weight even when you unload and reload them.

See [`examples/spool_status_output.json`](examples/spool_status_output.json) for status output format.

## Use with Claude Desktop

Install the MCP server to give Claude direct access to slicing and spool management.

```bash
# Install MCP package
~/.bambustudio-harness/venv/bin/pip install mcp
```

Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bambustudio": {
      "command": "~/.bambustudio-harness/venv/bin/python",
      "args": ["/path/to/bambustudio-agent-harness/mcp-bambustudio/server.py"]
    }
  }
}
```

After slicing, Claude automatically opens the result in BambuStudio. You can also ask:
"Slice this STL for my A1 with PLA", "How much white PLA do I have left?", or "Open this file in BambuStudio".

See [`mcp-bambustudio/README.md`](mcp-bambustudio/README.md) for detailed setup.

## All commands

### Workflow (high-level)

| Command | What it does |
|---------|-------------|
| `workflow auto --stl FILE --printer NAME --material MAT` | Full pipeline: STL to sliced project |
| `workflow auto ... --open` | Same, plus open result in BambuStudio GUI |
| `workflow auto ... --track-usage` | Same, plus deduct filament from inventory |
| `open-in-studio PATH` | Open a .3mf/.stl file in BambuStudio GUI |
| `workflow guided-start --stl FILE` | Start step-by-step guided workflow |
| `workflow review --project FILE.3mf` | Analyze project, suggest improvements |

### Spool inventory

| Command | What it does |
|---------|-------------|
| `spool add --id N --brand B --material M --color C` | Register a new spool |
| `spool load --id N --slot AMS:1` | Load spool into printer slot |
| `spool unload --slot AMS:1` | Unload spool (remembers remaining weight) |
| `spool status` | Show all slots and remaining weights |
| `spool list [--state loaded\|stored\|empty]` | List spools by state |
| `spool history [--id N]` | Show usage history per print |
| `spool remove --id N` | Remove spool from registry |

### Profile discovery

| Command | What it does |
|---------|-------------|
| `profiles list-printers` | All available printers |
| `profiles list-filaments --printer NAME` | Compatible materials |
| `profiles list-processes --printer NAME` | Quality presets |
| `profiles suggest --printer NAME --material MAT` | Recommend settings |
| `profiles validate --machine M --filament F --process P` | Check compatibility |

### Project, model, plate, slice, export, config

Lower-level commands for individual operations. Run `cli-anything-bambustudio --help` for the full list.

## Interactive mode

Run without arguments to enter the REPL:

```bash
cli-anything-bambustudio
```

All commands work interactively. Type `help` for the list, `exit` to quit.

## Troubleshooting

**"BambuStudio binary not found"**
Install BambuStudio from [bambulab.com](https://bambulab.com/en/download/studio), or set `BAMBUSTUDIO_BIN=/path/to/binary`.

**"No profiles directory found"**
Set `BAMBUSTUDIO_PROFILES=/path/to/profiles/BBL/`. On macOS this is inside the .app bundle.

**"Python 3.10+ required"**
Install a newer Python: `brew install python@3.12` (macOS) or `sudo apt install python3.12` (Linux).

## Running tests

```bash
# Unit tests (no BambuStudio binary needed)
pytest cli_anything/bambustudio/tests/ -v \
  --ignore=cli_anything/bambustudio/tests/test_full_e2e.py

# Full suite (requires BambuStudio)
pytest cli_anything/bambustudio/tests/ -v
```

## Architecture

```
CLI Layer (Click)        → bambustudio_cli.py (commands + REPL)
Core Layer               → core/ (workflow, config, inventory, project, model, slicer)
Utils Layer              → utils/ (backend subprocess, 3MF parser, output formatter)
BambuStudio Binary       → external C++ slicer (handles actual slicing)
```

## License

GPL-3.0 — inherited from [BambuStudio](https://github.com/bambulab/BambuStudio).
