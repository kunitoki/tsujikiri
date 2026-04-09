"""Tests for __main__.py — module entry point."""

from __future__ import annotations

import runpy
from unittest.mock import patch


def test_main_as_module():
    with patch("tsujikiri.cli.main") as mock_main:
        runpy.run_module("tsujikiri", run_name="__main__")
    mock_main.assert_called_once()
