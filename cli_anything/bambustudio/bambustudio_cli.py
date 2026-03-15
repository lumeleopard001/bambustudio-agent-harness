"""Agent-native CLI for BambuStudio 3D printing slicer.

Provides a Click-based CLI with command groups for project management,
model manipulation, plate control, slicing, export, and configuration.
Includes an interactive REPL mode with prompt_toolkit integration.
"""

from __future__ import annotations

import shlex
import sys
from typing import Optional

import click

from cli_anything.bambustudio.utils.output import OutputFormatter
from cli_anything.bambustudio.utils.bambustudio_backend import (
    BambuStudioBackend,
    BinaryNotFoundError,
    find_bambustudio,
)
from cli_anything.bambustudio.core.project import (
    create_project,
    open_project,
    get_project_info,
    list_plates,
    list_objects,
)
from cli_anything.bambustudio.core.slicer import slice_project, get_slice_estimate
from cli_anything.bambustudio.core.export import (
    export_3mf,
    export_stl,
    export_gcode,
    export_png,
    export_settings,
)
from cli_anything.bambustudio.core.model import (
    import_model,
    transform_object,
    arrange_objects,
    orient_objects,
    delete_object,
    list_models,
)
from cli_anything.bambustudio.core.plate import (
    list_plates as plate_list_plates,
    add_plate,
    remove_plate,
    get_plate_info,
)
from cli_anything.bambustudio.core.config import (
    get_config_value,
    set_config_value,
    list_profiles,
    show_profile,
    find_profiles_dir,
    list_printers,
    list_filaments,
    list_processes,
    suggest_preset,
    validate_combo,
)
from cli_anything.bambustudio.core.session import Session
from cli_anything.bambustudio.core.workflow import workflow_auto, workflow_guided_start, workflow_guided_select, workflow_guided_execute, workflow_review
from cli_anything.bambustudio.core.inventory import SpoolRegistry
from cli_anything.bambustudio.utils.repl_skin import ReplSkin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_backend(ctx: click.Context) -> BambuStudioBackend:
    """Get or create backend from context."""
    if "backend" not in ctx.obj:
        binary = ctx.obj.get("binary_path")
        if binary is None:
            binary = find_bambustudio()
        ctx.obj["backend"] = BambuStudioBackend(
            binary, debug_level=ctx.obj["debug"]
        )
    return ctx.obj["backend"]


def _get_project_path(ctx: click.Context, path: str | None = None) -> str:
    """Resolve project path from argument or --project flag."""
    p = path or ctx.obj.get("project")
    if not p:
        raise click.UsageError(
            "No project specified. Use --project or provide a path."
        )
    return p


# ---------------------------------------------------------------------------
# Root CLI group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON")
@click.option("--debug", type=int, default=1, help="Debug level 0-5")
@click.option(
    "--binary",
    type=click.Path(),
    default=None,
    help="BambuStudio binary path",
)
@click.option(
    "--project",
    type=click.Path(exists=True),
    default=None,
    help="Working 3MF project",
)
@click.pass_context
def cli(
    ctx: click.Context,
    json_mode: bool,
    debug: int,
    binary: Optional[str],
    project: Optional[str],
) -> None:
    """Agent-native CLI for BambuStudio 3D printing slicer."""
    ctx.ensure_object(dict)
    ctx.obj["formatter"] = OutputFormatter(json_mode=json_mode)
    ctx.obj["debug"] = debug
    ctx.obj["json_mode"] = json_mode

    # Initialize backend lazily — only when binary operations are needed
    ctx.obj["binary_path"] = binary
    ctx.obj["project"] = project

    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ═══════════════════════════════════════════════════════════════════════════
# project group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def project(ctx: click.Context) -> None:
    """Project management commands."""
    pass


