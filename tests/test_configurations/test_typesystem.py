"""Tests for TypesystemConfig parsing in configurations.py."""

from __future__ import annotations

from pathlib import Path

from tsujikiri.configurations import (
    ContainerTypeEntry,
    ConversionRuleEntry,
    CustomTypeEntry,
    FormatOverrideConfig,
    PrimitiveTypeEntry,
    TypedefTypeEntry,
    TypesystemConfig,
    load_input_config,
)


class TestTypesystemDefaults:
    def test_typesystem_empty_by_default(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text("source:\n  path: test.hpp\n")
        config = load_input_config(cfg)
        assert isinstance(config.typesystem, TypesystemConfig)
        assert config.typesystem.primitive_types == []
        assert config.typesystem.typedef_types == []
        assert config.typesystem.custom_types == []
        assert config.typesystem.container_types == []
        assert config.typesystem.smart_pointer_types == []


class TestPrimitiveTypes:
    def test_primitive_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            '    - cpp_name: "int64_t"\n'
            '      target_name: "int"\n'
            '    - cpp_name: "double"\n'
            '      target_name: "float"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.primitive_types) == 2
        assert config.typesystem.primitive_types[0] == PrimitiveTypeEntry(cpp_name="int64_t", target_name="int")
        assert config.typesystem.primitive_types[1] == PrimitiveTypeEntry(cpp_name="double", target_name="float")


class TestTypedefTypes:
    def test_typedef_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  typedef_types:\n"
            '    - cpp_name: "MyString"\n'
            '      target_name: "std::string"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.typedef_types) == 1
        assert config.typesystem.typedef_types[0] == TypedefTypeEntry(cpp_name="MyString", target_name="std::string")


class TestCustomTypes:
    def test_custom_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  custom_types:\n"
            '    - cpp_name: "QObject"\n'
            '    - cpp_name: "PyObject"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.custom_types) == 2
        assert config.typesystem.custom_types[0] == CustomTypeEntry(cpp_name="QObject")
        assert config.typesystem.custom_types[1] == CustomTypeEntry(cpp_name="PyObject")


class TestContainerTypes:
    def test_container_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  container_types:\n"
            '    - cpp_name: "std::vector"\n'
            '      kind: "list"\n'
            '    - cpp_name: "std::map"\n'
            '      kind: "map"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.container_types) == 2
        assert config.typesystem.container_types[0] == ContainerTypeEntry(cpp_name="std::vector", kind="list")
        assert config.typesystem.container_types[1] == ContainerTypeEntry(cpp_name="std::map", kind="map")


class TestSmartPointerTypes:
    def test_smart_pointer_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  smart_pointer_types:\n"
            '    - cpp_name: "std::shared_ptr"\n'
            '      kind: "shared"\n'
            '      getter: "get"\n'
            '    - cpp_name: "std::unique_ptr"\n'
            '      kind: "unique"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.smart_pointer_types) == 2
        first = config.typesystem.smart_pointer_types[0]
        assert first.cpp_name == "std::shared_ptr"
        assert first.kind == "shared"
        assert first.getter == "get"
        second = config.typesystem.smart_pointer_types[1]
        assert second.getter == "get"  # default


class TestFormatOverrideTypesystem:
    def test_typesystem_absent_gives_none(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    unsupported_types: []\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].typesystem is None

    def test_inline_typesystem_parsed(self, tmp_path: Path) -> None:
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\n"
            "format_overrides:\n"
            "  luabridge3:\n"
            "    typesystem:\n"
            "      primitive_types:\n"
            "        - { cpp_name: juce::String, target_name: str }\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        ts = cfg.format_overrides["luabridge3"].typesystem
        assert ts is not None
        assert len(ts.primitive_types) == 1
        assert ts.primitive_types[0].cpp_name == "juce::String"
        assert ts.primitive_types[0].target_name == "str"

    def test_typesystem_file_loads_from_external_file(self, tmp_path: Path) -> None:
        ts_file = tmp_path / "lua_types.input.yml"
        ts_file.write_text(
            "typesystem:\n  primitive_types:\n    - { cpp_name: juce::String, target_name: str }\n",
            encoding="utf-8",
        )
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    typesystem_file: lua_types.input.yml\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        ts = cfg.format_overrides["luabridge3"].typesystem
        assert ts is not None
        assert ts.primitive_types[0].cpp_name == "juce::String"

    def test_typesystem_file_standalone_no_wrapper_key(self, tmp_path: Path) -> None:
        ts_file = tmp_path / "types.yml"
        ts_file.write_text(
            "primitive_types:\n  - { cpp_name: MyInt, target_name: int }\n",
            encoding="utf-8",
        )
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    typesystem_file: types.yml\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        ts = cfg.format_overrides["luabridge3"].typesystem
        assert ts is not None
        assert ts.primitive_types[0].cpp_name == "MyInt"

    def test_typesystem_file_takes_precedence_over_inline(self, tmp_path: Path) -> None:
        ts_file = tmp_path / "ext.input.yml"
        ts_file.write_text(
            "typesystem:\n  primitive_types:\n    - { cpp_name: FromFile, target_name: file }\n",
            encoding="utf-8",
        )
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\n"
            "format_overrides:\n"
            "  luabridge3:\n"
            "    typesystem_file: ext.input.yml\n"
            "    typesystem:\n"
            "      primitive_types:\n"
            "        - { cpp_name: FromInline, target_name: inline }\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        ts = cfg.format_overrides["luabridge3"].typesystem
        assert ts is not None
        names = [e.cpp_name for e in ts.primitive_types]
        assert "FromFile" in names
        assert "FromInline" not in names

    def test_typesystem_file_absolute_path(self, tmp_path: Path) -> None:
        ts_file = tmp_path / "abs.input.yml"
        ts_file.write_text(
            "typesystem:\n  custom_types:\n    - { cpp_name: AbsType }\n",
            encoding="utf-8",
        )
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            f"source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    typesystem_file: {ts_file}\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        ts = cfg.format_overrides["luabridge3"].typesystem
        assert ts is not None
        assert ts.custom_types[0].cpp_name == "AbsType"

    def test_typesystem_file_field_stored(self, tmp_path: Path) -> None:
        ts_file = tmp_path / "stored.input.yml"
        ts_file.write_text("typesystem:\n  custom_types:\n    - { cpp_name: X }\n", encoding="utf-8")
        yml = tmp_path / "x.input.yml"
        yml.write_text(
            "source:\n  path: x.h\nformat_overrides:\n  luabridge3:\n    typesystem_file: stored.input.yml\n",
            encoding="utf-8",
        )
        cfg = load_input_config(yml)
        assert cfg.format_overrides["luabridge3"].typesystem_file == "stored.input.yml"

    def test_format_override_config_defaults(self) -> None:
        override = FormatOverrideConfig()
        assert override.typesystem is None
        assert override.typesystem_file == ""


class TestDeclaredFunctions:
    def test_declared_functions_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  declared_functions:\n"
            '    - name: "myWrapper"\n'
            '      namespace: "mylib"\n'
            '      return_type: "void"\n'
            "      parameters:\n"
            '        - name: "x"\n'
            '          type: "int"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.declared_functions) == 1
        fn = config.typesystem.declared_functions[0]
        assert fn.name == "myWrapper"
        assert fn.namespace == "mylib"
        assert fn.return_type == "void"
        assert fn.parameters[0]["name"] == "x"
        assert fn.parameters[0]["type"] == "int"

    def test_declared_functions_defaults(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text('source:\n  path: test.hpp\ntypesystem:\n  declared_functions:\n    - name: "bare"\n')
        config = load_input_config(cfg)
        fn = config.typesystem.declared_functions[0]
        assert fn.namespace == ""
        assert fn.return_type == "void"
        assert fn.parameters == []
        assert fn.wrapper_code is None


class TestConversionRules:
    def test_conversion_rules_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  conversion_rules:\n"
            '    - cpp_type: "MyColor"\n'
            '      native_to_target: "PyLong_FromLong(static_cast<long>(%%in))"\n'
            '      target_to_native: "static_cast<MyColor>(PyLong_AsLong(%%in))"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.conversion_rules) == 1
        rule = config.typesystem.conversion_rules[0]
        assert rule.cpp_type == "MyColor"
        assert "PyLong_FromLong" in rule.native_to_target
        assert "PyLong_AsLong" in rule.target_to_native

    def test_conversion_rules_empty_by_default(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text("source:\n  path: test.hpp\n")
        config = load_input_config(cfg)
        assert config.typesystem.conversion_rules == []

    def test_conversion_rules_multiple(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  conversion_rules:\n"
            '    - cpp_type: "MyColor"\n'
            '      native_to_target: "convert_color(%%in)"\n'
            '      target_to_native: "from_color(%%in)"\n'
            '    - cpp_type: "MyRect"\n'
            '      native_to_target: "convert_rect(%%in)"\n'
            '      target_to_native: "from_rect(%%in)"\n'
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.conversion_rules) == 2
        assert config.typesystem.conversion_rules[0] == ConversionRuleEntry(
            cpp_type="MyColor",
            native_to_target="convert_color(%%in)",
            target_to_native="from_color(%%in)",
        )
        assert config.typesystem.conversion_rules[1].cpp_type == "MyRect"


class TestMergeTypesystems:
    def test_priority_entries_come_first(self) -> None:
        from tsujikiri.configurations import merge_typesystems

        priority = TypesystemConfig(primitive_types=[PrimitiveTypeEntry("A", "a")])
        base = TypesystemConfig(primitive_types=[PrimitiveTypeEntry("B", "b")])
        merged = merge_typesystems(priority, base)
        assert [e.cpp_name for e in merged.primitive_types] == ["A", "B"]

    def test_priority_wins_first_match_on_same_cpp_name(self) -> None:
        from tsujikiri.configurations import merge_typesystems

        priority = TypesystemConfig(primitive_types=[PrimitiveTypeEntry("X", "priority")])
        base = TypesystemConfig(primitive_types=[PrimitiveTypeEntry("X", "base")])
        merged = merge_typesystems(priority, base)
        assert merged.primitive_types[0].target_name == "priority"

    def test_empty_priority_returns_base_entries(self) -> None:
        from tsujikiri.configurations import merge_typesystems

        priority = TypesystemConfig()
        base = TypesystemConfig(primitive_types=[PrimitiveTypeEntry("B", "b")])
        merged = merge_typesystems(priority, base)
        assert merged.primitive_types[0].cpp_name == "B"

    def test_all_fields_merged(self) -> None:
        from tsujikiri.configurations import (
            ContainerTypeEntry,
            ConversionRuleEntry,
            CustomTypeEntry,
            DeclaredFunctionEntry,
            SmartPointerTypeEntry,
            TypedefTypeEntry,
            merge_typesystems,
        )

        priority = TypesystemConfig(
            primitive_types=[PrimitiveTypeEntry("P", "p")],
            typedef_types=[TypedefTypeEntry("PT", "P")],
            custom_types=[CustomTypeEntry("PC")],
            container_types=[ContainerTypeEntry("PVec", "list")],
            smart_pointer_types=[SmartPointerTypeEntry("PSP", "shared")],
            declared_functions=[DeclaredFunctionEntry("pfn")],
            conversion_rules=[ConversionRuleEntry("PT2", "a", "b")],
        )
        base = TypesystemConfig(
            primitive_types=[PrimitiveTypeEntry("B", "b")],
            typedef_types=[TypedefTypeEntry("BT", "B")],
            custom_types=[CustomTypeEntry("BC")],
            container_types=[ContainerTypeEntry("BVec", "list")],
            smart_pointer_types=[SmartPointerTypeEntry("BSP", "shared")],
            declared_functions=[DeclaredFunctionEntry("bfn")],
            conversion_rules=[ConversionRuleEntry("BT2", "c", "d")],
        )
        merged = merge_typesystems(priority, base)
        assert len(merged.primitive_types) == 2
        assert len(merged.typedef_types) == 2
        assert len(merged.custom_types) == 2
        assert len(merged.container_types) == 2
        assert len(merged.smart_pointer_types) == 2
        assert len(merged.declared_functions) == 2
        assert len(merged.conversion_rules) == 2
