"""Session state management with undo/redo support."""

import io
import time
import zipfile
from typing import Any

from cli_anything.bambustudio.utils.threemf import ThreeMF


class Session:
    """Manages project state with undo/redo support.

    State is tracked via 3MF byte snapshots. Each snapshot captures
    the entire ZIP contents, enabling full undo/redo.
    """

    def __init__(self, project_path: str | None = None):
        self.project_path: str | None = project_path
        self._threemf: ThreeMF | None = None
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []
        self._dirty: bool = False
        self._history: list[dict] = []
        self.max_undo: int = 10

        if project_path:
            self.load(project_path)

    def load(self, path: str) -> None:
        """Load a 3MF project into the session."""
        self._threemf = ThreeMF.load(path)
        self.project_path = path
        self._dirty = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._history.append({
            "operation": "load",
            "description": f"Loaded {path}",
            "timestamp": time.time(),
        })

    def save(self, path: str | None = None) -> None:
        """Save the current project state."""
        if self._threemf is None:
            raise RuntimeError("No project loaded")
        out = path or self.project_path
        if not out:
            raise RuntimeError("No output path specified")
        self._threemf.save(out)
        self._dirty = False
        self._history.append({
            "operation": "save",
            "description": f"Saved to {out}",
            "timestamp": time.time(),
        })

    def snapshot(self, description: str) -> None:
        """Take a snapshot of current state for undo."""
        if self._threemf is None:
            return
        # Serialize current 3MF to bytes
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for internal_path, data in self._threemf._files.items():
                zf.writestr(internal_path, data)
        snapshot_bytes = buf.getvalue()

        self._undo_stack.append(snapshot_bytes)
        if len(self._undo_stack) > self.max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._dirty = True
        self._history.append({
            "operation": "snapshot",
            "description": description,
            "timestamp": time.time(),
        })

    def undo(self) -> str | None:
        """Undo last modification. Returns description of undone operation."""
        if not self._undo_stack or self._threemf is None:
            return None

        # Save current state to redo stack
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for internal_path, data in self._threemf._files.items():
                zf.writestr(internal_path, data)
        self._redo_stack.append(buf.getvalue())

        # Restore from undo stack
        snapshot = self._undo_stack.pop()
        self._threemf = ThreeMF._from_bytes(snapshot)
        self._dirty = True

        desc = "Undo"
        self._history.append({
            "operation": "undo",
            "description": desc,
            "timestamp": time.time(),
        })
        return desc

    def redo(self) -> str | None:
        """Redo last undone modification."""
        if not self._redo_stack or self._threemf is None:
            return None

        # Save current state to undo stack
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for internal_path, data in self._threemf._files.items():
                zf.writestr(internal_path, data)
        self._undo_stack.append(buf.getvalue())

        # Restore from redo stack
        snapshot = self._redo_stack.pop()
        self._threemf = ThreeMF._from_bytes(snapshot)
        self._dirty = True

        desc = "Redo"
        self._history.append({
            "operation": "redo",
            "description": desc,
            "timestamp": time.time(),
        })
        return desc

    def status(self) -> dict:
        """Return current session status."""
        return {
            "project_path": self.project_path,
            "loaded": self._threemf is not None,
            "dirty": self._dirty,
            "undo_depth": len(self._undo_stack),
            "redo_depth": len(self._redo_stack),
            "max_undo": self.max_undo,
        }

    def history(self) -> list[dict]:
        """Return operation history."""
        return list(self._history)

    @property
    def threemf(self) -> ThreeMF | None:
        return self._threemf

    @property
    def dirty(self) -> bool:
        return self._dirty
