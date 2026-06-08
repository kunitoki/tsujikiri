"""Tests for cli.py — argument parsing and end-to-end orchestration."""

from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from tsujikiri.cli import _is_directory_target, build_parser, main
from tsujikiri.parser import parse_translation_unit
from tsujikiri.configurations import SourceConfig


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

    def test_target_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "foo.yml", "--target", "luabridge3", "-"])
        assert args.input == "foo.yml"
        assert args.target == [["luabridge3", "-"]]

    def test_target_short_flag(self):
        p = build_parser()
        args = p.parse_args(["-i", "foo.yml", "-t", "luabridge3", "out.cpp"])
        assert args.input == "foo.yml"
        assert args.target == [["luabridge3", "out.cpp"]]

    def test_multiple_targets(self):
        p = build_parser()
        args = p.parse_args(
            [
                "--input",
                "foo.yml",
                "--target",
                "luabridge3",
                "out.cpp",
                "--target",
                "luals",
                "out.lua",
            ]
        )
        assert args.target == [["luabridge3", "out.cpp"], ["luals", "out.lua"]]

    def test_dry_run_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--dry-run"])
        assert args.dry_run is True

    def test_trace_transforms_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--trace-transforms"])
        assert args.trace_transforms is True

    def test_dump_ir_flag_no_file(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--dump-ir"])
        assert args.dump_ir == "-"

    def test_dump_ir_flag_with_file(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--dump-ir", "ir.json"])
        assert args.dump_ir == "ir.json"

    def test_validate_config_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--validate-config"])
        assert args.validate_config is True

    def test_pretty_flag_absent_is_none(self):
        p = build_parser()
        args = p.parse_args(["--input", "foo.yml", "--target", "luabridge3", "-"])
        assert args.pretty is None

    def test_pretty_flag_no_args_is_empty_list(self):
        p = build_parser()
        args = p.parse_args(["--input", "foo.yml", "--target", "luabridge3", "-", "--pretty"])
        assert args.pretty == []

    def test_pretty_flag_with_one_format(self):
        p = build_parser()
        args = p.parse_args(["--input", "foo.yml", "--target", "luabridge3", "-", "--pretty", "luabridge3"])
        assert args.pretty == ["luabridge3"]

    def test_pretty_flag_with_multiple_formats(self):
        p = build_parser()
        args = p.parse_args(
            [
                "--input",
                "foo.yml",
                "--target",
                "luabridge3",
                "-",
                "--pretty",
                "luabridge3",
                "pybind11",
            ]
        )
        assert args.pretty == ["luabridge3", "pybind11"]

    def test_strict_flag_absent_is_false(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-"])
        assert args.strict is False

    def test_strict_flag_is_true(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--strict"])
        assert args.strict is True


# ---------------------------------------------------------------------------
# _is_directory_target
# ---------------------------------------------------------------------------


class TestIsDirectoryTarget:
    def test_trailing_slash_is_dir(self):
        assert _is_directory_target("out/") is True

    def test_nested_trailing_slash(self):
        assert _is_directory_target("generated/cpp/") is True

    def test_plain_file_is_not_dir(self):
        assert _is_directory_target("out.cpp") is False

    def test_stdout_is_not_dir(self):
        assert _is_directory_target("-") is False

    def test_file_in_subdir_is_not_dir(self):
        assert _is_directory_target("generated/out.cpp") is False


# ---------------------------------------------------------------------------
# --list-formats
# ---------------------------------------------------------------------------


class TestListFormats:
    def test_prints_builtin_formats(self):
        stdout, _ = _run("--list-formats")
        assert "luabridge3" in stdout

    def test_each_format_on_own_line(self):
        stdout, _ = _run("--list-formats")
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        assert len(lines) >= 1

    def test_pyi_format_listed(self):
        stdout, _ = _run("--list-formats")
        assert "pyi" in stdout

    def test_pybind11_format_listed(self):
        stdout, _ = _run("--list-formats")
        assert "pybind11" in stdout


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_prints_summary(self, simple_input_yml):
        stdout, _ = _run(
            "--input",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            "-",
            "--dry-run",
        )
        assert "Classes" in stdout

    def test_dry_run_no_binding_code(self, simple_input_yml):
        stdout, _ = _run(
            "--input",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            "-",
            "--dry-run",
        )
        assert "getGlobalNamespace" not in stdout
        assert "beginClass" not in stdout


# ---------------------------------------------------------------------------
# Normal generation
# ---------------------------------------------------------------------------


class TestGeneration:
    def test_luabridge3_output_to_stdout(self, simple_input_yml):
        stdout, _ = _run("--input", str(simple_input_yml), "--target", "luabridge3", "-")
        assert "getGlobalNamespace" in stdout
        assert "Widget" in stdout

    def test_output_to_file(self, simple_input_yml, tmp_path):
        out_file = tmp_path / "bindings.cpp"
        _run(
            "--input",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "getGlobalNamespace" in content

    def test_multiple_targets(self, simple_input_yml, tmp_path):
        cpp_file = tmp_path / "bindings.cpp"
        lua_file = tmp_path / "bindings.lua"
        _run(
            "--input",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            str(cpp_file),
            "--target",
            "luals",
            str(lua_file),
        )
        assert cpp_file.exists()
        assert lua_file.exists()
        assert "getGlobalNamespace" in cpp_file.read_text(encoding="utf-8")
        assert "Widget" in lua_file.read_text(encoding="utf-8")

    def test_custom_output_format_by_path(self, simple_input_yml, tmp_path):
        fmt = tmp_path / "noop.output.yml"
        fmt.write_text("format_name: noop\ntemplate: |\n  NOOP_START\n  NOOP_END\n")
        stdout, _ = _run(
            "--input",
            str(simple_input_yml),
            "--target",
            str(fmt),
            "-",
        )
        assert "NOOP_START" in stdout
        assert "NOOP_END" in stdout


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_input_flag(self):
        _run("--target", "luabridge3", "-", expected_exit=2)

    def test_missing_target_flag(self):
        _run("--input", "foo.yml", expected_exit=2)

    def test_nonexistent_input_file(self, tmp_path):
        _, stderr = _run(
            "--input",
            str(tmp_path / "nope.yml"),
            "--target",
            "luabridge3",
            "-",
        )
        assert "not found" in stderr.lower() or "error" in stderr.lower()

    def test_unknown_format_raises(self, simple_input_yml):
        with pytest.raises((FileNotFoundError, SystemExit)):
            _run("--input", str(simple_input_yml), "--target", "definitely_fake_xyz", "-")

    def test_no_source_prints_error(self, no_source_input_yml):
        _, stderr = _run(
            "--input",
            str(no_source_input_yml),
            "--target",
            "luabridge3",
            "-",
        )
        assert "no source" in stderr.lower()


# ---------------------------------------------------------------------------
# Format-level overrides
# ---------------------------------------------------------------------------


class TestFormatOverrides:
    def test_format_filter_override(self, fmt_filters_input_yml):
        stdout, _ = _run("--input", str(fmt_filters_input_yml), "--target", "luabridge3", "-")
        assert "Widget" in stdout

    def test_format_transform_override(self, fmt_transforms_input_yml):
        stdout, _ = _run("--input", str(fmt_transforms_input_yml), "--target", "luabridge3", "-")
        assert "Widget" in stdout

    def test_format_generation_prefix_postfix(self, fmt_generation_input_yml):
        stdout, _ = _run("--input", str(fmt_generation_input_yml), "--target", "luabridge3", "-")
        assert "// FMT PREFIX" in stdout
        assert "// FMT POSTFIX" in stdout


# ---------------------------------------------------------------------------
# Declared functions with parameters (cli.py lines 303-308)
# ---------------------------------------------------------------------------


class TestDeclaredFunctionsInjection:
    def test_declared_function_with_parameters_appears_in_output(self, tmp_path: Path) -> None:
        """cli.py lines 303-308: declared function parameters are built as IRParameter list."""
        hpp = tmp_path / "empty.hpp"
        hpp.write_text("// empty\n")
        cfg = tmp_path / "decl.input.yml"
        cfg.write_text(
            yaml.dump(
                {
                    "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
                    "typesystem": {
                        "declared_functions": [
                            {
                                "name": "myWrapper",
                                "namespace": "mylib",
                                "return_type": "void",
                                "parameters": [
                                    {"name": "x", "type": "int"},
                                    {"name": "y", "type": "float"},
                                ],
                            }
                        ]
                    },
                }
            )
        )
        stdout, _ = _run("--input", str(cfg), "--target", "luabridge3", "-")
        assert "myWrapper" in stdout

    def test_declared_function_no_namespace_qualified_name(self, tmp_path: Path) -> None:
        """cli.py line 307: qualified = fn_decl.name when namespace is empty."""
        hpp = tmp_path / "empty.hpp"
        hpp.write_text("// empty\n")
        cfg = tmp_path / "decl_no_ns.input.yml"
        cfg.write_text(
            yaml.dump(
                {
                    "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
                    "typesystem": {
                        "declared_functions": [
                            {
                                "name": "bareFunc",
                                "return_type": "int",
                                "parameters": [{"name": "n", "type": "int"}],
                            }
                        ]
                    },
                }
            )
        )
        stdout, _ = _run("--input", str(cfg), "--target", "luabridge3", "-")
        assert "bareFunc" in stdout


# ---------------------------------------------------------------------------
# Per-source generation.includes
# ---------------------------------------------------------------------------


class TestPerSourceGenerationIncludes:
    def test_source_generation_includes_in_output(self, multi_source_with_generation_yml):
        stdout, _ = _run(
            "--input",
            str(multi_source_with_generation_yml),
            "--target",
            "luabridge3",
            "-",
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

        _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        assert manifest.exists()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert "version" in data
        assert data["version"] == "0.0.0"

    def test_no_change_exits_0_and_manifest_unchanged(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        input_yml = self._input_yml(tmp_path, hpp)
        manifest = tmp_path / "api.json"

        _run("--input", str(input_yml), "--target", "luabridge3", "-", "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["version"]

        _, stderr = _run(
            "--input", str(input_yml), "--target", "luabridge3", "-", "--manifest-file", str(manifest), "--check-compat"
        )

        assert "Breaking" not in stderr
        assert json.loads(manifest.read_text())["version"] == v1_version

    def test_breaking_change_exits_1(self, tmp_path):
        """Core scenario: adding a parameter to a function is a breaking change.

        v1: compute(int) -> int
        v2: compute(int, double) -> int   ← new required parameter breaks callers
        """
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )
        v1_version = json.loads(manifest.read_text())["version"]

        # v2: add a second parameter — breaking change
        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch(
            "sys.argv",
            [
                "tsujikiri",
                "--input",
                str(self._input_yml(tmp_path, v2_hpp, "v2")),
                "--target",
                "luabridge3",
                "-",
                "--manifest-file",
                str(manifest),
                "--check-compat",
            ],
        ):
            with patch("sys.stdout", stdout_io), patch("sys.stderr", stderr_io):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        stderr = stderr_io.getvalue()
        assert "Breaking" in stderr
        assert "compute" in stderr
        # Manifest must NOT be updated — baseline stays at v1 for the next check
        assert json.loads(manifest.read_text())["version"] == v1_version

    def test_breaking_change_method_on_class_exits_1(self, tmp_path):
        """Class method parameter count change is a breaking change."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { class Calc { public: int add(int a, int b); }; }\n")
        manifest = tmp_path / "api.json"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )
        v1_version = json.loads(manifest.read_text())["version"]

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { class Calc { public: int add(int a, int b, int c); }; }\n")

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch(
            "sys.argv",
            [
                "tsujikiri",
                "--input",
                str(self._input_yml(tmp_path, v2_hpp, "v2")),
                "--target",
                "luabridge3",
                "-",
                "--manifest-file",
                str(manifest),
                "--check-compat",
            ],
        ):
            with patch("sys.stdout", stdout_io), patch("sys.stderr", stderr_io):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        stderr = stderr_io.getvalue()
        assert "Breaking" in stderr
        assert "add" in stderr
        assert json.loads(manifest.read_text())["version"] == v1_version

    def test_breaking_change_does_not_write_output_file(self, tmp_path):
        """When --check-compat detects breaking changes, output files must not be written."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"
        out = tmp_path / "bindings.cpp"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            str(out),
            "--manifest-file",
            str(manifest),
        )
        v1_content = out.read_text(encoding="utf-8")
        v1_manifest = manifest.read_text(encoding="utf-8")

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch(
            "sys.argv",
            [
                "tsujikiri",
                "--input",
                str(self._input_yml(tmp_path, v2_hpp, "v2")),
                "--target",
                "luabridge3",
                str(out),
                "--manifest-file",
                str(manifest),
                "--check-compat",
            ],
        ):
            with patch("sys.stdout", stdout_io), patch("sys.stderr", stderr_io):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code == 1
        assert out.read_text(encoding="utf-8") == v1_content
        assert manifest.read_text(encoding="utf-8") == v1_manifest

    def test_additive_change_exits_0_with_warning(self, tmp_path):
        """Adding a new function is additive — warns but does not fail."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x); int reset(); }\n")

        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, v2_hpp, "v2")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
            "--check-compat",
        )

        assert "Breaking" not in stderr
        assert "WARNING" in stderr
        assert "reset" in stderr

    def test_breaking_without_check_compat_exits_0(self, tmp_path):
        """Without --check-compat, breaking changes are reported but do not fail."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, v2_hpp, "v2")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )  # no --check-compat

        assert "Breaking" in stderr
        # Manifest IS updated to v2 (no --check-compat to block it)
        data = json.loads(manifest.read_text())
        assert data["api"]["functions"][0]["params"] == ["int", "double"]

    def test_embed_version_in_generated_code(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"
        out = tmp_path / "bindings.cpp"

        _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            str(out),
            "--manifest-file",
            str(manifest),
            "--embed-version",
        )

        version = json.loads(manifest.read_text())["version"]
        content = out.read_text(encoding="utf-8")
        assert version in content
        assert "get_api_version" in content

    def test_no_embed_version_by_default(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        out = tmp_path / "bindings.cpp"

        _run("--input", str(self._input_yml(tmp_path, hpp)), "--target", "luabridge3", str(out))

        content = out.read_text(encoding="utf-8")
        assert "api_version" not in content
        assert "get_api_version" not in content

    def test_dry_run_shows_version(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")

        stdout, _ = _run("--input", str(self._input_yml(tmp_path, hpp)), "--target", "luabridge3", "-", "--dry-run")

        version_lines = [line for line in stdout.splitlines() if "Version" in line]
        assert len(version_lines) == 1
        assert version_lines[0].split(":")[-1].strip() == "0.0.0"

    def test_pure_breaking_no_additive_warning(self, tmp_path):
        """Removing a function entirely produces only a breaking change (no additive),
        covering the False branch of ``if report.additive_changes``."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run(
            "--input",
            str(self._input_yml(tmp_path, v1_hpp, "v1")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        # v2: remove the function entirely
        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { }\n")

        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, v2_hpp, "v2")),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        assert "Breaking" in stderr
        assert "WARNING" not in stderr

    def test_version_bump_skipped_when_old_manifest_has_no_semver(self, tmp_path):
        """suggest_version_bump returns None when the old manifest's version is not semver,
        covering the False branch of ``if new_version is not None``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        # Write a manifest with a non-semver version so suggest_version_bump returns None
        manifest.write_text(
            json.dumps(
                {
                    "version": "not-semver",
                    "module": "api",
                    "api": {"classes": [], "functions": [], "enums": []},
                }
            ),
            encoding="utf-8",
        )

        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        assert "Suggested version bump" not in stderr

    def test_no_version_bump_message_when_versions_match(self, tmp_path):
        """When the tampered manifest causes a version mismatch but the comparison report
        is empty, bump_semver returns the same version — covering the False branch
        of ``if new_version != old_version``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        # First run to get a correct manifest (correct uid + api section)
        _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        # Tamper only the version so the next run sees version != new_version,
        # but the api content is identical → compare_manifests finds no changes
        # → bump_semver returns the same version as old_manifest["version"]
        m = json.loads(manifest.read_text(encoding="utf-8"))
        m["version"] = "2.0.0"
        manifest.write_text(json.dumps(m), encoding="utf-8")

        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        assert "Suggested version bump" not in stderr

    def test_no_version_copied_when_uid_matches_no_version_key(self, tmp_path):
        """old manifest has no ``version`` key covering the False branch of ``elif \"version\" in old_manifest``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        # First run to get a manifest with the correct uid
        _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        # Remove the "version" key so the elif branch evaluates to False
        m = json.loads(manifest.read_text(encoding="utf-8"))
        del m["version"]
        manifest.write_text(json.dumps(m), encoding="utf-8")

        # Second run — uid matches, no "version" key → elif is False
        _, stderr = _run(
            "--input",
            str(self._input_yml(tmp_path, hpp)),
            "--target",
            "luabridge3",
            "-",
            "--manifest-file",
            str(manifest),
        )

        assert "Breaking" not in stderr


# ---------------------------------------------------------------------------
# pretty / pretty_options
# ---------------------------------------------------------------------------


class TestPrettyPrinting:
    def test_pretty_false_by_default_skips_pretty_printer(self, simple_input_yml):
        """When pretty is not set, pretty is never called."""
        with patch("tsujikiri.cli.pretty") as mock_fmt:
            _run("--input", str(simple_input_yml), "--target", "luabridge3", "-")
        mock_fmt.assert_not_called()

    def test_pretty_true_calls_pretty_printer(self, tmp_path):
        """When pretty: true, pretty is called with the generated content."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "pretty": True,
        }
        p = tmp_path / "fmt.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        fake_result = MagicMock()
        fake_result.stdout = "// formatted\n"
        with patch("subprocess.run", return_value=fake_result):
            stdout, _ = _run("--input", str(p), "--target", "luabridge3", "-")

        assert "// formatted" in stdout

    def test_pretty_true_passes_language_to_pretty_printer(self, tmp_path):
        """pretty receives the output config language ('cpp' for luabridge3)."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "pretty": True,
        }
        p = tmp_path / "fmt_lang.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(p), "--target", "luabridge3", "-")

        args, kwargs = mock_fmt.call_args
        assert args[1] == "cpp"

    def test_pretty_options_forwarded_to_pretty_printer(self, tmp_path):
        """pretty_options list is passed as extra_args to pretty."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "pretty": True,
            "pretty_options": ["--style=Google"],
        }
        p = tmp_path / "fmt_opts.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(p), "--target", "luabridge3", "-")

        args, kwargs = mock_fmt.call_args
        assert args[2] == ["--style=Google"]

    def test_pyi_pretty_language_is_python(self, tmp_path):
        """pyi format has language=python, so pretty receives 'python'."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"]},
            "pretty": True,
        }
        p = tmp_path / "pyi_lang.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        with patch("tsujikiri.cli.pretty", return_value="# ok\n") as mock_fmt:
            _run("--input", str(p), "--target", "pyi", "-")

        args, kwargs = mock_fmt.call_args
        assert args[1] == "python"

    def test_pyi_real_ruff_formats_output(self, tmp_path):
        """Integration test: pyi generation with pretty: true calls ruff and reformats."""
        data = {
            "source": {
                "path": str(Path(__file__).parent / "simple.hpp"),
                "parse_args": ["-std=c++17"],
            },
            "filters": {"namespaces": ["simple"], "constructors": {"include": True}},
            "pretty": True,
        }
        p = tmp_path / "pyi_ruff.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        stdout, _ = _run("--input", str(p), "--target", "pyi", "-")

        # ruff should have run — output is valid, well-formed Python
        assert "class Widget:" in stdout
        assert "def __init__" in stdout


# ---------------------------------------------------------------------------
# --trace-transforms
# ---------------------------------------------------------------------------


class TestTraceTransforms:
    def test_trace_transforms_outputs_to_stderr(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { class Foo { public: int val; }; }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
            "transforms": [{"stage": "rename_class", "from": "Foo", "to": "Bar"}],
        }
        p = tmp_path / "trace.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--target", "luabridge3", "-", "--trace-transforms")
        assert "[TRACE]" in stderr
        assert "RenameClassStage" in stderr

    def test_no_trace_by_default(self, simple_input_yml):
        _, stderr = _run("--input", str(simple_input_yml), "--target", "luabridge3", "-")
        assert "[TRACE]" not in stderr


# ---------------------------------------------------------------------------
# --dump-ir
# ---------------------------------------------------------------------------


class TestDumpIR:
    def test_dump_ir_to_stdout(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
        }
        p = tmp_path / "dump.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        gen_file = tmp_path / "out.cpp"

        # Use file target so stdout is only the IR dump
        stdout, _ = _run("--input", str(p), "--target", "luabridge3", str(gen_file), "--dump-ir")
        ir = json.loads(stdout)
        assert "functions" in ir or "classes" in ir

    def test_dump_ir_to_file(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
        }
        p = tmp_path / "dump.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        ir_file = tmp_path / "ir.json"

        _run("--input", str(p), "--target", "luabridge3", "-", "--dump-ir", str(ir_file))
        assert ir_file.exists()
        ir = json.loads(ir_file.read_text(encoding="utf-8"))
        assert "functions" in ir or "classes" in ir


# ---------------------------------------------------------------------------
# --validate-config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_exits_0(self, simple_input_yml):
        _, stderr = _run("--input", str(simple_input_yml), "--validate-config")
        assert "valid" in stderr.lower()

    def test_invalid_transform_stage_exits_1(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
            "transforms": [{"stage": "nonexistent_stage_xyz"}],
        }
        p = tmp_path / "invalid.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "ERROR" in stderr
        assert "nonexistent_stage_xyz" in stderr

    def test_missing_input_exits_1(self):
        _, stderr = _run("--validate-config", expected_exit=1)
        assert "error" in stderr.lower()

    def test_nonexistent_input_exits_1(self, tmp_path):
        _, stderr = _run(
            "--input",
            str(tmp_path / "nope.yml"),
            "--validate-config",
            expected_exit=1,
        )
        assert "error" in stderr.lower()

    def test_malformed_yaml_exits_1(self, tmp_path):
        p = tmp_path / "bad.input.yml"
        p.write_text(": : invalid: yaml: [\n", encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "error" in stderr.lower()

    def test_invalid_regex_namespace_exits_1(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["[invalid-regex"]},
        }
        p = tmp_path / "regex.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "ERROR" in stderr

    def test_ambiguous_output_source_exits_1(self, tmp_path):
        data = {
            "sources": [
                {"path": "a/utils.hpp"},
                {"path": "b/utils.hpp"},
            ],
            "outputs": [{"name": "ambiguous", "sources": ["utils.hpp"]}],
        }
        p = tmp_path / "ambiguous.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "Ambiguous source reference 'utils.hpp'" in stderr

    def test_source_entry_with_transforms_validated(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "sources": [
                {
                    "path": str(hpp),
                    "parse_args": ["-std=c++17"],
                    "transforms": [{"stage": "bad_stage_xyz"}],
                }
            ],
            "filters": {"namespaces": ["api"]},
        }
        p = tmp_path / "src_tf.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "bad_stage_xyz" in stderr

    def test_format_override_transforms_validated(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
            "format_overrides": {
                "luabridge3": {
                    "transforms": [{"stage": "bad_fmt_stage_xyz"}],
                },
            },
        }
        p = tmp_path / "fmt_tf.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config", expected_exit=1)
        assert "bad_fmt_stage_xyz" in stderr

    def test_invalid_target_format_exits_1(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
        }
        p = tmp_path / "valid.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run(
            "--input",
            str(p),
            "--target",
            "nonexistent_format_xyz",
            "-",
            "--validate-config",
            expected_exit=1,
        )
        assert "ERROR" in stderr

    def test_format_override_without_transforms_passes(self, tmp_path):
        """format_overrides entry with no ``transforms`` key — False branch of ``if override.transforms``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
            "format_overrides": {
                "luabridge3": {
                    "filters": {"namespaces": ["api"]},
                },
            },
        }
        p = tmp_path / "no_fmt_tf.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config")
        assert "valid" in stderr.lower()

    def test_valid_transform_stage_not_flagged(self, tmp_path):
        """A known transform stage passes validation — False branch of ``if spec.stage not in _REGISTRY``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "source": {"path": str(hpp), "parse_args": ["-std=c++17"]},
            "filters": {"namespaces": ["api"]},
            "transforms": [{"stage": "suppress_class", "pattern": "Foo"}],
        }
        p = tmp_path / "valid_stage.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--validate-config")
        assert "valid" in stderr.lower()


