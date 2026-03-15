"""Tests for project discovery (filesystem scan for 3MF/STL files)."""

import os
import time

import pytest

from cli_anything.bambustudio.core.discovery import discover_projects, _format_ago


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def scan_dir(tmp_path):
    """Create a temp directory with test 3D files."""
    # Recent 3MF file
    f1 = tmp_path / "skull.3mf"
    f1.write_bytes(b"\x00" * 1024)

    # Recent STL file
    f2 = tmp_path / "vase_v2.stl"
    f2.write_bytes(b"\x00" * 2048)

    # Non-3D file (should be ignored)
    f3 = tmp_path / "readme.txt"
    f3.write_text("not a 3d file")

    # Hidden file (should be ignored)
    f4 = tmp_path / ".hidden.3mf"
    f4.write_bytes(b"\x00" * 512)

    # Old file (40 days ago)
    f5 = tmp_path / "old_model.stl"
    f5.write_bytes(b"\x00" * 512)
    old_time = time.time() - (40 * 86400)
    os.utime(f5, (old_time, old_time))

    # OBJ file
    f6 = tmp_path / "character.obj"
    f6.write_bytes(b"\x00" * 4096)

    return tmp_path


# ── Basic scan ────────────────────────────────────────────────────────


class TestDiscoverProjects:
    def test_finds_3d_files(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)])
        names = [p["name"] for p in result["projects"]]
        assert "skull" in names
        assert "vase_v2" in names
        assert "character" in names

    def test_ignores_non_3d_files(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)])
        names = [p["name"] for p in result["projects"]]
        assert "readme" not in names

    def test_ignores_hidden_files(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)])
        names = [p["name"] for p in result["projects"]]
        assert ".hidden" not in names

    def test_ignores_old_files(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)], max_age_days=30)
        names = [p["name"] for p in result["projects"]]
        assert "old_model" not in names

    def test_includes_old_files_with_high_max_age(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)], max_age_days=60)
        names = [p["name"] for p in result["projects"]]
        assert "old_model" in names


# ── Query filtering ───────────────────────────────────────────────────


class TestQueryFiltering:
    def test_query_match(self, scan_dir):
        result = discover_projects(query="skull", scan_dirs=[str(scan_dir)])
        assert len(result["projects"]) == 1
        assert result["projects"][0]["name"] == "skull"

    def test_query_case_insensitive(self, scan_dir):
        result = discover_projects(query="SKULL", scan_dirs=[str(scan_dir)])
        assert len(result["projects"]) == 1

    def test_query_no_match(self, scan_dir):
        result = discover_projects(query="nonexistent", scan_dirs=[str(scan_dir)])
        assert result["projects"] == []
        assert result["total_found"] == 0

    def test_query_partial_match(self, scan_dir):
        result = discover_projects(query="vase", scan_dirs=[str(scan_dir)])
        assert len(result["projects"]) == 1
        assert result["projects"][0]["name"] == "vase_v2"


# ── Limit and sorting ────────────────────────────────────────────────


class TestLimitAndSorting:
    def test_limit(self, scan_dir):
        result = discover_projects(limit=1, scan_dirs=[str(scan_dir)])
        assert len(result["projects"]) == 1
        assert result["total_found"] == 3  # 3 valid files total

    def test_sorted_by_mtime_newest_first(self, scan_dir):
        # Touch skull to make it newest
        skull = scan_dir / "skull.3mf"
        os.utime(skull, None)  # update to now
        time.sleep(0.01)

        result = discover_projects(scan_dirs=[str(scan_dir)])
        assert result["projects"][0]["name"] == "skull"


# ── Result format ─────────────────────────────────────────────────────


class TestResultFormat:
    def test_project_fields(self, scan_dir):
        result = discover_projects(query="skull", scan_dirs=[str(scan_dir)])
        proj = result["projects"][0]
        assert "path" in proj
        assert "name" in proj
        assert "type" in proj
        assert "size_mb" in proj
        assert "modified" in proj
        assert "modified_ago" in proj
        assert "directory" in proj

    def test_type_field(self, scan_dir):
        result = discover_projects(query="skull", scan_dirs=[str(scan_dir)])
        assert result["projects"][0]["type"] == "3mf"

        result2 = discover_projects(query="vase", scan_dirs=[str(scan_dir)])
        assert result2["projects"][0]["type"] == "stl"

    def test_directories_scanned(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)])
        assert str(scan_dir) in result["directories_scanned"]

    def test_total_found(self, scan_dir):
        result = discover_projects(scan_dirs=[str(scan_dir)])
        assert result["total_found"] == 3


# ── Edge cases ────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nonexistent_directory(self):
        result = discover_projects(scan_dirs=["/nonexistent/path"])
        assert result["projects"] == []
        assert result["total_found"] == 0
        assert result["directories_scanned"] == []

    def test_empty_directory(self, tmp_path):
        result = discover_projects(scan_dirs=[str(tmp_path)])
        assert result["projects"] == []
        assert result["total_found"] == 0

    def test_multiple_directories(self, tmp_path):
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "a.3mf").write_bytes(b"\x00")

        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "b.stl").write_bytes(b"\x00")

        result = discover_projects(scan_dirs=[str(dir1), str(dir2)])
        assert result["total_found"] == 2


# ── Format ago helper ─────────────────────────────────────────────────


class TestFormatAgo:
    def test_just_now(self):
        assert _format_ago(30) == "just now"

    def test_minutes(self):
        assert _format_ago(120) == "2 minutes ago"

    def test_one_minute(self):
        assert _format_ago(60) == "1 minute ago"

    def test_hours(self):
        assert _format_ago(7200) == "2 hours ago"

    def test_one_hour(self):
        assert _format_ago(3600) == "1 hour ago"

    def test_days(self):
        assert _format_ago(172800) == "2 days ago"

    def test_one_day(self):
        assert _format_ago(86400) == "1 day ago"
