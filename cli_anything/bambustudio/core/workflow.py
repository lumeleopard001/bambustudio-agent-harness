"""High-level workflow commands for agent-native 3D printing.

Three interaction modes:
- auto:    STL → sliced project in one shot
- guided:  Multi-step API for step-by-step selection
- review:  Analyze existing project and suggest improvements
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
from cli_anything.bambustudio.utils.threemf import ThreeMF, create_minimal_3mf
from cli_anything.bambustudio.core.config import (
    find_profiles_dir,
    list_printers,
    list_filaments,
    list_processes,
    suggest_preset,
    validate_combo,
    _QUALITY_MAP,
)


# ═══════════════════════════════════════════════════════════════════════════
# Preflight check (binary --info only)
# ═══════════════════════════════════════════════════════════════════════════

def _preflight_check(
    project_path: str,
    backend: BambuStudioBackend,
    bed_size: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Pre-slice validation using binary --info.

    Checks model info and bed fit without slicing.

    Args:
        project_path: Path to the 3MF project.
        backend: BambuStudioBackend for --info call.
        bed_size: (width, depth) in mm. Defaults to (256, 256) for A1.

    Returns:
        Dict with preflight results and warnings.
    """
    warnings: list[str] = []
    info: dict[str, Any] = {"warnings": warnings}

    if bed_size is None:
        bed_size = (256.0, 256.0)

    # Get model info from binary
    result: BackendResult = backend.run(["--info"], input_files=[project_path])

    if not result.ok:
        info["error"] = result.error_message or "Failed to get project info"
        return info

    # Parse info from stdout (binary --info output)
    info["stdout"] = result.stdout[:500]  # truncate for safety

    # Also check via Python-side 3MF parsing
    try:
        tmf = ThreeMF.load(project_path)
        objects = tmf.get_objects()
        info["objects"] = [
            {
                "id": obj.id,
                "name": obj.name,
                "triangles": obj.triangle_count,
                "vertices": obj.vertex_count,
            }
            for obj in objects
        ]
        info["object_count"] = len(objects)
        total_triangles = sum(obj.triangle_count for obj in objects)
        info["total_triangles"] = total_triangles

        if total_triangles == 0:
            warnings.append("No geometry found — empty model")
        if total_triangles > 5_000_000:
            warnings.append(f"Very high triangle count ({total_triangles:,}) — slicing may be slow")

    except Exception as exc:
        warnings.append(f"Could not parse 3MF: {exc}")

    info["bed_size"] = {"width": bed_size[0], "depth": bed_size[1]}
    return info


# ═══════════════════════════════════════════════════════════════════════════
# workflow auto
# ═══════════════════════════════════════════════════════════════════════════

