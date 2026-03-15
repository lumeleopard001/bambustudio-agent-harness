"""Object manipulation for BambuStudio 3MF projects.

Handles importing models (STL/OBJ/STEP), transforming, arranging,
orienting, and deleting objects within a project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BackendResult,
)
from cli_anything.bambustudio.utils.threemf import ThreeMF


def import_model(
    project_path: str,
    model_file: str,
    backend: BambuStudioBackend,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Import an STL/OBJ/STEP model into a 3MF project.

    Args:
        project_path: Path to the target .3mf project.
        model_file: Path to the model file to import.
        backend: BambuStudioBackend instance.
        output_path: Where to save the result.  Overwrites the source
            project when *None*.

    Returns:
        Dict with import result or error details.
    """
    try:
        proj = Path(project_path)
        model = Path(model_file)

        if not proj.exists():
            return {"error": f"Project not found: {project_path}", "imported": False}
        if not model.exists():
            return {"error": f"Model file not found: {model_file}", "imported": False}

        dest = output_path or str(proj)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)

        cmd = ["--import", str(model), "--project", str(proj), "--output", dest]
        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or "Import failed",
                "stdout": result.stdout,
                "imported": False,
            }

        out = Path(dest)
        return {
            "imported": True,
            "model_file": str(model.resolve()),
            "project": str(out.resolve()),
            "file_size": out.stat().st_size if out.exists() else None,
        }
    except Exception as exc:
        return {"error": str(exc), "imported": False}


def transform_object(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
    rotate_z: float | None = None,
    rotate_x: float | None = None,
    rotate_y: float | None = None,
    scale: float | None = None,
) -> dict[str, Any]:
    """Transform objects in a project via a binary round-trip.

    Passes rotation and scale parameters to the BambuStudio binary
    which applies them and writes the result.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .3mf path.
        backend: BambuStudioBackend instance.
        rotate_z: Rotation around Z axis in degrees.
        rotate_x: Rotation around X axis in degrees.
        rotate_y: Rotation around Y axis in degrees.
        scale: Uniform scale factor (1.0 = 100%).

    Returns:
        Dict with transform result.
    """
    try:
        proj = Path(project_path)
        if not proj.exists():
            return {"error": f"File not found: {project_path}", "transformed": False}

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        cmd = ["--transform", str(proj), "--output", output_path]

        transforms_applied: list[str] = []
        if rotate_x is not None:
            cmd.extend(["--rotate-x", str(rotate_x)])
            transforms_applied.append(f"rotate_x={rotate_x}")
        if rotate_y is not None:
            cmd.extend(["--rotate-y", str(rotate_y)])
            transforms_applied.append(f"rotate_y={rotate_y}")
        if rotate_z is not None:
            cmd.extend(["--rotate-z", str(rotate_z)])
            transforms_applied.append(f"rotate_z={rotate_z}")
        if scale is not None:
            cmd.extend(["--scale", str(scale)])
            transforms_applied.append(f"scale={scale}")

        if not transforms_applied:
            return {"error": "No transform parameters specified", "transformed": False}

        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or "Transform failed",
                "stdout": result.stdout,
                "transformed": False,
            }

        out = Path(output_path)
        return {
            "transformed": True,
            "transforms": transforms_applied,
            "path": str(out.resolve()) if out.exists() else output_path,
            "file_size": out.stat().st_size if out.exists() else None,
        }
    except Exception as exc:
        return {"error": str(exc), "transformed": False}


def arrange_objects(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
) -> dict[str, Any]:
    """Auto-arrange objects on the build plate.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .3mf path.
        backend: BambuStudioBackend instance.

    Returns:
        Dict with arrange result.
    """
    try:
        proj = Path(project_path)
        if not proj.exists():
            return {"error": f"File not found: {project_path}", "arranged": False}

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        cmd = ["--arrange", str(proj), "--output", output_path]
        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or "Arrange failed",
                "stdout": result.stdout,
                "arranged": False,
            }

        out = Path(output_path)
        return {
            "arranged": True,
            "path": str(out.resolve()) if out.exists() else output_path,
            "file_size": out.stat().st_size if out.exists() else None,
        }
    except Exception as exc:
        return {"error": str(exc), "arranged": False}


def orient_objects(
    project_path: str,
    output_path: str,
    backend: BambuStudioBackend,
) -> dict[str, Any]:
    """Auto-orient objects for optimal printing.

    Args:
        project_path: Source .3mf path.
        output_path: Destination .3mf path.
        backend: BambuStudioBackend instance.

    Returns:
        Dict with orient result.
    """
    try:
        proj = Path(project_path)
        if not proj.exists():
            return {"error": f"File not found: {project_path}", "oriented": False}

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        cmd = ["--orient", str(proj), "--output", output_path]
        result: BackendResult = backend.run(cmd)

        if not result.ok:
            return {
                "error": result.stderr or "Orient failed",
                "stdout": result.stdout,
                "oriented": False,
            }

        out = Path(output_path)
        return {
            "oriented": True,
            "path": str(out.resolve()) if out.exists() else output_path,
            "file_size": out.stat().st_size if out.exists() else None,
        }
    except Exception as exc:
        return {"error": str(exc), "oriented": False}


def delete_object(
    project_path: str,
    object_id: int,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Delete an object from a project by ID.

    Performs Python-side XML removal — no binary backend needed.

    Args:
        project_path: Path to the .3mf file.
        object_id: ID of the object to remove.
        output_path: Destination path.  Overwrites source when *None*.

    Returns:
        Dict with deletion result.
    """
    try:
        proj = Path(project_path)
        if not proj.exists():
            return {"error": f"File not found: {project_path}", "deleted": False}

        tmf = ThreeMF.load(str(proj))
        objects_before = tmf.objects if hasattr(tmf, "objects") else []

        # Find the object to delete
        found = False
        for obj in objects_before:
            obj_id = getattr(obj, "id", None)
            if obj_id == object_id:
                found = True
                break

        if not found:
            return {
                "error": f"Object with id {object_id} not found",
                "deleted": False,
                "available_ids": [
                    obj.id for obj in objects_before if hasattr(obj, "id")
                ],
            }

        tmf.remove_object(object_id)

        dest = output_path or str(proj)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        tmf.save(dest)

        out = Path(dest)
        objects_after = tmf.objects if hasattr(tmf, "objects") else []
        return {
            "deleted": True,
            "object_id": object_id,
            "objects_before": len(objects_before),
            "objects_after": len(objects_after),
            "path": str(out.resolve()),
        }
    except Exception as exc:
        return {"error": str(exc), "deleted": False}


def list_models(
    path: str,
    backend: BambuStudioBackend | None = None,
) -> list[dict[str, Any]]:
    """List all model objects in a 3MF project.

    Equivalent to ``project.list_objects`` but lives in the model module
    for organisational convenience.

    Args:
        path: Path to the .3mf file.
        backend: Optional backend for enriched info.

    Returns:
        List of object info dicts.
    """
    try:
        p = Path(path)
        if not p.exists():
            return [{"error": f"File not found: {path}"}]

        tmf = ThreeMF.load(str(p))
        objects = tmf.objects if hasattr(tmf, "objects") else []

        result: list[dict[str, Any]] = []
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
            if hasattr(obj, "type"):
                entry["type"] = obj.type
            result.append(entry)

        return result
    except Exception as exc:
        return [{"error": str(exc)}]
