"""Slicing operations for BambuStudio projects.

Wraps the BambuStudio binary's slicing commands and parses result.json
output for time/material estimates.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BackendResult,
)


def slice_project(
    project_path: str,
    backend: BambuStudioBackend,
    plate: int = 0,
    output_dir: str | None = None,
    no_check: bool = False,
    settings_files: list[str] | None = None,
    filament_files: list[str] | None = None,
) -> dict[str, Any]:
    """Run the slicer on a project.

    Args:
        project_path: Path to the .3mf file to slice.
        backend: BambuStudioBackend instance for running the binary.
        plate: Plate index to slice (0 = all plates).
        output_dir: Directory for slice output files.  A temporary
            directory is used when *None*.
        no_check: If True, skip pre-flight checks (``--no-check``).
        settings_files: Optional list of --load-settings file paths.
        filament_files: Optional list of --load-filaments file paths.

    Returns:
        Dict with parsed result.json data or error details.
    """
    try:
        p = Path(project_path)
        if not p.exists():
            return {"error": f"File not found: {project_path}", "sliced": False}

        # Validate settings files exist before running
        for sf in (settings_files or []):
            if not os.path.isfile(sf):
                return {"error": f"Settings file not found: {sf}", "sliced": False}
        for ff in (filament_files or []):
            if not os.path.isfile(ff):
                return {"error": f"Filament file not found: {ff}", "sliced": False}

        use_temp = output_dir is None
        if use_temp:
            output_dir = tempfile.mkdtemp(prefix="bambustudio_slice_")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        cmd: list[str] = [
            "--slice", str(plate),
            "--outputdir", str(out_path),
        ]
        if no_check:
            cmd.append("--no-check")

        # Add settings loading flags
        for sf in (settings_files or []):
            cmd.extend(["--load-settings", sf])
        for ff in (filament_files or []):
            cmd.extend(["--load-filaments", ff])

        result: BackendResult = backend.run(cmd, input_files=[str(p)])

        if not result.ok:
            return {
                "error": result.stderr or "Slicing failed",
                "stdout": result.stdout,
                "sliced": False,
            }

        # Parse result.json produced by the slicer
        result_json_path = out_path / "result.json"
        parsed: dict[str, Any] = {}
        if result_json_path.exists():
            with open(result_json_path, "r", encoding="utf-8") as fh:
                parsed = json.load(fh)

        return {
            "sliced": True,
            "project": str(p.resolve()),
            "output_dir": str(out_path),
            "plate": plate,
            "result": parsed,
        }
    except json.JSONDecodeError as exc:
        return {"error": f"Failed to parse result.json: {exc}", "sliced": False}
    except Exception as exc:
        return {"error": str(exc), "sliced": False}


def get_slice_estimate(
    project_path: str,
    backend: BambuStudioBackend,
    plate: int = 0,
) -> dict[str, Any]:
    """Get time and material estimates by performing a slice.

    Slices the project into a temporary directory, then extracts
    estimated print time, filament usage, and layer count from the
    result.json.

    Args:
        project_path: Path to the .3mf file.
        backend: BambuStudioBackend instance.
        plate: Plate index (0 = all).

    Returns:
        Dict with estimate fields or error details.
    """
    slice_result = slice_project(
        project_path=project_path,
        backend=backend,
        plate=plate,
    )

    if not slice_result.get("sliced"):
        return {
            "error": slice_result.get("error", "Slicing failed"),
            "estimated": False,
        }

    parsed = slice_result.get("result", {})

    # Extract common estimate fields from the slicer output
    estimate: dict[str, Any] = {
        "estimated": True,
        "project": slice_result.get("project"),
        "plate": plate,
    }

    # BambuStudio result.json structure varies; extract what's available
    if "print_time" in parsed:
        estimate["print_time_seconds"] = parsed["print_time"]
    if "total_time" in parsed:
        estimate["print_time_seconds"] = parsed["total_time"]
    if "filament" in parsed:
        estimate["filament"] = parsed["filament"]
    if "filament_used_g" in parsed:
        estimate["filament_used_g"] = parsed["filament_used_g"]
    if "filament_used_m" in parsed:
        estimate["filament_used_m"] = parsed["filament_used_m"]
    if "total_layers" in parsed:
        estimate["total_layers"] = parsed["total_layers"]
    if "layer_height" in parsed:
        estimate["layer_height"] = parsed["layer_height"]

    # If structured plate data exists, include it
    if "plates" in parsed and isinstance(parsed["plates"], list):
        estimate["plates"] = parsed["plates"]

    # Pass through any unrecognised top-level keys
    for key in ("cost", "weight", "volume"):
        if key in parsed:
            estimate[key] = parsed[key]

    return estimate