def workflow_auto(
    stl_path: str,
    printer: str,
    material: str,
    quality: str = "standard",
    output_path: str | None = None,
    backend: BambuStudioBackend | None = None,
) -> dict[str, Any]:
    """Full auto workflow: STL → sliced 3MF project with estimates.

    Pipeline:
    1. suggest_preset(printer, material, quality)
    2. Create project with preset settings
    3. Import STL model
    4. Orient + Arrange
    5. Slice with --load-settings and --load-filaments
    6. Parse result.json → return estimates

    Args:
        stl_path: Path to the input STL file.
        printer: Printer name (e.g. 'Bambu Lab A1').
        material: Material type (e.g. 'PLA', 'ABS').
        quality: Quality tier: draft, standard, fine, extra-fine.
        output_path: Optional output 3MF path.
        backend: BambuStudioBackend instance.

    Returns:
        Dict with workflow result, estimates, and warnings.
    """
    stl = Path(stl_path)
    if not stl.exists():
        return {"error": f"STL file not found: {stl_path}", "ok": False}

    # Step 1: Suggest presets
    preset = suggest_preset(printer=printer, material=material, quality=quality)
    if "error" in preset:
        return {"error": preset["error"], "ok": False, "step": "suggest_preset"}

    # Prepare output path
    if output_path is None:
        output_path = os.path.join(
            tempfile.mkdtemp(prefix="bambustudio_auto_"),
            f"{stl.stem}_project.3mf",
        )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Step 2: Create project — minimal 3MF with printer preset
    try:
        tmf = create_minimal_3mf(
            output_path=output_path,
            printer_preset=preset["machine_preset"],
        )
    except Exception as exc:
        return {"error": f"Failed to create project: {exc}", "ok": False, "step": "create_project"}

    if backend is None:
        from cli_anything.bambustudio.utils.bambustudio_backend import find_bambustudio, BambuStudioBackend
        backend = BambuStudioBackend(find_bambustudio())

    # Step 3: Import STL into the project
    # BambuStudio CLI: binary input.stl --export-3mf output.3mf
    import_result = backend.run(
        ["--export-3mf", output_path],
        input_files=[str(stl)],
    )
    if not import_result.ok:
        return {
            "error": f"Model import failed: {import_result.error_message}",
            "ok": False,
            "step": "import_model",
        }

    # Step 4: Orient + Arrange (non-fatal — collect warnings)
    step_warnings: list[str] = []

    orient_result = backend.run(
        ["--orient", "--export-3mf", output_path],
        input_files=[output_path],
    )
    if not orient_result.ok:
        step_warnings.append(f"Orient skipped: {orient_result.error_message}")

    arrange_result = backend.run(
        ["--arrange", "--export-3mf", output_path],
        input_files=[output_path],
    )
    if not arrange_result.ok:
        step_warnings.append(f"Arrange skipped: {arrange_result.error_message}")

    # Step 5: Slice with settings files
    slice_dir = tempfile.mkdtemp(prefix="bambustudio_slice_")
    slice_args: list[str] = [
        "--slice", "0",
        "--outputdir", slice_dir,
    ]

    # Add settings loading flags
    if preset.get("process_file") and os.path.isfile(preset["process_file"]):
        slice_args.extend(["--load-settings", preset["process_file"]])
    if preset.get("filament_file") and os.path.isfile(preset["filament_file"]):
        slice_args.extend(["--load-filaments", preset["filament_file"]])
    if preset.get("machine_file") and os.path.isfile(preset["machine_file"]):
        slice_args.extend(["--load-settings", preset["machine_file"]])

    slice_result = backend.run(slice_args, input_files=[output_path])

    # Step 6: Parse results
    result: dict[str, Any] = {
        "ok": True,
        "stl": str(stl.resolve()),
        "output_3mf": output_path,
        "preset": preset.get("settings_summary", {}),
        "preset_files": {
            "machine": preset.get("machine_file"),
            "filament": preset.get("filament_file"),
            "process": preset.get("process_file"),
        },
        "warnings": step_warnings,
    }

    if slice_result.ok:
        result["sliced"] = True
        result["slice_duration_ms"] = slice_result.duration_ms

        # Parse result.json
        result_json_path = os.path.join(slice_dir, "result.json")
        if os.path.isfile(result_json_path):
            try:
                with open(result_json_path, "r", encoding="utf-8") as fh:
                    slice_data = json.load(fh)
                result["result"] = slice_data

                # Extract key estimates from sliced_plates
                plates = slice_data.get("sliced_plates", [])
                if plates:
                    plate = plates[0]
                    total_time = plate.get("total_predication", 0)
                    result["print_time_seconds"] = total_time
                    result["print_time_human"] = _format_time(total_time)

                    filaments = plate.get("filaments", [])
                    if filaments:
                        total_g = sum(f.get("total_used_g", 0) for f in filaments)
                        result["filament_used_g"] = round(total_g, 1)
            except (json.JSONDecodeError, OSError):
                result["warnings"].append("Could not parse result.json")
    else:
        result["sliced"] = False
        result["slice_error"] = slice_result.error_message
        result["warnings"].append(f"Slicing failed: {slice_result.error_message}")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# workflow guided (multi-step API)
# ═══════════════════════════════════════════════════════════════════════════

_GUIDED_STEPS = ["printer", "material", "quality", "confirm"]


