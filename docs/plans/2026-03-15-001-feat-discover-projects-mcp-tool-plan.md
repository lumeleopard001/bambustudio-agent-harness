---
title: "feat: Add discover_projects MCP tool for automatic project discovery"
type: feat
status: active
date: 2026-03-15
---

# feat: Add discover_projects MCP tool for automatic project discovery

## Overview

When a user says "vaata mu skull'ile peale" in Claude Desktop, the agent has no way
to find the file. `review_project` requires an absolute path, but the user doesn't
know or care about paths. The agent ends up asking "kus see fail asub?" which is
a UX dead end — the whole point of the MCP tool is that the agent does the work.

A new `discover_projects` tool scans the filesystem for recent 3MF/STL files and
returns them sorted by modification time, giving the agent the context it needs
to act autonomously.

## Problem Statement

**Current flow (6 messages, fails):**

```
User:  "vaata mu skull'ile peale"
Agent: calls spool_status → empty → useless
Agent: "failitee puudu"
User:  "bambu labis on avatud"
Agent: "vaata File → Recent Projects"
       → DEAD END — agent sends user on an errand
```

**Target flow (1-2 messages, works):**

```
User:  "vaata mu skull'ile peale"
Agent: calls discover_projects(query="skull")
       → finds ~/Downloads/scull m 2.3mf (modified 2 min ago)
Agent: calls review_project("~/Downloads/scull m 2.3mf")
       → returns analysis with suggestions
```

## Proposed Solution

### New MCP tool: `discover_projects`

```python
@mcp.tool()
def discover_projects(
    query: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Find recent 3MF and STL files on this machine.

    Scans common directories (Downloads, Desktop, Documents) for 3D print
    files, sorted by most recently modified. Use this when the user
    mentions a file but doesn't provide the full path.

    Args:
        query: Optional search term to filter by filename (e.g. "skull", "vase").
        limit: Maximum number of results (default: 10).
    """
```

### Discovery strategy (3 layers, sequential)

| Layer | Source | What | Reliability |
|-------|--------|------|-------------|
| 1 | Filesystem scan | `~/Downloads`, `~/Desktop`, `~/Documents`, `/tmp` for `*.3mf`, `*.stl` | High |
| 2 | BambuStudio log | Parse `~/Library/Application Support/BambuStudio/log/` for opened paths | Medium |
| 3 | Process args | `ps aux | grep BambuStudio` for command-line file arguments | Low |

**Why not `lsof`?** BambuStudio loads files into memory and closes the file handle.
Testing confirmed: `lsof -p <PID>` shows no 3MF/STL files even with a project open.

### Return format

```json
{
  "projects": [
    {
      "path": "/Users/lennart/Downloads/scull m 2.3mf",
      "name": "scull m 2",
      "type": "3mf",
      "size_mb": 57.2,
      "modified": "2026-03-15T18:30:00",
      "modified_ago": "5 minutes ago",
      "directory": "Downloads"
    }
  ],
  "total_found": 3,
  "directories_scanned": ["~/Downloads", "~/Desktop", "~/Documents"]
}
```

## Technical Considerations

### New file: `cli_anything/bambustudio/core/discovery.py`

Core logic separated from MCP server for testability.

```python
def discover_projects(
    query: str = "",
    limit: int = 10,
    scan_dirs: list[str] | None = None,
    max_age_days: int = 30,
) -> dict[str, Any]:
    """Scan filesystem for recent 3MF/STL files."""
```

**Scan directories (macOS defaults):**

```python
DEFAULT_SCAN_DIRS = [
    "~/Downloads",
    "~/Desktop",
    "~/Documents",
    "/tmp",
]
```

**File matching:**
- Extensions: `.3mf`, `.stl`, `.step`, `.obj`
- Max age: 30 days (configurable)
- Sorted by mtime descending (most recent first)
- Query: case-insensitive substring match on filename

**Performance guard:**
- `os.scandir()` (not `os.walk()`) — top-level only per directory
- Skip hidden files and directories
- Timeout: if a directory scan takes >2s, skip it
- No recursive scanning by default (Downloads can be huge)

