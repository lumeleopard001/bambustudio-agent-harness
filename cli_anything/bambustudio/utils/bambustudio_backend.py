"""Subprocess wrapper for the BambuStudio CLI binary.

Discovers the BambuStudio binary on macOS / Linux / Windows,
runs CLI commands as subprocesses, and returns structured results
with parsed error codes and output file tracking.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Error codes from BambuStudio.cpp lines 105-155 ────────────────────

CLI_ERRORS: dict[int, str] = {
    0: "Success",
    1: "Failed setting up server environment",
    2: "Invalid parameters to the slicer",
    3: "The input files are not found",
    4: "File list order is invalid",
    5: "The input preset file is invalid",
    6: "The input model file cannot be parsed",
    7: "Unsupported printer technology (not FDM)",
    8: "Unsupported CLI instruction",
    9: "Failed copying objects",
    10: "Failed scaling an object to fit the plate",
    11: "Failed exporting STL files",
    12: "Failed exporting OBJ files",
    13: "Failed exporting 3MF files",
    14: "Out of memory during slicing",
    15: "The selected printer is not supported",
    16: "The selected printer is not compatible with the 3MF",
    17: "The process preset is not compatible",
    18: "Invalid parameter values in the 3MF file",
    19: "post_process is not supported under CLI",
    20: "The printer bed size is too small for the print profile",
    21: "Auto-arranging failed",
    22: "Auto-orienting failed",
    23: "Cannot change Printable Area/Height/Exclude Area",
    24: "Unsupported 3MF version",
    25: "Empty plate or object not fully inside",
    26: "Incorrect slicing parameters",
    27: "Objects partly outside bed boundary",
    28: "Failed creating export cache directory",
    29: "Failed exporting cache data",
    30: "Cache data not found",
    31: "Cache data cannot be parsed",
    32: "Failed importing cache data",
    33: "Slicing time exceeds limit",
    34: "Triangle count exceeds limit",
    35: "No printable objects after skipping",
    36: "Filaments incompatible with plate type",
    37: "Filament temperature difference too large",
    38: "Object collision in print-by-object mode",
    39: "Object collision detected",
    40: "Spiral vase mode parameter conflict",
    41: "Filaments cannot be mapped to extruders",
    42: "Not supported: 2+ TPU filaments",
    43: "Filaments not supported by mapped extruder",
    44: "Slicing failed",
    45: "G-code conflicts detected",
    46: "G-code in unprintable area",
    47: "Filament unprintable at first layer",
    48: "G-code outside printable area",
    49: "G-code in wrapping detect area",
}


# ── Exceptions ─────────────────────────────────────────────────────────

class BinaryNotFoundError(RuntimeError):
    """Raised when the BambuStudio binary cannot be located."""
    pass


# ── Result dataclass ───────────────────────────────────────────────────

@dataclass
class BackendResult:
    """Structured result from a BambuStudio CLI invocation."""

    returncode: int
    stdout: str
    stderr: str
    result_json: dict | None = None
    error_message: str = ""
    duration_ms: int = 0
    output_files: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if the command succeeded (return code 0)."""
        return self.returncode == 0


# ── Binary discovery ───────────────────────────────────────────────────

