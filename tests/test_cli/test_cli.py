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
        args = p.parse_args([
            "--input", "foo.yml",
            "--target", "luabridge3", "out.cpp",
            "--target", "luals", "out.lua",
        ])
        assert args.target == [["luabridge3", "out.cpp"], ["luals", "out.lua"]]

    def test_classname_flag(self):
        p = build_parser()
        args = p.parse_args(["--input", "x.yml", "--target", "luabridge3", "-", "--classname", "Foo"])
        assert args.classname == "Foo"

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
            "--input", str(simple_input_yml),
            "--target", "luabridge3", "-",
            "--dry-run",
        )
        assert "Classes" in stdout

    def test_dry_run_no_binding_code(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--target", "luabridge3", "-",
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
            "--input", str(simple_input_yml),
            "--target", "luabridge3", str(out_file),
        )
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "getGlobalNamespace" in content

    def test_multiple_targets(self, simple_input_yml, tmp_path):
        cpp_file = tmp_path / "bindings.cpp"
        lua_file = tmp_path / "bindings.lua"
        _run(
            "--input", str(simple_input_yml),
            "--target", "luabridge3", str(cpp_file),
            "--target", "luals", str(lua_file),
        )
        assert cpp_file.exists()
        assert lua_file.exists()
        assert "getGlobalNamespace" in cpp_file.read_text(encoding="utf-8")
        assert "Widget" in lua_file.read_text(encoding="utf-8")

    def test_classname_filter(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--target", "luabridge3", "-",
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
            "--target", str(fmt), "-",
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
            "--input", str(tmp_path / "nope.yml"),
            "--target", "luabridge3", "-",
        )
        assert "not found" in stderr.lower() or "error" in stderr.lower()

    def test_unknown_format_raises(self, simple_input_yml):
        with pytest.raises((FileNotFoundError, SystemExit)):
            _run("--input", str(simple_input_yml), "--target", "definitely_fake_xyz", "-")

    def test_no_source_prints_error(self, no_source_input_yml):
        _, stderr = _run(
            "--input", str(no_source_input_yml),
            "--target", "luabridge3", "-",
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
# --classname not matching (suppresses non-matching classes)
# ---------------------------------------------------------------------------

class TestClassnameNoMatch:
    def test_classname_no_match_suppresses_class(self, simple_input_yml):
        stdout, _ = _run(
            "--input", str(simple_input_yml),
            "--target", "luabridge3", "-",
            "--classname", "NonExistent",
        )
        assert ".beginClass" not in stdout


# ---------------------------------------------------------------------------
# Declared functions with parameters (cli.py lines 303-308)
# ---------------------------------------------------------------------------

class TestDeclaredFunctionsInjection:
    def test_declared_function_with_parameters_appears_in_output(self, tmp_path: Path) -> None:
        """cli.py lines 303-308: declared function parameters are built as IRParameter list."""
        hpp = tmp_path / "empty.hpp"
        hpp.write_text("// empty\n")
        cfg = tmp_path / "decl.input.yml"
        cfg.write_text(yaml.dump({
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
        }))
        stdout, _ = _run("--input", str(cfg), "--target", "luabridge3", "-")
        assert "myWrapper" in stdout

    def test_declared_function_no_namespace_qualified_name(self, tmp_path: Path) -> None:
        """cli.py line 307: qualified = fn_decl.name when namespace is empty."""
        hpp = tmp_path / "empty.hpp"
        hpp.write_text("// empty\n")
        cfg = tmp_path / "decl_no_ns.input.yml"
        cfg.write_text(yaml.dump({
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
        }))
        stdout, _ = _run("--input", str(cfg), "--target", "luabridge3", "-")
        assert "bareFunc" in stdout


# ---------------------------------------------------------------------------
# Per-source generation.includes
# ---------------------------------------------------------------------------

class TestPerSourceGenerationIncludes:
    def test_source_generation_includes_in_output(self, multi_source_with_generation_yml):
        stdout, _ = _run(
            "--input", str(multi_source_with_generation_yml),
            "--target", "luabridge3", "-",
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
             "--target", "luabridge3", "-",
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

        _run("--input", str(input_yml), "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        _, stderr = _run("--input", str(input_yml), "--target", "luabridge3", "-",
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
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        # v2: add a second parameter — breaking change
        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch("sys.argv", ["tsujikiri",
                                "--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                                "--target", "luabridge3", "-",
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
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))
        v1_version = json.loads(manifest.read_text())["uid"]

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text(
            "namespace api { class Calc { public: int add(int a, int b, int c); }; }\n"
        )

        stdout_io, stderr_io = StringIO(), StringIO()
        with patch("sys.argv", ["tsujikiri",
                                "--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                                "--target", "luabridge3", "-",
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
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x); int reset(); }\n")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                         "--target", "luabridge3", "-",
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
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))

        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { int compute(int x, double y); }\n")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                         "--target", "luabridge3", "-",
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
             "--target", "luabridge3", str(out),
             "--manifest-file", str(manifest),
             "--embed-version")

        version = json.loads(manifest.read_text())["version"]
        content = out.read_text(encoding="utf-8")
        assert version in content
        assert "get_api_version" in content

    def test_no_embed_version_by_default(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        out = tmp_path / "bindings.cpp"

        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--target", "luabridge3", str(out))

        content = out.read_text(encoding="utf-8")
        assert "api_version" not in content
        assert "get_api_version" not in content

    def test_dry_run_shows_version(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")

        stdout, _ = _run("--input", str(self._input_yml(tmp_path, hpp)),
                         "--target", "luabridge3", "-", "--dry-run")

        version_lines = [
            line for line in stdout.splitlines()
            if "Version" in line
        ]
        assert len(version_lines) == 1
        assert version_lines[0].split(":")[-1].strip() == "0.0.0"

    def test_pure_breaking_no_additive_warning(self, tmp_path):
        """Removing a function entirely produces only a breaking change (no additive),
        covering the False branch of ``if report.additive_changes``."""
        v1_hpp = tmp_path / "v1.hpp"
        v1_hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        _run("--input", str(self._input_yml(tmp_path, v1_hpp, "v1")),
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))

        # v2: remove the function entirely
        v2_hpp = tmp_path / "v2.hpp"
        v2_hpp.write_text("namespace api { }\n")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, v2_hpp, "v2")),
                         "--target", "luabridge3", "-",
                         "--manifest-file", str(manifest))

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
            json.dumps({
                "uid": "a" * 64,
                "version": "not-semver",
                "module": "api",
                "api": {"classes": [], "functions": [], "enums": []},
            }),
            encoding="utf-8",
        )

        _, stderr = _run("--input", str(self._input_yml(tmp_path, hpp)),
                         "--target", "luabridge3", "-",
                         "--manifest-file", str(manifest))

        assert "Suggested version bump" not in stderr

    def test_no_version_bump_message_when_versions_match(self, tmp_path):
        """When the tampered manifest causes a uid mismatch but the comparison report
        is empty, bump_semver returns the same version — covering the False branch
        of ``if new_version != old_version``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        # First run to get a correct manifest (correct uid + api section)
        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))

        # Tamper only the uid so the next run sees uid != new_uid,
        # but the api content is identical → compare_manifests finds no changes
        # → bump_semver returns the same version as old_manifest["version"]
        m = json.loads(manifest.read_text(encoding="utf-8"))
        m["uid"] = "0" * 64
        m["version"] = "2.0.0"
        manifest.write_text(json.dumps(m), encoding="utf-8")

        _, stderr = _run("--input", str(self._input_yml(tmp_path, hpp)),
                         "--target", "luabridge3", "-",
                         "--manifest-file", str(manifest))

        assert "Suggested version bump" not in stderr

    def test_no_version_copied_when_uid_matches_no_version_key(self, tmp_path):
        """uid unchanged AND old manifest has no ``version`` key —
        covering the False branch of ``elif \"version\" in old_manifest``."""
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int compute(int x); }\n")
        manifest = tmp_path / "api.json"

        # First run to get a manifest with the correct uid
        _run("--input", str(self._input_yml(tmp_path, hpp)),
             "--target", "luabridge3", "-",
             "--manifest-file", str(manifest))

        # Remove the "version" key so the elif branch evaluates to False
        m = json.loads(manifest.read_text(encoding="utf-8"))
        del m["version"]
        manifest.write_text(json.dumps(m), encoding="utf-8")

        # Second run — uid matches, no "version" key → elif is False
        _, stderr = _run("--input", str(self._input_yml(tmp_path, hpp)),
                         "--target", "luabridge3", "-",
                         "--manifest-file", str(manifest))

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
            "--input", str(tmp_path / "nope.yml"),
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

    def test_source_entry_with_transforms_validated(self, tmp_path):
        hpp = tmp_path / "api.hpp"
        hpp.write_text("namespace api { int x(); }\n")
        data = {
            "sources": [{
                "path": str(hpp),
                "parse_args": ["-std=c++17"],
                "transforms": [{"stage": "bad_stage_xyz"}],
            }],
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
            "--input", str(p),
            "--target", "nonexistent_format_xyz", "-",
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
