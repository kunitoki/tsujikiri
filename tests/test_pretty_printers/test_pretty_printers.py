"""Tests for pretty_printers.py — post-generation output pretty printing."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tsujikiri.pretty_printers import get_pretty_printer_command, pretty


class TestGetPrettyPrinterCommand:
    def test_cpp_maps_to_clang_format(self):
        assert get_pretty_printer_command("cpp") == ["clang-format"]

    def test_python_maps_to_ruff_format(self):
        assert get_pretty_printer_command("python") == ["ruff", "format"]

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

    def test_python_calls_ruff_format(self):
        fake_result = MagicMock()
        fake_result.stdout = "x = 1\n"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            result = pretty("x=1", "python")
        mock_run.assert_called_once_with(
            ["ruff", "format", "-"],
            input="x=1",
            capture_output=True,
            text=True,
            check=True,
        )
        assert result == "x = 1\n"

    def test_python_with_extra_args(self):
        fake_result = MagicMock()
        fake_result.stdout = "x = 1\n"
        with patch("subprocess.run", return_value=fake_result) as mock_run:
            pretty("x=1", "python", extra_args=["--line-length=79"])
        call_args = mock_run.call_args[0][0]
        assert call_args == ["ruff", "format", "--line-length=79", "-"]

    def test_python_real_ruff(self):
        """Integration test: verify ruff actually runs and reformats Python."""
        unformatted = "x=1\ny=2\nz  =  3"
        result = pretty(unformatted, "python")
        assert "x = 1" in result
        assert "y = 2" in result
        assert "z = 3" in result

    def test_python_real_ruff_pyi_stub(self):
        """Integration test: ruff formats a Python type stub (.pyi-style content)."""
        unformatted = (
            "from __future__ import annotations\n"
            "class   Foo :\n"
            "    def bar(self,x:int)->str:...\n"
            "    def baz(self)->None:...\n"
        )
        result = pretty(unformatted, "python")
        assert "class Foo:" in result
        assert "def bar(self, x: int) -> str: ..." in result
        assert "def baz(self) -> None: ..." in result
