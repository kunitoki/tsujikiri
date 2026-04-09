"""Integration tests for parser.py — parse combined.hpp via libclang."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).parent


class TestNamespaceAndTopLevel:
    def test_classes_found(self, parsed_module):
        names = {c.name for c in parsed_module.classes}
        assert "Shape" in names
        assert "Circle" in names
        assert "Calculator" in names

    def test_enum_found(self, parsed_module):
        names = {e.name for e in parsed_module.enums}
        assert "Color" in names

    def test_free_functions_found(self, parsed_module):
        names = {f.name for f in parsed_module.functions}
        assert "computeArea" in names

    def test_module_name(self, parsed_module):
        assert parsed_module.name == "combined"


class TestEnumParsing:
    def test_color_values(self, parsed_module):
        color = next(e for e in parsed_module.enums if e.name == "Color")
        value_names = {v.name for v in color.values}
        assert {"Red", "Green", "Blue"} == value_names

    def test_color_value_integers(self, parsed_module):
        color = next(e for e in parsed_module.enums if e.name == "Color")
        by_name = {v.name: v.value for v in color.values}
        assert by_name["Red"] == 0
        assert by_name["Green"] == 1
        assert by_name["Blue"] == 2

    def test_enum_qualified_name(self, parsed_module):
        color = next(e for e in parsed_module.enums if e.name == "Color")
        assert "mylib" in color.qualified_name


class TestShapeClass:
    def _shape(self, parsed_module):
        return next(c for c in parsed_module.classes if c.name == "Shape")

    def test_namespace(self, parsed_module):
        assert self._shape(parsed_module).namespace == "mylib"

    def test_qualified_name(self, parsed_module):
        assert "mylib" in self._shape(parsed_module).qualified_name

    def test_constructors(self, parsed_module):
        shape = self._shape(parsed_module)
        assert len(shape.constructors) >= 1

    def test_methods_present(self, parsed_module):
        shape = self._shape(parsed_module)
        method_names = {m.name for m in shape.methods}
        assert "area" in method_names
        assert "perimeter" in method_names
        assert "getName" in method_names
        assert "setName" in method_names

    def test_area_is_const(self, parsed_module):
        shape = self._shape(parsed_module)
        area = next(m for m in shape.methods if m.name == "area")
        assert area.is_const is True

    def test_field_scale(self, parsed_module):
        shape = self._shape(parsed_module)
        field_names = {f.name for f in shape.fields}
        assert "scale_" in field_names

    def test_no_bases(self, parsed_module):
        shape = self._shape(parsed_module)
        assert shape.bases == []


class TestCircleClass:
    def _circle(self, parsed_module):
        return next(c for c in parsed_module.classes if c.name == "Circle")

    def test_inherits_from_shape(self, parsed_module):
        circle = self._circle(parsed_module)
        assert "mylib::Shape" in circle.bases

    def test_overloaded_resize(self, parsed_module):
        circle = self._circle(parsed_module)
        resize_methods = [m for m in circle.methods if m.name == "resize"]
        assert len(resize_methods) == 2
        assert all(m.is_overload for m in resize_methods)

    def test_radius_field(self, parsed_module):
        circle = self._circle(parsed_module)
        field_names = {f.name for f in circle.fields}
        assert "radius_" in field_names


class TestCalculatorClass:
    def _calc(self, parsed_module):
        return next(c for c in parsed_module.classes if c.name == "Calculator")

    def test_overloaded_add(self, parsed_module):
        calc = self._calc(parsed_module)
        add_methods = [m for m in calc.methods if m.name == "add"]
        assert len(add_methods) == 2
        assert all(m.is_overload for m in add_methods)

    def test_static_max(self, parsed_module):
        calc = self._calc(parsed_module)
        max_methods = [m for m in calc.methods if m.name == "max"]
        assert len(max_methods) == 2
        assert all(m.is_static for m in max_methods)
        assert all(m.is_overload for m in max_methods)

    def test_getValue_is_const(self, parsed_module):
        calc = self._calc(parsed_module)
        get_value = next(m for m in calc.methods if m.name == "getValue")
        assert get_value.is_const is True

    def test_field_value(self, parsed_module):
        calc = self._calc(parsed_module)
        assert any(f.name == "value_" for f in calc.fields)


class TestFreeFunctions:
    def test_computeArea_overloaded(self, parsed_module):
        fns = [f for f in parsed_module.functions if f.name == "computeArea"]
        assert len(fns) == 2
        assert all(f.is_overload for f in fns)

    def test_computeArea_return_type(self, parsed_module):
        fn = next(f for f in parsed_module.functions if f.name == "computeArea")
        assert "double" in fn.return_type


class TestNamespaceFiltering:
    def test_only_mylib_namespace(self, parsed_module):
        for cls in parsed_module.classes:
            assert cls.namespace == "mylib"

    def test_class_by_name_populated(self, parsed_module):
        assert "Shape" in parsed_module.class_by_name
        assert "Circle" in parsed_module.class_by_name


# ---------------------------------------------------------------------------
# Unit tests for private helpers
# ---------------------------------------------------------------------------

class TestSourceFileHelper:
    def test_returns_none_when_no_file(self):
        from tsujikiri.parser import _source_file
        cursor = MagicMock()
        cursor.location.file = None
        assert _source_file(cursor) is None


class TestParseTranslationUnitErrors:
    def test_raises_file_not_found(self):
        from tsujikiri.configurations import SourceConfig
        from tsujikiri.parser import parse_translation_unit
        src = SourceConfig(path="/definitely/does/not/exist.hpp")
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            parse_translation_unit(src, [], "test")


# ---------------------------------------------------------------------------
# Nested classes and enums (nested_types.hpp)
# ---------------------------------------------------------------------------

class TestNestedTypes:
    def test_container_class_found(self, nested_parsed_module):
        names = {c.name for c in nested_parsed_module.classes}
        assert "Container" in names

    def test_nested_enum_parsed(self, nested_parsed_module):
        container = next(c for c in nested_parsed_module.classes if c.name == "Container")
        enum_names = {e.name for e in container.enums}
        assert "Status" in enum_names

    def test_nested_enum_values(self, nested_parsed_module):
        container = next(c for c in nested_parsed_module.classes if c.name == "Container")
        status = next(e for e in container.enums if e.name == "Status")
        value_names = {v.name for v in status.values}
        assert "Active" in value_names
        assert "Inactive" in value_names

    def test_inner_class_parsed(self, nested_parsed_module):
        container = next(c for c in nested_parsed_module.classes if c.name == "Container")
        inner_names = {c.name for c in container.inner_classes}
        assert "Item" in inner_names

    def test_inner_class_qualified_name(self, nested_parsed_module):
        container = next(c for c in nested_parsed_module.classes if c.name == "Container")
        item = next(c for c in container.inner_classes if c.name == "Item")
        assert "Container" in item.qualified_name
        assert "Item" in item.qualified_name

    def test_toplevel_non_namespace_triggers_continue(self, nested_parsed_module):
        # nested_types.hpp has a top-level typedef; parser skips it (continue)
        # If parsing succeeded, the continue branch was exercised
        assert nested_parsed_module.name == "nested"
