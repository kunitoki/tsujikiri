"""Integration tests for parser.py — parse combined.hpp via libclang."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tsujikiri.configurations import SourceConfig
from tsujikiri.parser import (
    parse_translation_unit,
    _source_file,
    _collect_attr_blocks,
    _read_source_lines,
    _get_attributes,
    _get_default_value,
    _SOURCE_CACHE,
)

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

    def test_area_is_virtual(self, parsed_module):
        shape = self._shape(parsed_module)
        area = next(m for m in shape.methods if m.name == "area")
        assert area.is_virtual is True

    def test_area_is_pure_virtual(self, parsed_module):
        shape = self._shape(parsed_module)
        area = next(m for m in shape.methods if m.name == "area")
        assert area.is_pure_virtual is True

    def test_area_is_noexcept(self, parsed_module):
        shape = self._shape(parsed_module)
        area = next(m for m in shape.methods if m.name == "area")
        assert area.is_noexcept is True

    def test_perimeter_not_noexcept(self, parsed_module):
        shape = self._shape(parsed_module)
        perimeter = next(m for m in shape.methods if m.name == "perimeter")
        assert perimeter.is_noexcept is False

    def test_class_is_abstract(self, parsed_module):
        shape = self._shape(parsed_module)
        assert shape.is_abstract is True

    def test_class_has_virtual_methods(self, parsed_module):
        shape = self._shape(parsed_module)
        assert shape.has_virtual_methods is True

    def test_default_ctor_noexcept(self, parsed_module):
        shape = self._shape(parsed_module)
        default_ctor = next(c for c in shape.constructors if not c.parameters)
        assert default_ctor.is_noexcept is True

    def test_explicit_ctor(self, parsed_module):
        shape = self._shape(parsed_module)
        name_ctor = next(c for c in shape.constructors if c.parameters)
        assert name_ctor.is_explicit is True

    def test_default_ctor_not_explicit(self, parsed_module):
        shape = self._shape(parsed_module)
        default_ctor = next(c for c in shape.constructors if not c.parameters)
        assert default_ctor.is_explicit is False

    def test_field_scale(self, parsed_module):
        shape = self._shape(parsed_module)
        field_names = {f.name for f in shape.fields}
        assert "scale_" in field_names

    def test_no_bases(self, parsed_module):
        shape = self._shape(parsed_module)
        assert shape.bases == []  # Shape has no base classes

    def test_getname_has_skip_attribute(self, parsed_module):
        shape = self._shape(parsed_module)
        getName = next(m for m in shape.methods if m.name == "getName")
        assert any("tsujikiri::skip" in a for a in getName.attributes)

    def test_setname_has_rename_attribute(self, parsed_module):
        shape = self._shape(parsed_module)
        setName = next(m for m in shape.methods if m.name == "setName")
        assert any("tsujikiri::rename" in a for a in setName.attributes)

    def test_getscale_has_custom_attribute(self, parsed_module):
        shape = self._shape(parsed_module)
        getScale = next(m for m in shape.methods if m.name == "getScale")
        assert any("mygame::no_export" in a for a in getScale.attributes)

    def test_area_has_no_attributes(self, parsed_module):
        shape = self._shape(parsed_module)
        area = next(m for m in shape.methods if m.name == "area")
        assert area.attributes == []


class TestCircleClass:
    def _circle(self, parsed_module):
        return next(c for c in parsed_module.classes if c.name == "Circle")

    def test_inherits_from_shape(self, parsed_module):
        circle = self._circle(parsed_module)
        assert any(b.qualified_name == "mylib::Shape" for b in circle.bases)

    def test_base_access_is_public(self, parsed_module):
        circle = self._circle(parsed_module)
        shape_base = next(b for b in circle.bases if b.qualified_name == "mylib::Shape")
        assert shape_base.access == "public"

    def test_overloaded_resize(self, parsed_module):
        circle = self._circle(parsed_module)
        resize_methods = [m for m in circle.methods if m.name == "resize"]
        assert len(resize_methods) == 2
        assert all(m.is_overload for m in resize_methods)

    def test_radius_field(self, parsed_module):
        circle = self._circle(parsed_module)
        field_names = {f.name for f in circle.fields}
        assert "radius_" in field_names

    def test_default_ctor_noexcept(self, parsed_module):
        circle = self._circle(parsed_module)
        default_ctor = next(c for c in circle.constructors if not c.parameters)
        assert default_ctor.is_noexcept is True

    def test_explicit_ctor(self, parsed_module):
        circle = self._circle(parsed_module)
        radius_ctor = next(c for c in circle.constructors if c.parameters)
        assert radius_ctor.is_explicit is True

    def test_area_noexcept(self, parsed_module):
        circle = self._circle(parsed_module)
        area = next(m for m in circle.methods if m.name == "area")
        assert area.is_noexcept is True

    def test_class_not_abstract(self, parsed_module):
        circle = self._circle(parsed_module)
        assert circle.is_abstract is False


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

    def test_computeArea_single_param_is_noexcept(self, parsed_module):
        fns = [f for f in parsed_module.functions if f.name == "computeArea"]
        single = next(f for f in fns if len(f.parameters) == 1)
        assert single.is_noexcept is True

    def test_computeArea_two_params_not_noexcept(self, parsed_module):
        fns = [f for f in parsed_module.functions if f.name == "computeArea"]
        two_param = next(f for f in fns if len(f.parameters) == 2)
        assert two_param.is_noexcept is False


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
        cursor = MagicMock()
        cursor.location.file = None
        assert _source_file(cursor) is None


class TestParseTranslationUnitErrors:
    def test_raises_file_not_found(self):
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


# ---------------------------------------------------------------------------
# Unit tests for attribute-extraction helpers
# ---------------------------------------------------------------------------

class TestCollectAttrBlocks:
    def test_empty_string(self):
        assert _collect_attr_blocks("") == []

    def test_no_attribute_syntax(self):
        assert _collect_attr_blocks("void method();") == []

    def test_single_attribute(self):
        assert _collect_attr_blocks("[[tsujikiri::skip]]") == ["tsujikiri::skip"]

    def test_attribute_with_arg(self):
        result = _collect_attr_blocks('[[tsujikiri::rename("foo")]]')
        assert result == ['tsujikiri::rename("foo")']

    def test_two_attrs_in_one_block(self):
        result = _collect_attr_blocks("[[ns::a, ns::b]]")
        assert result == ["ns::a", "ns::b"]

    def test_attribute_in_trailing_text(self):
        result = _collect_attr_blocks(" [[myns::tag]];")
        assert "myns::tag" in result


class TestReadSourceLines:
    def test_oserror_returns_empty(self):
        fake = "/no/such/file_unique_test_path_xyzzy.hpp"
        _SOURCE_CACHE.pop(fake, None)
        with patch("builtins.open", side_effect=OSError("no file")):
            result = _read_source_lines(fake)
        assert result == []

    def test_caches_result(self, tmp_path):
        f = tmp_path / "cached.hpp"
        f.write_text("int x;\n")
        path = str(f)
        _SOURCE_CACHE.pop(path, None)
        first = _read_source_lines(path)
        second = _read_source_lines(path)
        assert first is second  # same list object from cache


class TestGetAttributesHelpers:
    def test_no_file_returns_empty(self):
        cursor = MagicMock()
        cursor.location.file = None
        assert _get_attributes(cursor) == []

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "empty.hpp"
        f.write_text("")
        _SOURCE_CACHE.pop(str(f), None)
        cursor = MagicMock()
        cursor.location.file.name = str(f)
        cursor.extent.start.line = 1
        cursor.extent.start.column = 1
        cursor.extent.end.line = 1
        cursor.extent.end.column = 1
        assert _get_attributes(cursor) == []

    def test_previous_line_attribute(self, parsed_module):
        # combined.hpp has [[mygame::no_export]] on its own line before setScale
        shape = next(c for c in parsed_module.classes if c.name == "Shape")
        setScale = next(m for m in shape.methods if m.name == "setScale")
        assert any("mygame::no_export" in a for a in setScale.attributes)


# ---------------------------------------------------------------------------
# Default parameter value extraction (defaults.hpp)
# ---------------------------------------------------------------------------

class TestGetDefaultValue:
    def test_no_tokens_returns_none(self):
        cursor = MagicMock()
        cursor.get_tokens.return_value = []
        assert _get_default_value(cursor) is None

    def test_no_equals_returns_none(self):
        cursor = MagicMock()
        tok = MagicMock()
        tok.spelling = "x"
        cursor.get_tokens.return_value = [tok]
        assert _get_default_value(cursor) is None

    def test_equals_with_no_following_token_returns_none(self):
        cursor = MagicMock()
        eq = MagicMock()
        eq.spelling = "="
        cursor.get_tokens.return_value = [eq]
        assert _get_default_value(cursor) is None


class TestDefaultParameterValues:
    def _cls(self, defaults_parsed_module):
        return next(c for c in defaults_parsed_module.classes if c.name == "Defaults")

    def test_integer_default_on_compute(self, defaults_parsed_module):
        cls = self._cls(defaults_parsed_module)
        compute = next(m for m in cls.methods if m.name == "compute")
        x = next(p for p in compute.parameters if p.name == "x")
        assert x.default_value == "0"

    def test_second_integer_default_on_compute(self, defaults_parsed_module):
        cls = self._cls(defaults_parsed_module)
        compute = next(m for m in cls.methods if m.name == "compute")
        y = next(p for p in compute.parameters if p.name == "y")
        assert y.default_value == "1"

    def test_float_default_on_scale(self, defaults_parsed_module):
        cls = self._cls(defaults_parsed_module)
        scale = next(m for m in cls.methods if m.name == "scale")
        factor = next(p for p in scale.parameters if p.name == "factor")
        assert factor.default_value == "1.0"

    def test_bool_default_on_scale(self, defaults_parsed_module):
        cls = self._cls(defaults_parsed_module)
        scale = next(m for m in cls.methods if m.name == "scale")
        normalize = next(p for p in scale.parameters if p.name == "normalize")
        assert normalize.default_value == "true"

    def test_no_default_returns_none(self, defaults_parsed_module):
        cls = self._cls(defaults_parsed_module)
        no_default = next(m for m in cls.methods if m.name == "noDefault")
        for p in no_default.parameters:
            assert p.default_value is None

    def test_free_function_defaults(self, defaults_parsed_module):
        fn = next(f for f in defaults_parsed_module.functions if f.name == "freeWithDefault")
        x = next(p for p in fn.parameters if p.name == "x")
        assert x.default_value == "42"
        flag = next(p for p in fn.parameters if p.name == "flag")
        assert flag.default_value == "false"
