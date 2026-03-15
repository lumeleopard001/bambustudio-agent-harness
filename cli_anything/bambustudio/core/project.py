"""Project lifecycle management for BambuStudio 3MF projects.

Handles creating, opening, saving, and inspecting 3MF project files.
All functions return dicts suitable for OutputFormatter consumption.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.threemf import (
    ThreeMF,
    create_minimal_3mf,
)
from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BackendResult,
)


def create_project(
    output_path: str,
    printer_preset: str | None = None,
) -> dict[str, Any]:
    """Create a new empty 3MF project file.

    Args:
        output_path: Destination path for the new .3mf file.
        printer_preset: Optional printer preset name to embed in config.

    Returns:
        Dict with project creation info or error details.
    """
    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        tmf = create_minimal_3mf(printer_preset=printer_preset)
        tmf.save(str(out))

        return {
            "path": str(out.resolve()),
            "printer_preset": printer_preset,
            "objects": 0,
            "plates": len(tmf.plates) if hasattr(tmf, "plates") else 1,
            "created": True,
        }
    except Exception as exc:
        return {"error": str(exc), "created": False}


def open_project(path: str) -> dict[str, Any]:
    """Open and validate a 3MF project file.

    Args:
        path: Path to an existing .3mf file.

    Returns:
        Dict with project info or error details.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}"}
        if p.suffix.lower() != ".3mf":
            return {"error": f"Not a 3MF file: {path}"}

        tmf = ThreeMF.load(str(p))

        objects = tmf.objects if hasattr(tmf, "objects") else []
        plates = tmf.plates if hasattr(tmf, "plates") else []

        return {
            "path": str(p.resolve()),
            "file_size": p.stat().st_size,
            "objects": len(objects),
            "plates": len(plates),
            "valid": True,
        }
    except Exception as exc:
        return {"error": str(exc), "valid": False}


def save_project(tmf: ThreeMF, output_path: str) -> dict[str, Any]:
    """Save a ThreeMF instance to a file.

    Args:
        tmf: The ThreeMF object to save.
        output_path: Destination file path.

    Returns:
        Dict with save result info.
    """
    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmf.save(str(out))

        return {
            "path": str(out.resolve()),
            "file_size": out.stat().st_size,
            "saved": True,
        }
    except Exception as exc:
        return {"error": str(exc), "saved": False}


def get_project_info(
    path: str,
    backend: BambuStudioBackend | None = None,
) -> dict[str, Any]:
    """Get comprehensive project information.

    Uses Python-side 3MF parsing for structure info.  If a backend is
    provided, also runs ``--info`` on the binary for extra metadata
    (printer model, filament, etc.).

    Args:
        path: Path to the .3mf file.
        backend: Optional BambuStudioBackend for enriched info.

    Returns:
        Dict with project metadata.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}"}

        tmf = ThreeMF.load(str(p))

        objects = tmf.objects if hasattr(tmf, "objects") else []
        plates = tmf.plates if hasattr(tmf, "plates") else []

        info: dict[str, Any] = {
            "path": str(p.resolve()),
            "file_size": p.stat().st_size,
            "objects": [
                {
                    "id": getattr(obj, "id", idx),
                    "name": getattr(obj, "name", f"object_{idx}"),
                    "vertices": getattr(obj, "vertices", None),
                    "triangles": getattr(obj, "triangles", None),
                }
                for idx, obj in enumerate(objects)
            ],
            "plates": [
                {
                    "index": getattr(plate, "index", idx),
                    "object_ids": getattr(plate, "object_ids", []),
                }
                for idx, plate in enumerate(plates)
            ],
        }

        # Enrich with binary backend info when available
        if backend is not None:
            try:
                result: BackendResult = backend.run(["--info", str(p)])
                if result.ok:
                    info["backend_info"] = result.data
            except Exception:
                pass  # binary info is best-effort

        return info
    except Exception as exc:
        return {"error": str(exc)}


def list_plates(path: str) -> list[dict[str, Any]]:
    """List all plates in a 3MF project with their objects.

    Args:
        path: Path to the .3mf file.

    Returns:
        List of plate info dicts.
    """
    try:
        p = Path(path)
        if not p.exists():
            return [{"error": f"File not found: {path}"}]

        tmf = ThreeMF.load(str(p))
        plates = tmf.plates if hasattr(tmf, "plates") else []

        return [
            {
                "index": getattr(plate, "index", idx),
                "object_ids": getattr(plate, "object_ids", []),
                "object_count": len(getattr(plate, "object_ids", [])),
            }
            for idx, plate in enumerate(plates)
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def list_objects(
    path: str,
    backend: BambuStudioBackend | None = None,
) -> list[dict[str, Any]]:
    """List all objects in a 3MF project with mesh statistics.

    Args:
        path: Path to the .3mf file.
        backend: Optional backend for enriched mesh stats.

    Returns:
        List of object info dicts.
    """
    try:
        p = Path(path)
        if not p.exists():
            return [{"error": f"File not found: {path}"}]

        tmf = ThreeMF.load(str(p))
        objects = tmf.objects if hasattr(tmf, "objects") else []

        result = []
        for idx, obj in enumerate(objects):
            entry: dict[str, Any] = {
                "id": getattr(obj, "id", idx),
                "name": getattr(obj, "name", f"object_{idx}"),
                "vertices": getattr(obj, "vertices", None),
                "triangles": getattr(obj, "triangles", None),
            }
            if hasattr(obj, "volume"):
                entry["volume"] = obj.volume
            if hasattr(obj, "bounding_box"):
                entry["bounding_box"] = obj.bounding_box
            result.append(entry)

        return result
    except Exception as exc:
        return [{"error": str(exc)}]
