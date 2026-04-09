"""Tests for formats/__init__.py — built-in format discovery and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.formats import list_builtin_formats, resolve_format_path


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
