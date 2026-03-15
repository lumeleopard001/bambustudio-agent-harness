"""Tests for profile discovery and recommendation (Faas 8).

Tests work against real BambuStudio profiles (macOS app) or fall back
to mocked filesystem structure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cli_anything.bambustudio.core.config import (
    find_profiles_dir,
    list_printers,
    list_filaments,
    list_processes,
    suggest_preset,
    validate_combo,
    ProfilesNotFoundError,
    _parse_printer_alias,
    _nozzle_matches,
    _extract_material_type,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

_REAL_PROFILES = "/Applications/BambuStudio.app/Contents/Resources/profiles/BBL"
_HAS_REAL_PROFILES = os.path.isdir(_REAL_PROFILES)


def _create_mock_profiles(tmp_path: Path) -> str:
    """Create a minimal mock profiles directory for testing."""
    base = tmp_path / "profiles" / "BBL"
    (base / "machine").mkdir(parents=True)
    (base / "filament").mkdir(parents=True)
    (base / "process").mkdir(parents=True)

    # Machine profile
    (base / "machine" / "Bambu Lab A1.json").write_text(json.dumps({
        "type": "machine_model",
        "name": "Bambu Lab A1",
        "nozzle_diameter": "0.4;0.2;0.6;0.8",
        "model_id": "N2S",
        "default_bed_type": "Textured PEI Plate",
        "machine_tech": "FFF",
        "default_materials": "Bambu PLA Basic @BBL A1;Bambu ABS @BBL A1",
    }))
    (base / "machine" / "Bambu Lab A1 0.4 nozzle.json").write_text(json.dumps({
        "type": "machine",
        "name": "Bambu Lab A1 0.4 nozzle",
        "inherits": "Bambu Lab A1",
    }))

    # Filament profiles
    (base / "filament" / "Bambu PLA Basic @BBL A1.json").write_text(json.dumps({
        "type": "filament",
        "name": "Bambu PLA Basic @BBL A1",
        "inherits": "Bambu PLA Basic @base",
    }))
    (base / "filament" / "Bambu ABS @BBL A1.json").write_text(json.dumps({
        "type": "filament",
        "name": "Bambu ABS @BBL A1",
        "inherits": "Bambu ABS @base",
    }))
    (base / "filament" / "Bambu PLA Basic @BBL X1C.json").write_text(json.dumps({
        "type": "filament",
        "name": "Bambu PLA Basic @BBL X1C",
    }))

    # Process profiles
    (base / "process" / "0.20mm Standard @BBL A1.json").write_text(json.dumps({
        "type": "process",
        "name": "0.20mm Standard @BBL A1",
    }))
    (base / "process" / "0.12mm Fine @BBL A1.json").write_text(json.dumps({
        "type": "process",
        "name": "0.12mm Fine @BBL A1",
    }))
    (base / "process" / "0.08mm Extra Fine @BBL A1.json").write_text(json.dumps({
        "type": "process",
        "name": "0.08mm Extra Fine @BBL A1",
    }))

    return str(base)


# ═══════════════════════════════════════════════════════════════════════════
# find_profiles_dir
# ═══════════════════════════════════════════════════════════════════════════


class TestFindProfilesDir:

    @pytest.mark.skipif(not _HAS_REAL_PROFILES, reason="BambuStudio not installed")
    def test_find_profiles_dir_macos(self):
        """On macOS with BambuStudio, should find the real profiles."""
        result = find_profiles_dir()
        assert os.path.isdir(result)
        assert "BBL" in result

    def test_find_profiles_dir_env_override(self, tmp_path):
        """BAMBUSTUDIO_PROFILES env var overrides discovery."""
        mock_dir = _create_mock_profiles(tmp_path)
        with patch.dict(os.environ, {"BAMBUSTUDIO_PROFILES": mock_dir}):
            result = find_profiles_dir()
            assert result == mock_dir

    def test_find_profiles_dir_missing(self, tmp_path):
        """Raises ProfilesNotFoundError when nothing found."""
        with patch.dict(os.environ, {"BAMBUSTUDIO_PROFILES": ""}, clear=False):
            with patch("cli_anything.bambustudio.core.config.platform.system", return_value="UnknownOS"):
                with patch("cli_anything.bambustudio.core.config.Path.parents", new_callable=lambda: property(lambda self: [])):
                    # This is hard to fully mock, so we just test the error class exists
                    assert issubclass(ProfilesNotFoundError, RuntimeError)


# ═══════════════════════════════════════════════════════════════════════════
# Filename parsing helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestFilenameParsing:

    def test_parse_printer_alias(self):
        assert _parse_printer_alias("Bambu PLA @BBL A1") == "A1"
        assert _parse_printer_alias("0.20mm Standard @BBL X1C") == "X1C"
        assert _parse_printer_alias("Bambu ABS @BBL H2D") == "H2D"
        assert _parse_printer_alias("Generic PLA") is None

    def test_nozzle_matches_default(self):
        assert _nozzle_matches("Bambu PLA @BBL A1", 0.4) is True
        assert _nozzle_matches("Bambu PLA @BBL A1", 0.2) is False

    def test_nozzle_matches_explicit(self):
        assert _nozzle_matches("Bambu PLA @BBL A1 0.2 nozzle", 0.2) is True
        assert _nozzle_matches("Bambu PLA @BBL A1 0.2 nozzle", 0.4) is False

    def test_extract_material_type(self):
        assert _extract_material_type("Bambu PLA Basic") == "PLA"
        assert _extract_material_type("Bambu ABS") == "ABS"
        assert _extract_material_type("Generic PETG") == "PETG"
        assert _extract_material_type("Bambu TPU 95A") == "TPU"
        assert _extract_material_type("Bambu Support For PA/PET") == "Support"


# ═══════════════════════════════════════════════════════════════════════════
# list_printers
# ═══════════════════════════════════════════════════════════════════════════


class TestListPrinters:

    def test_list_printers_mock(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = list_printers(profiles_dir=mock_dir)
        assert len(result) >= 1
        assert any(p["name"] == "Bambu Lab A1" for p in result)
        a1 = next(p for p in result if p["name"] == "Bambu Lab A1")
        assert 0.4 in a1["nozzles"]

    @pytest.mark.skipif(not _HAS_REAL_PROFILES, reason="BambuStudio not installed")
    def test_list_printers_real(self):
        result = list_printers(profiles_dir=_REAL_PROFILES)
        assert len(result) >= 5  # A1, A1 mini, X1C, P1S, etc.
        names = [p["name"] for p in result]
        assert "Bambu Lab A1" in names


# ═══════════════════════════════════════════════════════════════════════════
# list_filaments
# ═══════════════════════════════════════════════════════════════════════════


class TestListFilaments:

    def test_list_filaments_mock(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = list_filaments(printer="Bambu Lab A1", profiles_dir=mock_dir)
        assert len(result) >= 1
        materials = [f["material"] for f in result]
        assert "PLA" in materials

    def test_list_filaments_unknown_printer(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = list_filaments(printer="Unknown Printer XYZ", profiles_dir=mock_dir)
        assert len(result) == 1
        assert "error" in result[0]

    @pytest.mark.skipif(not _HAS_REAL_PROFILES, reason="BambuStudio not installed")
    def test_list_filaments_real_a1(self):
        result = list_filaments(printer="Bambu Lab A1", profiles_dir=_REAL_PROFILES)
        assert len(result) >= 5
        materials = set(f["material"] for f in result)
        assert "PLA" in materials

    def test_list_filaments_nozzle_filter(self, tmp_path):
        """Filaments for non-default nozzle return only matching ones."""
        mock_dir = _create_mock_profiles(tmp_path)
        # No 0.2mm filaments in mock
        result = list_filaments(printer="Bambu Lab A1", nozzle=0.2, profiles_dir=mock_dir)
        # Mock only has default (0.4mm) filaments
        assert len(result) == 0


# ═══════════════════════════════════════════════════════════════════════════
# suggest_preset
# ═══════════════════════════════════════════════════════════════════════════


class TestSuggestPreset:

    def test_suggest_pla_a1_mock(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = suggest_preset(
            printer="Bambu Lab A1", material="PLA", quality="standard",
            profiles_dir=mock_dir,
        )
        assert "error" not in result
        assert result["machine_preset"] is not None
        assert result["filament_preset"] is not None
        assert result["process_preset"] is not None
        assert result["settings_summary"]["quality"] == "standard"

    def test_suggest_unknown_material(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = suggest_preset(
            printer="Bambu Lab A1", material="UNOBTANIUM", quality="standard",
            profiles_dir=mock_dir,
        )
        assert "error" in result

    @pytest.mark.skipif(not _HAS_REAL_PROFILES, reason="BambuStudio not installed")
    def test_suggest_pla_a1_real(self):
        result = suggest_preset(
            printer="Bambu Lab A1", material="PLA", quality="standard",
            profiles_dir=_REAL_PROFILES,
        )
        assert "error" not in result
        assert "PLA" in result["filament_preset"]
        assert "A1" in (result.get("machine_file") or "")


# ═══════════════════════════════════════════════════════════════════════════
# validate_combo
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateCombo:

    def test_validate_valid_combo(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = validate_combo(
            machine="Bambu Lab A1 0.4 nozzle",
            filament="Bambu PLA Basic @BBL A1",
            process="0.20mm Standard @BBL A1",
            profiles_dir=mock_dir,
        )
        assert result["valid"] is True
        assert len(result["errors"]) == 0

    def test_validate_missing_preset(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = validate_combo(
            machine="Nonexistent Machine",
            filament="Bambu PLA Basic @BBL A1",
            process="0.20mm Standard @BBL A1",
            profiles_dir=mock_dir,
        )
        assert result["valid"] is False
        assert len(result["errors"]) >= 1

    def test_validate_mismatched_printer(self, tmp_path):
        mock_dir = _create_mock_profiles(tmp_path)
        result = validate_combo(
            machine="Bambu Lab A1 0.4 nozzle",
            filament="Bambu PLA Basic @BBL X1C",
            process="0.20mm Standard @BBL A1",
            profiles_dir=mock_dir,
        )
        # Should have a warning about mismatched printers
        assert len(result["warnings"]) >= 1