class TestSourceResolutionErrors:
    def test_ambiguous_output_source_exits_1_before_generation(self, tmp_path):
        data = {
            "sources": [
                {"path": "a/utils.hpp"},
                {"path": "b/utils.hpp"},
            ],
            "outputs": [{"name": "ambiguous", "sources": ["utils.hpp"]}],
        }
        p = tmp_path / "ambiguous.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        _, stderr = _run("--input", str(p), "--target", "luabridge3", "-", expected_exit=1)

        assert "tsujikiri: error: Ambiguous source reference 'utils.hpp'" in stderr


# ---------------------------------------------------------------------------
# --verbose (cli.py lines 235-244)
# ---------------------------------------------------------------------------


class TestVerbose:
    def test_verbose_emitted_line_printed(self, simple_input_yml: Path) -> None:
        """--verbose prints [filter] emitted line to stderr (lines 236-242)."""
        _, stderr = _run(
            "--input",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            "-",
            "--verbose",
        )
        assert "[filter] emitted:" in stderr


# ---------------------------------------------------------------------------
# --pretty CLI flag (global and per-format)
# ---------------------------------------------------------------------------

HERE_CLI = Path(__file__).parent


def _make_input_yml(tmp_path: Path, **extra: object) -> Path:
    """Write a minimal input.yml pointing at simple.hpp with optional extra fields."""
    data: dict = {
        "source": {
            "path": str(HERE_CLI / "simple.hpp"),
            "parse_args": ["-std=c++17"],
        },
        "filters": {"namespaces": ["simple"]},
    }
    data.update(extra)
    p = tmp_path / "test.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


