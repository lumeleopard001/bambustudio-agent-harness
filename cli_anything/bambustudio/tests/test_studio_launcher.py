"""Tests for BambuStudio GUI launcher (open_in_bambustudio)."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from cli_anything.bambustudio.utils.bambustudio_backend import open_in_bambustudio


# ── Mock tests (always run) ──────────────────────────────────────────────

_DEVNULL = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}


class TestOpenInBambustudio:
    """Unit tests for open_in_bambustudio — no real BambuStudio needed."""

    def test_file_not_found(self):
        result = open_in_bambustudio("/nonexistent/path/model.3mf")
        assert not result["opened"]
        assert "not found" in result["error"].lower()

    def test_unsupported_platform(self, monkeypatch, tmp_path):
        dummy = tmp_path / "test.3mf"
        dummy.touch()
        monkeypatch.setattr(sys, "platform", "win32")
        result = open_in_bambustudio(str(dummy))
        assert not result["opened"]
        assert "win32" in result["error"]

    @patch("subprocess.Popen")
    def test_macos_calls_open(self, mock_popen, monkeypatch, tmp_path):
        dummy = tmp_path / "project.3mf"
        dummy.touch()
        monkeypatch.setattr(sys, "platform", "darwin")
        result = open_in_bambustudio(str(dummy))
        assert result["opened"]
        assert result["method"] == "macOS open"
        mock_popen.assert_called_once_with(
            ["open", "-a", "BambuStudio", str(dummy)], **_DEVNULL,
        )

    @patch("subprocess.Popen")
    def test_linux_calls_bambustudio(self, mock_popen, monkeypatch, tmp_path):
        dummy = tmp_path / "project.3mf"
        dummy.touch()
        monkeypatch.setattr(sys, "platform", "linux")
        result = open_in_bambustudio(str(dummy))
        assert result["opened"]
        assert result["method"] == "linux"
        mock_popen.assert_called_once_with(
            ["bambu-studio", str(dummy)], **_DEVNULL,
        )

    @patch("subprocess.Popen", side_effect=FileNotFoundError("bambu-studio not found"))
    def test_popen_oserror_returns_error_dict(self, mock_popen, monkeypatch, tmp_path):
        dummy = tmp_path / "project.3mf"
        dummy.touch()
        monkeypatch.setattr(sys, "platform", "linux")
        result = open_in_bambustudio(str(dummy))
        assert not result["opened"]
        assert "Failed to launch" in result["error"]


# ── Real tests (skip unless BambuStudio installed) ───────────────────────


@pytest.mark.studio
class TestOpenInBambustudioReal:
    """Integration tests that actually launch BambuStudio.

    Run with: pytest -m studio
    Requires BambuStudio to be installed.
    """

    def test_opens_3mf(self, minimal_3mf):
        result = open_in_bambustudio(str(minimal_3mf))
        assert result["opened"]
        assert result["path"] == str(minimal_3mf)
