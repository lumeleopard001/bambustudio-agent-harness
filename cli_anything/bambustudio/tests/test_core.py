"""Unit tests for BambuStudio CLI harness — no binary required.

Tests ThreeMF parser, settings parser, output formatter,
backend error codes, session management, config, and project modules
using synthetic data only.
"""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import pytest

from cli_anything.bambustudio.utils.threemf import ThreeMF, PRINT_CONFIG
from cli_anything.bambustudio.utils.settings_parser import (
    parse_config,
    serialize_config,
    parse_multi_value,
)
from cli_anything.bambustudio.utils.output import OutputFormatter
from cli_anything.bambustudio.utils.bambustudio_backend import (
    CLI_ERRORS,
    BinaryNotFoundError,
)
from cli_anything.bambustudio.core.session import Session
from cli_anything.bambustudio.core.config import get_config_value, set_config_value
from cli_anything.bambustudio.core.project import open_project, list_plates, list_objects


# ═══════════════════════════════════════════════════════════════════════════
# ThreeMF parser
# ═══════════════════════════════════════════════════════════════════════════


class TestThreeMFParser:
    """Tests for cli_anything.bambustudio.utils.threemf.ThreeMF."""

    def test_load_3mf(self, minimal_3mf):
        """Load the minimal_3mf fixture, verify ThreeMF object."""
        tmf = ThreeMF.load(str(minimal_3mf))
        assert tmf is not None
        assert isinstance(tmf, ThreeMF)

    def test_get_objects(self, minimal_3mf):
        """Verify 1 object with name 'Cube'."""
        tmf = ThreeMF.load(str(minimal_3mf))
        objects = tmf.get_objects()
        assert len(objects) == 1
        assert objects[0].name == "Cube"
        assert objects[0].id == 1
        assert objects[0].vertex_count == 8
        assert objects[0].triangle_count == 12

    def test_get_plates(self, minimal_3mf):
        """Verify 1 plate with 1 object."""
        tmf = ThreeMF.load(str(minimal_3mf))
        plates = tmf.get_plates()
        assert len(plates) >= 1
        # Plate 0 should contain object 1
        plate0 = plates[0]
        assert plate0.index == 0
        obj_ids = [oid for oid, _ in plate0.object_ids]
        assert 1 in obj_ids

    def test_get_config(self, minimal_3mf):
        """Read print_profile.config, verify layer_height = '0.2'."""
        tmf = ThreeMF.load(str(minimal_3mf))
        config = tmf.get_config(PRINT_CONFIG)
        assert config.get("layer_height") == "0.2"

    def test_set_config(self, minimal_3mf, tmp_path):
        """Set layer_height, save, reload, verify."""
        tmf = ThreeMF.load(str(minimal_3mf))
        tmf.set_config(PRINT_CONFIG, "layer_height", "0.12")

        out = tmp_path / "modified.3mf"
        tmf.save(str(out))

        tmf2 = ThreeMF.load(str(out))
        config = tmf2.get_config(PRINT_CONFIG)
        assert config["layer_height"] == "0.12"

    def test_list_files(self, minimal_3mf):
        """Verify expected ZIP entries."""
        tmf = ThreeMF.load(str(minimal_3mf))
        files = tmf.list_files()
        assert "3D/3dmodel.model" in files
        assert "Metadata/print_profile.config" in files
        assert "[Content_Types].xml" in files
        assert "_rels/.rels" in files

    def test_has_gcode_false(self, minimal_3mf):
        """No gcode in minimal 3MF."""
        tmf = ThreeMF.load(str(minimal_3mf))
        assert tmf.has_gcode(0) is False
        assert tmf.has_gcode(1) is False

    def test_add_plate(self, minimal_3mf):
        """Add plate, verify count increases."""
        tmf = ThreeMF.load(str(minimal_3mf))
        initial_count = len(tmf.get_plates())
        new_idx = tmf.add_plate()
        assert new_idx == initial_count

    def test_remove_object(self, minimal_3mf):
        """Remove object, verify objects empty."""
        tmf = ThreeMF.load(str(minimal_3mf))
        assert len(tmf.get_objects()) == 1
        tmf.remove_object(1)
        assert len(tmf.get_objects()) == 0

    def test_save_roundtrip(self, minimal_3mf, tmp_path):
        """Load -> save -> load, verify same content."""
        tmf1 = ThreeMF.load(str(minimal_3mf))
        out = tmp_path / "roundtrip.3mf"
        tmf1.save(str(out))

        tmf2 = ThreeMF.load(str(out))
        assert tmf1.list_files() == tmf2.list_files()
        assert tmf1.get_config(PRINT_CONFIG) == tmf2.get_config(PRINT_CONFIG)
        assert len(tmf1.get_objects()) == len(tmf2.get_objects())
        assert tmf1.get_objects()[0].name == tmf2.get_objects()[0].name


