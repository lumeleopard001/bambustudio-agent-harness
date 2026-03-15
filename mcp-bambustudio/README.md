# BambuStudio MCP Server

Claude Desktop integration for 3D printing with BambuStudio.

## Setup

### 1. Install the MCP package

```bash
~/.bambustudio-harness/venv/bin/pip install mcp
```

### 2. Add to Claude Desktop config

Open Claude Desktop settings, navigate to "MCP Servers", and add:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "bambustudio": {
      "command": "~/.bambustudio-harness/venv/bin/python",
      "args": [
        "/path/to/bambustudio-agent-harness/mcp-bambustudio/server.py"
      ]
    }
  }
}
```

Replace `/path/to/` with the actual path to the repository.

### 3. Restart Claude Desktop

Close and reopen Claude Desktop. You should see "BambuStudio" in the MCP tools list.

## Available Tools

| Tool | Description |
|------|-------------|
| `slice_stl` | Slice an STL file — returns print time, filament usage, output path |
| `spool_status` | Show all spools, loaded slots, remaining weights |
| `spool_add` | Register a new filament spool |
| `spool_load` | Load a spool into a printer slot |
| `spool_unload` | Unload a spool from a slot |
| `available_printers` | List all printers |
| `available_materials` | List materials for a printer |
| `open_in_studio` | Open a .3mf/.stl file in BambuStudio GUI |
| `review_project` | Analyze a 3MF project |

## Example Conversation

> **You:** Slice this STL file for my A1 printer with PLA
>
> **Claude:** *calls slice_stl with your file path*
>
> Print time: 45 minutes
> Filament: 12.3g PLA
> Output: /tmp/bambustudio_auto_xxx/model_project.3mf

> **You:** How much filament do I have left?
>
> **Claude:** *calls spool_status*
>
> AMS:1 — Spool #1 (PLA white): 847.3g (84.7%)
> AMS:2 — Spool #2 (PLA black): 412.8g (41.3%)
> AMS:3 — empty
> AMS:4 — Spool #4 (PLA blue): 123.5g (12.4%) ⚠️ running low
