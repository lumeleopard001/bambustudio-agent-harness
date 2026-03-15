"""Filament spool inventory and usage tracking.

Manages a persistent registry of filament spools with state tracking
(loaded/stored/empty) and an append-only usage log for per-print accounting.

Data files:
  ~/.bambustudio-harness/spools.json   - spool registry (atomic writes)
  ~/.bambustudio-harness/usage.jsonl   - usage log (append-only)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default spool weights by material (grams)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "PLA": 1000.0,
    "PETG": 1000.0,
    "ABS": 1000.0,
    "ASA": 1000.0,
    "HIPS": 1000.0,
    "PVA": 1000.0,
    "PA": 1000.0,
    "PC": 1000.0,
    "PET": 1000.0,
    "TPU": 500.0,
}

# Valid slot identifiers for Bambu Lab A1 Combo (AMS Lite 4 + 1 external)
VALID_SLOTS = {"AMS:1", "AMS:2", "AMS:3", "AMS:4", "EXT:1"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_weight(material: str) -> float:
    return _DEFAULT_WEIGHTS.get(material.upper(), 1000.0)


class SpoolRegistry:
    """Persistent filament spool registry with atomic writes."""

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.path.join(Path.home(), ".bambustudio-harness")
        self._data_dir = data_dir
        os.makedirs(self._data_dir, exist_ok=True)

    @property
    def spools_path(self) -> str:
        return os.path.join(self._data_dir, "spools.json")

    @property
    def usage_path(self) -> str:
        return os.path.join(self._data_dir, "usage.jsonl")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        """Load spool registry from disk."""
        if not os.path.isfile(self.spools_path):
            return []
        try:
            with open(self.spools_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, OSError):
            # Corrupt file — return empty, caller can re-save
            return []

    def _save(self, spools: list[dict[str, Any]]) -> None:
        """Atomic write: write to tempfile then rename."""
        fd, tmp_path = tempfile.mkstemp(
            dir=self._data_dir, suffix=".tmp", prefix="spools_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(spools, fh, indent=2, default=str)
            os.replace(tmp_path, self.spools_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _find_spool(
        self, spools: list[dict[str, Any]], spool_id: int
    ) -> dict[str, Any] | None:
        for s in spools:
            if s.get("id") == spool_id:
                return s
        return None

    def _find_by_slot(
        self, spools: list[dict[str, Any]], slot: str
    ) -> dict[str, Any] | None:
        for s in spools:
            if s.get("slot") == slot and s.get("state") == "loaded":
                return s
        return None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def add(
        self,
        spool_id: int,
        brand: str,
        material: str,
        variant: str = "",
        color: str = "",
        weight: float | None = None,
        slot: str | None = None,
    ) -> dict[str, Any]:
        """Register a new spool.

        Returns the created spool dict. If --slot is given, the spool
        starts in 'loaded' state; otherwise 'stored'.
        """
        spools = self._load()

        # Check for duplicate ID
        if self._find_spool(spools, spool_id) is not None:
            raise ValueError(f"Spool #{spool_id} already exists")

        if slot is not None:
            slot = slot.upper()
            if slot not in VALID_SLOTS:
                raise ValueError(
                    f"Invalid slot '{slot}'. Valid: {sorted(VALID_SLOTS)}"
                )
            # Auto-unload occupant
            occupant = self._find_by_slot(spools, slot)
            if occupant is not None:
                occupant["state"] = "stored"
                occupant["slot"] = None
                occupant["updated"] = _now_iso()

        start_g = weight if weight is not None else _default_weight(material)

        spool: dict[str, Any] = {
            "id": spool_id,
            "brand": brand,
            "material": material.upper(),
            "variant": variant,
            "color": color,
            "start_g": start_g,
            "remain_g": start_g,
            "state": "loaded" if slot else "stored",
            "slot": slot,
            "created": _now_iso(),
            "updated": _now_iso(),
        }

        spools.append(spool)
        self._save(spools)
        return spool

    def load_spool(self, spool_id: int, slot: str) -> dict[str, Any]:
        """Load a spool into a slot. Auto-unloads any occupant."""
        slot = slot.upper()
        if slot not in VALID_SLOTS:
            raise ValueError(
                f"Invalid slot '{slot}'. Valid: {sorted(VALID_SLOTS)}"
            )

        spools = self._load()
        spool = self._find_spool(spools, spool_id)
        if spool is None:
            raise ValueError(f"Spool #{spool_id} not found")

        if spool["state"] == "empty":
            raise ValueError(f"Spool #{spool_id} is empty and cannot be loaded")

        # Auto-unload occupant
        occupant = self._find_by_slot(spools, slot)
        unloaded = None
        if occupant is not None and occupant["id"] != spool_id:
            occupant["state"] = "stored"
            occupant["slot"] = None
            occupant["updated"] = _now_iso()
            unloaded = occupant["id"]

        spool["state"] = "loaded"
        spool["slot"] = slot
        spool["updated"] = _now_iso()

        self._save(spools)

        result: dict[str, Any] = {"spool": spool}
        if unloaded is not None:
            result["unloaded_spool_id"] = unloaded
            result["warning"] = f"Spool #{unloaded} was auto-unloaded from {slot}"
        return result

    def unload(self, slot: str) -> dict[str, Any]:
        """Unload a spool from a slot (state -> stored)."""
        slot = slot.upper()
        if slot not in VALID_SLOTS:
            raise ValueError(
                f"Invalid slot '{slot}'. Valid: {sorted(VALID_SLOTS)}"
            )

        spools = self._load()
        spool = self._find_by_slot(spools, slot)
        if spool is None:
            raise ValueError(f"No spool loaded in slot {slot}")

        spool["state"] = "stored"
        spool["slot"] = None
        spool["updated"] = _now_iso()

        self._save(spools)
        return spool

    def status(self) -> dict[str, Any]:
        """Return full inventory status with slot map."""
        spools = self._load()

        slots: dict[str, Any] = {}
        for slot_name in sorted(VALID_SLOTS):
            occupant = self._find_by_slot(spools, slot_name)
            if occupant:
                slots[slot_name] = {
                    "spool_id": occupant["id"],
                    "material": occupant["material"],
                    "color": occupant["color"],
                    "remain_g": occupant["remain_g"],
                    "remain_pct": round(
                        occupant["remain_g"] / occupant["start_g"] * 100, 1
                    )
                    if occupant["start_g"] > 0
                    else 0,
                }
            else:
                slots[slot_name] = None

        return {
            "slots": slots,
            "spools": spools,
            "total_spools": len(spools),
            "loaded": sum(1 for s in spools if s["state"] == "loaded"),
            "stored": sum(1 for s in spools if s["state"] == "stored"),
            "empty": sum(1 for s in spools if s["state"] == "empty"),
        }

    def list_spools(self, state: str | None = None) -> list[dict[str, Any]]:
        """List spools, optionally filtered by state."""
        spools = self._load()
        if state is not None:
            state = state.lower()
            spools = [s for s in spools if s.get("state") == state]
        return spools

    def get(self, spool_id: int) -> dict[str, Any] | None:
        """Get a single spool by ID."""
        spools = self._load()
        return self._find_spool(spools, spool_id)

    def remove(self, spool_id: int) -> dict[str, Any]:
        """Remove a spool from the registry."""
        spools = self._load()
        spool = self._find_spool(spools, spool_id)
        if spool is None:
            raise ValueError(f"Spool #{spool_id} not found")

        spools = [s for s in spools if s["id"] != spool_id]
        self._save(spools)
        return spool

    def deduct_usage(
        self,
        spool_id: int,
        total_g: float,
        print_g: float | None = None,
        purge_g: float | None = None,
        project: str = "",
    ) -> dict[str, Any]:
        """Deduct filament usage from a spool and log it.

        Args:
            spool_id: Spool to deduct from.
            total_g: Total filament used (print + purge).
            print_g: Print-only filament (optional, derived from total - purge).
            purge_g: Purge/waste filament (optional, derived from total - print).
            project: Project/file name for the log.

        Returns:
            Dict with updated spool and usage entry.
        """
        spools = self._load()
        spool = self._find_spool(spools, spool_id)
        if spool is None:
            raise ValueError(f"Spool #{spool_id} not found")

        # Calculate print/purge split
        if print_g is None and purge_g is not None:
            print_g = total_g - purge_g
        elif purge_g is None and print_g is not None:
            purge_g = total_g - print_g
        elif print_g is None and purge_g is None:
            print_g = total_g
            purge_g = 0.0

        # Deduct
        old_remain = spool["remain_g"]
        new_remain = max(0.0, old_remain - total_g)
        spool["remain_g"] = round(new_remain, 1)
        spool["updated"] = _now_iso()

        # Transition to empty if exhausted
        warnings: list[str] = []
        if new_remain <= 0:
            spool["state"] = "empty"
            spool["slot"] = None
            warnings.append(f"Spool #{spool_id} is now empty")
        elif new_remain < 50:
            warnings.append(
                f"Spool #{spool_id} is running low: {new_remain:.1f}g remaining"
            )

        self._save(spools)

        # Log usage
        entry = {
            "ts": _now_iso(),
            "spool_id": spool_id,
            "print_g": round(print_g, 1),
            "purge_g": round(purge_g, 1),
            "total_g": round(total_g, 1),
            "project": project,
        }
        self._append_usage(entry)

        result: dict[str, Any] = {
            "spool": spool,
            "usage": entry,
            "previous_remain_g": round(old_remain, 1),
        }
        if warnings:
            result["warnings"] = warnings
        return result

    def _append_usage(self, entry: dict[str, Any]) -> None:
        """Append a usage entry to the JSONL log."""
        with open(self.usage_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def history(self, spool_id: int | None = None) -> list[dict[str, Any]]:
        """Read usage history, optionally filtered by spool ID."""
        if not os.path.isfile(self.usage_path):
            return []
        entries: list[dict[str, Any]] = []
        with open(self.usage_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if spool_id is None or entry.get("spool_id") == spool_id:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries

    def track_workflow_usage(
        self,
        result_data: dict[str, Any],
        project_name: str = "",
    ) -> list[dict[str, Any]]:
        """Track filament usage from a workflow result.

        Reads filament usage from result.json data (sliced_plates.filaments)
        and deducts from loaded spools by slot index.

        Args:
            result_data: The 'result' dict from workflow_auto (parsed result.json).
            project_name: Name of the project/STL file.

        Returns:
            List of deduction results (one per filament used).
        """
        plates = result_data.get("sliced_plates", [])
        if not plates:
            return []

        # Build slot-position lookup: filament ID → physical slot name
        _SLOT_BY_INDEX = {0: "AMS:1", 1: "AMS:2", 2: "AMS:3", 3: "AMS:4", 4: "EXT:1"}

        spools = self._load()
        spool_by_slot: dict[str, dict[str, Any]] = {
            s["slot"]: s
            for s in spools
            if s["state"] == "loaded" and s.get("slot")
        }

        deductions: list[dict[str, Any]] = []
        for plate in plates:
            filaments = plate.get("filaments", [])
            for fil in filaments:
                fil_idx = fil.get("id", 0)
                total_g = fil.get("total_used_g", 0)
                main_g = fil.get("main_used_g", 0)
                purge_g = total_g - main_g if main_g > 0 else 0

                if total_g <= 0:
                    continue

                # Map filament index to physical slot, then find spool
                slot_name = _SLOT_BY_INDEX.get(fil_idx)
                spool = spool_by_slot.get(slot_name) if slot_name else None

                if spool is not None:
                    try:
                        result = self.deduct_usage(
                            spool_id=spool["id"],
                            total_g=total_g,
                            print_g=main_g if main_g > 0 else None,
                            purge_g=purge_g if purge_g > 0 else None,
                            project=project_name,
                        )
                        deductions.append(result)
                    except ValueError as e:
                        deductions.append({"error": str(e), "filament_index": fil_idx})
                else:
                    deductions.append({
                        "warning": f"No loaded spool in slot {slot_name or f'index-{fil_idx}'}",
                        "total_g": total_g,
                        "filament_index": fil_idx,
                    })

        return deductions
