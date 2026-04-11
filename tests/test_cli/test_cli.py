"""Tests for cli.py — argument parsing and end-to-end orchestration."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

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
        args = p.parse_args(["-i", "foo.yml", "-o", "luabridge3"])
        assert args.input == "foo.yml"
        assert args.output == "luabridge3"

    def test_classname_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--output", "luabridge3", "--classname", "Foo"])
        assert args.classname == "Foo"

    def test_dry_run_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--output", "luabridge3", "--dry-run"])
        assert args.dry_run is True


# ---------------------------------------------------------------------------
# --list-formats
# ---------------------------------------------------------------------------

class TestListFormats:
    def test_prints_builtin_formats(self):
        stdout, _ = _run("--list-formats")
        assert "luabridge3" in stdout

    def test_each_format_on_own_line(self):
        stdout, _ = _run("--list-formats")
        lines = [l.strip() for l in stdout.splitlines() if l.strip()]
        assert len(lines) >= 1


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_prints_summary(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "luabridge3",
            "--dry-run",
        )
        assert "Classes" in stdout

    def test_dry_run_no_binding_code(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "luabridge3",
            "--dry-run",
        )
        assert "getGlobalNamespace" not in stdout
        assert "beginClass" not in stdout


# ---------------------------------------------------------------------------
# Normal generation
# ---------------------------------------------------------------------------

class TestGeneration:
    def test_luabridge3_output_to_stdout(self, simple_input_yml):
        stdout, _ = _run("--input", str(simple_input_yml), "--output", "luabridge3")
        assert "getGlobalNamespace" in stdout
        assert "Widget" in stdout

    def test_output_file(self, simple_input_yml, tmp_path):
        out_file = tmp_path / "bindings.cpp"
        _run(
            "--input", str(simple_input_yml),
            "--output", "luabridge3",
            "--output-file", str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "getGlobalNamespace" in content

    def test_classname_filter(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "luabridge3",
            "--classname", "Widget",
        )
        assert "Widget" in stdout

    def test_custom_output_format_by_path(self, simple_input_yml, tmp_path):
        fmt = tmp_path / "noop.output.yml"
        fmt.write_text(
            "format_name: noop\n"
            "template: |\n"
            "  NOOP_START\n"
            "  NOOP_END\n"
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
        _run("--output", "luabridge3", expected_exit=2)

    def test_missing_output_flag(self):
        _run("--input", "foo.yml", expected_exit=2)

    def test_nonexistent_input_file(self, tmp_path):
        _, stderr = _run(
            "--input", str(tmp_path / "nope.yml"),
            "--output", "luabridge3",
        )
        assert "not found" in stderr.lower() or "error" in stderr.lower()

    def test_unknown_format_raises(self, simple_input_yml):
        with pytest.raises((FileNotFoundError, SystemExit)):
            _run("--input", str(simple_input_yml), "--output", "definitely_fake_xyz")

    def test_no_source_prints_error(self, no_source_input_yml):
        _, stderr = _run(
            "--input", str(no_source_input_yml),
            "--output", "luabridge3",
        )
        assert "no source" in stderr.lower()


# ---------------------------------------------------------------------------
# Format-level overrides
# ---------------------------------------------------------------------------

class TestFormatOverrides:
    def test_format_filter_override(self, fmt_filters_input_yml):
        stdout, _ = _run("--input", str(fmt_filters_input_yml), "--output", "luabridge3")
        assert "Widget" in stdout

    def test_format_transform_override(self, fmt_transforms_input_yml):
        stdout, _ = _run("--input", str(fmt_transforms_input_yml), "--output", "luabridge3")
        assert "Widget" in stdout

    def test_format_generation_prefix_postfix(self, fmt_generation_input_yml):
        stdout, _ = _run("--input", str(fmt_generation_input_yml), "--output", "luabridge3")
        assert "// FMT PREFIX" in stdout
        assert "// FMT POSTFIX" in stdout


# ---------------------------------------------------------------------------
# --classname not matching (suppresses non-matching classes)
# ---------------------------------------------------------------------------

class TestClassnameNoMatch:
    def test_classname_no_match_suppresses_class(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--output", "luabridge3",
            "--classname", "NonExistent",
        )
        assert ".beginClass" not in stdout


# ---------------------------------------------------------------------------
# Per-source generation.includes
# ---------------------------------------------------------------------------

class TestPerSourceGenerationIncludes:
    def test_source_generation_includes_in_output(self, multi_source_with_generation_yml):
        stdout, _ = _run(
            "--input", str(multi_source_with_generation_yml),
            "--output", "luabridge3",
        )
        assert "<simple_extra.h>" in stdout


# ---------------------------------------------------------------------------
# --manifest-file / --check-compat / --embed-version
# ---------------------------------------------------------------------------

class TestManifestCompatibility:
    """End-to-end tests simulating API changes detected at generation time."""

    def _input_yml(self, tmp_path: Path, hpp_path: Path, name: str = "api") -> Path:
        data = {
            "source": {
                "path": str(hpp_path),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["api"]},
        }
        p = tmp_path / f"{name}.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def test_manifest_created_on_first_run(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--output", "luabridge3",
             "--manifest-file", str(manifest))

        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "uid" in data
        assert len(data["uid"]) == 64  # SHA-256 hex digest

    def test_no_change_exits_0_and_manifest_unchanged(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        input_yml = self._input_yml(tmp_path, hpp)
        manifest = tmp_path / "api.json"

        _run("--input", str(input_yml), "--output", "luabridge3",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        _, stderr = _run("--input", str(input_yml), "--output", "luabridge3",
                         "--manifest-file", str(manifest), "--check-compat")

        assert "Breaking" not in stderr
        assert json.loads(manifest.read_text())["uid"] == v1_version

    def test_breaking_change_exits_1(self, tmp_path):
        """Core scenario: adding a parameter to a function is a breaking change.

        v1: compute(int) -> int
        v2: compute(int, double) -> int   ← new required parameter breaks callers
        """
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, v1_hpp, "v1")),
             "--output", "luabridge3",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        # v2: add a second parameter — breaking change
        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch("sys.argv", ["tsujikiri",
                                 "--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                                 "--output", "luabridge3",
                                 "--manifest-file", str(manifest),
                                 "--check-compat"]):
            with patch("sys.stdout", stdout_io), patch("sys.stderr", stderr_io):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        stderr = stderr_io.getvalue()
        assert "Breaking" in stderr
        assert "compute" in stderr
        # Manifest must NOT be updated — baseline stays at v1 for the next check
        assert json.loads(manifest.read_text())["uid"] == v1_version

    def test_breaking_change_method_on_class_exits_1(self, tmp_path):
        """Class method parameter count change is a breaking change."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text(
            "namespace api { class Calc { public: int add(int a, int b); }; }\n"
        )
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, v1_hpp, "v1")),
             "--output", "luabridge3",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text(
            "namespace api { class Calc { public: int add(int a, int b, int c); }; }\n"
        )

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch("sys.argv", ["tsujikiri",
                                 "--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                                 "--output", "luabridge3",
                                 "--manifest-file", str(manifest),
                                 "--check-compat"]):
            with patch("sys.stdout", stdout_io), patch("sys.stderr", stderr_io):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        stderr = stderr_io.getvalue()
        assert "Breaking" in stderr
        assert "add" in stderr
        assert json.loads(manifest.read_text())["uid"] == v1_version

    def test_additive_change_exits_0_with_warning(self, tmp_path):
        """Adding a new function is additive — warns but does not fail."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, v1_hpp, "v1")),
             "--output", "luabridge3",
             "--manifest-file", str(manifest))

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x); int reset(); }\n")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                         "--output", "luabridge3",
                         "--manifest-file", str(manifest), "--check-compat")

        assert "Breaking" not in stderr
        assert "WARNING" in stderr
        assert "reset" in stderr

    def test_breaking_without_check_compat_exits_0(self, tmp_path):
        """Without --check-compat, breaking changes are reported but do not fail."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, v1_hpp, "v1")),
             "--output", "luabridge3",
             "--manifest-file", str(manifest))

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                         "--output", "luabridge3",
                         "--manifest-file", str(manifest))  # no --check-compat

        assert "Breaking" in stderr
        # Manifest IS updated to v2 (no --check-compat to block it)
        data = json.loads(manifest.read_text())
        assert data["api"]["functions"][0]["params"] == ["int", "double"]

    def test_embed_version_in_generated_code(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"
        out = tmp_path / "bindings.cpp"

        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--output", "luabridge3",
             "--manifest-file", str(manifest),
             "--embed-version",
             "--output-file", str(out))

        version = json.loads(manifest.read_text())["uid"]
        content = out.read_text(encoding="utf-8")
        assert version in content
        assert "get_api_version" in content

    def test_no_embed_version_by_default(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        out = tmp_path / "bindings.cpp"

        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--output", "luabridge3",
             "--output-file", str(out))

        content = out.read_text(encoding="utf-8")
        assert "api_version" not in content
        assert "get_api_version" not in content

    def test_dry_run_shows_version(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")

        stdout, _ = _run("--input", str(self._input_yml(tmp_path, hpp)),
                         "--output", "luabridge3", "--dry-run")

        version_lines = [
            line for line in stdout.splitlines()
            if "Version" in line
        ]
        assert len(version_lines) == 1
        assert len(version_lines[0].split(":")[-1].strip()) == 64


# ---------------------------------------------------------------------------
# format / format_options
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_format_false_by_default_skips_formatter(self, simple_input_yml):
        """When format is not set, format_content is never called."""
        with patch("tsujikiri.cli.format_content") as mock_fmt:
            _run("--input", str(simple_input_yml), "--output", "luabridge3")
        mock_fmt.assert_not_called()

    def test_format_true_calls_formatter(self, tmp_path):
        """When format: true, format_content is called with the generated content."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "format": True,
        }
        p = tmp_path / "fmt.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        fake_result = MagicMock()
        fake_result.stdout = "// formatted\n"
        with patch("subprocess.run", return_value=fake_result):
            stdout, _ = _run("--input", str(p), "--output", "luabridge3")

        assert "// formatted" in stdout

    def test_format_true_passes_language_to_formatter(self, tmp_path):
        """format_content receives the output config language ('cpp' for luabridge3)."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "format": True,
        }
        p = tmp_path / "fmt_lang.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        with patch("tsujikiri.cli.format_content", return_value="// ok\n") as mock_fmt:
            _run("--input", str(p), "--output", "luabridge3")

        args, kwargs = mock_fmt.call_args
        assert args[1] == "cpp"

    def test_format_options_forwarded_to_formatter(self, tmp_path):
        """format_options list is passed as extra_args to format_content."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "format": True,
            "format_options": ["--style=Google"],
        }
        p = tmp_path / "fmt_opts.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        with patch("tsujikiri.cli.format_content", return_value="// ok\n") as mock_fmt:
            _run("--input", str(p), "--output", "luabridge3")

        args, kwargs = mock_fmt.call_args
        assert args[2] == ["--style=Google"]