def workflow_guided_start(stl_path: str) -> dict[str, Any]:
    """Start a guided workflow session.

    Creates a session file and returns the first step (printer selection).

    Args:
        stl_path: Path to the input STL file.

    Returns:
        Dict with step info, options, and session file path.
    """
    stl = Path(stl_path)
    if not stl.exists():
        return {"error": f"STL file not found: {stl_path}"}

    # Create session state
    session = {
        "stl_path": str(stl.resolve()),
        "current_step": "printer",
        "selections": {},
    }

    # Save to temp file
    session_file = os.path.join(
        tempfile.mkdtemp(prefix="bambustudio_guided_"),
        "session.json",
    )
    with open(session_file, "w", encoding="utf-8") as fh:
        json.dump(session, fh, indent=2)

    # Get printer options
    printers = list_printers()
    printer_names = [p["name"] for p in printers if "error" not in p]

    # Recommend A1 as default
    recommended = "Bambu Lab A1"
    if recommended not in printer_names and printer_names:
        recommended = printer_names[0]

    return {
        "step": "printer",
        "options": printer_names,
        "recommended": recommended,
        "session_file": session_file,
        "stl": str(stl.resolve()),
    }


def workflow_guided_select(
    session_file: str,
    step: str,
    value: str,
) -> dict[str, Any]:
    """Make a selection in the guided workflow.

    Validates the selection and advances to the next step.

    Args:
        session_file: Path to the session JSON file.
        step: Step name (printer, material, quality).
        value: Selected value.

    Returns:
        Dict with next step info, options, and updated session.
    """
    # Load session
    try:
        with open(session_file, "r", encoding="utf-8") as fh:
            session = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": f"Invalid session file: {exc}"}

    expected_step = session.get("current_step")
    if step != expected_step:
        return {
            "error": f"Expected step '{expected_step}', got '{step}'",
            "current_step": expected_step,
        }

    valid_steps = _GUIDED_STEPS
    if step not in valid_steps:
        return {"error": f"Unknown step: {step}. Valid: {valid_steps}"}

    # Record selection
    session["selections"][step] = value

    # Advance to next step
    current_idx = valid_steps.index(step)
    if current_idx + 1 < len(valid_steps):
        next_step = valid_steps[current_idx + 1]
    else:
        next_step = "done"

    session["current_step"] = next_step

    # Save updated session
    with open(session_file, "w", encoding="utf-8") as fh:
        json.dump(session, fh, indent=2)

    # Build response based on next step
    result: dict[str, Any] = {
        "session_file": session_file,
        "selections": session["selections"],
    }

    if next_step == "material":
        printer = session["selections"]["printer"]
        filaments = list_filaments(printer=printer)
        materials = sorted(set(f.get("material", "") for f in filaments if "error" not in f))
        result["step"] = "material"
        result["options"] = materials
        result["recommended"] = "PLA" if "PLA" in materials else (materials[0] if materials else "")

    elif next_step == "quality":
        result["step"] = "quality"
        result["options"] = list(_QUALITY_MAP.keys())
        result["recommended"] = "standard"

    elif next_step == "confirm":
        # Generate preset suggestion
        selections = session["selections"]
        preset = suggest_preset(
            printer=selections.get("printer", ""),
            material=selections.get("material", ""),
            quality=selections.get("quality", "standard"),
        )
        result["step"] = "confirm"
        result["summary"] = preset
        result["ready"] = "error" not in preset

    else:
        result["step"] = "done"

    return result


def workflow_guided_execute(
    session_file: str,
    backend: BambuStudioBackend | None = None,
) -> dict[str, Any]:
    """Execute the guided workflow after all selections are made.

    Reads session state and delegates to workflow_auto.

    Args:
        session_file: Path to the session JSON file.
        backend: Optional BambuStudioBackend instance.

    Returns:
        Same result as workflow_auto.
    """
    try:
        with open(session_file, "r", encoding="utf-8") as fh:
            session = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        return {"error": f"Invalid session file: {exc}"}

    selections = session.get("selections", {})
    required = ["printer", "material", "quality"]
    missing = [s for s in required if s not in selections]
    if missing:
        return {
            "error": f"Missing selections: {missing}",
            "current_step": session.get("current_step"),
        }

    return workflow_auto(
        stl_path=session["stl_path"],
        printer=selections["printer"],
        material=selections["material"],
        quality=selections.get("quality", "standard"),
        backend=backend,
    )


# ═══════════════════════════════════════════════════════════════════════════
# workflow review
# ═══════════════════════════════════════════════════════════════════════════