### MCP server change: `mcp-bambustudio/server.py`

Add import and tool registration:

```python
from cli_anything.bambustudio.core.discovery import discover_projects as _discover

@mcp.tool()
def discover_projects(query: str = "", limit: int = 10) -> dict[str, Any]:
    """Find recent 3MF and STL files on this machine.
    ..."""
    return _discover(query=query, limit=limit)
```

### CLI change: `bambustudio_cli.py`

Add `project discover` subcommand:

```bash
cli-anything-bambustudio project discover
cli-anything-bambustudio project discover --query skull
cli-anything-bambustudio project discover --query skull --limit 5
```

### Server instructions update

Change MCP server instructions to guide the agent:

```python
mcp = FastMCP(
    "BambuStudio",
    instructions=(
        "3D printing tools for Bambu Lab printers. "
        "When the user mentions a file without giving a path, "
        "call discover_projects first to find it. "
        "Then use review_project or slice_stl with the discovered path."
    ),
)
```

This is critical — it teaches the agent the **correct workflow pattern**.

## System-Wide Impact

- **No breaking changes.** New tool only, existing tools unchanged.
- **MCP tool count:** 9 → 10. Acceptable since this solves the #1 usability blocker.
- **No new dependencies.** Uses only `os`, `pathlib`, `time` from stdlib.
- **Security:** Scans only user home directories. No arbitrary path traversal.
  The tool returns paths but doesn't read file contents.

## Acceptance Criteria

### Functional

- [ ] `discover_projects()` returns recent 3MF/STL files from ~/Downloads, ~/Desktop, ~/Documents
- [ ] `discover_projects(query="skull")` filters by filename substring (case-insensitive)
- [ ] Results sorted by modification time (newest first)
- [ ] Each result includes: path, name, type, size_mb, modified, modified_ago
- [ ] Files older than 30 days excluded by default
- [ ] Empty result returns `{"projects": [], "total_found": 0}` (not an error)

### MCP Integration

- [ ] Tool registered in MCP server with clear docstring
- [ ] Server `instructions` updated to guide agent to use discover_projects first
- [ ] Works in Claude Desktop (tested manually)

### CLI Integration

- [ ] `project discover` subcommand works
- [ ] `--json` flag produces structured output
- [ ] `--query` and `--limit` flags work

### Tests

- [ ] Unit tests with mocked filesystem (tmpdir with test files)
- [ ] Test query filtering (match, no match, case insensitive)
- [ ] Test age filtering (recent file included, old file excluded)
- [ ] Test empty directory handling
- [ ] Test limit parameter

## Implementation Phases

### Phase 1: Core discovery (MVP)

**Files:**

| File | Change |
|------|--------|
| `cli_anything/bambustudio/core/discovery.py` | **New.** `discover_projects()` function |
| `mcp-bambustudio/server.py` | Add `discover_projects` tool + update instructions |
| `cli_anything/bambustudio/tests/test_discovery.py` | **New.** Unit tests |

**Estimated scope:** ~120 lines core + ~80 lines tests + ~15 lines MCP

### Phase 2: CLI integration

| File | Change |
|------|--------|
| `cli_anything/bambustudio/bambustudio_cli.py` | Add `project discover` subcommand |

### Phase 3: BambuStudio log parsing (optional, future)

Parse BambuStudio's log files for recently opened projects. This adds a second
discovery source but is fragile (log format may change between versions).

## Sources & References

### Internal

- MCP server: `mcp-bambustudio/server.py` (9 existing tools)
- Workflow auto: `cli_anything/bambustudio/core/workflow.py:103-254`
- BambuStudio config dir: `~/Library/Application Support/BambuStudio/`

### Research findings (2026-03-15)

- `lsof -p <PID>` does NOT show open 3MF/STL files — BambuStudio loads to memory
- BambuStudio user config at `~/Library/Application Support/BambuStudio/user/3337974836/`
  contains only custom filament presets, no recent files list
- BambuStudio log files are encrypted (`.enc` extension) — not parseable
- Real test case: `~/Downloads/scull m 2.3mf` (57MB skull decoration project)
