"""Tests for cli.py — argument parsing and end-to-end orchestration."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from tsujikiri.cli import build_parser, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(*args: str, expected_exit: int | None = None) -> tuple[str, str]:
    """Run main() with given CLI args, capture stdout/stderr."""
    stdout, stderr = StringIO(), StringIO()
    with patch("sys.argv", ["tsujikiri", *args]):
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            try:
                main()
            except SystemExit as e:
                if expected_exit is not None and e.code != expected_exit:
                    raise
    return stdout.getvalue(), stderr.getvalue()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_returns_parser(self):
        p = build_parser()
        assert p is not None

    def test_list_formats_flag(self):
        p = build_parser()
        args = p.parse_args(["--list-formats"])
        assert args.list_formats is True

    def test_input_and_output(self):
        p = build_parser()
        args = p.parse_args(["--input", "foo.yml", "--output", "luabridge3"])
        assert args.input == "foo.yml"
        assert args.output == "luabridge3"

    def test_short_flags(self):
        p = build_parser()
        args = p.parse_args(["-i", "foo.yml", "-o", "pybind11"])
        assert args.input == "foo.yml"
        assert args.output == "pybind11"

    def test_classname_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--output", "pybind11", "--classname", "Foo"])
        assert args.classname == "Foo"

    def test_dry_run_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--output", "pybind11", "--dry-run"])
        assert args.dry_run is True


# ---------------------------------------------------------------------------
# --list-formats
# ---------------------------------------------------------------------------

class TestListFormats:
    def test_prints_builtin_formats(self):
        stdout, _ = _run("--list-formats")
        assert "luabridge3" in stdout
        assert "pybind11" in stdout
        assert "c_api" in stdout

    def test_each_format_on_own_line(self):
        stdout, _ = _run("--list-formats")
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        assert len(lines) >= 3


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_prints_summary(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "pybind11",
            "--dry-run",
        )
        assert "Classes" in stdout

    def test_dry_run_no_binding_code(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "pybind11",
            "--dry-run",
        )
        assert "py::class_" not in stdout
        assert "PYBIND11_MODULE" not in stdout


# ---------------------------------------------------------------------------
# Normal generation
# ---------------------------------------------------------------------------

class TestGeneration:
    def test_pybind11_output_to_stdout(self, simple_input_yml):
        stdout, _ = _run("--input", str(simple_input_yml), "--output", "pybind11")
        assert "PYBIND11_MODULE" in stdout
        assert "Widget" in stdout

    def test_luabridge3_output_to_stdout(self, simple_input_yml):
        stdout, _ = _run("--input", str(simple_input_yml), "--output", "luabridge3")
        assert "getGlobalNamespace" in stdout
        assert "Widget" in stdout

    def test_c_api_output_to_stdout(self, simple_input_yml):
        stdout, _ = _run("--input", str(simple_input_yml), "--output", "c_api")
        assert "Widget_t" in stdout

    def test_output_file(self, simple_input_yml, tmp_path):
        out_file = tmp_path / "bindings.cpp"
        _run(
            "--input", str(simple_input_yml),
            "--output", "pybind11",
            "--output-file", str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text()
        assert "PYBIND11_MODULE" in content

    def test_classname_filter(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "pybind11",
            "--classname", "Widget",
        )
        assert "Widget" in stdout

    def test_custom_output_format_by_path(self, simple_input_yml, tmp_path):
        fmt = tmp_path / "noop.output.yml"
        fmt.write_text(
            "format_name: noop\n"
            "templates:\n"
            "  prologue: 'NOOP_START\\n'\n"
            "  epilogue: 'NOOP_END\\n'\n"
        )
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", str(fmt),
        )
        assert "NOOP_START" in stdout
        assert "NOOP_END" in stdout


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_input_flag(self):
        _run("--output", "pybind11", expected_exit=2)

    def test_missing_output_flag(self):
        _run("--input", "foo.yml", expected_exit=2)

    def test_nonexistent_input_file(self, tmp_path):
        _, stderr = _run(
            "--input", str(tmp_path / "nope.yml"),
            "--output", "pybind11",
        )
        assert "not found" in stderr.lower() or "error" in stderr.lower()

    def test_unknown_format_raises(self, simple_input_yml):
        with pytest.raises((FileNotFoundError, SystemExit)):
            _run("--input", str(simple_input_yml), "--output", "definitely_fake_xyz")
