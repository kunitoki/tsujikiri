"""Tests for configurations.py — YAML loading of InputConfig and OutputConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import (
    FilterPattern,
    InputConfig,
    OutputConfig,
    SourceConfig,
    TemplateSet,
    load_input_config,
    load_output_config,
)
from tsujikiri.formats import resolve_format_path

HERE = Path(__file__).parent


class TestInputConfigLoading:
    @pytest.fixture(scope="class")
    def cfg(self):
        return load_input_config(HERE / "simple.input.yml")

    def test_source_path(self, cfg):
        assert "simple.hpp" in cfg.source.path

    def test_parse_args(self, cfg):
        assert "-std=c++17" in cfg.source.parse_args

    def test_namespaces(self, cfg):
        assert cfg.filters.namespaces == ["myns"]

    def test_source_exclude_patterns(self, cfg):
        assert "*.mm" in cfg.filters.sources.exclude_patterns

    def test_class_blacklist(self, cfg):
        names = [p.pattern for p in cfg.filters.classes.blacklist]
        assert "Private" in names

    def test_class_blacklist_regex(self, cfg):
        regex_patterns = [p for p in cfg.filters.classes.blacklist if p.is_regex]
        assert any(p.pattern == ".*Impl$" for p in regex_patterns)

    def test_class_internal(self, cfg):
        assert any(p.pattern == "BaseHelper" for p in cfg.filters.classes.internal)

    def test_method_global_blacklist_regex(self, cfg):
        patterns = cfg.filters.methods.global_blacklist
        assert any(p.pattern == "operator.*" and p.is_regex for p in patterns)

    def test_method_per_class(self, cfg):
        assert "Foo" in cfg.filters.methods.per_class
        assert any(p.pattern == "internalReset" for p in cfg.filters.methods.per_class["Foo"])

    def test_field_blacklist(self, cfg):
        assert any(p.pattern == "pimpl_" for p in cfg.filters.fields.global_blacklist)

    def test_constructors_include(self, cfg):
        assert cfg.filters.constructors.include is True

    def test_function_blacklist(self, cfg):
        assert any(p.pattern == "detail_helper" for p in cfg.filters.functions.blacklist)

    def test_enum_blacklist(self, cfg):
        assert any(p.pattern == "InternalState" for p in cfg.filters.enums.blacklist)

    def test_transforms(self, cfg):
        assert len(cfg.transforms) == 2
        assert cfg.transforms[0].stage == "rename_method"
        assert cfg.transforms[0].kwargs["from"] == "getValue"
        assert cfg.transforms[0].kwargs["to"] == "get"
        assert cfg.transforms[1].stage == "suppress_class"

    def test_tweaks(self, cfg):
        assert "Foo" in cfg.tweaks
        assert cfg.tweaks["Foo"].rename == "FooExported"
        assert "legacyApi" in cfg.tweaks["Foo"].skip_methods


class TestOutputConfigLoading:
    @pytest.mark.parametrize("fmt", ["luabridge3", "pybind11", "c_api"])
    def test_loads_without_error(self, fmt):
        cfg = load_output_config(resolve_format_path(fmt))
        assert isinstance(cfg, OutputConfig)
        assert cfg.format_name == fmt

    def test_luabridge3_has_unsupported_types(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert "CFStringRef" in cfg.unsupported_types
        assert "OSType" in cfg.unsupported_types

    def test_luabridge3_prologue_not_empty(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert cfg.templates.prologue.strip() != ""

    def test_pybind11_class_begin(self):
        cfg = load_output_config(resolve_format_path("pybind11"))
        assert "py::class_" in cfg.templates.class_begin

    def test_c_api_class_begin(self):
        cfg = load_output_config(resolve_format_path("c_api"))
        assert "typedef struct" in cfg.templates.class_begin

    def test_template_set_defaults(self):
        ts = TemplateSet()
        assert ts.prologue == ""
        assert ts.class_begin == ""

    def test_source_config_defaults(self):
        sc = SourceConfig(path="foo.hpp")
        assert sc.parse_args == []
        assert sc.include_paths == []

    def test_filter_pattern_plain(self):
        fp = FilterPattern(pattern="MyClass")
        assert not fp.is_regex

    def test_filter_pattern_regex(self):
        fp = FilterPattern(pattern=".*Impl$", is_regex=True)
        assert fp.is_regex
