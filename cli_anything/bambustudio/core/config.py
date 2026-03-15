"""Configuration management for BambuStudio projects.

Read/write project print settings and browse BambuStudio's bundled
printer/filament/process profiles. Includes profile discovery, preset
suggestion, and combination validation for agent-native workflows.
"""

from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path
from typing import Any

from cli_anything.bambustudio.utils.threemf import ThreeMF
from cli_anything.bambustudio.utils.settings_parser import (
    parse_config,
    serialize_config,
)


# Common config file names inside a 3MF archive
_CONFIG_NAMES = (
    "Metadata/print_profile.config",
    "Metadata/plate_1.config",
    "print_profile.config",
)


def _read_project_config(tmf: ThreeMF) -> tuple[str, dict[str, str]]:
    """Locate and parse the print config inside a ThreeMF archive.

    Returns:
        Tuple of (config_entry_name, parsed_dict).

    Raises:
        FileNotFoundError: If no config entry is found.
    """
    for name in _CONFIG_NAMES:
        try:
            raw = tmf.read_entry(name)
            if raw is not None:
                return name, parse_config(raw)
        except Exception:
            continue
    raise FileNotFoundError("No print config found in project")


def get_config_value(path: str, key: str) -> dict[str, Any]:
    """Get a setting value from the project's print profile config.

    Args:
        path: Path to the .3mf file.
        key: Config key to look up.

    Returns:
        Dict with the key, value, and source config name.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}"}

        tmf = ThreeMF.load(str(p))
        config_name, config = _read_project_config(tmf)

        if key not in config:
            return {
                "error": f"Key '{key}' not found in config",
                "available_keys": sorted(config.keys()),
                "config_file": config_name,
            }

        return {
            "key": key,
            "value": config[key],
            "config_file": config_name,
        }
    except FileNotFoundError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": str(exc)}


def set_config_value(
    path: str,
    key: str,
    value: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Set a setting value in the project's print profile config.

    Args:
        path: Path to the .3mf file.
        key: Config key to set.
        value: New value (as string).
        output_path: Destination path.  Overwrites source when *None*.

    Returns:
        Dict with the updated key/value or error details.
    """
    try:
        p = Path(path)
        if not p.exists():
            return {"error": f"File not found: {path}", "updated": False}

        tmf = ThreeMF.load(str(p))
        config_name, config = _read_project_config(tmf)

        old_value = config.get(key)
        config[key] = value

        # Write back
        new_content = serialize_config(config)
        tmf.write_entry(config_name, new_content)

        dest = output_path or str(p)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        tmf.save(dest)

        return {
            "updated": True,
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "config_file": config_name,
            "path": str(Path(dest).resolve()),
        }
    except FileNotFoundError as exc:
        return {"error": str(exc), "updated": False}
    except Exception as exc:
        return {"error": str(exc), "updated": False}