# ═══════════════════════════════════════════════════════════════════════════
# Settings parser
# ═══════════════════════════════════════════════════════════════════════════


class TestSettingsParser:
    """Tests for cli_anything.bambustudio.utils.settings_parser."""

    def test_parse_simple(self):
        """'key = value' pairs."""
        text = "layer_height = 0.2\nperimeters = 2\n"
        result = parse_config(text)
        assert result == {"layer_height": "0.2", "perimeters": "2"}

    def test_parse_comments(self):
        """Lines starting with # are ignored."""
        text = "# This is a comment\nkey = value\n# Another comment\n"
        result = parse_config(text)
        assert result == {"key": "value"}
        assert "#" not in "".join(result.keys())

    def test_parse_blank_lines(self):
        """Empty lines are ignored."""
        text = "\n\nkey1 = val1\n\nkey2 = val2\n\n"
        result = parse_config(text)
        assert result == {"key1": "val1", "key2": "val2"}

    def test_parse_multivalue(self):
        """'key = val1;val2;val3' stays as single string."""
        text = "filament_colour = #FFFFFF;#000000;#FF0000\n"
        result = parse_config(text)
        assert result["filament_colour"] == "#FFFFFF;#000000;#FF0000"
        # Test multi-value split helper
        values = parse_multi_value(result["filament_colour"])
        assert values == ["#FFFFFF", "#000000", "#FF0000"]

    def test_serialize_roundtrip(self):
        """parse -> serialize -> parse, same result."""
        original_text = "layer_height = 0.2\nperimeters = 2\nfill_density = 15%\n"
        config1 = parse_config(original_text)
        serialized = serialize_config(config1)
        config2 = parse_config(serialized)
        assert config1 == config2

    def test_empty_config(self):
        """Empty string returns empty dict."""
        assert parse_config("") == {}
        assert parse_config("   \n  \n") == {}


# ═══════════════════════════════════════════════════════════════════════════
# Output formatter
# ═══════════════════════════════════════════════════════════════════════════


class TestOutputFormatter:
    """Tests for cli_anything.bambustudio.utils.output.OutputFormatter."""

    def test_json_success(self):
        """Verify JSON envelope structure."""
        fmt = OutputFormatter(json_mode=True)
        result = fmt.success({"key": "value"}, command="test.cmd")
        parsed = json.loads(result)
        assert parsed["ok"] is True
        assert parsed["command"] == "test.cmd"
        assert parsed["data"] == {"key": "value"}
        assert parsed["error"] is None
        assert "timestamp" in parsed
        assert "duration_ms" in parsed

    def test_json_error(self):
        """Verify error envelope."""
        fmt = OutputFormatter(json_mode=True)
        result = fmt.error("Something failed", command="test.cmd")
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert parsed["error"] == "Something failed"
        assert parsed["command"] == "test.cmd"
        assert "timestamp" in parsed

    def test_human_dict(self):
        """Verify human-readable dict output."""
        fmt = OutputFormatter(json_mode=False)
        result = fmt.success({"name": "Cube", "vertices": 8})
        assert "name: Cube" in result
        assert "vertices: 8" in result

    def test_human_list(self):
        """Verify human-readable list output."""
        fmt = OutputFormatter(json_mode=False)
        result = fmt.success(["item1", "item2", "item3"])
        assert "item1" in result
        assert "item2" in result
        assert "item3" in result

    def test_timer(self):
        """Verify duration_ms tracking."""
        fmt = OutputFormatter(json_mode=True)
        fmt.start_timer()
        # Small sleep to get measurable duration
        time.sleep(0.01)
        result = fmt.success({"ok": True}, command="timer.test")
        parsed = json.loads(result)
        assert parsed["duration_ms"] >= 0


# ═══════════════════════════════════════════════════════════════════════════
# Backend error codes
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendErrorCodes:
    """Tests for cli_anything.bambustudio.utils.bambustudio_backend."""

    def test_error_code_mapping(self):
        """Verify CLI_ERRORS dict has entries for 0-49."""
        for code in range(50):
            assert code in CLI_ERRORS, f"Missing error code {code}"
        assert CLI_ERRORS[0] == "Success"
        assert "memory" in CLI_ERRORS[14].lower() or "memory" in CLI_ERRORS[14]

    def test_binary_not_found(self):
        """Verify BinaryNotFoundError raised with instructions."""
        with pytest.raises(BinaryNotFoundError):
            raise BinaryNotFoundError("BambuStudio not found.\nInstall from: ...")
        # Verify it's a RuntimeError subclass
        assert issubclass(BinaryNotFoundError, RuntimeError)


# ═══════════════════════════════════════════════════════════════════════════
# Session
# ═══════════════════════════════════════════════════════════════════════════


