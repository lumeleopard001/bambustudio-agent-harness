"""Unified output formatting for CLI commands."""

import json
import time
from datetime import datetime, timezone
from typing import Any


class OutputFormatter:
    """Formats command output as JSON or human-readable text."""

    def __init__(self, json_mode: bool = False):
        self.json_mode = json_mode
        self._start_time: float | None = None

    def start_timer(self):
        self._start_time = time.monotonic()

    def _elapsed_ms(self) -> int:
        if self._start_time is None:
            return 0
        return int((time.monotonic() - self._start_time) * 1000)

    def success(self, data: Any, command: str = "") -> str:
        if self.json_mode:
            return json.dumps({
                "ok": True,
                "command": command,
                "data": data,
                "error": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_ms": self._elapsed_ms(),
            }, indent=2, default=str)
        return _format_human(data)

    def error(self, message: str, command: str = "", data: Any = None) -> str:
        if self.json_mode:
            return json.dumps({
                "ok": False,
                "command": command,
                "data": data,
                "error": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_ms": self._elapsed_ms(),
            }, indent=2, default=str)
        return f"Error: {message}"


def _format_human(data: Any) -> str:
    """Format data for human consumption."""
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    if isinstance(item, dict):
                        parts = [f"{k}={v}" for k, v in item.items()]
                        lines.append(f"  - {', '.join(parts)}")
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return str(data)
