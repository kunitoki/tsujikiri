"""Tests for TypesystemConfig parsing in configurations.py."""

from __future__ import annotations

from pathlib import Path

from tsujikiri.configurations import (
    ContainerTypeEntry,
    ConversionRuleEntry,
    CustomTypeEntry,
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
        assert config.typesystem.load_typesystems == []


class TestPrimitiveTypes:
    def test_primitive_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"int64_t\"\n"
            "      python_name: \"int\"\n"
            "    - cpp_name: \"double\"\n"
            "      python_name: \"float\"\n"
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.primitive_types) == 2
        assert config.typesystem.primitive_types[0] == PrimitiveTypeEntry(cpp_name="int64_t", python_name="int")
        assert config.typesystem.primitive_types[1] == PrimitiveTypeEntry(cpp_name="double", python_name="float")


class TestTypedefTypes:
    def test_typedef_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  typedef_types:\n"
            "    - cpp_name: \"MyString\"\n"
            "      source: \"std::string\"\n"
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.typedef_types) == 1
        assert config.typesystem.typedef_types[0] == TypedefTypeEntry(cpp_name="MyString", source="std::string")


class TestCustomTypes:
    def test_custom_types_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  custom_types:\n"
            "    - cpp_name: \"QObject\"\n"
            "    - cpp_name: \"PyObject\"\n"
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
            "    - cpp_name: \"std::vector\"\n"
            "      kind: \"list\"\n"
            "    - cpp_name: \"std::map\"\n"
            "      kind: \"map\"\n"
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
            "    - cpp_name: \"std::shared_ptr\"\n"
            "      kind: \"shared\"\n"
            "      getter: \"get\"\n"
            "    - cpp_name: \"std::unique_ptr\"\n"
            "      kind: \"unique\"\n"
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.smart_pointer_types) == 2
        first = config.typesystem.smart_pointer_types[0]
        assert first.cpp_name == "std::shared_ptr"
        assert first.kind == "shared"
        assert first.getter == "get"
        second = config.typesystem.smart_pointer_types[1]
        assert second.getter == "get"  # default


class TestLoadTypesystems:
    def test_load_typesystems_entry_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  load_typesystems:\n"
            "    - path: \"other.input.yml\"\n"
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.load_typesystems) == 1
        assert "other.input.yml" in config.typesystem.load_typesystems[0].path

    def test_merges_entries_from_loaded_typesystem(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: base.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"int64_t\"\n"
            "      python_name: \"int\"\n"
            "  custom_types:\n"
            "    - cpp_name: \"QObject\"\n"
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "source:\n  path: child.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"float\"\n"
            "      python_name: \"float\"\n"
            "  load_typesystems:\n"
            "    - path: base.input.yml\n"
        )
        config = load_input_config(child)
        prim_names = [p.cpp_name for p in config.typesystem.primitive_types]
        assert "float" in prim_names
        assert "int64_t" in prim_names
        custom_names = [c.cpp_name for c in config.typesystem.custom_types]
        assert "QObject" in custom_names

class TestDeclaredFunctions:
    def test_declared_functions_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  declared_functions:\n"
            "    - name: \"myWrapper\"\n"
            "      namespace: \"mylib\"\n"
            "      return_type: \"void\"\n"
            "      parameters:\n"
            "        - name: \"x\"\n"
            "          type: \"int\"\n"
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
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  declared_functions:\n"
            "    - name: \"bare\"\n"
        )
        config = load_input_config(cfg)
        fn = config.typesystem.declared_functions[0]
        assert fn.namespace == ""
        assert fn.return_type == "void"
        assert fn.parameters == []
        assert fn.wrapper_code is None


class TestLoadTypesystemsComposition:
    def test_local_wins_on_collision(self, tmp_path: Path) -> None:
        base = tmp_path / "base.input.yml"
        base.write_text(
            "source:\n  path: base.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"int64_t\"\n"
            "      python_name: \"int\"\n"
        )
        child = tmp_path / "child.input.yml"
        child.write_text(
            "source:\n  path: child.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"int64_t\"\n"
            "      python_name: \"long\"\n"
            "  load_typesystems:\n"
            "    - path: base.input.yml\n"
        )
        config = load_input_config(child)
        entry = next(p for p in config.typesystem.primitive_types if p.cpp_name == "int64_t")
        assert entry.python_name == "long"  # local wins over loaded


class TestLoadTypesystemNoTypesystemSection:
    def test_load_typesystem_file_without_typesystem_key_is_silently_ignored(
        self, tmp_path: Path
    ) -> None:
        """configurations.py branch 480->475: loaded file has no 'typesystem' key → silently skipped."""
        base = tmp_path / "base.input.yml"
        base.write_text("source:\n  path: base.hpp\n")  # no typesystem section
        child = tmp_path / "child.input.yml"
        child.write_text(
            "source:\n  path: child.hpp\n"
            "typesystem:\n"
            "  primitive_types:\n"
            "    - cpp_name: \"int\"\n"
            "      python_name: \"int\"\n"
            "  load_typesystems:\n"
            "    - path: base.input.yml\n"
        )
        config = load_input_config(child)
        # base has no typesystem, child's own entries survive
        assert len(config.typesystem.primitive_types) == 1
        assert config.typesystem.primitive_types[0].cpp_name == "int"


class TestConversionRules:
    def test_conversion_rules_parsed(self, tmp_path: Path) -> None:
        cfg = tmp_path / "test.input.yml"
        cfg.write_text(
            "source:\n  path: test.hpp\n"
            "typesystem:\n"
            "  conversion_rules:\n"
            "    - cpp_type: \"MyColor\"\n"
            "      native_to_target: \"PyLong_FromLong(static_cast<long>(%%in))\"\n"
            "      target_to_native: \"static_cast<MyColor>(PyLong_AsLong(%%in))\"\n"
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
            "    - cpp_type: \"MyColor\"\n"
            "      native_to_target: \"convert_color(%%in)\"\n"
            "      target_to_native: \"from_color(%%in)\"\n"
            "    - cpp_type: \"MyRect\"\n"
            "      native_to_target: \"convert_rect(%%in)\"\n"
            "      target_to_native: \"from_rect(%%in)\"\n"
        )
        config = load_input_config(cfg)
        assert len(config.typesystem.conversion_rules) == 2
        assert config.typesystem.conversion_rules[0] == ConversionRuleEntry(
            cpp_type="MyColor",
            native_to_target="convert_color(%%in)",
            target_to_native="from_color(%%in)",
        )
        assert config.typesystem.conversion_rules[1].cpp_type == "MyRect"