def list_profiles(
    profiles_dir: str,
    profile_type: str = "machine",
) -> list[dict[str, Any]]:
    """List available presets from BambuStudio's resource profiles.

    Scans ``resources/profiles/BBL/`` for profile files of the given
    type (machine, filament, process).

    Args:
        profiles_dir: Path to the ``resources/profiles/BBL/`` directory.
        profile_type: One of ``"machine"``, ``"filament"``, or ``"process"``.

    Returns:
        List of profile summary dicts.
    """
    try:
        base = Path(profiles_dir)
        if not base.exists():
            return [{"error": f"Profiles directory not found: {profiles_dir}"}]

        # BambuStudio organises profiles in subdirectories by type
        type_dir = base / profile_type
        if not type_dir.exists():
            # Fall back to flat structure — scan for matching files
            type_dir = base

        results: list[dict[str, Any]] = []

        # Scan for .json profile files
        for profile_file in sorted(type_dir.glob("*.json")):
            try:
                with open(profile_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append({
                    "name": data.get("name", profile_file.stem),
                    "type": profile_type,
                    "file": str(profile_file),
                    "inherits": data.get("inherits", None),
                })
            except (json.JSONDecodeError, OSError):
                results.append({
                    "name": profile_file.stem,
                    "type": profile_type,
                    "file": str(profile_file),
                    "parse_error": True,
                })

        # Also scan for INI-style config files
        for profile_file in sorted(type_dir.glob("*.ini")):
            try:
                raw = profile_file.read_text(encoding="utf-8")
                config = parse_config(raw)
                results.append({
                    "name": config.get("name", profile_file.stem),
                    "type": profile_type,
                    "file": str(profile_file),
                    "inherits": config.get("inherits", None),
                })
            except OSError:
                results.append({
                    "name": profile_file.stem,
                    "type": profile_type,
                    "file": str(profile_file),
                    "parse_error": True,
                })

        if not results:
            return [{"error": f"No {profile_type} profiles found in {profiles_dir}"}]

        return results
    except Exception as exc:
        return [{"error": str(exc)}]


def show_profile(
    profiles_dir: str,
    profile_name: str,
) -> dict[str, Any]:
    """Show details of a specific profile by name.

    Searches all JSON and INI profile files for a matching name.

    Args:
        profiles_dir: Path to the ``resources/profiles/BBL/`` directory.
        profile_name: Profile name or filename stem to look up.

    Returns:
        Dict with full profile data or error details.
    """
    try:
        base = Path(profiles_dir)
        if not base.exists():
            return {"error": f"Profiles directory not found: {profiles_dir}"}

        # Search recursively for the profile
        for profile_file in base.rglob("*.json"):
            try:
                with open(profile_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                name = data.get("name", profile_file.stem)
                if name == profile_name or profile_file.stem == profile_name:
                    return {
                        "name": name,
                        "file": str(profile_file),
                        "format": "json",
                        "settings": data,
                    }
            except (json.JSONDecodeError, OSError):
                continue

        for profile_file in base.rglob("*.ini"):
            try:
                raw = profile_file.read_text(encoding="utf-8")
                config = parse_config(raw)
                name = config.get("name", profile_file.stem)
                if name == profile_name or profile_file.stem == profile_name:
                    return {
                        "name": name,
                        "file": str(profile_file),
                        "format": "ini",
                        "settings": config,
                    }
            except OSError:
                continue

        return {"error": f"Profile '{profile_name}' not found in {profiles_dir}"}
    except Exception as exc:
        return {"error": str(exc)}


# ═══════════════════════════════════════════════════════════════════════════
# Profile discovery and recommendation (Faas 8)
# ═══════════════════════════════════════════════════════════════════════════

# Printer short-name mapping for filename parsing
_PRINTER_ALIASES: dict[str, str] = {
    "A1": "Bambu Lab A1",
    "A1M": "Bambu Lab A1 mini",
    "X1C": "Bambu Lab X1 Carbon",
    "X1E": "Bambu Lab X1E",
    "X1": "Bambu Lab X1",
    "P1P": "Bambu Lab P1P",
    "P1S": "Bambu Lab P1S",
    "P2S": "Bambu Lab P2S",
    "H2C": "Bambu Lab H2C",
    "H2D": "Bambu Lab H2D",
    "H2DP": "Bambu Lab H2D Pro",
    "H2S": "Bambu Lab H2S",
}

# Quality → layer height mapping
_QUALITY_MAP: dict[str, str] = {
    "draft": "0.28mm",
    "standard": "0.20mm",
    "fine": "0.12mm",
    "extra-fine": "0.08mm",
    "high-quality": "0.08mm",
}


class ProfilesNotFoundError(RuntimeError):
    """Raised when the BambuStudio profiles directory cannot be found."""
    pass


def find_profiles_dir() -> str:
    """Discover BambuStudio's bundled profiles directory.

    Search order:
    1. BAMBUSTUDIO_PROFILES env var
    2. macOS app bundle
    3. Linux system install
    4. Source repo fallback

    Returns:
        Absolute path to the profiles/BBL/ directory.

    Raises:
        ProfilesNotFoundError: If no profiles directory is found.
    """
    env_path = os.environ.get("BAMBUSTUDIO_PROFILES")
    if env_path and os.path.isdir(env_path):
        return env_path

    system = platform.system()

    if system == "Darwin":
        mac_path = "/Applications/BambuStudio.app/Contents/Resources/profiles/BBL"
        if os.path.isdir(mac_path):
            return mac_path

    if system == "Linux":
        linux_candidates = [
            "/usr/share/BambuStudio/resources/profiles/BBL",
            "/usr/local/share/BambuStudio/resources/profiles/BBL",
            os.path.expanduser("~/snap/bambu-studio/current/usr/share/BambuStudio/resources/profiles/BBL"),
        ]
        for path in linux_candidates:
            if os.path.isdir(path):
                return path

    # Source repo fallback — walk up from this file to find resources/
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "resources" / "profiles" / "BBL"
        if candidate.is_dir():
            return str(candidate)

    raise ProfilesNotFoundError(
        "BambuStudio profiles not found.\n"
        "Install BambuStudio or set BAMBUSTUDIO_PROFILES=/path/to/profiles/BBL"
    )


def _parse_printer_alias(filename: str) -> str | None:
    """Extract printer short alias from a '@BBL ALIAS' filename pattern."""
    match = re.search(r"@BBL\s+(\S+)", filename)
    if match:
        return match.group(1)
    return None


def _nozzle_matches(filename: str, nozzle: float) -> bool:
    """Check if a profile filename matches the given nozzle size.

    Files without an explicit nozzle spec default to 0.4mm.
    """
    nozzle_match = re.search(r"(\d+\.\d+)\s*nozzle", filename)
    if nozzle_match:
        return abs(float(nozzle_match.group(1)) - nozzle) < 0.01
    # No nozzle spec in filename → default 0.4mm
    return abs(nozzle - 0.4) < 0.01


def list_printers(profiles_dir: str | None = None) -> list[dict[str, Any]]:
    """List all available printers with nozzle options.

    Scans machine/ directory for top-level printer model files
    (excludes template/gcode files).

    Returns:
        List of printer dicts: [{name, model_id, nozzles, bed_size, ...}]
    """
    try:
        pdir = profiles_dir or find_profiles_dir()
    except ProfilesNotFoundError as exc:
        return [{"error": str(exc)}]

    machine_dir = Path(pdir) / "machine"
    if not machine_dir.is_dir():
        return [{"error": f"No machine/ directory in {pdir}"}]

    # Only load top-level model files (type=machine_model), skip templates
    printers: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for f in sorted(machine_dir.glob("*.json")):
        # Skip template files (contain 'template' in name)
        if "template" in f.stem.lower():
            continue
        # Skip nozzle-specific variants for listing (we aggregate nozzles)
        if "nozzle" in f.stem.lower():
            continue

        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        name = data.get("name", f.stem)
        if name in seen_names:
            continue
        seen_names.add(name)

        # Parse nozzle options from nozzle_diameter field
        nozzles_raw = data.get("nozzle_diameter", "0.4")
        # Handle both string ("0.4;0.2") and list (["0.4", "0.2"]) formats
        if isinstance(nozzles_raw, list):
            nozzle_strs = nozzles_raw
        else:
            nozzle_strs = [n.strip() for n in str(nozzles_raw).split(";") if n.strip()]
        nozzles = sorted(set(float(n) for n in nozzle_strs if n))

        entry: dict[str, Any] = {
            "name": name,
            "model_id": data.get("model_id", ""),
            "nozzles": nozzles,
            "default_bed_type": data.get("default_bed_type", ""),
            "machine_tech": data.get("machine_tech", "FFF"),
        }

        # Extract default materials list
        defaults = data.get("default_materials", "")
        if defaults:
            entry["default_materials_count"] = len([m for m in defaults.split(";") if m.strip()])

        printers.append(entry)

    return printers


def list_filaments(
    printer: str,
    nozzle: float = 0.4,
    profiles_dir: str | None = None,
) -> list[dict[str, Any]]:
    """List filaments compatible with a given printer+nozzle combo.

    Uses filename pattern matching for performance:
    'Bambu PLA Basic @BBL A1.json' → printer alias 'A1'.

    Returns:
        List of filament dicts: [{name, material, file, ...}]
    """
    try:
        pdir = profiles_dir or find_profiles_dir()
    except ProfilesNotFoundError as exc:
        return [{"error": str(exc)}]

    filament_dir = Path(pdir) / "filament"
    if not filament_dir.is_dir():
        return [{"error": f"No filament/ directory in {pdir}"}]

    # Determine printer alias for filename matching
    printer_alias = None
    for alias, full_name in _PRINTER_ALIASES.items():
        if full_name.lower() == printer.lower() or alias.lower() == printer.lower():
            printer_alias = alias
            break

    if not printer_alias:
        # Try extracting from the printer name directly
        parts = printer.replace("Bambu Lab ", "").replace(" ", "")
        for alias in _PRINTER_ALIASES:
            if alias.lower() == parts.lower():
                printer_alias = alias
                break

    if not printer_alias:
        return [{"error": f"Unknown printer: {printer}. Known: {list(_PRINTER_ALIASES.values())}"}]

    filaments: list[dict[str, Any]] = []

    for f in sorted(filament_dir.glob("*.json")):
        stem = f.stem
        # Quick filename filter — must contain the printer alias
        alias_in_name = _parse_printer_alias(stem)
        if alias_in_name != printer_alias:
            continue
        # Check nozzle compatibility
        if not _nozzle_matches(stem, nozzle):
            continue

        # Extract material type from filename (before @)
        material_part = stem.split("@")[0].strip() if "@" in stem else stem
        # Determine material category
        material_type = _extract_material_type(material_part)

        filaments.append({
            "name": stem,
            "material": material_type,
            "file": str(f),
        })

    return filaments


def _extract_material_type(name: str) -> str:
    """Extract the material category from a filament name.

    'Bambu PLA Basic' → 'PLA'
    'Generic PETG' → 'PETG'
    'Bambu Support For PA/PET' → 'Support'
    """
    name_upper = name.upper()
    # Check 'Support' first — it contains 'PA'/'PET' as substrings
    if "SUPPORT" in name_upper:
        return "Support"
    for mat in ["PLA", "PETG", "ABS", "TPU", "ASA", "HIPS", "PVA", "PA", "PC", "PET"]:
        # Use word boundary matching: ' PLA', 'PLA ', start/end
        # Simple check: look for the material as a standalone token
        if f" {mat} " in f" {name_upper} ":
            return mat
    return name.split()[-1] if name.split() else "Unknown"


def list_processes(
    printer: str,
    nozzle: float = 0.4,
    profiles_dir: str | None = None,
) -> list[dict[str, Any]]:
    """List print quality presets for a given printer+nozzle combo.

    Returns:
        List of process dicts: [{name, layer_height, quality, file, ...}]
    """
    try:
        pdir = profiles_dir or find_profiles_dir()
    except ProfilesNotFoundError as exc:
        return [{"error": str(exc)}]

    process_dir = Path(pdir) / "process"
    if not process_dir.is_dir():
        return [{"error": f"No process/ directory in {pdir}"}]

    # Determine printer alias
    printer_alias = None
    for alias, full_name in _PRINTER_ALIASES.items():
        if full_name.lower() == printer.lower() or alias.lower() == printer.lower():
            printer_alias = alias
            break

    if not printer_alias:
        return [{"error": f"Unknown printer: {printer}. Known: {list(_PRINTER_ALIASES.values())}"}]

    processes: list[dict[str, Any]] = []

    for f in sorted(process_dir.glob("*.json")):
        stem = f.stem
        alias_in_name = _parse_printer_alias(stem)
        if alias_in_name != printer_alias:
            continue
        if not _nozzle_matches(stem, nozzle):
            continue

        # Extract layer height and quality label from filename
        lh_match = re.match(r"(\d+\.\d+)mm\s+(.*?)(?:\s+@)", stem)
        layer_height = ""
        quality_label = ""
        if lh_match:
            layer_height = lh_match.group(1)
            quality_label = lh_match.group(2).strip()

        processes.append({
            "name": stem,
            "layer_height": layer_height,
            "quality": quality_label,
            "file": str(f),
        })

    return processes


def suggest_preset(
    printer: str,
    material: str,
    quality: str = "standard",
    profiles_dir: str | None = None,
) -> dict[str, Any]:
    """Recommend a (machine, filament, process) preset triple.

    Args:
        printer: Printer name (e.g. 'Bambu Lab A1').
        material: Material type (e.g. 'PLA', 'ABS', 'PETG').
        quality: Quality tier: draft, standard, fine, extra-fine.
        profiles_dir: Override profiles directory.

    Returns:
        Dict with recommended preset file paths and summary.
    """
    try:
        pdir = profiles_dir or find_profiles_dir()
    except ProfilesNotFoundError as exc:
        return {"error": str(exc)}

    # Resolve printer alias
    printer_alias = None
    for alias, full_name in _PRINTER_ALIASES.items():
        if full_name.lower() == printer.lower() or alias.lower() == printer.lower():
            printer_alias = alias
            printer = full_name
            break

    if not printer_alias:
        return {"error": f"Unknown printer: {printer}. Known: {list(_PRINTER_ALIASES.values())}"}

    # 1. Find machine preset
    machine_dir = Path(pdir) / "machine"
    machine_preset = None
    machine_file = None
    for f in machine_dir.glob("*.json"):
        if f.stem.lower() == printer.lower() or f.stem == f"{printer} 0.4 nozzle":
            machine_preset = f.stem
            machine_file = str(f)
            break
    # Fallback: find the nozzle-specific file
    if not machine_file:
        for f in machine_dir.glob("*.json"):
            if printer.lower() in f.stem.lower() and "0.4 nozzle" in f.stem.lower() and "template" not in f.stem.lower():
                machine_preset = f.stem
                machine_file = str(f)
                break

    if not machine_file:
        return {"error": f"No machine preset found for {printer}"}

    # 2. Find filament preset
    filaments = list_filaments(printer=printer, nozzle=0.4, profiles_dir=pdir)
    filament_preset = None
    filament_file = None
    material_upper = material.upper()

    # Prefer 'Basic' or exact match, then any match
    for fil in filaments:
        if "error" in fil:
            continue
        fil_material = fil.get("material", "").upper()
        if fil_material == material_upper:
            name = fil["name"]
            # Prefer 'Basic' variant
            if "basic" in name.lower() or filament_preset is None:
                filament_preset = name
                filament_file = fil["file"]
                if "basic" in name.lower():
                    break

    if not filament_file:
        return {
            "error": f"No {material} filament found for {printer}",
            "available_materials": sorted(set(
                f.get("material", "") for f in filaments if "error" not in f
            )),
        }

    # 3. Find process preset
    layer_prefix = _QUALITY_MAP.get(quality.lower(), "0.20mm")
    processes = list_processes(printer=printer, nozzle=0.4, profiles_dir=pdir)
    process_preset = None
    process_file = None

    # Exact layer height match first
    for proc in processes:
        if "error" in proc:
            continue
        if proc.get("layer_height", "") + "mm" == layer_prefix or layer_prefix.startswith(proc.get("layer_height", "x")):
            process_preset = proc["name"]
            process_file = proc["file"]
            break

    # Fallback: any process with 'Standard'
    if not process_file:
        for proc in processes:
            if "error" not in proc and "standard" in proc.get("quality", "").lower():
                process_preset = proc["name"]
                process_file = proc["file"]
                break

    # Last fallback: first available
    if not process_file and processes and "error" not in processes[0]:
        process_preset = processes[0]["name"]
        process_file = processes[0]["file"]

    if not process_file:
        return {"error": f"No process preset found for {printer} at {quality} quality"}

    return {
        "machine_preset": machine_preset,
        "machine_file": machine_file,
        "filament_preset": filament_preset,
        "filament_file": filament_file,
        "process_preset": process_preset,
        "process_file": process_file,
        "settings_summary": {
            "printer": printer,
            "material": material,
            "quality": quality,
            "layer_height": layer_prefix,
        },
    }


def validate_combo(
    machine: str,
    filament: str,
    process: str,
    profiles_dir: str | None = None,
) -> dict[str, Any]:
    """Check if a preset combination is valid.

    Validates that:
    1. All three presets exist
    2. Filament and process are for the same printer
    3. No known incompatibilities

    Returns:
        Dict with {valid, warnings, errors}.
    """
    try:
        pdir = profiles_dir or find_profiles_dir()
    except ProfilesNotFoundError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    errors: list[str] = []
    warnings: list[str] = []

    base = Path(pdir)

    # Check machine preset exists
    machine_found = False
    for f in (base / "machine").glob("*.json"):
        if f.stem == machine or f.stem.lower() == machine.lower():
            machine_found = True
            break
    if not machine_found:
        errors.append(f"Machine preset not found: {machine}")

    # Check filament preset exists
    filament_found = False
    filament_alias = None
    for f in (base / "filament").glob("*.json"):
        if f.stem == filament or f.stem.lower() == filament.lower():
            filament_found = True
            filament_alias = _parse_printer_alias(f.stem)
            break
    if not filament_found:
        errors.append(f"Filament preset not found: {filament}")

    # Check process preset exists
    process_found = False
    process_alias = None
    for f in (base / "process").glob("*.json"):
        if f.stem == process or f.stem.lower() == process.lower():
            process_found = True
            process_alias = _parse_printer_alias(f.stem)
            break
    if not process_found:
        errors.append(f"Process preset not found: {process}")

    # Cross-validate printer aliases
    if filament_alias and process_alias and filament_alias != process_alias:
        warnings.append(
            f"Filament targets printer {filament_alias} but process targets {process_alias}"
        )

    # Check machine vs filament alias
    machine_alias = _parse_printer_alias(machine) if machine_found else None
    if machine_alias and filament_alias and machine_alias != filament_alias:
        warnings.append(
            f"Machine is {machine_alias} but filament targets {filament_alias}"
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "machine": machine,
        "filament": filament,
        "process": process,
    }
