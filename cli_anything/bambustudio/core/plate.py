"""Plate management for BambuStudio 3MF projects.

Handles listing, adding, removing, and inspecting build plates within
a 3MF project via Python-side XML manipulation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BackendResult,
)
from cli_anything.bambustudio.utils.threemf import ThreeMF


def list_plates(path: str) -> list[dict[str, Any]]:
    """List all plates in a 3MF project.

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
                "name": getattr(plate, "name", f"Plate {idx + 1}"),
                "object_ids": getattr(plate, "object_ids", []),
                "object_count": len(getattr(plate, "object_ids", [])),
            }
            for idx, plate in enumerate(plates)
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def add_plate(
    path: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Add a new empty plate to the project.

    Args:
        path: Path to the .3mf file.
        output_path: Destination path.  Overwrites source when *None*.

    Returns:
        Dict with the new plate info or error details.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}", "added": False}

        tmf = ThreeMF.load(str(p))
        plates_before = tmf.plates if hasattr(tmf, "plates") else []
        count_before = len(plates_before)

        tmf.add_plate()

        dest = output_path or str(p)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        tmf.save(dest)

        plates_after = tmf.plates if hasattr(tmf, "plates") else []

        return {
            "added": True,
            "plates_before": count_before,
            "plates_after": len(plates_after),
            "new_plate_index": len(plates_after) - 1,
            "path": str(Path(dest).resolve()),
        }
    except Exception as exc:
        return {"error": str(exc), "added": False}


def remove_plate(
    path: str,
    plate_index: int,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Remove a plate from the project by index.

    Objects assigned to the removed plate are unassigned but not deleted.

    Args:
        path: Path to the .3mf file.
        plate_index: Zero-based index of the plate to remove.
        output_path: Destination path.  Overwrites source when *None*.

    Returns:
        Dict with removal result or error details.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}", "removed": False}

        tmf = ThreeMF.load(str(p))
        plates = tmf.plates if hasattr(tmf, "plates") else []

        if plate_index < 0 or plate_index >= len(plates):
            return {
                "error": f"Plate index {plate_index} out of range (0..{len(plates) - 1})",
                "removed": False,
                "plate_count": len(plates),
            }

        # Prevent removing the last plate
        if len(plates) <= 1:
            return {
                "error": "Cannot remove the only plate",
                "removed": False,
                "plate_count": len(plates),
            }

        count_before = len(plates)
        tmf.remove_plate(plate_index)

        dest = output_path or str(p)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        tmf.save(dest)

        plates_after = tmf.plates if hasattr(tmf, "plates") else []

        return {
            "removed": True,
            "plate_index": plate_index,
            "plates_before": count_before,
            "plates_after": len(plates_after),
            "path": str(Path(dest).resolve()),
        }
    except Exception as exc:
        return {"error": str(exc), "removed": False}


def get_plate_info(
    path: str,
    plate_index: int,
    backend: BambuStudioBackend | None = None,
) -> dict[str, Any]:
    """Get detailed information about a specific plate.

    Args:
        path: Path to the .3mf file.
        plate_index: Zero-based index of the plate.
        backend: Optional backend for enriched metadata.

    Returns:
        Dict with plate details or error info.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}"}

        tmf = ThreeMF.load(str(p))
        plates = tmf.plates if hasattr(tmf, "plates") else []

        if plate_index < 0 or plate_index >= len(plates):
            return {
                "error": f"Plate index {plate_index} out of range (0..{len(plates) - 1})",
                "plate_count": len(plates),
            }

        plate = plates[plate_index]
        objects = tmf.objects if hasattr(tmf, "objects") else []

        # Build object details for this plate
        plate_obj_ids = plate.object_ids if hasattr(plate, "object_ids") else []
        plate_objects: list[dict[str, Any]] = []
        for obj in objects:
            obj_id = obj.id if hasattr(obj, "id") else None
            if obj_id in plate_obj_ids:
                plate_objects.append({
                    "id": obj_id,
                    "name": obj.name if hasattr(obj, "name") else f"object_{obj_id}",
                    "vertices": obj.vertices if hasattr(obj, "vertices") else None,
                    "triangles": obj.triangles if hasattr(obj, "triangles") else None,
                })

        info: dict[str, Any] = {
            "index": plate_index,
            "name": plate.name if hasattr(plate, "name") else f"Plate {plate_index + 1}",
            "object_ids": plate_obj_ids,
            "object_count": len(plate_obj_ids),
            "objects": plate_objects,
        }

        # Enrich with backend info if available
        if backend is not None:
            try:
                result: BackendResult = backend.run([
                    "--plate-info", str(p),
                    "--plate", str(plate_index),
                ])
                if result.ok and result.data:
                    info["backend_info"] = result.data
            except Exception:
                pass  # best-effort enrichment

        return info
    except Exception as exc:
        return {"error": str(exc)}