@project.command("new")
@click.option("--printer", required=True, help="Printer preset name")
@click.option(
    "-o", "--output", required=True, type=click.Path(), help="Output 3MF path"
)
@click.pass_context
def project_new(ctx: click.Context, printer: str, output: str) -> None:
    """Create a new 3MF project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = create_project(printer_preset=printer, output_path=output)
        click.echo(fmt.success(result, command="project.new"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="project.new"))
        raise SystemExit(1)


@project.command("info")
@click.argument("path", required=False)
@click.pass_context
def project_info(ctx: click.Context, path: Optional[str]) -> None:
    """Show project information."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx, path)
        backend = _get_backend(ctx)
        result = get_project_info(project_path, backend)
        click.echo(fmt.success(result, command="project.info"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="project.info"))
        raise SystemExit(1)


@project.command("list-plates")
@click.argument("path", required=False)
@click.pass_context
def project_list_plates(ctx: click.Context, path: Optional[str]) -> None:
    """List plates in the project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx, path)
        result = list_plates(project_path)
        click.echo(fmt.success(result, command="project.list-plates"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="project.list-plates"))
        raise SystemExit(1)


@project.command("list-objects")
@click.argument("path", required=False)
@click.pass_context
def project_list_objects(ctx: click.Context, path: Optional[str]) -> None:
    """List objects in the project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx, path)
        backend = _get_backend(ctx)
        result = list_objects(project_path, backend)
        click.echo(fmt.success(result, command="project.list-objects"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="project.list-objects"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# model group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def model(ctx: click.Context) -> None:
    """Model import and manipulation commands."""
    pass


@model.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def model_import(ctx: click.Context, file: str, output: Optional[str]) -> None:
    """Import an STL/OBJ/STEP model file."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = import_model(
            file, project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="model.import"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.import"))
        raise SystemExit(1)


@model.command("transform")
@click.option("--rotate-z", type=float, default=None, help="Rotate around Z axis (degrees)")
@click.option("--rotate-x", type=float, default=None, help="Rotate around X axis (degrees)")
@click.option("--rotate-y", type=float, default=None, help="Rotate around Y axis (degrees)")
@click.option("--scale", type=float, default=None, help="Scale factor")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def model_transform(
    ctx: click.Context,
    rotate_z: Optional[float],
    rotate_x: Optional[float],
    rotate_y: Optional[float],
    scale: Optional[float],
    output: Optional[str],
) -> None:
    """Transform an object (rotate, scale)."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = transform_object(
            project_path=project_path,
            rotate_x=rotate_x,
            rotate_y=rotate_y,
            rotate_z=rotate_z,
            scale=scale,
            output_path=output,
            backend=backend,
        )
        click.echo(fmt.success(result, command="model.transform"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.transform"))
        raise SystemExit(1)


@model.command("arrange")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def model_arrange(ctx: click.Context, output: Optional[str]) -> None:
    """Auto-arrange objects on the build plate."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = arrange_objects(
            project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="model.arrange"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.arrange"))
        raise SystemExit(1)


@model.command("orient")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def model_orient(ctx: click.Context, output: Optional[str]) -> None:
    """Auto-orient objects for optimal printing."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = orient_objects(
            project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="model.orient"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.orient"))
        raise SystemExit(1)


@model.command("delete")
@click.option("--object-id", required=True, type=int, help="Object ID to delete")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def model_delete(ctx: click.Context, object_id: int, output: Optional[str]) -> None:
    """Delete an object from the project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = delete_object(
            object_id=object_id,
            project_path=project_path,
            output_path=output,
            backend=backend,
        )
        click.echo(fmt.success(result, command="model.delete"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.delete"))
        raise SystemExit(1)


@model.command("list")
@click.pass_context
def model_list(ctx: click.Context) -> None:
    """List all objects in the project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = list_models(project_path=project_path, backend=backend)
        click.echo(fmt.success(result, command="model.list"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="model.list"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# plate group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def plate(ctx: click.Context) -> None:
    """Build plate management commands."""
    pass


@plate.command("list")
@click.pass_context
def plate_list(ctx: click.Context) -> None:
    """List all plates."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        result = plate_list_plates(project_path)
        click.echo(fmt.success(result, command="plate.list"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="plate.list"))
        raise SystemExit(1)


@plate.command("add")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def plate_add(ctx: click.Context, output: Optional[str]) -> None:
    """Add a new plate."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = add_plate(
            project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="plate.add"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="plate.add"))
        raise SystemExit(1)


@plate.command("remove")
@click.option("--plate", "plate_n", required=True, type=int, help="Plate number to remove")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def plate_remove(ctx: click.Context, plate_n: int, output: Optional[str]) -> None:
    """Remove a plate."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = remove_plate(
            plate_number=plate_n,
            project_path=project_path,
            output_path=output,
            backend=backend,
        )
        click.echo(fmt.success(result, command="plate.remove"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="plate.remove"))
        raise SystemExit(1)


@plate.command("info")
@click.option("--plate", "plate_n", required=True, type=int, help="Plate number")
@click.pass_context
def plate_info(ctx: click.Context, plate_n: int) -> None:
    """Show plate details."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = get_plate_info(
            plate_number=plate_n, project_path=project_path, backend=backend
        )
        click.echo(fmt.success(result, command="plate.info"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="plate.info"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# slice group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group("slice")
@click.pass_context
def slice_group(ctx: click.Context) -> None:
    """Slicing commands."""
    pass


@slice_group.command("run")
@click.option("--plate", "plate_n", type=int, default=None, help="Plate number to slice")
@click.option("--no-check", is_flag=True, help="Skip pre-slice checks")
@click.option("--output-dir", type=click.Path(), default=None, help="Output directory")
@click.pass_context
def slice_run(
    ctx: click.Context,
    plate_n: Optional[int],
    no_check: bool,
    output_dir: Optional[str],
) -> None:
    """Slice the project."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = slice_project(
            project_path=project_path,
            backend=backend,
            plate=plate_n or 0,
            no_check=no_check,
            output_dir=output_dir,
        )
        click.echo(fmt.success(result, command="slice.run"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="slice.run"))
        raise SystemExit(1)


@slice_group.command("estimate")
@click.option("--plate", "plate_n", type=int, default=None, help="Plate number")
@click.pass_context
def slice_estimate(ctx: click.Context, plate_n: Optional[int]) -> None:
    """Get time and material estimate."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = get_slice_estimate(
            project_path=project_path, plate=plate_n, backend=backend
        )
        click.echo(fmt.success(result, command="slice.estimate"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="slice.estimate"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# export group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group("export")
@click.pass_context
def export_group(ctx: click.Context) -> None:
    """Export commands."""
    pass


@export_group.command("3mf")
@click.option("-o", "--output", required=True, type=click.Path(), help="Output 3MF path")
@click.option("--min-save", is_flag=True, help="Minimal save (skip thumbnails)")
@click.pass_context
def export_3mf_cmd(ctx: click.Context, output: str, min_save: bool) -> None:
    """Export project as 3MF."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = export_3mf(
            project_path=project_path,
            output_path=output,
            minimal=min_save,
            backend=backend,
        )
        click.echo(fmt.success(result, command="export.3mf"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="export.3mf"))
        raise SystemExit(1)


@export_group.command("stl")
@click.option("-o", "--output", required=True, type=click.Path(), help="Output STL path")
@click.pass_context
def export_stl_cmd(ctx: click.Context, output: str) -> None:
    """Export project as STL."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = export_stl(
            project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="export.stl"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="export.stl"))
        raise SystemExit(1)


@export_group.command("gcode")
@click.option(
    "-o", "--output-dir", required=True, type=click.Path(), help="Output directory"
)
@click.option("--plate", "plate_n", type=int, default=None, help="Plate number")
@click.pass_context
def export_gcode_cmd(
    ctx: click.Context, output_dir: str, plate_n: Optional[int]
) -> None:
    """Export sliced G-code."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = export_gcode(
            project_path=project_path,
            output_dir=output_dir,
            plate=plate_n,
            backend=backend,
        )
        click.echo(fmt.success(result, command="export.gcode"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="export.gcode"))
        raise SystemExit(1)


@export_group.command("png")
@click.option("-o", "--output", required=True, type=click.Path(), help="Output PNG path")
@click.option("--plate", "plate_n", type=int, default=None, help="Plate number")
@click.option("--camera-view", type=str, default=None, help="Camera view preset")
@click.pass_context
def export_png_cmd(
    ctx: click.Context,
    output: str,
    plate_n: Optional[int],
    camera_view: Optional[str],
) -> None:
    """Export plate preview as PNG."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = export_png(
            project_path=project_path,
            output_path=output,
            plate=plate_n,
            camera_view=camera_view,
            backend=backend,
        )
        click.echo(fmt.success(result, command="export.png"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="export.png"))
        raise SystemExit(1)


@export_group.command("settings")
@click.option(
    "-o", "--output", required=True, type=click.Path(), help="Output settings path"
)
@click.pass_context
def export_settings_cmd(ctx: click.Context, output: str) -> None:
    """Export project settings."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        backend = _get_backend(ctx)
        result = export_settings(
            project_path=project_path, output_path=output, backend=backend
        )
        click.echo(fmt.success(result, command="export.settings"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="export.settings"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# config group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Configuration and profile commands."""
    pass


@config.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Get a configuration value."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        result = get_config_value(path=project_path, key=key)
        click.echo(fmt.success(result, command="config.get"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="config.get"))
        raise SystemExit(1)


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output path")
@click.pass_context
def config_set(
    ctx: click.Context, key: str, value: str, output: Optional[str]
) -> None:
    """Set a configuration value."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        project_path = _get_project_path(ctx)
        result = set_config_value(
            path=project_path,
            key=key,
            value=value,
            output_path=output,
        )
        click.echo(fmt.success(result, command="config.set"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="config.set"))
        raise SystemExit(1)


@config.command("profiles-list")
@click.option(
    "--type",
    "profile_type",
    type=click.Choice(["machine", "filament", "process"]),
    default=None,
    help="Profile type filter",
)
@click.pass_context
def config_profiles_list(
    ctx: click.Context, profile_type: Optional[str]
) -> None:
    """List available presets."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        profiles_dir = find_profiles_dir()
        result = list_profiles(profiles_dir=profiles_dir, profile_type=profile_type or "machine")
        click.echo(fmt.success(result, command="config.profiles-list"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="config.profiles-list"))
        raise SystemExit(1)


@config.command("profiles-show")
@click.argument("name")
@click.pass_context
def config_profiles_show(ctx: click.Context, name: str) -> None:
    """Show preset details."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        profiles_dir = find_profiles_dir()
        result = show_profile(profiles_dir=profiles_dir, profile_name=name)
        click.echo(fmt.success(result, command="config.profiles-show"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="config.profiles-show"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# session group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def session(ctx: click.Context) -> None:
    """Session management commands (REPL mode)."""
    pass


@session.command("status")
@click.pass_context
def session_status(ctx: click.Context) -> None:
    """Show current session information."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        sess: Session = ctx.obj.get("session", Session())
        result = {
            "project": ctx.obj.get("project"),
            "binary": ctx.obj.get("binary_path"),
            "debug": ctx.obj.get("debug"),
            "history_length": len(sess.history) if hasattr(sess, "history") else 0,
        }
        click.echo(fmt.success(result, command="session.status"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="session.status"))
        raise SystemExit(1)


@session.command("undo")
@click.pass_context
def session_undo(ctx: click.Context) -> None:
    """Undo the last change."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        sess: Session = ctx.obj.get("session", Session())
        result = sess.undo()
        click.echo(fmt.success(result, command="session.undo"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="session.undo"))
        raise SystemExit(1)


@session.command("redo")
@click.pass_context
def session_redo(ctx: click.Context) -> None:
    """Redo the last undone change."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        sess: Session = ctx.obj.get("session", Session())
        result = sess.redo()
        click.echo(fmt.success(result, command="session.redo"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="session.redo"))
        raise SystemExit(1)


@session.command("history")
@click.pass_context
def session_history(ctx: click.Context) -> None:
    """Show command history for this session."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        sess: Session = ctx.obj.get("session", Session())
        result = sess.get_history() if hasattr(sess, "get_history") else []
        click.echo(fmt.success(result, command="session.history"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="session.history"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# profiles group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def profiles(ctx: click.Context) -> None:
    """Printer, filament, and process profile discovery."""
    pass


@profiles.command("list-printers")
@click.pass_context
def profiles_list_printers(ctx: click.Context) -> None:
    """List all available printers."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = list_printers()
        click.echo(fmt.success(result, command="profiles.list-printers"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="profiles.list-printers"))
        raise SystemExit(1)


@profiles.command("list-filaments")
@click.option("--printer", required=True, help="Printer name (e.g. 'Bambu Lab A1')")
@click.option("--nozzle", type=float, default=0.4, help="Nozzle diameter (default 0.4)")
@click.pass_context
def profiles_list_filaments(ctx: click.Context, printer: str, nozzle: float) -> None:
    """List filaments compatible with a printer."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = list_filaments(printer=printer, nozzle=nozzle)
        click.echo(fmt.success(result, command="profiles.list-filaments"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="profiles.list-filaments"))
        raise SystemExit(1)


@profiles.command("list-processes")
@click.option("--printer", required=True, help="Printer name")
@click.option("--nozzle", type=float, default=0.4, help="Nozzle diameter (default 0.4)")
@click.pass_context
def profiles_list_processes(ctx: click.Context, printer: str, nozzle: float) -> None:
    """List print quality presets for a printer."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = list_processes(printer=printer, nozzle=nozzle)
        click.echo(fmt.success(result, command="profiles.list-processes"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="profiles.list-processes"))
        raise SystemExit(1)


@profiles.command("suggest")
@click.option("--printer", required=True, help="Printer name")
@click.option("--material", required=True, help="Material type (PLA, ABS, PETG, ...)")
@click.option("--quality", default="standard", help="Quality: draft, standard, fine, extra-fine")
@click.pass_context
def profiles_suggest(ctx: click.Context, printer: str, material: str, quality: str) -> None:
    """Recommend a preset triple (machine + filament + process)."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = suggest_preset(printer=printer, material=material, quality=quality)
        click.echo(fmt.success(result, command="profiles.suggest"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="profiles.suggest"))
        raise SystemExit(1)


@profiles.command("validate")
@click.option("--machine", required=True, help="Machine preset name")
@click.option("--filament", required=True, help="Filament preset name")
@click.option("--process", required=True, help="Process preset name")
@click.pass_context
def profiles_validate(ctx: click.Context, machine: str, filament: str, process: str) -> None:
    """Validate a preset combination."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = validate_combo(machine=machine, filament=filament, process=process)
        click.echo(fmt.success(result, command="profiles.validate"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="profiles.validate"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# workflow group
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def workflow(ctx: click.Context) -> None:
    """High-level workflow commands for agent-native use."""
    pass


@workflow.command("auto")
@click.option("--stl", required=True, type=click.Path(exists=True), help="Input STL file")
@click.option("--printer", required=True, help="Printer name (e.g. 'Bambu Lab A1')")
@click.option("--material", required=True, help="Material type (PLA, ABS, PETG, ...)")
@click.option("--quality", default="standard", help="Quality: draft, standard, fine, extra-fine")
@click.option("-o", "--output", type=click.Path(), default=None, help="Output 3MF path")
@click.option("--track-usage", is_flag=True, help="Deduct filament from spool inventory after slicing")
@click.pass_context
def workflow_auto_cmd(
    ctx: click.Context, stl: str, printer: str, material: str, quality: str,
    output: Optional[str], track_usage: bool,
) -> None:
    """Full auto workflow: STL → sliced project with estimates."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        backend = _get_backend(ctx)
        result = workflow_auto(
            stl_path=stl, printer=printer, material=material,
            quality=quality, output_path=output, backend=backend,
        )

        # Track filament usage if requested
        if track_usage and result.get("ok") and result.get("result"):
            import os
            try:
                registry = SpoolRegistry()
                deductions = registry.track_workflow_usage(
                    result["result"],
                    project_name=os.path.basename(stl),
                )
                result["usage_tracking"] = deductions
            except Exception as track_err:
                result.setdefault("warnings", []).append(
                    f"Usage tracking failed: {track_err}"
                )

        click.echo(fmt.success(result, command="workflow.auto"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="workflow.auto"))
        raise SystemExit(1)


@workflow.command("guided-start")
@click.option("--stl", required=True, type=click.Path(exists=True), help="Input STL file")
@click.pass_context
def workflow_guided_start_cmd(ctx: click.Context, stl: str) -> None:
    """Start a guided workflow session."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = workflow_guided_start(stl_path=stl)
        click.echo(fmt.success(result, command="workflow.guided-start"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="workflow.guided-start"))
        raise SystemExit(1)


@workflow.command("guided-select")
@click.option("--session-file", required=True, type=click.Path(exists=True), help="Session file")
@click.option("--step", required=True, help="Step name (printer, material, quality)")
@click.option("--value", required=True, help="Selected value")
@click.pass_context
def workflow_guided_select_cmd(ctx: click.Context, session_file: str, step: str, value: str) -> None:
    """Make a selection in the guided workflow."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        result = workflow_guided_select(session_file=session_file, step=step, value=value)
        click.echo(fmt.success(result, command="workflow.guided-select"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="workflow.guided-select"))
        raise SystemExit(1)


@workflow.command("guided-execute")
@click.option("--session-file", required=True, type=click.Path(exists=True), help="Session file")
@click.pass_context
def workflow_guided_execute_cmd(ctx: click.Context, session_file: str) -> None:
    """Execute the guided workflow after all selections are made."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        backend = _get_backend(ctx)
        result = workflow_guided_execute(session_file=session_file, backend=backend)
        click.echo(fmt.success(result, command="workflow.guided-execute"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="workflow.guided-execute"))
        raise SystemExit(1)


@workflow.command("review")
@click.option("--project", "project_path", required=True, type=click.Path(exists=True), help="3MF project to review")
@click.pass_context
def workflow_review_cmd(ctx: click.Context, project_path: str) -> None:
    """Review an existing project and suggest improvements."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        backend = _get_backend(ctx)
        result = workflow_review(project_path=project_path, backend=backend)
        click.echo(fmt.success(result, command="workflow.review"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="workflow.review"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# spool group (filament inventory)
# ═══════════════════════════════════════════════════════════════════════════


@cli.group()
@click.pass_context
def spool(ctx: click.Context) -> None:
    """Filament spool inventory and usage tracking."""
    pass


@spool.command("add")
@click.option("--id", "spool_id", required=True, type=int, help="Spool ID number")
@click.option("--brand", required=True, help="Brand (Bambu, Sunlu, eSun, ...)")
@click.option("--material", required=True, help="Material type (PLA, PETG, ABS, TPU, ...)")
@click.option("--variant", default="", help="Variant (Basic, Silk, Matte, ...)")
@click.option("--color", required=True, help="Color name (white, black, red, ...)")
@click.option("--weight", type=float, default=None, help="Spool weight in grams (default: auto by material)")
@click.option("--slot", default=None, help="Load into slot (AMS:1-4 or EXT:1)")
@click.pass_context
def spool_add(
    ctx: click.Context, spool_id: int, brand: str, material: str,
    variant: str, color: str, weight: Optional[float], slot: Optional[str],
) -> None:
    """Register a new filament spool."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.add(
            spool_id=spool_id, brand=brand, material=material,
            variant=variant, color=color, weight=weight, slot=slot,
        )
        click.echo(fmt.success(result, command="spool.add"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.add"))
        raise SystemExit(1)


@spool.command("load")
@click.option("--id", "spool_id", required=True, type=int, help="Spool ID to load")
@click.option("--slot", required=True, help="Target slot (AMS:1-4 or EXT:1)")
@click.pass_context
def spool_load(ctx: click.Context, spool_id: int, slot: str) -> None:
    """Load a spool into a printer slot."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.load_spool(spool_id, slot)
        click.echo(fmt.success(result, command="spool.load"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.load"))
        raise SystemExit(1)


@spool.command("unload")
@click.option("--slot", required=True, help="Slot to unload (AMS:1-4 or EXT:1)")
@click.pass_context
def spool_unload(ctx: click.Context, slot: str) -> None:
    """Unload a spool from a slot (moves to storage)."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.unload(slot)
        click.echo(fmt.success(result, command="spool.unload"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.unload"))
        raise SystemExit(1)


@spool.command("status")
@click.pass_context
def spool_status(ctx: click.Context) -> None:
    """Show all spools and loaded slots."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.status()
        click.echo(fmt.success(result, command="spool.status"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.status"))
        raise SystemExit(1)


@spool.command("list")
@click.option("--state", type=click.Choice(["loaded", "stored", "empty"]), default=None, help="Filter by state")
@click.pass_context
def spool_list(ctx: click.Context, state: Optional[str]) -> None:
    """List spools, optionally filtered by state."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.list_spools(state=state)
        click.echo(fmt.success(result, command="spool.list"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.list"))
        raise SystemExit(1)


@spool.command("history")
@click.option("--id", "spool_id", type=int, default=None, help="Filter by spool ID")
@click.pass_context
def spool_history(ctx: click.Context, spool_id: Optional[int]) -> None:
    """Show usage history for spools."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.history(spool_id=spool_id)
        click.echo(fmt.success(result, command="spool.history"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.history"))
        raise SystemExit(1)


@spool.command("remove")
@click.option("--id", "spool_id", required=True, type=int, help="Spool ID to remove")
@click.pass_context
def spool_remove(ctx: click.Context, spool_id: int) -> None:
    """Remove a spool from the registry."""
    fmt: OutputFormatter = ctx.obj["formatter"]
    fmt.start_timer()
    try:
        registry = SpoolRegistry()
        result = registry.remove(spool_id)
        click.echo(fmt.success(result, command="spool.remove"))
    except Exception as e:
        click.echo(fmt.error(str(e), command="spool.remove"))
        raise SystemExit(1)


# ═══════════════════════════════════════════════════════════════════════════
# REPL command
# ═══════════════════════════════════════════════════════════════════════════


@cli.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Interactive REPL mode."""
    from cli_anything.bambustudio import __version__

    skin = ReplSkin("bambustudio", version=__version__)
    skin.print_banner()

    pt_session = skin.create_prompt_session()

    # Initialise a session object for undo/redo tracking
    sess = Session()
    ctx.obj["session"] = sess

    project_name = ""
    if ctx.obj.get("project"):
        import os

        project_name = os.path.basename(ctx.obj["project"])

    while True:
        try:
            line = skin.get_input(
                pt_session, project_name=project_name, context=""
            )
        except KeyboardInterrupt:
            # Ctrl+C — clear line, continue
            click.echo()
            continue
        except EOFError:
            # Ctrl+D — exit
            skin.print_goodbye()
            break

        if not line:
            continue

        # Built-in REPL commands
        lower = line.strip().lower()
        if lower in ("quit", "exit"):
            skin.print_goodbye()
            break
        if lower == "help":
            click.echo(cli.get_help(ctx))
            continue

        # Parse the input line as CLI arguments and invoke
        try:
            args = shlex.split(line)
        except ValueError as e:
            skin.error(f"Parse error: {e}")
            continue

        try:
            # Create a new context for each command invocation within the
            # REPL so that Click does not carry stale state between runs.
            cli.main(
                args=args,
                prog_name="bambustudio",
                standalone_mode=False,
                parent=ctx,
                **{
                    "obj": ctx.obj,
                },
            )
        except SystemExit:
            # Commands raise SystemExit(1) on error — catch so REPL stays alive
            pass
        except click.UsageError as e:
            skin.error(str(e))
        except click.exceptions.Exit:
            pass
        except BinaryNotFoundError as e:
            skin.error(f"BambuStudio binary not found: {e}")
        except Exception as e:
            skin.error(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the BambuStudio CLI."""
    cli(auto_envvar_prefix="BAMBUSTUDIO")


if __name__ == "__main__":
    main()
