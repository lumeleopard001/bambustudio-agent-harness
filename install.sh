#!/usr/bin/env bash
# BambuStudio Agent Harness — One-command installer
# Usage: bash install.sh  (run from the cloned repo directory)

set -euo pipefail

HARNESS_DIR="$HOME/.bambustudio-harness"
VENV_DIR="$HARNESS_DIR/venv"
REPO_DIR=""
MIN_PYTHON="3.10"

# Colors (if terminal supports them)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    RED='\033[0;31m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' NC=''
fi

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!!]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# ---------------------------------------------------------------
# Step 1: Check Python >= 3.10
# ---------------------------------------------------------------
echo "=== BambuStudio Agent Harness Installer ==="
echo ""

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        if [ -n "$ver" ]; then
            major=${ver%%.*}
            minor=${ver#*.}
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                PYTHON="$cmd"
                break
            fi
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python >= $MIN_PYTHON not found.

    macOS:  brew install python@3.12
    Linux:  sudo apt install python3.12 python3.12-venv

    Then re-run this installer."
fi
info "Python found: $PYTHON ($($PYTHON --version 2>&1))"

# ---------------------------------------------------------------
# Step 2: Check BambuStudio
# ---------------------------------------------------------------
BS_FOUND=false

if [ "$(uname)" = "Darwin" ]; then
    # macOS: check /Applications
    if [ -d "/Applications/BambuStudio.app" ]; then
        BS_FOUND=true
        info "BambuStudio found: /Applications/BambuStudio.app"
    fi
elif [ -f "/usr/bin/bambu-studio" ] || [ -f "/usr/local/bin/bambu-studio" ]; then
    BS_FOUND=true
    info "BambuStudio found in PATH"
fi

if [ "$BS_FOUND" = false ]; then
    warn "BambuStudio not found (the CLI tool will search for it at runtime).
    Download from: https://bambulab.com/en/download/studio

    The tool can still be installed — it will find BambuStudio later."
fi

# ---------------------------------------------------------------
# Step 3: Find or clone repo
# ---------------------------------------------------------------
# Check if we're running from inside the repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/setup.py" ] && grep -q "cli-anything-bambustudio" "$SCRIPT_DIR/setup.py" 2>/dev/null; then
    REPO_DIR="$SCRIPT_DIR"
    info "Running from repo: $REPO_DIR"
else
    fail "Please run this script from the repository root directory.

    git clone <repo-url>
    cd bambustudio-agent-harness
    bash install.sh"
fi

# ---------------------------------------------------------------
# Step 4: Create virtualenv
# ---------------------------------------------------------------
echo ""
echo "Creating virtual environment..."

if [ -d "$VENV_DIR" ]; then
    warn "Existing venv found at $VENV_DIR — removing"
    rm -rf "$VENV_DIR"
fi

"$PYTHON" -m venv "$VENV_DIR"
info "Virtual environment created: $VENV_DIR"

# ---------------------------------------------------------------
# Step 5: Install package
# ---------------------------------------------------------------
echo ""
echo "Installing bambustudio-agent-harness..."

"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$REPO_DIR"
info "Package installed"

# ---------------------------------------------------------------
# Step 6: Create symlink in a PATH-accessible location
# ---------------------------------------------------------------
BIN_NAME="cli-anything-bambustudio"
SYMLINK_DIR="$HARNESS_DIR/bin"
mkdir -p "$SYMLINK_DIR"

VENV_BIN="$VENV_DIR/bin/$BIN_NAME"
SYMLINK_PATH="$SYMLINK_DIR/$BIN_NAME"

if [ -f "$VENV_BIN" ]; then
    ln -sf "$VENV_BIN" "$SYMLINK_PATH"
    info "Symlink created: $SYMLINK_PATH"
else
    warn "Entry point $BIN_NAME not found in venv — checking pip install"
fi

# Check if symlink dir is in PATH
if [[ ":$PATH:" != *":$SYMLINK_DIR:"* ]]; then
    SHELL_RC=""
    if [ -n "${ZSH_VERSION:-}" ] || [ "$SHELL" = "/bin/zsh" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -n "${BASH_VERSION:-}" ] || [ "$SHELL" = "/bin/bash" ]; then
        SHELL_RC="$HOME/.bashrc"
    fi

    if [ -n "$SHELL_RC" ]; then
        # Avoid duplicate PATH entries on re-run
        if ! grep -q "bambustudio-harness/bin" "$SHELL_RC" 2>/dev/null; then
            echo "" >> "$SHELL_RC"
            echo "# BambuStudio Agent Harness" >> "$SHELL_RC"
            echo "export PATH=\"$SYMLINK_DIR:\$PATH\"" >> "$SHELL_RC"
            info "Added $SYMLINK_DIR to PATH in $SHELL_RC"
        else
            info "PATH already configured in $SHELL_RC"
        fi
        warn "Run 'source $SHELL_RC' or open a new terminal for PATH changes"
    else
        warn "Add this to your shell profile:
    export PATH=\"$SYMLINK_DIR:\$PATH\""
    fi
fi

# ---------------------------------------------------------------
# Step 7: Verify installation
# ---------------------------------------------------------------
echo ""
echo "Verifying installation..."

if "$VENV_BIN" --help &>/dev/null; then
    info "Verification passed"
else
    warn "Verification failed — the tool may still work after PATH update"
fi

# ---------------------------------------------------------------
# Step 8: Create data directory
# ---------------------------------------------------------------
mkdir -p "$HARNESS_DIR"
info "Data directory: $HARNESS_DIR"

# ---------------------------------------------------------------
# Step 9: Install MCP package and configure Claude Desktop
# ---------------------------------------------------------------
echo ""
echo "Setting up Claude Desktop integration..."

"$VENV_DIR/bin/pip" install --quiet mcp 2>/dev/null && info "MCP package installed" || warn "MCP package install failed (Claude Desktop integration optional)"

CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
CLAUDE_CONFIG="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"
MCP_SERVER_PATH="$REPO_DIR/mcp-bambustudio/server.py"
MCP_PYTHON="$VENV_DIR/bin/python"

if [ "$(uname)" = "Darwin" ] && [ -d "$CLAUDE_CONFIG_DIR" ]; then
    # Claude Desktop is installed — configure MCP server
    if [ -f "$CLAUDE_CONFIG" ]; then
        # Check if bambustudio is already configured
        if grep -q "bambustudio" "$CLAUDE_CONFIG" 2>/dev/null; then
            info "Claude Desktop MCP already configured"
        else
            # Add bambustudio server to existing config
            "$VENV_DIR/bin/python" -c "
import json, sys
try:
    with open('$CLAUDE_CONFIG', 'r') as f:
        config = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    config = {}
if 'mcpServers' not in config:
    config['mcpServers'] = {}
config['mcpServers']['bambustudio'] = {
    'command': '$MCP_PYTHON',
    'args': ['$MCP_SERVER_PATH']
}
with open('$CLAUDE_CONFIG', 'w') as f:
    json.dump(config, f, indent=2)
print('OK')
" 2>/dev/null && info "Claude Desktop MCP configured" || warn "Could not update Claude Desktop config"
        fi
    else
        # Create new config file
        mkdir -p "$CLAUDE_CONFIG_DIR"
        cat > "$CLAUDE_CONFIG" << MCPEOF
{
  "mcpServers": {
    "bambustudio": {
      "command": "$MCP_PYTHON",
      "args": ["$MCP_SERVER_PATH"]
    }
  }
}
MCPEOF
        info "Claude Desktop MCP config created"
    fi
    warn "Restart Claude Desktop to activate (Quit + reopen)"
else
    if [ "$(uname)" = "Darwin" ]; then
        warn "Claude Desktop not detected — install from https://claude.ai/download"
        echo "    After installing, re-run: bash install.sh"
    fi
fi

# ---------------------------------------------------------------
# Done
# ---------------------------------------------------------------
echo ""
echo "=================================================="
echo -e "${GREEN}Installation complete!${NC}"
echo "=================================================="
echo ""
echo "Quick start:"
echo "  $BIN_NAME --help"
echo ""
echo "Or with full path:"
echo "  $VENV_BIN --help"
echo ""
echo "Slice an STL:"
echo "  $BIN_NAME --json workflow auto \\"
echo "    --stl model.stl \\"
echo "    --printer \"Bambu Lab A1\" \\"
echo "    --material PLA"
echo ""
echo "Interactive mode:"
echo "  $BIN_NAME"
echo ""

if [ "$BS_FOUND" = false ]; then
    echo -e "${YELLOW}Note:${NC} Install BambuStudio for full functionality:"
    echo "  https://bambulab.com/en/download/studio"
    echo ""
fi