def find_bambustudio() -> str:
    """Discover the BambuStudio binary path.

    Search order:
    1. BAMBUSTUDIO_BIN environment variable
    2. Platform-specific default locations

    Returns:
        Absolute path to the BambuStudio binary.

    Raises:
        BinaryNotFoundError: If the binary cannot be found, with
            platform-specific installation instructions.
    """
    # 1. Environment variable override
    env_path = os.environ.get("BAMBUSTUDIO_BIN")
    if env_path:
        if os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path
        raise BinaryNotFoundError(
            f"BAMBUSTUDIO_BIN={env_path} is set but the file is missing or not executable."
        )

    system = platform.system()

    # 2. Platform-specific paths
    if system == "Darwin":
        mac_path = "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"
        if os.path.isfile(mac_path):
            return mac_path
        raise BinaryNotFoundError(
            "BambuStudio not found.\n"
            "Install from: https://bambulab.com/en/download/studio\n"
            "Expected location: /Applications/BambuStudio.app\n"
            "Or set BAMBUSTUDIO_BIN=/path/to/BambuStudio"
        )

    if system == "Linux":
        candidates = [
            shutil.which("bambu-studio"),
            "/usr/bin/bambu-studio",
            "/usr/local/bin/bambu-studio",
            os.path.expanduser("~/snap/bambu-studio/current/usr/bin/bambu-studio"),
            "/var/lib/flatpak/exports/bin/com.bambulab.BambuStudio",
            os.path.expanduser(
                "~/.local/share/flatpak/exports/bin/com.bambulab.BambuStudio"
            ),
        ]
        for path in candidates:
            if path and os.path.isfile(path) and os.access(path, os.X_OK):
                return path
        raise BinaryNotFoundError(
            "BambuStudio not found.\n"
            "Install from: https://bambulab.com/en/download/studio\n"
            "Or via: sudo apt install bambu-studio / snap install bambu-studio / flatpak\n"
            "Or set BAMBUSTUDIO_BIN=/path/to/bambu-studio"
        )

    if system == "Windows":
        program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        win_path = os.path.join(program_files, "BambuStudio", "bambu-studio.exe")
        if os.path.isfile(win_path):
            return win_path
        # Also check shutil.which for PATH-installed versions
        which_path = shutil.which("bambu-studio")
        if which_path:
            return which_path
        raise BinaryNotFoundError(
            "BambuStudio not found.\n"
            "Install from: https://bambulab.com/en/download/studio\n"
            f"Expected location: {win_path}\n"
            "Or set BAMBUSTUDIO_BIN=C:\\path\\to\\bambu-studio.exe"
        )

    raise BinaryNotFoundError(
        f"Unsupported platform: {system}. "
        "Set BAMBUSTUDIO_BIN=/path/to/bambustudio binary."
    )


# ── Backend class ──────────────────────────────────────────────────────

