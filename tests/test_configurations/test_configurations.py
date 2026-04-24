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

    def test_luabridge3_template_not_empty(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert cfg.template.strip() != ""

    def test_luabridge3_template_has_begin_class(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert "beginClass" in cfg.template

    def test_luabridge3_language_is_cpp(self):
        cfg = load_output_config(resolve_format_path("luabridge3"))
        assert cfg.language == "cpp"

    def test_luals_language_is_lua(self):
        cfg = load_output_config(resolve_format_path("luals"))
        assert cfg.language == "lua"

    def test_language_defaults_to_empty_string(self, tmp_path):
        yml = tmp_path / "nolang.output.yml"
        yml.write_text("format_name: nolang\ntemplate: |\n  NOOP\n", encoding="utf-8")
        cfg = load_output_config(yml)
        assert cfg.language == ""

    def test_template_file_relative_path(self, tmp_path):
        tpl = tmp_path / "my.tpl"
        tpl.write_text("TEMPLATE_CONTENT\n", encoding="utf-8")
        yml = tmp_path / "test.output.yml"
        yml.write_text("format_name: test\ntemplate_file: my.tpl\n", encoding="utf-8")
        cfg = load_output_config(yml)
        assert cfg.template == "TEMPLATE_CONTENT\n"

    def test_template_file_absolute_path(self, tmp_path):
        tpl = tmp_path / "abs.tpl"
        tpl.write_text("ABS_CONTENT\n", encoding="utf-8")
        yml = tmp_path / "test.output.yml"
        yml.write_text(f"format_name: test\ntemplate_file: {tpl}\n", encoding="utf-8")
        cfg = load_output_config(yml)
        assert cfg.template == "ABS_CONTENT\n"

    def test_template_file_overrides_inline_template(self, tmp_path):
        tpl = tmp_path / "override.tpl"
        tpl.write_text("FROM_FILE\n", encoding="utf-8")
        yml = tmp_path / "test.output.yml"
        yml.write_text("format_name: test\ntemplate: |\n  INLINE\ntemplate_file: override.tpl\n", encoding="utf-8")
        cfg = load_output_config(yml)
        assert cfg.template == "FROM_FILE\n"

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
            "source:\n  path: 'dummy.hpp'\nfilters:\n  classes:\n    blacklist:\n      - 'MyClass'\n",
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

    def test_format_override_template_extends_set(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.template_extends != ""
        assert "custom" in override.template_extends

    def test_format_override_template_extends_has_super(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert "super()" in override.template_extends

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

    def test_format_override_pretty_parsed(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.pretty is True

    def test_format_override_pretty_options_parsed(self, cfg):
        override = cfg.format_overrides["luabridge3"]
        assert override.pretty_options == ["--style=LLVM"]


class TestPrettyFields:
    def test_pretty_defaults_to_false(self, tmp_path):
        yml = tmp_path / "noformat.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.pretty is False

    def test_pretty_options_defaults_to_empty(self, tmp_path):
        yml = tmp_path / "noformat.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.pretty_options == []

    def test_pretty_true_parsed(self, tmp_path):
        yml = tmp_path / "withformat.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\npretty: true\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.pretty is True

    def test_pretty_false_explicit(self, tmp_path):
        yml = tmp_path / "noformat2.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\npretty: false\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.pretty is False

    def test_pretty_options_parsed(self, tmp_path):
        yml = tmp_path / "fmtopts.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\n"
            "pretty: true\n"
            "pretty_options:\n  - '--style=Google'\n  - '--sort-includes'\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert "--style=Google" in cfg.pretty_options
        assert "--sort-includes" in cfg.pretty_options


class TestSystemIncludePaths:
    def test_source_config_system_include_paths(self, tmp_path: Path) -> None:
        yaml_text = (
            "source:\n"
            "  path: test.hpp\n"
            "  system_include_paths:\n"
            "    - /usr/include/mylib\n"
            "    - /opt/frameworks/include\n"
        )
        cfg_path = tmp_path / "test.input.yml"
        cfg_path.write_text(yaml_text)
        config = load_input_config(cfg_path)
        assert config.source is not None
        assert config.source.system_include_paths == [
            "/usr/include/mylib",
            "/opt/frameworks/include",
        ]

    def test_system_include_paths_defaults_empty(self) -> None:
        cfg = SourceConfig(path="foo.hpp")
        assert cfg.system_include_paths == []


class TestFormatOverrideTemplateExtendsFile:
    def test_template_extends_file_loads_content(self, tmp_path: Path) -> None:
        tpl_file = tmp_path / "override.tpl"
        tpl_file.write_text('{% extends "luabridge3.tpl" %}', encoding="utf-8")
        inp = tmp_path / "x.input.yml"
        inp.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    template_extends_file: override.tpl\n",
            encoding="utf-8",
        )
        cfg = load_input_config(inp)
        override = cfg.format_overrides["luabridge3"]
        assert '{% extends "luabridge3.tpl" %}' in override.template_extends

    def test_template_extends_file_absolute_path(self, tmp_path: Path) -> None:
        tpl_file = tmp_path / "abs.tpl"
        tpl_file.write_text("// ABSOLUTE", encoding="utf-8")
        inp = tmp_path / "y.input.yml"
        inp.write_text(
            f"source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    template_extends_file: {tpl_file}\n",
            encoding="utf-8",
        )
        cfg = load_input_config(inp)
        assert "// ABSOLUTE" in cfg.format_overrides["luabridge3"].template_extends

    def test_template_extends_file_overrides_inline(self, tmp_path: Path) -> None:
        tpl_file = tmp_path / "file.tpl"
        tpl_file.write_text("// FROM FILE", encoding="utf-8")
        inp = tmp_path / "z.input.yml"
        inp.write_text(
            "source:\n  path: x.h\n"
            "format_overrides:\n"
            "  luabridge3:\n"
            "    template_extends: '// INLINE'\n"
            "    template_extends_file: file.tpl\n",
            encoding="utf-8",
        )
        cfg = load_input_config(inp)
        assert "// FROM FILE" in cfg.format_overrides["luabridge3"].template_extends
        assert "// INLINE" not in cfg.format_overrides["luabridge3"].template_extends

    def test_template_extends_file_field_stored(self, tmp_path: Path) -> None:
        tpl_file = tmp_path / "stored.tpl"
        tpl_file.write_text("x", encoding="utf-8")
        inp = tmp_path / "s.input.yml"
        inp.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    template_extends_file: stored.tpl\n",
            encoding="utf-8",
        )
        cfg = load_input_config(inp)
        assert cfg.format_overrides["luabridge3"].template_extends_file == "stored.tpl"


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


class TestCustomDataLoading:
    def test_absent_key_yields_empty_dict(self, tmp_path):
        yml = tmp_path / "no_custom.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.custom_data == {}

    def test_null_value_yields_empty_dict(self, tmp_path):
        yml = tmp_path / "null_custom.input.yml"
        yml.write_text("source:\n  path: 'dummy.hpp'\ncustom_data:\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.custom_data == {}

    def test_scalar_int(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  xyz: 1\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.custom_data["xyz"] == 1

    def test_scalar_float(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  ratio: 42.1337\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert abs(cfg.custom_data["ratio"] - 42.1337) < 1e-9

    def test_scalar_bool(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  flag: true\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.custom_data["flag"] is True

    def test_scalar_string(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  label: hello\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.custom_data["label"] == "hello"

    def test_list_value(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  abc:\n    - a\n    - b\n    - c\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.custom_data["abc"] == ["a", "b", "c"]

    def test_nested_dict(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        yml.write_text(
            "source:\n  path: 'dummy.hpp'\ncustom_data:\n  nested:\n    x: 10\n    y: 20\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.custom_data["nested"] == {"x": 10, "y": 20}

    def test_mixed_types(self, tmp_path):
        yml = tmp_path / "custom.input.yml"
        content = (
            "source:\n  path: 'dummy.hpp'\n"
            "custom_data:\n"
            "  xyz: 1\n"
            "  abc:\n    - a\n    - b\n    - c\n"
            "  something_else: true\n"
            "  something_new: 42.1337\n"
        )
        yml.write_text(content, encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.custom_data["xyz"] == 1
        assert cfg.custom_data["abc"] == ["a", "b", "c"]
        assert cfg.custom_data["something_else"] is True
        assert abs(cfg.custom_data["something_new"] - 42.1337) < 1e-9

    def test_default_field_is_empty_dict(self):
        cfg = InputConfig()
        assert cfg.custom_data == {}


class TestFormatOverridePretty:
    def test_pretty_absent_gives_none(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    unsupported_types: []\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].pretty is None

    def test_pretty_true_parsed(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    pretty: true\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].pretty is True

    def test_pretty_false_parsed(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    pretty: false\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        # False must not be confused with absent (None)
        assert cfg.format_overrides["luabridge3"].pretty is False

    def test_pretty_options_absent_gives_none(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    unsupported_types: []\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].pretty_options is None

    def test_pretty_options_parsed(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    pretty_options:\n      - '--style=Google'\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].pretty_options == ["--style=Google"]

    def test_pretty_defaults_to_none_on_direct_construction(self) -> None:
        override = FormatOverrideConfig()
        assert override.pretty is None
        assert override.pretty_options is None


class TestConfigLoads:
    def test_no_loads_loads_normally(self, tmp_path: Path) -> None:
        yml = tmp_path / "plain.input.yml"
        yml.write_text("source:\n  path: plain.hpp\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.source is not None
        assert "plain.hpp" in cfg.source.path

    def test_empty_loads_list(self, tmp_path: Path) -> None:
        yml = tmp_path / "empty.input.yml"
        yml.write_text("loads: []\nsource:\n  path: empty.hpp\n", encoding="utf-8")
        cfg = load_input_config(yml)
        assert cfg.source is not None

    def test_loaded_source_appears_when_child_has_none(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: base.hpp\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.source is not None
        assert "base.hpp" in cfg.source.path

    def test_child_source_wins_over_loaded(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: base.hpp\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\nsource:\n  path: child.hpp\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.source is not None
        assert "child.hpp" in cfg.source.path

    def test_loaded_sources_list_prepended(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("sources:\n  - path: base.hpp\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\nsources:\n  - path: child.hpp\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert len(cfg.sources) == 2
        assert "base.hpp" in cfg.sources[0].source.path
        assert "child.hpp" in cfg.sources[1].source.path

    def test_loaded_transforms_prepended(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: b.hpp\ntransforms:\n  - stage: suppress_class\n    pattern: Base\n",
            encoding="utf-8",
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\n"
            "transforms:\n  - stage: suppress_class\n    pattern: Child\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        assert len(cfg.transforms) == 2
        assert cfg.transforms[0].kwargs["pattern"] == "Base"
        assert cfg.transforms[1].kwargs["pattern"] == "Child"

    def test_loaded_scalar_provides_default(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: b.hpp\npretty: true\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\nsource:\n  path: c.hpp\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.pretty is True

    def test_child_scalar_wins_over_loaded(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: b.hpp\npretty: true\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\nsource:\n  path: c.hpp\npretty: false\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.pretty is False

    def test_loaded_filters_namespaces_merged(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: b.hpp\nfilters:\n  namespaces:\n    - base_ns\n",
            encoding="utf-8",
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\nfilters:\n  namespaces:\n    - child_ns\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        assert "base_ns" in cfg.filters.namespaces
        assert "child_ns" in cfg.filters.namespaces
        assert cfg.filters.namespaces.index("base_ns") < cfg.filters.namespaces.index("child_ns")

    def test_loaded_generation_includes_prepended(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: b.hpp\ngeneration:\n  includes:\n    - '<base.h>'\n",
            encoding="utf-8",
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\ngeneration:\n  includes:\n    - '<child.h>'\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        assert "<base.h>" in cfg.generation.includes
        assert "<child.h>" in cfg.generation.includes
        assert cfg.generation.includes.index("<base.h>") < cfg.generation.includes.index("<child.h>")

    def test_loaded_custom_data_merged(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: b.hpp\ncustom_data:\n  from_base: 1\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\ncustom_data:\n  from_child: 2\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        assert cfg.custom_data["from_base"] == 1
        assert cfg.custom_data["from_child"] == 2

    def test_child_custom_data_wins_on_collision(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: b.hpp\ncustom_data:\n  key: base_val\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\ncustom_data:\n  key: child_val\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        assert cfg.custom_data["key"] == "child_val"

    def test_multiple_loads_order_preserved(self, tmp_path: Path) -> None:
        a = tmp_path / "a.input.yml"
        a.write_text(
            "source:\n  path: a.hpp\ntransforms:\n  - stage: suppress_class\n    pattern: A\n", encoding="utf-8"
        )
        b = tmp_path / "b.input.yml"
        b.write_text(
            "source:\n  path: b.hpp\ntransforms:\n  - stage: suppress_class\n    pattern: B\n", encoding="utf-8"
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - a.input.yml\n  - b.input.yml\nsource:\n  path: c.hpp\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        patterns = [t.kwargs["pattern"] for t in cfg.transforms]
        assert patterns == ["A", "B"]

    def test_nested_loads(self, tmp_path: Path) -> None:
        common = tmp_path / "common.input.yml"
        common.write_text("source:\n  path: common.hpp\ncustom_data:\n  level: common\n", encoding="utf-8")
        middle = tmp_path / "middle.input.yml"
        middle.write_text(
            "loads:\n  - common.input.yml\nsource:\n  path: middle.hpp\ncustom_data:\n  mid: true\n",
            encoding="utf-8",
        )
        top = tmp_path / "top.input.yml"
        top.write_text(
            "loads:\n  - middle.input.yml\nsource:\n  path: top.hpp\n",
            encoding="utf-8",
        )
        cfg = load_input_config(top)
        assert "top.hpp" in cfg.source.path
        assert cfg.custom_data["level"] == "common"
        assert cfg.custom_data["mid"] is True

    def test_cycle_detection_no_infinite_loop(self, tmp_path: Path) -> None:
        a = tmp_path / "a.input.yml"
        b = tmp_path / "b.input.yml"
        a.write_text("loads:\n  - b.input.yml\nsource:\n  path: a.hpp\n", encoding="utf-8")
        b.write_text("loads:\n  - a.input.yml\nsource:\n  path: b.hpp\n", encoding="utf-8")
        cfg = load_input_config(a)
        assert "a.hpp" in cfg.source.path

    def test_self_loads_cycle_detection(self, tmp_path: Path) -> None:
        a = tmp_path / "self.input.yml"
        a.write_text("loads:\n  - self.input.yml\nsource:\n  path: self.hpp\n", encoding="utf-8")
        cfg = load_input_config(a)
        assert "self.hpp" in cfg.source.path

    def test_relative_path_resolved_from_loading_file(self, tmp_path: Path) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        base = subdir / "base.input.yml"
        base.write_text("source:\n  path: sub.hpp\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - sub/base.input.yml\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.source is not None
        assert "sub.hpp" in cfg.source.path

    def test_loaded_typesystem_merged(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: b.hpp\ntypesystem:\n  primitive_types:\n    - { cpp_name: int32_t, target_name: int }\n",
            encoding="utf-8",
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "loads:\n  - base.input.yml\nsource:\n  path: c.hpp\n",
            encoding="utf-8",
        )
        cfg = load_input_config(child)
        names = [e.cpp_name for e in cfg.typesystem.primitive_types]
        assert "int32_t" in names

    def test_loads_key_not_in_resulting_config(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: b.hpp\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text("loads:\n  - base.input.yml\nsource:\n  path: c.hpp\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert not hasattr(cfg, "loads")

    def test_absolute_loads_path(self, tmp_path: Path) -> None:
        base = tmp_path / "abs_base.input.yml"
        base.write_text("source:\n  path: abs.hpp\ncustom_data:\n  abs: true\n", encoding="utf-8")
        child = tmp_path / "child.input.yml"
        child.write_text(f"loads:\n  - {base}\nsource:\n  path: c.hpp\n", encoding="utf-8")
        cfg = load_input_config(child)
        assert cfg.custom_data["abs"] is True
