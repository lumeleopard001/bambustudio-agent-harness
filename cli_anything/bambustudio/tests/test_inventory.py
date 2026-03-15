"""Tests for filament spool inventory and usage tracking."""

import json
import os

import pytest

from cli_anything.bambustudio.core.inventory import (
    SpoolRegistry,
    VALID_SLOTS,
    _default_weight,
)


@pytest.fixture
def registry(tmp_path):
    """SpoolRegistry with temp data dir."""
    return SpoolRegistry(data_dir=str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════════
# Default weights
# ═══════════════════════════════════════════════════════════════════════════


class TestDefaultWeights:
    def test_pla_1000g(self):
        assert _default_weight("PLA") == 1000.0

    def test_tpu_500g(self):
        assert _default_weight("TPU") == 500.0

    def test_unknown_defaults_1000g(self):
        assert _default_weight("MYSTERY") == 1000.0

    def test_case_insensitive(self):
        assert _default_weight("pla") == 1000.0
        assert _default_weight("tpu") == 500.0


# ═══════════════════════════════════════════════════════════════════════════
# Spool add
# ═══════════════════════════════════════════════════════════════════════════


class TestSpoolAdd:
    def test_add_basic(self, registry):
        spool = registry.add(
            spool_id=1, brand="Bambu", material="PLA",
            variant="Basic", color="white",
        )
        assert spool["id"] == 1
        assert spool["material"] == "PLA"
        assert spool["start_g"] == 1000.0
        assert spool["remain_g"] == 1000.0
        assert spool["state"] == "stored"
        assert spool["slot"] is None

    def test_add_with_slot(self, registry):
        spool = registry.add(
            spool_id=1, brand="Bambu", material="PLA",
            color="white", slot="AMS:1",
        )
        assert spool["state"] == "loaded"
        assert spool["slot"] == "AMS:1"

    def test_add_custom_weight(self, registry):
        spool = registry.add(
            spool_id=1, brand="Sunlu", material="PLA",
            color="black", weight=750.0,
        )
        assert spool["start_g"] == 750.0
        assert spool["remain_g"] == 750.0

    def test_add_tpu_default_500g(self, registry):
        spool = registry.add(
            spool_id=1, brand="Bambu", material="TPU", color="yellow",
        )
        assert spool["start_g"] == 500.0

    def test_add_duplicate_id_raises(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white")
        with pytest.raises(ValueError, match="already exists"):
            registry.add(spool_id=1, brand="Bambu", material="PLA", color="black")

    def test_add_invalid_slot_raises(self, registry):
        with pytest.raises(ValueError, match="Invalid slot"):
            registry.add(
                spool_id=1, brand="Bambu", material="PLA",
                color="white", slot="BAD:9",
            )

    def test_add_auto_unloads_occupant(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        spool2 = registry.add(spool_id=2, brand="Bambu", material="PLA", color="black", slot="AMS:1")

        assert spool2["slot"] == "AMS:1"
        assert spool2["state"] == "loaded"

        # Original spool should be stored
        original = registry.get(1)
        assert original["state"] == "stored"
        assert original["slot"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Spool load / unload
# ═══════════════════════════════════════════════════════════════════════════


class TestSpoolLoadUnload:
    def test_load_stored_spool(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white")
        result = registry.load_spool(1, "AMS:2")

        spool = result["spool"]
        assert spool["state"] == "loaded"
        assert spool["slot"] == "AMS:2"

    def test_load_auto_unloads_occupant(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        registry.add(spool_id=2, brand="Bambu", material="PLA", color="black")

        result = registry.load_spool(2, "AMS:1")
        assert result["spool"]["slot"] == "AMS:1"
        assert result["unloaded_spool_id"] == 1

        original = registry.get(1)
        assert original["state"] == "stored"

    def test_load_nonexistent_raises(self, registry):
        with pytest.raises(ValueError, match="not found"):
            registry.load_spool(99, "AMS:1")

    def test_load_empty_spool_raises(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", weight=1.0)
        registry.load_spool(1, "AMS:1")
        registry.deduct_usage(1, total_g=2.0)  # empties it
        with pytest.raises(ValueError, match="empty"):
            registry.load_spool(1, "AMS:2")

    def test_load_invalid_slot_raises(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white")
        with pytest.raises(ValueError, match="Invalid slot"):
            registry.load_spool(1, "NOPE:1")

    def test_unload(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:3")
        spool = registry.unload("AMS:3")

        assert spool["state"] == "stored"
        assert spool["slot"] is None

    def test_unload_empty_slot_raises(self, registry):
        with pytest.raises(ValueError, match="No spool loaded"):
            registry.unload("AMS:4")

    def test_reload_preserves_remain(self, registry):
        """Spool remembers its remaining weight across load/unload cycles."""
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        registry.deduct_usage(1, total_g=100.0)

        registry.unload("AMS:1")
        result = registry.load_spool(1, "AMS:3")

        assert result["spool"]["remain_g"] == 900.0
        assert result["spool"]["slot"] == "AMS:3"


# ═══════════════════════════════════════════════════════════════════════════
# Status and listing
# ═══════════════════════════════════════════════════════════════════════════


class TestStatusAndListing:
    def test_status_empty(self, registry):
        status = registry.status()
        assert status["total_spools"] == 0
        assert all(v is None for v in status["slots"].values())

    def test_status_with_spools(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        registry.add(spool_id=2, brand="Bambu", material="PETG", color="red")

        status = registry.status()
        assert status["total_spools"] == 2
        assert status["loaded"] == 1
        assert status["stored"] == 1
        assert status["slots"]["AMS:1"]["spool_id"] == 1
        assert status["slots"]["AMS:2"] is None

    def test_list_all(self, registry):
        registry.add(spool_id=1, brand="A", material="PLA", color="w")
        registry.add(spool_id=2, brand="B", material="PLA", color="b")
        assert len(registry.list_spools()) == 2

    def test_list_by_state(self, registry):
        registry.add(spool_id=1, brand="A", material="PLA", color="w", slot="AMS:1")
        registry.add(spool_id=2, brand="B", material="PLA", color="b")

        loaded = registry.list_spools(state="loaded")
        stored = registry.list_spools(state="stored")
        assert len(loaded) == 1
        assert len(stored) == 1
        assert loaded[0]["id"] == 1
        assert stored[0]["id"] == 2

    def test_get_existing(self, registry):
        registry.add(spool_id=42, brand="X", material="PLA", color="y")
        spool = registry.get(42)
        assert spool is not None
        assert spool["id"] == 42

    def test_get_nonexistent(self, registry):
        assert registry.get(999) is None


# ═══════════════════════════════════════════════════════════════════════════
# Remove
# ═══════════════════════════════════════════════════════════════════════════


class TestSpoolRemove:
    def test_remove_existing(self, registry):
        registry.add(spool_id=1, brand="A", material="PLA", color="w")
        removed = registry.remove(1)
        assert removed["id"] == 1
        assert registry.get(1) is None

    def test_remove_nonexistent_raises(self, registry):
        with pytest.raises(ValueError, match="not found"):
            registry.remove(99)


# ═══════════════════════════════════════════════════════════════════════════
# Usage deduction
# ═══════════════════════════════════════════════════════════════════════════


class TestUsageDeduction:
    def test_deduct_basic(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        result = registry.deduct_usage(1, total_g=5.2, print_g=4.8, purge_g=0.4, project="cube.3mf")

        assert result["spool"]["remain_g"] == 994.8
        assert result["usage"]["total_g"] == 5.2
        assert result["usage"]["print_g"] == 4.8
        assert result["usage"]["purge_g"] == 0.4
        assert result["previous_remain_g"] == 1000.0

    def test_deduct_clamps_to_zero(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", weight=10.0, slot="AMS:1")
        result = registry.deduct_usage(1, total_g=15.0)

        assert result["spool"]["remain_g"] == 0.0
        assert result["spool"]["state"] == "empty"
        assert "empty" in result["warnings"][0].lower()
        # Log shows actual deducted (10g), not requested (15g)
        assert result["usage"]["total_g"] == 10.0
        assert result["usage"]["requested_g"] == 15.0

    def test_deduct_low_warning(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", weight=100.0, slot="AMS:1")
        result = registry.deduct_usage(1, total_g=60.0)

        assert result["spool"]["remain_g"] == 40.0
        assert any("running low" in w for w in result.get("warnings", []))

    def test_deduct_derives_purge(self, registry):
        registry.add(spool_id=1, brand="X", material="PLA", color="w", slot="AMS:1")
        result = registry.deduct_usage(1, total_g=5.0, print_g=4.5)
        assert result["usage"]["purge_g"] == 0.5

    def test_deduct_nonexistent_raises(self, registry):
        with pytest.raises(ValueError, match="not found"):
            registry.deduct_usage(99, total_g=1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Usage history
# ═══════════════════════════════════════════════════════════════════════════


class TestUsageHistory:
    def test_empty_history(self, registry):
        assert registry.history() == []

    def test_history_after_deduction(self, registry):
        registry.add(spool_id=1, brand="A", material="PLA", color="w", slot="AMS:1")
        registry.deduct_usage(1, total_g=5.0, project="test.3mf")
        registry.deduct_usage(1, total_g=3.0, project="other.3mf")

        all_history = registry.history()
        assert len(all_history) == 2
        assert all_history[0]["project"] == "test.3mf"
        assert all_history[1]["project"] == "other.3mf"

    def test_history_filter_by_spool(self, registry):
        registry.add(spool_id=1, brand="A", material="PLA", color="w", slot="AMS:1")
        registry.add(spool_id=2, brand="B", material="PLA", color="b", slot="AMS:2")
        registry.deduct_usage(1, total_g=5.0)
        registry.deduct_usage(2, total_g=3.0)
        registry.deduct_usage(1, total_g=2.0)

        spool1_history = registry.history(spool_id=1)
        assert len(spool1_history) == 2

        spool2_history = registry.history(spool_id=2)
        assert len(spool2_history) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Workflow usage tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkflowTracking:
    def test_track_single_filament(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")

        result_data = {
            "sliced_plates": [{
                "id": 1,
                "filaments": [{
                    "id": 0,
                    "total_used_g": 5.2,
                    "main_used_g": 4.8,
                }],
            }],
        }

        deductions = registry.track_workflow_usage(result_data, "cube.3mf")
        assert len(deductions) == 1
        assert deductions[0]["spool"]["remain_g"] == 994.8

    def test_track_multi_filament(self, registry):
        registry.add(spool_id=1, brand="Bambu", material="PLA", color="white", slot="AMS:1")
        registry.add(spool_id=2, brand="Bambu", material="PLA", color="black", slot="AMS:2")

        result_data = {
            "sliced_plates": [{
                "id": 1,
                "filaments": [
                    {"id": 0, "total_used_g": 10.0, "main_used_g": 9.0},
                    {"id": 1, "total_used_g": 3.0, "main_used_g": 2.5},
                ],
            }],
        }

        deductions = registry.track_workflow_usage(result_data, "dual.3mf")
        assert len(deductions) == 2
        assert registry.get(1)["remain_g"] == 990.0
        assert registry.get(2)["remain_g"] == 997.0

    def test_track_with_slot_gap(self, registry):
        """Filament ID maps to physical slot, not loaded-list index.

        If AMS:1 and AMS:3 are loaded but AMS:2 is empty, filament id=2
        (AMS:3) must deduct from the spool in AMS:3, not from the second
        spool in the loaded list.
        """
        registry.add(spool_id=1, brand="A", material="PLA", color="white", slot="AMS:1")
        # AMS:2 is empty — gap
        registry.add(spool_id=3, brand="B", material="PLA", color="red", slot="AMS:3")

        result_data = {
            "sliced_plates": [{
                "id": 1,
                "filaments": [
                    {"id": 0, "total_used_g": 5.0, "main_used_g": 4.5},  # AMS:1
                    {"id": 2, "total_used_g": 3.0, "main_used_g": 2.5},  # AMS:3 (not AMS:2!)
                ],
            }],
        }

        deductions = registry.track_workflow_usage(result_data, "gap_test.3mf")
        assert len(deductions) == 2

        # Spool 1 (AMS:1) should lose 5g
        assert registry.get(1)["remain_g"] == 995.0
        # Spool 3 (AMS:3) should lose 3g — NOT spool 1
        assert registry.get(3)["remain_g"] == 997.0

    def test_track_no_loaded_spools(self, registry):
        result_data = {
            "sliced_plates": [{
                "id": 1,
                "filaments": [{"id": 0, "total_used_g": 5.0, "main_used_g": 4.5}],
            }],
        }

        deductions = registry.track_workflow_usage(result_data)
        assert len(deductions) == 1
        assert "warning" in deductions[0]

    def test_track_empty_result(self, registry):
        deductions = registry.track_workflow_usage({})
        assert deductions == []


# ═══════════════════════════════════════════════════════════════════════════
# Full lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestFullLifecycle:
    def test_add_load_use_unload_reload_use_empty(self, registry):
        """Full spool lifecycle: add → load → use → unload → reload → use → empty."""
        # Add spool to storage
        spool = registry.add(spool_id=1, brand="Bambu", material="PLA", color="white")
        assert spool["state"] == "stored"

        # Load into AMS:1
        result = registry.load_spool(1, "AMS:1")
        assert result["spool"]["state"] == "loaded"
        assert result["spool"]["remain_g"] == 1000.0

        # Print something
        registry.deduct_usage(1, total_g=200.0, project="part1.3mf")
        assert registry.get(1)["remain_g"] == 800.0

        # Unload (store away)
        spool = registry.unload("AMS:1")
        assert spool["state"] == "stored"
        assert spool["remain_g"] == 800.0  # remembers

        # Reload into different slot
        result = registry.load_spool(1, "AMS:3")
        assert result["spool"]["slot"] == "AMS:3"
        assert result["spool"]["remain_g"] == 800.0  # still remembers

        # Use until empty
        registry.deduct_usage(1, total_g=800.0, project="big_part.3mf")
        spool = registry.get(1)
        assert spool["state"] == "empty"
        assert spool["remain_g"] == 0.0

        # Cannot reload empty spool
        with pytest.raises(ValueError, match="empty"):
            registry.load_spool(1, "AMS:1")

        # History shows both prints
        history = registry.history(spool_id=1)
        assert len(history) == 2
        assert history[0]["project"] == "part1.3mf"
        assert history[1]["project"] == "big_part.3mf"


# ═══════════════════════════════════════════════════════════════════════════
# Persistence (file I/O)
# ═══════════════════════════════════════════════════════════════════════════


class TestPersistence:
    def test_data_survives_new_instance(self, tmp_path):
        """Data persists across SpoolRegistry instances."""
        reg1 = SpoolRegistry(data_dir=str(tmp_path))
        reg1.add(spool_id=1, brand="A", material="PLA", color="w", slot="AMS:1")
        reg1.deduct_usage(1, total_g=50.0, project="x.3mf")

        reg2 = SpoolRegistry(data_dir=str(tmp_path))
        spool = reg2.get(1)
        assert spool is not None
        assert spool["remain_g"] == 950.0

        history = reg2.history()
        assert len(history) == 1

    def test_corrupt_json_returns_empty(self, tmp_path):
        """Corrupt spools.json is handled gracefully."""
        path = tmp_path / "spools.json"
        path.write_text("NOT VALID JSON {{{")

        reg = SpoolRegistry(data_dir=str(tmp_path))
        assert reg.list_spools() == []

    def test_missing_file_returns_empty(self, tmp_path):
        """Missing spools.json returns empty list."""
        reg = SpoolRegistry(data_dir=str(tmp_path))
        assert reg.list_spools() == []

    def test_atomic_write(self, tmp_path):
        """Spools file is written atomically."""
        reg = SpoolRegistry(data_dir=str(tmp_path))
        reg.add(spool_id=1, brand="A", material="PLA", color="w")

        # File should be valid JSON
        with open(tmp_path / "spools.json", "r") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["id"] == 1

    def test_usage_log_is_jsonl(self, tmp_path):
        """Usage log is valid JSONL (one JSON object per line)."""
        reg = SpoolRegistry(data_dir=str(tmp_path))
        reg.add(spool_id=1, brand="A", material="PLA", color="w", slot="AMS:1")
        reg.deduct_usage(1, total_g=5.0, project="a.3mf")
        reg.deduct_usage(1, total_g=3.0, project="b.3mf")

        with open(tmp_path / "usage.jsonl", "r") as f:
            lines = [l.strip() for l in f if l.strip()]

        assert len(lines) == 2
        for line in lines:
            entry = json.loads(line)  # should not raise
            assert "spool_id" in entry
            assert "total_g" in entry
