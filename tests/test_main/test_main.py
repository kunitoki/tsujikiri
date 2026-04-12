"""Tests for __main__.py — module entry point."""

from __future__ import annotations

import runpy
from unittest.mock import patch


def test_main_as_module():
    with patch("tsujikiri.cli.main") as mock_main:
        runpy.run_module("tsujikiri", run_name="__main__")
    mock_main.assert_called_once()


def test_main_not_run_when_not_main():
    """False branch of ``if __name__ == "__main__":`` — main() must not be called."""
    with patch("tsujikiri.cli.main") as mock_main:
        runpy.run_module("tsujikiri", run_name="tsujikiri")
    mock_main.assert_not_called()