class TestPrettyFlag:
    def test_absent_uses_yaml_false(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=False)
        with patch("tsujikiri.cli.pretty") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        mock_fmt.assert_not_called()

    def test_absent_uses_yaml_true(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=True)
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        mock_fmt.assert_called_once()

    def test_no_args_enables_all(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=False)
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-", "--pretty")
        mock_fmt.assert_called_once()

    def test_matching_format_enables(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=False)
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-", "--pretty", "luabridge3")
        mock_fmt.assert_called_once()

    def test_nonmatching_format_disables(self, tmp_path: Path) -> None:
        # YAML says pretty: true but CLI --pretty pybind11 should disable for luabridge3
        yml = _make_input_yml(tmp_path, pretty=True)
        with patch("tsujikiri.cli.pretty") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-", "--pretty", "pybind11")
        mock_fmt.assert_not_called()

    def test_multiple_formats_in_one_run(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=False)
        out_lua = tmp_path / "out.lua"
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run(
                "--input",
                str(yml),
                "--target",
                "luabridge3",
                "-",
                "--target",
                "luals",
                str(out_lua),
                "--pretty",
            )
        assert mock_fmt.call_count == 2

    def test_cli_enables_only_listed_format_in_multi_target(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty=False)
        out_lua = tmp_path / "out.lua"
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run(
                "--input",
                str(yml),
                "--target",
                "luabridge3",
                "-",
                "--target",
                "luals",
                str(out_lua),
                "--pretty",
                "luabridge3",
            )
        assert mock_fmt.call_count == 1
        assert mock_fmt.call_args[0][1] == "cpp"

    def test_format_override_true_overrides_global_false(self, tmp_path: Path) -> None:
        yml = _make_input_yml(
            tmp_path,
            pretty=False,
            format_overrides={"luabridge3": {"pretty": True}},
        )
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        mock_fmt.assert_called_once()

    def test_format_override_false_overrides_global_true(self, tmp_path: Path) -> None:
        yml = _make_input_yml(
            tmp_path,
            pretty=True,
            format_overrides={"luabridge3": {"pretty": False}},
        )
        with patch("tsujikiri.cli.pretty") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        mock_fmt.assert_not_called()

    def test_format_override_options_used_when_format_enables(self, tmp_path: Path) -> None:
        yml = _make_input_yml(
            tmp_path,
            format_overrides={"luabridge3": {"pretty": True, "pretty_options": ["--style=LLVM"]}},
        )
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        assert mock_fmt.call_args[0][2] == ["--style=LLVM"]

    def test_format_override_options_fallback_to_global(self, tmp_path: Path) -> None:
        yml = _make_input_yml(
            tmp_path,
            pretty=True,
            pretty_options=["--style=Google"],
            format_overrides={"luabridge3": {"pretty": True}},
        )
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-")
        assert mock_fmt.call_args[0][2] == ["--style=Google"]

    def test_cli_enables_uses_format_override_options(self, tmp_path: Path) -> None:
        yml = _make_input_yml(
            tmp_path,
            format_overrides={"luabridge3": {"pretty_options": ["--style=LLVM"]}},
        )
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-", "--pretty")
        assert mock_fmt.call_args[0][2] == ["--style=LLVM"]

    def test_cli_enables_falls_back_to_global_options_when_no_format_override(self, tmp_path: Path) -> None:
        yml = _make_input_yml(tmp_path, pretty_options=["--style=Google"])
        with patch("tsujikiri.cli.pretty", return_value="// ok\n") as mock_fmt:
            _run("--input", str(yml), "--target", "luabridge3", "-", "--pretty")
        assert mock_fmt.call_args[0][2] == ["--style=Google"]