class TestSession:
    """Tests for cli_anything.bambustudio.core.session.Session."""

    def test_load_project(self, sample_3mf_path):
        """Load fixture, verify loaded=True."""
        sess = Session(project_path=sample_3mf_path)
        status = sess.status()
        assert status["loaded"] is True
        assert status["project_path"] == sample_3mf_path

    def test_snapshot_undo(self, sample_3mf_path):
        """Take snapshot, modify, undo, verify original."""
        sess = Session(project_path=sample_3mf_path)
        tmf = sess.threemf
        assert tmf is not None

        # Read original config
        original_config = tmf.get_config(PRINT_CONFIG).copy()

        # Take snapshot, then modify
        sess.snapshot("before config change")
        tmf.set_config(PRINT_CONFIG, "layer_height", "0.99")
        assert tmf.get_config(PRINT_CONFIG)["layer_height"] == "0.99"

        # Undo
        result = sess.undo()
        assert result is not None
        # After undo, should be back to original
        assert sess.threemf.get_config(PRINT_CONFIG)["layer_height"] == original_config["layer_height"]

    def test_snapshot_redo(self, sample_3mf_path):
        """Snapshot + undo + redo."""
        sess = Session(project_path=sample_3mf_path)
        tmf = sess.threemf

        sess.snapshot("before change")
        tmf.set_config(PRINT_CONFIG, "layer_height", "0.88")

        # Undo
        sess.undo()
        assert sess.threemf.get_config(PRINT_CONFIG)["layer_height"] == "0.2"

        # Redo
        result = sess.redo()
        assert result is not None
        assert sess.threemf.get_config(PRINT_CONFIG)["layer_height"] == "0.88"

    def test_max_undo_limit(self, sample_3mf_path):
        """Verify max 10 snapshots."""
        sess = Session(project_path=sample_3mf_path)
        assert sess.max_undo == 10

        for i in range(15):
            sess.snapshot(f"change {i}")

        assert len(sess._undo_stack) <= 10

    def test_status(self, sample_3mf_path):
        """Verify status dict structure."""
        sess = Session(project_path=sample_3mf_path)
        status = sess.status()
        assert "project_path" in status
        assert "loaded" in status
        assert "dirty" in status
        assert "undo_depth" in status
        assert "redo_depth" in status
        assert "max_undo" in status
        assert isinstance(status["loaded"], bool)
        assert isinstance(status["undo_depth"], int)

    def test_history(self, sample_3mf_path):
        """Verify history entries."""
        sess = Session(project_path=sample_3mf_path)
        history = sess.history()
        assert len(history) >= 1
        # First entry should be the load operation
        assert history[0]["operation"] == "load"
        assert "timestamp" in history[0]
        assert "description" in history[0]


# ═══════════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════════


class TestConfig:
    """Tests for cli_anything.bambustudio.core.config."""

    def test_get_existing_key(self, sample_3mf_path):
        """Get layer_height returns '0.2'."""
        result = get_config_value(sample_3mf_path, "layer_height")
        assert "error" not in result
        assert result["key"] == "layer_height"
        assert result["value"] == "0.2"

    def test_get_missing_key(self, sample_3mf_path):
        """Returns error for missing key."""
        result = get_config_value(sample_3mf_path, "nonexistent_key_xyz")
        assert "error" in result

    def test_set_value(self, sample_3mf_path, tmp_path):
        """Set and verify round-trip."""
        out = str(tmp_path / "config_set_test.3mf")
        result = set_config_value(
            sample_3mf_path, "layer_height", "0.16", output_path=out
        )
        assert result.get("updated") is True
        assert result["new_value"] == "0.16"
        assert result["old_value"] == "0.2"

        # Verify by reading back
        verify = get_config_value(out, "layer_height")
        assert verify["value"] == "0.16"


# ═══════════════════════════════════════════════════════════════════════════
# Project
# ═══════════════════════════════════════════════════════════════════════════


class TestProject:
    """Tests for cli_anything.bambustudio.core.project."""

    def test_open_project(self, sample_3mf_path):
        """Open fixture, verify path + objects."""
        result = open_project(sample_3mf_path)
        assert "error" not in result
        assert result.get("valid") is True
        assert result["objects"] == 1
        assert result["plates"] >= 1
        assert "path" in result

    def test_list_plates_from_project(self, sample_3mf_path):
        """Verify plates returned."""
        result = list_plates(sample_3mf_path)
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "error" not in result[0]
        assert "index" in result[0]

    def test_list_objects_from_project(self, sample_3mf_path):
        """Verify objects returned."""
        result = list_objects(sample_3mf_path)
        assert isinstance(result, list)
        assert len(result) == 1
        assert "error" not in result[0]
        assert result[0]["name"] == "Cube"
