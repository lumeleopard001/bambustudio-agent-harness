"""Tests for workflow commands (Faas 9-10).

Tests auto, guided, and review workflows using mock backend
and synthetic 3MF fixtures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli_anything.bambustudio.core.workflow import (
    workflow_auto,
    workflow_guided_start,
    workflow_guided_select,
    workflow_guided_execute,
    workflow_review,
    _preflight_check,
    _format_time,
)
from cli_anything.bambustudio.utils.bambustudio_backend import BackendResult


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _create_mock_profiles(tmp_path: Path) -> str:
    """Create mock profiles directory."""
    base = tmp_path / "profiles" / "BBL"
    (base / "machine").mkdir(parents=True)
    (base / "filament").mkdir(parents=True)
    (base / "process").mkdir(parents=True)

    (base / "machine" / "Bambu Lab A1.json").write_text(json.dumps({
        "type": "machine_model", "name": "Bambu Lab A1",
        "nozzle_diameter": "0.4;0.2;0.6;0.8", "model_id": "N2S",
        "machine_tech": "FFF",
    }))
    (base / "machine" / "Bambu Lab A1 0.4 nozzle.json").write_text(json.dumps({
        "type": "machine", "name": "Bambu Lab A1 0.4 nozzle",
        "inherits": "Bambu Lab A1",
    }))
    (base / "filament" / "Bambu PLA Basic @BBL A1.json").write_text(json.dumps({
        "type": "filament", "name": "Bambu PLA Basic @BBL A1",
    }))
    (base / "process" / "0.20mm Standard @BBL A1.json").write_text(json.dumps({
        "type": "process", "name": "0.20mm Standard @BBL A1",
    }))

    return str(base)


@pytest.fixture
def mock_profiles(tmp_path) -> str:
    return _create_mock_profiles(tmp_path)


@pytest.fixture
def mock_stl(tmp_path) -> str:
    """Create a minimal (empty) STL file for testing."""
    stl_path = tmp_path / "test_cube.stl"
    # Binary STL header (80 bytes) + triangle count (4 bytes) = 84 bytes
    stl_path.write_bytes(b"\0" * 80 + b"\x00\x00\x00\x00")
    return str(stl_path)


@pytest.fixture
def mock_backend(tmp_path):
    """Backend that returns success for all operations."""
    from cli_anything.bambustudio.utils.bambustudio_backend import BambuStudioBackend

    backend = BambuStudioBackend.__new__(BambuStudioBackend)
    backend.binary_path = "/mock/bambustudio"
    backend.debug_level = 1

    result_json = {
        "return_code": 0,
        "sliced_plates": [{
            "id": 1,
            "total_predication": 1800,
            "filaments": [{"total_used_g": 5.2}],
        }],
    }

    def mock_run(args, input_files=None, timeout=600):
        # For slice commands, write a result.json
        for i, arg in enumerate(args):
            if arg == "--outputdir" and i + 1 < len(args):
                out_dir = args[i + 1]
                os.makedirs(out_dir, exist_ok=True)
                rj_path = os.path.join(out_dir, "result.json")
                with open(rj_path, "w") as fh:
                    json.dump(result_json, fh)

        return BackendResult(
            returncode=0, stdout="OK", stderr="",
            result_json=result_json, error_message="Success",
            duration_ms=100, output_files=[],
        )

    backend.run = MagicMock(side_effect=mock_run)
    return backend


# ═══════════════════════════════════════════════════════════════════════════
# workflow auto
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowAuto:

    def test_auto_mock(self, mock_stl, mock_backend, mock_profiles, tmp_path):
        """Auto workflow with mock backend and profiles."""
        output = str(tmp_path / "output.3mf")
        with patch("cli_anything.bambustudio.core.config.find_profiles_dir", return_value=mock_profiles):
            with patch("cli_anything.bambustudio.core.workflow.find_profiles_dir", return_value=mock_profiles):
                result = workflow_auto(
                    stl_path=mock_stl,
                    printer="Bambu Lab A1",
                    material="PLA",
                    quality="standard",
                    output_path=output,
                    backend=mock_backend,
                )
        assert result.get("ok") is True
        assert "output_3mf" in result

    def test_auto_missing_stl(self, mock_backend, mock_profiles):
        """Auto workflow with non-existent STL fails."""
        result = workflow_auto(
            stl_path="/nonexistent/file.stl",
            printer="Bambu Lab A1",
            material="PLA",
            backend=mock_backend,
        )
        assert result.get("ok") is False
        assert "error" in result

    def test_auto_unknown_printer(self, mock_stl, mock_backend, mock_profiles):
        """Auto workflow with unknown printer fails at suggest_preset."""
        with patch("cli_anything.bambustudio.core.config.find_profiles_dir", return_value=mock_profiles):
            with patch("cli_anything.bambustudio.core.workflow.find_profiles_dir", return_value=mock_profiles):
                result = workflow_auto(
                    stl_path=mock_stl,
                    printer="Unknown Printer XYZ",
                    material="PLA",
                    backend=mock_backend,
                )
        assert result.get("ok") is False
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════
# workflow guided
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowGuided:

    def test_guided_start(self, mock_stl, mock_profiles):
        """Start creates session file and returns printer options."""
        with patch("cli_anything.bambustudio.core.workflow.list_printers") as mock_lp:
            mock_lp.return_value = [
                {"name": "Bambu Lab A1", "nozzles": [0.4]},
                {"name": "Bambu Lab X1C", "nozzles": [0.4]},
            ]
            result = workflow_guided_start(stl_path=mock_stl)

        assert result["step"] == "printer"
        assert len(result["options"]) >= 1
        assert os.path.isfile(result["session_file"])

    def test_guided_select_sequence(self, mock_stl, mock_profiles):
        """Full guided selection sequence: printer → material → quality → confirm."""
        with patch("cli_anything.bambustudio.core.workflow.list_printers") as mock_lp:
            mock_lp.return_value = [{"name": "Bambu Lab A1", "nozzles": [0.4]}]
            start = workflow_guided_start(stl_path=mock_stl)

        session_file = start["session_file"]

        # Select printer
        with patch("cli_anything.bambustudio.core.workflow.list_filaments") as mock_lf:
            mock_lf.return_value = [
                {"name": "Bambu PLA Basic @BBL A1", "material": "PLA", "file": "/mock/pla.json"},
            ]
            r1 = workflow_guided_select(session_file, step="printer", value="Bambu Lab A1")
        assert r1["step"] == "material"
        assert "PLA" in r1["options"]

        # Select material
        r2 = workflow_guided_select(session_file, step="material", value="PLA")
        assert r2["step"] == "quality"

        # Select quality
        with patch("cli_anything.bambustudio.core.workflow.suggest_preset") as mock_sp:
            mock_sp.return_value = {
                "machine_preset": "Bambu Lab A1 0.4 nozzle",
                "filament_preset": "Bambu PLA Basic @BBL A1",
                "process_preset": "0.20mm Standard @BBL A1",
                "settings_summary": {"printer": "Bambu Lab A1", "material": "PLA", "quality": "standard"},
            }
            r3 = workflow_guided_select(session_file, step="quality", value="standard")
        assert r3["step"] == "confirm"
        assert r3["ready"] is True

    def test_guided_invalid_step(self, mock_stl, mock_profiles):
        """Wrong step order returns error."""
        with patch("cli_anything.bambustudio.core.workflow.list_printers") as mock_lp:
            mock_lp.return_value = [{"name": "Bambu Lab A1", "nozzles": [0.4]}]
            start = workflow_guided_start(stl_path=mock_stl)

        result = workflow_guided_select(
            start["session_file"], step="quality", value="standard"
        )
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════
# workflow review
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowReview:

    def test_review_good_project(self, minimal_3mf):
        """Review of minimal 3MF should return a score."""
        result = workflow_review(project_path=str(minimal_3mf))
        assert "overall_score" in result
        assert result["overall_score"] in ("good", "needs-attention", "problematic")
        assert "current_settings" in result
        assert "recommendations" in result

    def test_review_settings_extraction(self, minimal_3mf):
        """Review extracts layer_height, infill, etc."""
        result = workflow_review(project_path=str(minimal_3mf))
        settings = result["current_settings"]
        assert settings["layer_height"] == "0.2"
        assert settings["infill_density"] == "15%"
        assert settings["objects"] == 1

    def test_review_missing_file(self):
        result = workflow_review(project_path="/nonexistent.3mf")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════
# Preflight
# ═══════════════════════════════════════════════════════════════════════════


class TestPreflight:

    def test_preflight_with_mock(self, minimal_3mf, mock_backend):
        """Preflight check parses objects and checks bed fit."""
        result = _preflight_check(
            str(minimal_3mf), mock_backend, bed_size=(256, 256)
        )
        assert "objects" in result
        assert result["object_count"] == 1
        assert result["total_triangles"] == 12


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestHelpers:

    def test_format_time_seconds(self):
        assert _format_time(45) == "45s"

    def test_format_time_minutes(self):
        assert _format_time(150) == "2m 30s"

    def test_format_time_hours(self):
        assert _format_time(7200) == "2h 0m"
        assert _format_time(5430) == "1h 30m"
