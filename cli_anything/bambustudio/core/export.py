"""Export operations for BambuStudio projects.

Supports exporting to 3MF, STL, G-code, PNG screenshots, and JSON settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BackendResult,
)


def _run_export(
    backend: BambuStudioBackend,
    cmd: list[str],
    output_path: str,
    export_type: str,
) -> dict[str, Any]:
    """Shared helper that runs a backend export command.

    Args:
        backend: BambuStudioBackend instance.
        cmd: Full argument list for the binary.
        output_path: Expected output file path.
        export_type: Human-readable export type label.

    Returns:
        Dict with export result or error.
    """
    try:
        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or f"{export_type} export failed",
                "stdout": result.stdout,
                "exported": False,
            }

        out = Path(output_path)
        return {
            "exported": True,
            "type": export_type,
            "path": str(out.resolve()) if out.exists() else output_path,
            "file_size": out.stat().st_size if out.exists() else None,
        }
    except Exception as exc:
        return {"error": str(exc), "exported": False}


def export_3mf(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
    min_save: bool = False,
) -> dict[str, Any]:
    """Export project as a 3MF file.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .3mf path.
        backend: BambuStudioBackend instance.
        min_save: If True, produce a minimal 3MF (``--min-save``).

    Returns:
        Dict with export result.
    """
    p = Path(project_path)
    if not p.exists():
        return {"error": f"File not found: {project_path}", "exported": False}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["--export-3mf", str(p), "--output", output_path]
    if min_save:
        cmd.append("--min-save")

    return _run_export(backend, cmd, output_path, "3mf")


def export_stl(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
) -> dict[str, Any]:
    """Export project as an STL file.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .stl path.
        backend: BambuStudioBackend instance.

    Returns:
        Dict with export result.
    """
    p = Path(project_path)
    if not p.exists():
        return {"error": f"File not found: {project_path}", "exported": False}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["--export-stl", str(p), "--output", output_path]
    return _run_export(backend, cmd, output_path, "stl")


def export_gcode(
    project_path: str,
    output_dir: str,
    backend: BambuStudioBackend,
    plate: int = 0,
) -> dict[str, Any]:
    """Export sliced G-code from project.

    The project must be sliced first; this exports the resulting G-code
    files to *output_dir*.

    Args:
        project_path: Source .3mf path.
        output_dir: Directory for G-code output.
        backend: BambuStudioBackend instance.
        plate: Plate index (0 = all).

    Returns:
        Dict with export result.
    """
    p = Path(project_path)
    if not p.exists():
        return {"error": f"File not found: {project_path}", "exported": False}

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["--export-gcode", str(p), "--output-dir", str(out_dir)]
    if plate:
        cmd.extend(["--plate", str(plate)])

    try:
        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or "G-code export failed",
                "stdout": result.stdout,
                "exported": False,
            }

        # Collect generated gcode files
        gcode_files = sorted(out_dir.glob("*.gcode"))
        return {
            "exported": True,
            "type": "gcode",
            "output_dir": str(out_dir.resolve()),
            "plate": plate,
            "files": [str(f) for f in gcode_files],
            "file_count": len(gcode_files),
        }
    except Exception as exc:
        return {"error": str(exc), "exported": False}


def export_png(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
    plate: int = 0,
    camera_view: int = 0,
) -> dict[str, Any]:
    """Export a plate screenshot as PNG.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .png path.
        backend: BambuStudioBackend instance.
        plate: Plate index to capture.
        camera_view: Camera angle preset index.

    Returns:
        Dict with export result.
    """
    p = Path(project_path)
    if not p.exists():
        return {"error": f"File not found: {project_path}", "exported": False}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "--export-png", str(p),
        "--output", output_path,
        "--plate", str(plate),
        "--camera-view", str(camera_view),
    ]
    return _run_export(backend, cmd, output_path, "png")


def export_settings(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
) -> dict[str, Any]:
    """Export project settings as JSON.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .json path.
        backend: BambuStudioBackend instance.

    Returns:
        Dict with export result.
    """
    p = Path(project_path)
    if not p.exists():
        return {"error": f"File not found: {project_path}", "exported": False}

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["--export-settings", str(p), "--output", output_path]
    return _run_export(backend, cmd, output_path, "settings")
