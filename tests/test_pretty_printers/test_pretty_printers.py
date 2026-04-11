"""Tests for pretty_printers.py — post-generation output pretty printing."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tsujikiri.pretty_printers import get_pretty_printer_command, pretty


class TestGetPrettyPrinterCommand:
    def test_cpp_maps_to_clang_format(self):
        assert get_pretty_printer_command("cpp") == "clang-format"

    def test_unknown_language_returns_none(self):
        assert get_pretty_printer_command("brainfuck") is None

    def test_empty_language_returns_none(self):
        assert get_pretty_printer_command("") is None

    def test_lua_not_registered(self):
        assert get_pretty_printer_command("lua") is None


class TestPretty:
    def test_unknown_language_returns_content_unchanged(self):
        content = "some content"
        assert pretty(content, "lua") == content

    def test_empty_language_returns_content_unchanged(self):
        content = "something"
        assert pretty(content, "") == content

    def test_cpp_calls_clang_format(self):
        fake_result = MagicMock()
        fake_result.stdout = "formatted"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            result = pretty("int x=1;", "cpp")
        mock_run.assert_called_once_with(
            ["clang-format", "-"],
            input="int x=1;",
            capture_output=True,
            text=True,
            check=True,
        )
        assert result == "formatted"

    def test_cpp_with_extra_args(self):
        fake_result = MagicMock()
        fake_result.stdout = "formatted"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            pretty("int x=1;", "cpp", extra_args=["--style=Google"])
        call_args = mock_run.call_args[0][0]
        assert call_args == ["clang-format", "--style=Google", "-"]

    def test_cpp_with_multiple_extra_args(self):
        fake_result = MagicMock()
        fake_result.stdout = "formatted"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            pretty("int x=1;", "cpp", extra_args=["--style=LLVM", "--sort-includes"])
        call_args = mock_run.call_args[0][0]
        assert call_args == ["clang-format", "--style=LLVM", "--sort-includes", "-"]

    def test_no_extra_args_uses_empty_list(self):
        fake_result = MagicMock()
        fake_result.stdout = "out"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            pretty("x", "cpp", extra_args=None)
        call_args = mock_run.call_args[0][0]
        assert "-" in call_args
        assert call_args == ["clang-format", "-"]

    def test_pretty_printer_failure_raises(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "clang-format")):
            with pytest.raises(subprocess.CalledProcessError):
                pretty("bad code", "cpp")

    def test_pretty_printer_not_found_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError):
                pretty("code", "cpp")

    def test_cpp_real_clang_format(self):
        """Integration test: verify clang-format actually runs and reformats C++."""
        unformatted = "int   x=1;int   y=2;"
        result = pretty(unformatted, "cpp")
        assert "int x = 1;" in result
        assert "int y = 2;" in result