# ---------------------------------------------------------------------------
# Multi-output generation
# ---------------------------------------------------------------------------


class TestMultiOutputGeneration:
    def test_two_files_created(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "out"
        outdir.mkdir()
        _run("-i", str(multi_output_input_yml), "--target", "luabridge3", str(outdir) + "/")
        assert (outdir / "foo_bindings.cpp").exists()
        assert (outdir / "bar_bindings.cpp").exists()

    def test_foo_bindings_contains_foo_not_bar(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "out"
        outdir.mkdir()
        _run("-i", str(multi_output_input_yml), "--target", "luabridge3", str(outdir) + "/")
        content = (outdir / "foo_bindings.cpp").read_text()
        assert "Foo" in content
        assert "Bar" not in content

    def test_bar_bindings_contains_bar_not_foo(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "out"
        outdir.mkdir()
        _run("-i", str(multi_output_input_yml), "--target", "luabridge3", str(outdir) + "/")
        content = (outdir / "bar_bindings.cpp").read_text()
        assert "Bar" in content
        assert "Foo" not in content

    def test_multiple_formats_produce_correct_extensions(self, multi_output_input_yml, tmp_path):
        cpp_dir = tmp_path / "cpp"
        lua_dir = tmp_path / "lua"
        cpp_dir.mkdir()
        lua_dir.mkdir()
        _run(
            "-i",
            str(multi_output_input_yml),
            "--target",
            "luabridge3",
            str(cpp_dir) + "/",
            "--target",
            "luals",
            str(lua_dir) + "/",
        )
        assert (cpp_dir / "foo_bindings.cpp").exists()
        assert (cpp_dir / "bar_bindings.cpp").exists()
        assert (lua_dir / "foo_bindings.lua").exists()
        assert (lua_dir / "bar_bindings.lua").exists()

    def test_single_manifest_written(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "out"
        manifest_path = tmp_path / "api.manifest.json"
        outdir.mkdir()
        _run(
            "-i",
            str(multi_output_input_yml),
            "--target",
            "luabridge3",
            str(outdir) + "/",
            "--manifest-file",
            str(manifest_path),
        )
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        class_names = {c["name"] for c in manifest["api"]["classes"]}
        assert "Foo" in class_names
        assert "Bar" in class_names

    def test_error_dir_target_without_outputs(self, simple_input_yml, tmp_path):
        outdir = tmp_path / "out"
        outdir.mkdir()
        _, stderr = _run(
            "-i",
            str(simple_input_yml),
            "--target",
            "luabridge3",
            str(outdir) + "/",
            expected_exit=1,
        )
        assert "outputs:" in stderr
        assert "directory output" in stderr

    def test_error_outputs_without_dir_target(self, multi_output_input_yml, tmp_path):
        _, stderr = _run(
            "-i",
            str(multi_output_input_yml),
            "--target",
            "luabridge3",
            str(tmp_path / "out.cpp"),
            expected_exit=1,
        )
        assert "outputs:" in stderr
        assert "all targets" in stderr

    def test_outdir_created_if_missing(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "nested" / "new_dir"
        # Do not mkdir — the CLI must create it
        _run("-i", str(multi_output_input_yml), "--target", "luabridge3", str(outdir) + "/")
        assert (outdir / "foo_bindings.cpp").exists()

    def test_fmt_generation_prefix_applied_per_group(self, tmp_path):
        """format_overrides generation prefix is applied in multi-output mode (covers lines 493-496)."""
        data = {
            "outputs": [
                {"name": "foo_bindings", "sources": [str(HERE_CLI / "multi_out_a.hpp")]},
            ],
            "filters": {
                "namespaces": ["alpha"],
                "constructors": {"include": False},
            },
            "format_overrides": {
                "luabridge3": {
                    "generation": {
                        "prefix": "// MULTI PREFIX\n",
                    },
                },
            },
        }
        p = tmp_path / "multi_fmt_gen.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        outdir = tmp_path / "out"
        outdir.mkdir()
        _run("-i", str(p), "--target", "luabridge3", str(outdir) + "/")
        content = (outdir / "foo_bindings.cpp").read_text()
        assert "// MULTI PREFIX" in content

    def test_output_scoped_fmt_generation_prefix_only_applies_to_named_group(self, tmp_path):
        data = {
            "outputs": [
                {"name": "foo_bindings", "sources": [str(HERE_CLI / "multi_out_a.hpp")]},
                {"name": "bar_bindings", "sources": [str(HERE_CLI / "multi_out_b.hpp")]},
            ],
            "filters": {
                "namespaces": ["alpha"],
                "constructors": {"include": False},
            },
            "format_overrides": [
                {
                    "luabridge3": {
                        "generation": {
                            "prefix": "// GLOBAL PREFIX\n",
                        },
                    },
                },
                {
                    "output": "foo_bindings",
                    "luabridge3": {
                        "generation": {
                            "prefix": "// FOO PREFIX\n",
                        },
                    },
                },
            ],
        }
        p = tmp_path / "multi_fmt_gen_scoped.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        outdir = tmp_path / "out"
        outdir.mkdir()

        _run("-i", str(p), "--target", "luabridge3", str(outdir) + "/")

        foo_content = (outdir / "foo_bindings.cpp").read_text()
        bar_content = (outdir / "bar_bindings.cpp").read_text()
        assert "// FOO PREFIX" in foo_content
        assert "// GLOBAL PREFIX" not in foo_content
        assert "// GLOBAL PREFIX" in bar_content
        assert "// FOO PREFIX" not in bar_content

    def test_error_mixed_targets_with_outputs(self, multi_output_input_yml, tmp_path):
        outdir = tmp_path / "out"
        outdir.mkdir()
        _, stderr = _run(
            "-i",
            str(multi_output_input_yml),
            "--target",
            "luabridge3",
            str(outdir) + "/",
            "--target",
            "luals",
            str(tmp_path / "out.lua"),
            expected_exit=1,
        )
        assert "all targets" in stderr

    def test_error_format_without_extension(self, multi_output_input_yml, tmp_path):
        fmt_dir = tmp_path / "fmts"
        fmt_dir.mkdir()
        (fmt_dir / "noext.output.yml").write_text(
            "format_name: noext\nlanguage: cpp\ntemplate: |\n  NOOP\n",
            encoding="utf-8",
        )
        outdir = tmp_path / "out"
        outdir.mkdir()
        _, stderr = _run(
            "-i",
            str(multi_output_input_yml),
            "--formats-dir",
            str(fmt_dir),
            "--target",
            "noext",
            str(outdir) + "/",
            expected_exit=1,
        )
        assert "extension" in stderr

    def test_pretty_applied_per_group(self, tmp_path):
        """Pretty printing runs for each group output (covers line 529)."""
        data = {
            "outputs": [
                {"name": "foo_bindings", "sources": [str(HERE_CLI / "multi_out_a.hpp")]},
            ],
            "filters": {
                "namespaces": ["alpha"],
                "constructors": {"include": False},
            },
            "pretty": True,
        }
        p = tmp_path / "multi_pretty.input.yml"
        p.write_text(yaml.dump(data), encoding="utf-8")
        outdir = tmp_path / "out"
        outdir.mkdir()
        with patch("tsujikiri.cli.pretty", return_value="// pretty\n") as mock_fmt:
            _run("-i", str(p), "--target", "luabridge3", str(outdir) + "/")
        mock_fmt.assert_called_once()


# ---------------------------------------------------------------------------
# parse_translation_unit clang_errors accumulator
# ---------------------------------------------------------------------------


class TestParseTranslationUnitClangErrors:
    HERE = Path(__file__).parent

    def test_errors_collected_for_broken_header(self):
        source = SourceConfig(path=str(self.HERE / "broken.hpp"), parse_args=["-std=c++17"])
        errors: list[str] = []
        parse_translation_unit(source, [], "test_module", clang_errors=errors)
        assert len(errors) >= 1
        assert any("error" in e.lower() or "fatal" in e.lower() for e in errors)

    def test_warnings_not_collected_in_accumulator(self):
        source = SourceConfig(path=str(self.HERE / "warning.hpp"), parse_args=["-std=c++17"])
        errors: list[str] = []
        parse_translation_unit(source, [], "test_module", clang_errors=errors)
        assert errors == []

    def test_clean_header_produces_no_errors(self):
        source = SourceConfig(path=str(self.HERE / "simple.hpp"), parse_args=["-std=c++17"])
        errors: list[str] = []
        parse_translation_unit(source, ["simple"], "test_module", clang_errors=errors)
        assert errors == []

    def test_none_accumulator_does_not_raise(self):
        source = SourceConfig(path=str(self.HERE / "broken.hpp"), parse_args=["-std=c++17"])
        parse_translation_unit(source, [], "test_module", clang_errors=None)

    def test_no_accumulator_kwarg_does_not_raise(self):
        source = SourceConfig(path=str(self.HERE / "simple.hpp"), parse_args=["-std=c++17"])
        parse_translation_unit(source, ["simple"], "test_module")


# ---------------------------------------------------------------------------
# --strict
# ---------------------------------------------------------------------------


class TestStrict:
    def test_strict_flag_absent_does_not_fail_on_broken_header(self, broken_input_yml, tmp_path):
        out_file = tmp_path / "out.cpp"
        # Without --strict, broken headers still exit 0
        _run("--input", str(broken_input_yml), "--target", "luabridge3", str(out_file))
        # File written (may be empty bindings, but the tool should not abort)
        assert out_file.exists()

    def test_strict_exits_1_on_broken_header(self, broken_input_yml, tmp_path):
        out_file = tmp_path / "out.cpp"
        with patch(
            "sys.argv",
            ["tsujikiri", "--input", str(broken_input_yml), "--target", "luabridge3", str(out_file), "--strict"],
        ):
            with patch("sys.stdout", StringIO()), patch("sys.stderr", StringIO()):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1

    def test_strict_no_output_written_on_broken_header(self, broken_input_yml, tmp_path):
        out_file = tmp_path / "out.cpp"
        with patch(
            "sys.argv",
            ["tsujikiri", "--input", str(broken_input_yml), "--target", "luabridge3", str(out_file), "--strict"],
        ):
            with patch("sys.stdout", StringIO()), patch("sys.stderr", StringIO()):
                with pytest.raises(SystemExit):
                    main()
        assert not out_file.exists()

    def test_strict_exits_0_on_clean_header(self, simple_input_yml, tmp_path):
        out_file = tmp_path / "out.cpp"
        _run("--input", str(simple_input_yml), "--target", "luabridge3", str(out_file), "--strict")
        assert out_file.exists()

    def test_strict_exits_0_on_warning_only_header(self, warning_input_yml, tmp_path):
        out_file = tmp_path / "out.cpp"
        _run("--input", str(warning_input_yml), "--target", "luabridge3", str(out_file), "--strict")
        # Warnings alone must not trigger strict failure
        assert out_file.exists()

    def test_strict_exits_1_on_broken_header_in_output_groups(self, tmp_path):
        broken_hpp = Path(__file__).parent / "broken.hpp"
        data = {
            "outputs": [{"name": "out_a", "sources": [str(broken_hpp)]}],
            "filters": {"namespaces": []},
        }
        input_yml = tmp_path / "broken_groups.input.yml"
        input_yml.write_text(yaml.dump(data), encoding="utf-8")
        outdir = tmp_path / "out"
        outdir.mkdir()
        with patch(
            "sys.argv",
            ["tsujikiri", "--input", str(input_yml), "--target", "luabridge3", str(outdir) + "/", "--strict"],
        ):
            with patch("sys.stdout", StringIO()), patch("sys.stderr", StringIO()):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1
        assert not (outdir / "out_a.cpp").exists()

    def test_strict_with_dry_run_exits_1_on_broken_header(self, broken_input_yml):
        with patch(
            "sys.argv",
            ["tsujikiri", "--input", str(broken_input_yml), "--target", "luabridge3", "-", "--strict", "--dry-run"],
        ):
            with patch("sys.stdout", StringIO()) as mock_stdout, patch("sys.stderr", StringIO()):
                with pytest.raises(SystemExit) as exc_info:
                    main()
        assert exc_info.value.code == 1
        assert mock_stdout.getvalue() == ""


# ---------------------------------------------------------------------------
# Effective custom_data merging
# ---------------------------------------------------------------------------


class TestEffectiveCustomData:
    """Generator receives merged custom_data = global + format_override.custom_data."""

    def _run(self, tmp_path: Path, input_yaml: str, fmt_yaml: str) -> str:
        """Helper: write input + format YAML, run CLI, return stdout."""
        fmt_file = tmp_path / "test.output.yml"
        fmt_file.write_text(fmt_yaml, encoding="utf-8")

        input_file = tmp_path / "test.input.yml"
        input_file.write_text(input_yaml, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tsujikiri",
                "--input",
                str(input_file),
                "--target",
                str(fmt_file),
                "-",
            ],
            capture_output=True,
            text=True,
        )
        return result.stdout

    def _fmt_yaml(self, template: str) -> str:
        return (
            "format_name: test\nformat_version: '1'\n"
            "description: test\nlanguage: python\nextension: .py\n"
            "template: |\n" + "\n".join(f"  {line}" for line in template.splitlines()) + "\n"
        )

    def test_global_custom_data_only(self, tmp_path: Path) -> None:
        input_yaml = (
            "source:\n  path: /dev/null\n"
            "custom_data:\n  key: global\n"
            "format_overrides:\n  test:\n    template_extends: ''\n"
        )
        out = self._run(
            tmp_path,
            input_yaml,
            self._fmt_yaml("{{ custom_data.key }}"),
        )
        assert "global" in out

    def test_format_override_custom_data_extends_global(self, tmp_path: Path) -> None:
        input_yaml = (
            "source:\n  path: /dev/null\n"
            "custom_data:\n  from_global: yes\n"
            "format_overrides:\n  test:\n    custom_data:\n      from_fmt: yes\n"
        )
        out = self._run(
            tmp_path,
            input_yaml,
            self._fmt_yaml("{{ custom_data.from_global }},{{ custom_data.from_fmt }}"),
        )
        assert "True,True" in out

    def test_format_override_custom_data_wins_on_collision(self, tmp_path: Path) -> None:
        input_yaml = (
            "source:\n  path: /dev/null\n"
            "custom_data:\n  key: global\n"
            "format_overrides:\n  test:\n    custom_data:\n      key: override\n"
        )
        out = self._run(
            tmp_path,
            input_yaml,
            self._fmt_yaml("{{ custom_data.key }}"),
        )
        assert "override" in out

    def test_no_format_override_passes_global_unchanged(self, tmp_path: Path) -> None:
        input_yaml = "source:\n  path: /dev/null\ncustom_data:\n  key: global\n"
        out = self._run(
            tmp_path,
            input_yaml,
            self._fmt_yaml("{{ custom_data.key }}"),
        )
        assert "global" in out
