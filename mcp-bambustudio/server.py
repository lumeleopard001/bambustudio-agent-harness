"""MCP Server for BambuStudio Agent Harness.

Exposes slicing, profile discovery, and spool inventory as MCP tools
for Claude Desktop and other MCP-compatible clients.

Usage:
    python -m mcp-bambustudio.server          # stdio transport (Claude Desktop)
    python mcp-bambustudio/server.py          # direct run
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# Add parent dir to path so we can import cli_anything
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "Error: 'mcp' package not found. Install it with:\n"
        "  pip install mcp\n",
        file=sys.stderr,
    )
    sys.exit(1)

from cli_anything.bambustudio.core.workflow import workflow_auto, workflow_review, workflow_slice_project
from cli_anything.bambustudio.core.discovery import discover_projects as _discover_projects
from cli_anything.bambustudio.utils.bambustudio_backend import open_in_bambustudio
from cli_anything.bambustudio.core.config import (
    list_printers,
    list_filaments,
    suggest_preset,
)
from cli_anything.bambustudio.core.inventory import SpoolRegistry


mcp = FastMCP(
    "BambuStudio",
    instructions=(
        "3D printing tools for Bambu Lab printers. "
        "When the user mentions a file without giving a path, "
        "call discover_projects first to find it. "
        "For 3MF files (from Makerworld or BambuStudio), use slice_project. "
        "For raw STL files, use slice_stl."
    ),
)


@mcp.tool()
def slice_stl(
    stl_path: str,
    printer: str = "Bambu Lab A1",
    material: str = "PLA",
    quality: str = "standard",
    track_usage: bool = False,
) -> dict[str, Any]:
    """Slice an STL file for 3D printing.

    Takes an STL file path and returns print time estimate, filament usage,
    and the output 3MF project path.

    Args:
        stl_path: Absolute path to the STL file.
        printer: Printer name (default: Bambu Lab A1).
        material: Material type: PLA, PETG, ABS, TPU (default: PLA).
        quality: Print quality: draft, standard, fine, extra-fine (default: standard).
        track_usage: If True, deduct filament from loaded spools.
    """
    result = workflow_auto(
        stl_path=stl_path,
        printer=printer,
        material=material,
        quality=quality,
    )

    if track_usage and result.get("ok") and result.get("result"):
        try:
            registry = SpoolRegistry()
            deductions = registry.track_workflow_usage(
                result["result"],
                project_name=os.path.basename(stl_path),
            )
            result["usage_tracking"] = deductions
        except Exception as e:
            result.setdefault("warnings", []).append(f"Usage tracking failed: {e}")

    return result


@mcp.tool()
def spool_status() -> dict[str, Any]:
    """Show filament inventory: all spools, loaded slots, and remaining weights."""
    registry = SpoolRegistry()
    return registry.status()


@mcp.tool()
def spool_add(
    spool_id: int,
    brand: str,
    material: str,
    color: str,
    variant: str = "",
    weight: float | None = None,
    slot: str | None = None,
) -> dict[str, Any]:
    """Register a new filament spool.

    Args:
        spool_id: Unique numeric ID for this spool.
        brand: Brand name (Bambu, Sunlu, eSun, ...).
        material: Material type (PLA, PETG, ABS, TPU, ...).
        color: Color name (white, black, red, ...).
        variant: Variant (Basic, Silk, Matte). Optional.
        weight: Spool weight in grams. Auto-detected by material if omitted.
        slot: Load directly into slot (AMS:1, AMS:2, AMS:3, AMS:4, EXT:1). Optional.
    """
    registry = SpoolRegistry()
    return registry.add(
        spool_id=spool_id, brand=brand, material=material,
        variant=variant, color=color, weight=weight, slot=slot,
    )


@mcp.tool()
def spool_load(spool_id: int, slot: str) -> dict[str, Any]:
    """Load a spool into a printer slot. Auto-unloads any occupant.

    Args:
        spool_id: ID of the spool to load.
        slot: Target slot (AMS:1, AMS:2, AMS:3, AMS:4, or EXT:1).
    """
    registry = SpoolRegistry()
    return registry.load_spool(spool_id, slot)


@mcp.tool()
def spool_unload(slot: str) -> dict[str, Any]:
    """Unload a spool from a slot (moves to storage, remembers remaining weight).

    Args:
        slot: Slot to unload (AMS:1, AMS:2, AMS:3, AMS:4, or EXT:1).
    """
    registry = SpoolRegistry()
    return registry.unload(slot)


@mcp.tool()
def available_printers() -> list[dict[str, Any]]:
    """List all available 3D printers with nozzle options."""
    return list_printers()


@mcp.tool()
def available_materials(printer: str = "Bambu Lab A1") -> list[dict[str, Any]]:
    """List filament materials compatible with a printer.

    Args:
        printer: Printer name (default: Bambu Lab A1).
    """
    return list_filaments(printer=printer)


@mcp.tool()
def open_in_studio(project_path: str) -> dict[str, Any]:
    """Open a sliced project in BambuStudio for visual preview and printing.

    After opening, click 'Send to Printer' in BambuStudio to start printing.

    Args:
        project_path: Absolute path to the .3mf or .stl file.
    """
    return open_in_bambustudio(project_path)


@mcp.tool()
def discover_projects(query: str = "", limit: int = 10) -> dict[str, Any]:
    """Find recent 3MF and STL files on this machine.

    Scans Downloads, Desktop, and Documents for 3D print files,
    sorted by most recently modified. Use this when the user
    mentions a file but doesn't provide the full path.

    Args:
        query: Optional search term to filter by filename (e.g. "skull", "vase").
        limit: Maximum number of results (default: 10).
    """
    return _discover_projects(query=query, limit=limit)


@mcp.tool()
def slice_project(
    project_path: str,
    printer: str = "Bambu Lab A1",
    material: str = "PLA",
    quality: str = "standard",
    plate: int = 0,
    track_usage: bool = False,
) -> dict[str, Any]:
    """Slice a 3MF project for 3D printing.

    Handles both BambuStudio-native and third-party 3MF files.
    For third-party files that crash the slicer, automatically extracts
    geometry and applies the specified printer/material/quality settings.

    Args:
        project_path: Absolute path to the .3mf file.
        printer: Printer name (default: Bambu Lab A1). Used if embedded presets fail.
        material: Material type: PLA, PETG, ABS, TPU (default: PLA). Used if embedded presets fail.
        quality: Print quality: draft, standard, fine (default: standard). Used if embedded presets fail.
        plate: Plate to slice (0 = all plates).
        track_usage: If True, deduct filament from loaded spools.
    """
    result = workflow_slice_project(
        project_path=project_path,
        printer=printer,
        material=material,
        quality=quality,
        plate=plate,
    )

    if track_usage and result.get("ok") and result.get("result"):
        try:
            registry = SpoolRegistry()
            deductions = registry.track_workflow_usage(
                result["result"],
                project_name=os.path.basename(project_path),
            )
            result["usage_tracking"] = deductions
        except Exception as e:
            result.setdefault("warnings", []).append(f"Usage tracking failed: {e}")

    return result


@mcp.tool()
def review_project(project_path: str) -> dict[str, Any]:
    """Review an existing 3MF project and suggest improvements.

    Args:
        project_path: Absolute path to the .3mf file.
    """
    return workflow_review(project_path=project_path)


if __name__ == "__main__":
    mcp.run()
