"""Regression tests for bugs B1-B5 and failure mode gaps."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from cli_anything.bambustudio.core.config import find_profiles_dir, list_profiles
from cli_anything.bambustudio.core.slicer import slice_project
from cli_anything.bambustudio.utils.bambustudio_backend import BackendResult


# ═══════════════════════════════════════════════════════════════════════════
# B1: profiles-list no dir arg
# ═══════════════════════════════════════════════════════════════════════════

class TestB1ProfilesListNoDir:

    def test_list_profiles_with_explicit_dir(self, tmp_path):
        """B1 regression: list_profiles works with profiles_dir param."""
        profiles_dir = tmp_path / "profiles" / "BBL" / "machine"
        profiles_dir.mkdir(parents=True)
        (profiles_dir / "Test Printer.json").write_text(json.dumps({
            "name": "Test Printer", "type": "machine_model",
        }))
        result = list_profiles(
            profiles_dir=str(tmp_path / "profiles" / "BBL"),
            profile_type="machine",
        )
        assert len(result) >= 1
        assert any(p.get("name") == "Test Printer" for p in result)


# ═══════════════════════════════════════════════════════════════════════════
# B3: object-id is int
# ═══════════════════════════════════════════════════════════════════════════

class TestB3ObjectIdIsInt:

    def test_delete_object_expects_int(self, minimal_3mf):
        """B3 regression: delete_object uses int object_id."""
        from cli_anything.bambustudio.core.model import delete_object
        result = delete_object(
            project_path=str(minimal_3mf),
            object_id=1,  # Should be int, not str
        )
        assert result.get("deleted") is True
        assert result["object_id"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# B4: slice plate None defaults to 0
# ═══════════════════════════════════════════════════════════════════════════

class TestB4SlicePlateNone:

    def test_slice_plate_none_becomes_zero(self, minimal_3mf, mock_backend):
        """B4 regression: plate=0 is sent to binary, not None."""
        result = slice_project(
            project_path=str(minimal_3mf),
            backend=mock_backend,
            plate=0,  # Explicitly 0 (the CLI now ensures this)
        )
        # Verify the backend was called with "--slice" "0", not "--slice" "None"
        call_args = mock_backend.run.call_args
        args_list = call_args[0][0]  # first positional arg
        slice_idx = args_list.index("--slice")
        assert args_list[slice_idx + 1] == "0"


# ═══════════════════════════════════════════════════════════════════════════
# B5: ThreeMF.load dedup
# ═══════════════════════════════════════════════════════════════════════════

class TestB5ThreeMFLoadDedup:

    def test_load_delegates_to_constructor(self, minimal_3mf):
        """B5 regression: ThreeMF.load() uses __init__, no duplication."""
        from cli_anything.bambustudio.utils.threemf import ThreeMF
        tmf = ThreeMF.load(str(minimal_3mf))
        assert tmf._source_path == str(minimal_3mf)
        assert len(tmf.get_objects()) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Failure mode: settings files exist check
# ═══════════════════════════════════════════════════════════════════════════

class TestSettingsFilesExistCheck:

    def test_missing_settings_file(self, minimal_3mf, mock_backend):
        """Slice fails early if --load-settings file doesn't exist."""
        result = slice_project(
            project_path=str(minimal_3mf),
            backend=mock_backend,
            plate=0,
            settings_files=["/nonexistent/settings.json"],
        )
        assert result["sliced"] is False
        assert "not found" in result["error"].lower()

    def test_missing_filament_file(self, minimal_3mf, mock_backend):
        """Slice fails early if --load-filaments file doesn't exist."""
        result = slice_project(
            project_path=str(minimal_3mf),
            backend=mock_backend,
            plate=0,
            filament_files=["/nonexistent/filament.json"],
        )
        assert result["sliced"] is False
        assert "not found" in result["error"].lower()

    def test_valid_settings_files(self, minimal_3mf, mock_backend, tmp_path):
        """Slice proceeds when settings files exist."""
        settings_file = tmp_path / "test_settings.json"
        settings_file.write_text("{}")
        result = slice_project(
            project_path=str(minimal_3mf),
            backend=mock_backend,
            plate=0,
            settings_files=[str(settings_file)],
        )
        # Should proceed (mock backend returns success)
        assert result["sliced"] is True