class BambuStudioBackend:
    """Subprocess wrapper for BambuStudio CLI operations.

    Usage::

        backend = BambuStudioBackend()
        result = backend.slice("project.3mf", plate=1)
        if result.ok:
            print(f"Sliced in {result.duration_ms}ms")
        else:
            print(f"Error: {result.error_message}")
    """

    def __init__(
        self,
        binary_path: str | None = None,
        debug_level: int = 1,
    ) -> None:
        """Initialize the backend.

        Args:
            binary_path: Explicit path to BambuStudio binary.
                         Auto-discovered if None.
            debug_level: CLI debug verbosity (0=quiet, 1=normal, 2+=verbose).
        """
        self.binary_path = binary_path or find_bambustudio()
        self.debug_level = debug_level

    def run(
        self,
        args: list[str],
        input_files: list[str] | None = None,
        timeout: int = 600,
    ) -> BackendResult:
        """Execute a BambuStudio CLI command.

        The command is built as: [binary] [input_files...] [args...]
        BambuStudio CLI expects input files before flags.

        Args:
            args: CLI arguments (e.g., ["--slice", "0", "--export-3mf", "out.3mf"]).
            input_files: Input file paths to prepend to the command.
            timeout: Maximum execution time in seconds.

        Returns:
            BackendResult with returncode, stdout, stderr, parsed result.json,
            mapped error message, duration, and list of created output files.
        """
        cmd = [self.binary_path]
        if input_files:
            cmd.extend(input_files)
        cmd.extend(args)

        # Determine output directory for result.json scanning
        output_dir = self._extract_output_dir(args)

        # Snapshot existing files in output_dir for diff
        existing_files: set[str] = set()
        if output_dir and os.path.isdir(output_dir):
            existing_files = {
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
            }

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - start) * 1000)
            return BackendResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                error_message=f"Command timed out after {timeout}s",
                duration_ms=elapsed,
            )
        except FileNotFoundError:
            return BackendResult(
                returncode=-1,
                stdout="",
                stderr=f"Binary not found: {self.binary_path}",
                error_message=f"Binary not found: {self.binary_path}",
                duration_ms=0,
            )

        elapsed = int((time.monotonic() - start) * 1000)

        # Detect new output files
        new_files: list[str] = []
        if output_dir and os.path.isdir(output_dir):
            current_files = {
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
            }
            new_files = sorted(current_files - existing_files)

        # Parse result.json if present in output_dir
        result_json = None
        if output_dir:
            result_path = os.path.join(output_dir, "result.json")
            if os.path.isfile(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        result_json = json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass

        # Map error code
        error_message = CLI_ERRORS.get(
            proc.returncode,
            f"Unknown error (code {proc.returncode})" if proc.returncode != 0 else "",
        )

        return BackendResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            result_json=result_json,
            error_message=error_message,
            duration_ms=elapsed,
            output_files=new_files,
        )

    # ── High-level commands ────────────────────────────────────────────

    def slice(
        self,
        project_path: str,
        plate: int = 0,
        output_dir: str | None = None,
        no_check: bool = False,
    ) -> BackendResult:
        """Slice a project file.

        Args:
            project_path: Path to .3mf project.
            plate: Plate index to slice (0 = all plates).
            output_dir: Directory for sliced output. Defaults to
                        project directory.
            no_check: If True, skip compatibility checks.

        Returns:
            BackendResult with slicing outcome.
        """
        args = ["--slice", str(plate)]
        if output_dir:
            args.extend(["--outputdir", output_dir])
        if no_check:
            args.append("--no-check")
        if self.debug_level > 0:
            args.extend(["--debug", str(self.debug_level)])
        return self.run(args, input_files=[project_path])

    def export_3mf(
        self,
        project_path: str,
        output_path: str,
        min_save: bool = False,
    ) -> BackendResult:
        """Export a project as 3MF.

        Args:
            project_path: Input .3mf project path.
            output_path: Output .3mf file path.
            min_save: If True, export minimal 3MF (no thumbnails/gcode).

        Returns:
            BackendResult.
        """
        args = ["--export-3mf", output_path]
        if min_save:
            args.append("--min-save")
        return self.run(args, input_files=[project_path])

    def export_stl(
        self,
        project_path: str,
        output_dir: str | None = None,
    ) -> BackendResult:
        """Export the project as a single STL file.

        Args:
            project_path: Input .3mf project path.
            output_dir: Output directory. Defaults to project directory.

        Returns:
            BackendResult.
        """
        args = ["--export-stl"]
        if output_dir:
            args.extend(["--outputdir", output_dir])
        return self.run(args, input_files=[project_path])

    def export_stls(
        self,
        project_path: str,
        output_dir: str,
    ) -> BackendResult:
        """Export each object as a separate STL file.

        Args:
            project_path: Input .3mf project path.
            output_dir: Output directory for STL files.

        Returns:
            BackendResult.
        """
        args = ["--export-stls", "--outputdir", output_dir]
        return self.run(args, input_files=[project_path])

    def export_png(
        self,
        project_path: str,
        plate: int = 0,
        camera_view: int = 0,
        output_dir: str | None = None,
    ) -> BackendResult:
        """Export a plate thumbnail as PNG.

        Args:
            project_path: Input .3mf project path.
            plate: Plate index.
            camera_view: Camera angle preset (0=default).
            output_dir: Output directory for PNG.

        Returns:
            BackendResult.
        """
        args = [
            "--export-png",
            "--plate", str(plate),
            "--camera-view", str(camera_view),
        ]
        if output_dir:
            args.extend(["--outputdir", output_dir])
        return self.run(args, input_files=[project_path])

    def export_settings(
        self,
        project_path: str,
        output_path: str,
    ) -> BackendResult:
        """Export project settings/presets to a file.

        Args:
            project_path: Input .3mf project path.
            output_path: Output settings file path.

        Returns:
            BackendResult.
        """
        args = ["--export-settings", output_path]
        return self.run(args, input_files=[project_path])

    def info(self, project_path: str) -> BackendResult:
        """Get project information (plates, objects, settings).

        Args:
            project_path: Input .3mf project path.

        Returns:
            BackendResult with project info in stdout.
        """
        args = ["--info"]
        return self.run(args, input_files=[project_path])

    def arrange(
        self,
        project_path: str,
        output_path: str,
    ) -> BackendResult:
        """Auto-arrange objects on the build plate.

        Args:
            project_path: Input .3mf project path.
            output_path: Output .3mf with arranged objects.

        Returns:
            BackendResult.
        """
        args = ["--arrange", "--export-3mf", output_path]
        return self.run(args, input_files=[project_path])

    def orient(
        self,
        project_path: str,
        output_path: str,
    ) -> BackendResult:
        """Auto-orient objects for optimal printing.

        Args:
            project_path: Input .3mf project path.
            output_path: Output .3mf with oriented objects.

        Returns:
            BackendResult.
        """
        args = ["--orient", "--export-3mf", output_path]
        return self.run(args, input_files=[project_path])

    def transform(
        self,
        project_path: str,
        output_path: str,
        rotate: float | None = None,
        rotate_x: float | None = None,
        rotate_y: float | None = None,
        scale: float | None = None,
    ) -> BackendResult:
        """Apply geometric transformations to objects.

        Args:
            project_path: Input .3mf project path.
            output_path: Output .3mf with transformed objects.
            rotate: Rotation around Z axis in degrees.
            rotate_x: Rotation around X axis in degrees.
            rotate_y: Rotation around Y axis in degrees.
            scale: Uniform scale factor (1.0 = no change).

        Returns:
            BackendResult.
        """
        args = []
        if rotate is not None:
            args.extend(["--rotate", str(rotate)])
        if rotate_x is not None:
            args.extend(["--rotate-x", str(rotate_x)])
        if rotate_y is not None:
            args.extend(["--rotate-y", str(rotate_y)])
        if scale is not None:
            args.extend(["--scale", str(scale)])
        args.extend(["--export-3mf", output_path])
        return self.run(args, input_files=[project_path])

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _extract_output_dir(args: list[str]) -> str | None:
        """Extract --outputdir value from args list, or infer from output paths.

        Args:
            args: CLI argument list.

        Returns:
            Output directory path, or None.
        """
        for i, arg in enumerate(args):
            if arg == "--outputdir" and i + 1 < len(args):
                return args[i + 1]

        # Infer from --export-3mf or --export-settings path
        for i, arg in enumerate(args):
            if arg in ("--export-3mf", "--export-settings") and i + 1 < len(args):
                parent = os.path.dirname(args[i + 1])
                return parent if parent else None

        return None


# ── GUI launch ────────────────────────────────────────────────────────

def open_in_bambustudio(path: str) -> dict[str, Any]:
    """Open a .3mf/.stl file in BambuStudio GUI.

    Non-blocking: uses Popen so the calling process continues immediately.
    macOS: open -a BambuStudio <path>
    Linux: bambu-studio <path>
    """
    if not os.path.isfile(path):
        return {"opened": False, "error": f"File not found: {path}"}

    _DEVNULL = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "BambuStudio", path], **_DEVNULL)
            return {"opened": True, "method": "macOS open", "path": path}
        elif sys.platform == "linux":
            subprocess.Popen(["bambu-studio", path], **_DEVNULL)
            return {"opened": True, "method": "linux", "path": path}
        else:
            return {
                "opened": False,
                "error": f"Auto-open not supported on {sys.platform}. Open manually: {path}",
            }
    except OSError as exc:
        return {"opened": False, "error": f"Failed to launch BambuStudio: {exc}"}
