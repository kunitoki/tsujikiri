"""Tests for configurations.py — YAML loading of InputConfig and OutputConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import (
    FilterPattern,
    FormatOverrideConfig,
    InputConfig,
    OutputConfig,
    SourceConfig,
    SourceEntry,
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
    @pytest.mark.parametrize("fmt", ["luabridge3"])
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

    def test_luabridge3_class_begin(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert "beginClass" in cfg.templates.class_begin

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

    def test_plain_string_pattern_in_yaml(self, tmp_path):
        """_parse_filter_pattern handles plain string entries (not dicts)."""
        yml = tmp_path / "plain.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\n"
            "filters:\n  classes:\n    blacklist:\n      - 'MyClass'\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        names = [p.pattern for p in cfg.filters.classes.blacklist]
        assert "MyClass" in names


class TestMultiSourceLoading:
    @pytest.fixture(scope="class")
    def cfg(self):
        return load_input_config(HERE / "multi.input.yml")

    def test_sources_list_populated(self, cfg):
        assert len(cfg.sources) == 2

    def test_no_single_source_field(self, cfg):
        assert cfg.source is None

    def test_get_source_entries_returns_sources(self, cfg):
        entries = cfg.get_source_entries()
        assert len(entries) == 2

    def test_first_source_parse_args(self, cfg):
        assert "-std=c++17" in cfg.sources[0].source.parse_args

    def test_second_source_parse_args(self, cfg):
        assert "-std=c++20" in cfg.sources[1].source.parse_args

    def test_first_source_has_per_source_filters(self, cfg):
        assert cfg.sources[0].filters is not None
        assert cfg.sources[0].filters.namespaces == ["myns"]

    def test_second_source_has_no_per_source_filters(self, cfg):
        assert cfg.sources[1].filters is None

    def test_second_source_has_per_source_transforms(self, cfg):
        assert cfg.sources[1].transforms is not None
        assert cfg.sources[1].transforms[0].stage == "suppress_class"

    def test_first_source_has_per_source_generation_includes(self, cfg):
        assert cfg.sources[0].generation is not None
        assert "<myns_extra.h>" in cfg.sources[0].generation.includes

    def test_top_level_filters_still_present(self, cfg):
        assert cfg.filters.namespaces == ["default_ns"]

    def test_top_level_generation(self, cfg):
        assert "<top_level.h>" in cfg.generation.includes
        assert cfg.generation.prefix == "// top prefix\n"

    def test_format_overrides_parsed(self, cfg):
        assert "luabridge3" in cfg.format_overrides

    def test_format_override_templates(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert "class_begin" in override.templates
        assert "custom" in override.templates["class_begin"]

    def test_format_override_super_in_template(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert "{super}" in override.templates["prologue"]

    def test_format_override_extra_unsupported_types(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert "MyOpaqueType" in override.unsupported_types

    def test_format_override_filters_parsed(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.filters is not None
        assert override.filters.namespaces == ["luans"]

    def test_format_override_filters_class_blacklist(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.filters is not None
        names = [p.pattern for p in override.filters.classes.blacklist]
        assert "LuaInternal" in names

    def test_format_override_transforms_parsed(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.transforms is not None
        assert len(override.transforms) == 1
        assert override.transforms[0].stage == "suppress_class"
        assert override.transforms[0].kwargs["pattern"] == "LuaUnused"

    def test_format_override_generation_parsed(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.generation is not None
        assert "<luabridge3_extra.h>" in override.generation.includes
        assert override.generation.prefix == "// lua prefix\n"
        assert override.generation.postfix == "// lua postfix\n"

    def test_format_override_no_filters_when_absent(self, cfg):
        # Only luabridge3 is defined; a missing key returns None filters
        override = cfg.format_overrides.get("luals")
        assert override is None


class TestGetSourceEntries:
    def test_single_source_normalised_to_list(self):
        cfg = InputConfig(source=SourceConfig(path="foo.hpp"))
        entries = cfg.get_source_entries()
        assert len(entries) == 1
        assert entries[0].source.path == "foo.hpp"

    def test_sources_list_takes_precedence(self):
        entry = SourceEntry(source=SourceConfig(path="bar.hpp"))
        cfg = InputConfig(sources=[entry])
        entries = cfg.get_source_entries()
        assert len(entries) == 1
        assert entries[0].source.path == "bar.hpp"

    def test_empty_config_returns_empty(self):
        cfg = InputConfig()
        assert cfg.get_source_entries() == []
