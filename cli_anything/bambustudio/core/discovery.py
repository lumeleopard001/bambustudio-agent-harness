"""Discover 3MF/STL files on the local filesystem.

Scans common directories (Downloads, Desktop, Documents) for recent
3D print files. Designed for agent use: when a user mentions a file
without giving a full path, this module finds it.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


_3D_EXTENSIONS = {".3mf", ".stl", ".step", ".stp", ".obj"}

DEFAULT_SCAN_DIRS = [
    "~/Downloads",
    "~/Desktop",
    "~/Documents",
]

# Skip scanning if a single directory takes longer than this
_DIR_SCAN_TIMEOUT_S = 2.0


def discover_projects(
    query: str = "",
    limit: int = 10,
    scan_dirs: list[str] | None = None,
    max_age_days: int = 30,
) -> dict[str, Any]:
    """Scan filesystem for recent 3MF and STL files.

    Args:
        query: Optional substring to filter filenames (case-insensitive).
        limit: Maximum number of results to return.
        scan_dirs: Directories to scan. Defaults to ~/Downloads, ~/Desktop, ~/Documents.
        max_age_days: Ignore files older than this many days.

    Returns:
        Dict with 'projects' list sorted by modification time (newest first),
        'total_found' count, and 'directories_scanned' list.
    """
    dirs = scan_dirs or DEFAULT_SCAN_DIRS
    cutoff = time.time() - (max_age_days * 86400)
    query_lower = query.lower()

    found: list[dict[str, Any]] = []
    scanned: list[str] = []

    for raw_dir in dirs:
        dir_path = Path(raw_dir).expanduser()
        if not dir_path.is_dir():
            continue

        scanned.append(str(dir_path))
        scan_start = time.monotonic()

        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    # Timeout guard
                    if time.monotonic() - scan_start > _DIR_SCAN_TIMEOUT_S:
                        break

                    if not entry.is_file(follow_symlinks=False):
                        continue

                    name = entry.name
                    if name.startswith("."):
                        continue

                    stem, ext = os.path.splitext(name)
                    if ext.lower() not in _3D_EXTENSIONS:
                        continue

                    try:
                        stat = entry.stat()
                    except OSError:
                        continue

                    if stat.st_mtime < cutoff:
                        continue

                    if query_lower and query_lower not in name.lower():
                        continue

                    found.append({
                        "path": entry.path,
                        "name": stem,
                        "type": ext.lstrip(".").lower(),
                        "size_mb": round(stat.st_size / (1024 * 1024), 1),
                        "modified": stat.st_mtime,
                        "directory": dir_path.name,
                    })
        except PermissionError:
            continue

    # Sort by modification time, newest first
    found.sort(key=lambda f: f["modified"], reverse=True)

    # Format timestamps
    now = time.time()
    for item in found:
        mtime = item["modified"]
        item["modified_ago"] = _format_ago(now - mtime)
        item["modified"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(mtime)
        )

    total = len(found)
    return {
        "projects": found[:limit],
        "total_found": total,
        "directories_scanned": scanned,
    }


def _format_ago(seconds: float) -> str:
    """Format seconds into a human-readable 'ago' string."""
    s = int(seconds)
    if s < 60:
        return "just now"
    if s < 3600:
        m = s // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if s < 86400:
        h = s // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = s // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"
