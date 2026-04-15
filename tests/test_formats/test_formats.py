"""Tests for formats/__init__.py — built-in format discovery and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.formats import apply_format_inheritance, list_builtin_formats, resolve_format_path


class TestListBuiltinFormats:
    def test_returns_list(self):
        result = list_builtin_formats()
        assert isinstance(result, list)

    def test_contains_expected_formats(self):
        result = list_builtin_formats()
        assert "luabridge3" in result

    def test_sorted(self):
        result = list_builtin_formats()
        assert result == sorted(result)

    def test_no_extension_in_names(self):
        for name in list_builtin_formats():
            assert not name.endswith(".yml")
            assert not name.endswith(".output")


class TestResolveFormatPath:
    @pytest.mark.parametrize("fmt", ["luabridge3"])
    def test_builtin_resolves_to_existing_file(self, fmt):
        path = resolve_format_path(fmt)
        assert isinstance(path, Path)
        assert path.exists()
        assert path.suffix == ".yml"

    def test_filesystem_path_resolves(self, tmp_path):
        yml = tmp_path / "custom.output.yml"
        yml.write_text("format_name: custom\ntemplates: {}\n", encoding="utf-8")
        result = resolve_format_path(str(yml))
        assert result == yml

    def test_unknown_name_raises(self):
        with pytest.raises(FileNotFoundError, match="Output format not found"):
            resolve_format_path("definitely_does_not_exist_xyz")

    def test_builtin_path_contains_format_name(self):
        path = resolve_format_path("luabridge3")
        assert "luabridge3" in path.name

    def test_extra_dir_resolution(self, tmp_path):
        fmt_file = tmp_path / "myfmt.output.yml"
        fmt_file.write_text("format_name: myfmt\ntemplates: {}\n", encoding="utf-8")
        result = resolve_format_path("myfmt", extra_dirs=[tmp_path])
        assert result == fmt_file

    def test_extra_dir_not_found_in_first_tries_second(self, tmp_path):
        """First extra dir lacks the file; second has it — covers the False branch of ``candidate.exists()``."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        fmt_file = dir2 / "myfmt2.output.yml"
        fmt_file.write_text("format_name: myfmt2\n", encoding="utf-8")
        result = resolve_format_path("myfmt2", extra_dirs=[dir1, dir2])
        assert result == fmt_file


# ---------------------------------------------------------------------------
# apply_format_inheritance
# ---------------------------------------------------------------------------

def _write_fmt(directory: Path, name: str, content: str) -> Path:
    f = directory / f"{name}.output.yml"
    f.write_text(content, encoding="utf-8")
    return f


class TestApplyFormatInheritance:
    def test_no_extends_returns_config_unchanged(self, tmp_path):
        _write_fmt(tmp_path, "plain", "format_name: plain\ntype_mappings:\n  'int': 'integer'\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "plain.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.type_mappings == {"int": "integer"}
        assert result.extends == ""

    def test_inherits_type_mappings_from_base(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\ntype_mappings:\n  'int': 'integer'\n  'float': 'number'\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\ntype_mappings:\n  'float': 'real'\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        # child wins on 'float', inherits 'int' from base
        assert result.type_mappings["int"] == "integer"
        assert result.type_mappings["float"] == "real"

    def test_inherits_operator_mappings_from_base(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\noperator_mappings:\n  'operator+': '__add'\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\noperator_mappings:\n  'operator-': '__sub'\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.operator_mappings["operator+"] == "__add"
        assert result.operator_mappings["operator-"] == "__sub"

    def test_inherits_unsupported_types_union(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\nunsupported_types:\n  - CFStringRef\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\nunsupported_types:\n  - MyOpaque\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert "MyOpaque" in result.unsupported_types
        assert "CFStringRef" in result.unsupported_types

    def test_child_unsupported_types_come_first(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\nunsupported_types:\n  - BaseType\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\nunsupported_types:\n  - ChildType\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.unsupported_types.index("ChildType") < result.unsupported_types.index("BaseType")

    def test_unsupported_types_deduplicated(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\nunsupported_types:\n  - Shared\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\nunsupported_types:\n  - Shared\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.unsupported_types.count("Shared") == 1

    def test_inherits_language_when_child_empty(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\nlanguage: cpp\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.language == "cpp"

    def test_child_language_takes_precedence(self, tmp_path):
        _write_fmt(tmp_path, "base", "format_name: base\nlanguage: cpp\n")
        _write_fmt(tmp_path, "child", "format_name: child\nextends: base\nlanguage: lua\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "child.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.language == "lua"

    def test_chained_inheritance(self, tmp_path):
        _write_fmt(tmp_path, "a", "format_name: a\ntype_mappings:\n  'int': 'integer'\n")
        _write_fmt(tmp_path, "b", "format_name: b\nextends: a\ntype_mappings:\n  'float': 'number'\n")
        _write_fmt(tmp_path, "c", "format_name: c\nextends: b\ntype_mappings:\n  'bool': 'boolean'\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "c.output.yml")
        result = apply_format_inheritance(cfg, extra_dirs=[tmp_path])
        assert result.type_mappings["int"] == "integer"
        assert result.type_mappings["float"] == "number"
        assert result.type_mappings["bool"] == "boolean"

    def test_circular_inheritance_raises(self, tmp_path):
        _write_fmt(tmp_path, "x", "format_name: x\nextends: y\n")
        _write_fmt(tmp_path, "y", "format_name: y\nextends: x\n")
        from tsujikiri.configurations import load_output_config
        cfg = load_output_config(tmp_path / "x.output.yml")
        with pytest.raises(ValueError, match="Circular format inheritance"):
            apply_format_inheritance(cfg, extra_dirs=[tmp_path])

    def test_extends_builtin_luabridge3(self):
        """A child format can extend the built-in luabridge3 format."""
        from tsujikiri.configurations import OutputConfig
        cfg = OutputConfig(
            format_name="mychild",
            extends="luabridge3",
            type_mappings={"MyStr": "string"},
        )
        result = apply_format_inheritance(cfg)
        # Inherits luabridge3 operator mappings
        assert "operator+" in result.operator_mappings
        # Child type mapping preserved
        assert result.type_mappings["MyStr"] == "string"