def workflow_review(
    project_path: str,
    backend: BambuStudioBackend | None = None,
) -> dict[str, Any]:
    """Review an existing 3MF project and suggest improvements.

    Analyzes:
    - Current printer/filament/process settings
    - Preset validity
    - Model geometry (triangle count, object count)
    - Basic recommendations

    Args:
        project_path: Path to the 3MF file.
        backend: Optional backend for enriched analysis.

    Returns:
        Dict with current settings, recommendations, and score.
    """
    proj = Path(project_path)
    if not proj.exists():
        return {"error": f"File not found: {project_path}"}

    try:
        tmf = ThreeMF.load(str(proj))
    except Exception as exc:
        return {"error": f"Failed to load project: {exc}"}

    recommendations: list[dict[str, Any]] = []
    current_settings: dict[str, Any] = {}

    # Read print profile config
    print_config = tmf.get_config("Metadata/print_profile.config")
    project_config = tmf.get_config("Metadata/project_settings.config")

    # Extract key settings
    layer_height = print_config.get("layer_height", "unknown")
    infill = print_config.get("fill_density", "unknown")
    support = print_config.get("support_material", "0")
    perimeters = print_config.get("perimeters", "unknown")
    printer_model = project_config.get("printer_model", "unknown")

    current_settings = {
        "printer": printer_model,
        "layer_height": layer_height,
        "infill_density": infill,
        "support_enabled": support != "0",
        "perimeters": perimeters,
    }

    # Analyze objects
    objects = tmf.get_objects()
    plates = tmf.get_plates()
    total_triangles = sum(obj.triangle_count for obj in objects)

    current_settings["objects"] = len(objects)
    current_settings["plates"] = len(plates)
    current_settings["total_triangles"] = total_triangles

    # Recommendations
    if layer_height != "unknown":
        try:
            lh = float(layer_height)
            if lh > 0.3:
                recommendations.append({
                    "setting": "layer_height",
                    "current": layer_height,
                    "recommended": "0.20",
                    "reason": "Layer height above 0.3mm may reduce print quality",
                    "severity": "warning",
                })
            elif lh < 0.06:
                recommendations.append({
                    "setting": "layer_height",
                    "current": layer_height,
                    "recommended": "0.08",
                    "reason": "Very thin layers significantly increase print time",
                    "severity": "info",
                })
        except ValueError:
            pass

    if infill != "unknown":
        try:
            inf_val = float(infill.replace("%", ""))
            if inf_val > 60:
                recommendations.append({
                    "setting": "fill_density",
                    "current": infill,
                    "recommended": "15-30%",
                    "reason": "High infill uses more material with diminishing strength gains",
                    "severity": "info",
                })
            elif inf_val < 5 and inf_val > 0:
                recommendations.append({
                    "setting": "fill_density",
                    "current": infill,
                    "recommended": "10-15%",
                    "reason": "Very low infill may cause weak prints or top surface issues",
                    "severity": "warning",
                })
        except ValueError:
            pass

    if total_triangles > 3_000_000:
        recommendations.append({
            "setting": "model_complexity",
            "current": f"{total_triangles:,} triangles",
            "recommended": "Reduce mesh density",
            "reason": "High poly count increases slicing time",
            "severity": "info",
        })

    if len(objects) == 0:
        recommendations.append({
            "setting": "objects",
            "current": "0",
            "recommended": "Import a model",
            "reason": "Project has no objects to print",
            "severity": "error",
        })

    # Preflight check if backend is available
    if backend is not None:
        preflight = _preflight_check(str(proj), backend)
        if "error" not in preflight:
            current_settings["preflight"] = preflight
            for w in preflight.get("warnings", []):
                recommendations.append({
                    "setting": "preflight",
                    "current": w,
                    "recommended": "Review",
                    "reason": w,
                    "severity": "warning",
                })

    # Overall score
    error_count = sum(1 for r in recommendations if r["severity"] == "error")
    warning_count = sum(1 for r in recommendations if r["severity"] == "warning")

    if error_count > 0:
        score = "problematic"
    elif warning_count > 0:
        score = "needs-attention"
    else:
        score = "good"

    return {
        "current_settings": current_settings,
        "recommendations": recommendations,
        "overall_score": score,
        "recommendation_count": len(recommendations),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _format_time(seconds: int) -> str:
    """Format seconds into human-readable time string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
