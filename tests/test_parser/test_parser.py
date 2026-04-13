"""Integration tests for parser.py — parse combined.hpp via libclang."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clang import cindex as ci
from clang.cindex import CursorKind
from tsujikiri.configurations import SourceConfig
from tsujikiri.clang_base_enumerations import CursorKind, AccessSpecifier
from tsujikiri.parser import (
    parse_translation_unit,
    _collect_attr_blocks,
    _get_attributes,
    _get_default_value,
    _parse_enum,
    _read_source_lines,
    _source_file,
    _type_from_tokens,
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

    def test_empty_part_from_trailing_comma_ignored(self):
        """``[[ns::a, ]]`` splits into 'ns::a' and '' — the empty part must be skipped."""
        result = _collect_attr_blocks("[[ns::a, ]]")
        assert result == ["ns::a"]


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


# ---------------------------------------------------------------------------
# Branch coverage: _parse_enum skips non-ENUM_CONSTANT_DECL children (183->182)
# ---------------------------------------------------------------------------

class TestParseEnumSkipsNonConstant:
    def test_non_enum_constant_child_is_ignored(self):
        """If a cursor child has a kind other than ENUM_CONSTANT_DECL it must be skipped."""
        cursor = MagicMock()
        cursor.spelling = "TestEnum"
        cursor.location.file = None  # _get_attributes returns [] for None file

        non_const_child = MagicMock()
        non_const_child.kind = CursorKind.UNEXPOSED_DECL

        good_child = MagicMock()
        good_child.kind = CursorKind.ENUM_CONSTANT_DECL
        good_child.spelling = "ValueA"
        good_child.enum_value = 0
        good_child.location.file = None

        cursor.get_children.return_value = [non_const_child, good_child]

        result = _parse_enum(cursor, "ns")
        assert len(result.values) == 1
        assert result.values[0].name == "ValueA"


# ---------------------------------------------------------------------------
# Branch coverage: namespace not in filter is skipped (302->299)
# ---------------------------------------------------------------------------

class TestNamespaceNotInFilter:
    def test_unmatched_namespace_excluded(self, tmp_path: Path) -> None:
        """Parsing a file with two namespaces while filtering for only one must
        exclude entities from the other namespace, exercising the False branch
        of ``if not namespaces or entry.spelling in namespaces``."""
        hpp = tmp_path / "multi_ns.hpp"
        hpp.write_text(
            "namespace wanted { int foo(); }\n"
            "namespace unwanted { int bar(); }\n",
            encoding="utf-8",
        )
        src = SourceConfig(path=str(hpp), parse_args=["-std=c++17"])
        module = parse_translation_unit(src, ["wanted"], "multi_ns_test")
        fn_names = {f.name for f in module.functions}
        assert "foo" in fn_names
        assert "bar" not in fn_names


# ---------------------------------------------------------------------------
# Branch coverage: explicit -x flag not duplicated (319->322)
# ---------------------------------------------------------------------------

class TestExplicitXArgNotDuplicated:
    def test_parse_with_explicit_x_cpp(self, tmp_path: Path) -> None:
        """When parse_args already contains ``-x``, it must not be prepended again."""
        hpp = tmp_path / "xarg.hpp"
        hpp.write_text("namespace ns { int foo(); }\n", encoding="utf-8")
        src = SourceConfig(path=str(hpp), parse_args=["-std=c++17", "-x", "c++"])
        module = parse_translation_unit(src, ["ns"], "xarg_test")
        assert module is not None
        assert any(f.name == "foo" for f in module.functions)


# ---------------------------------------------------------------------------
# Branch coverage: -isysroot already in args skips darwin sysroot (323->326)
# ---------------------------------------------------------------------------

class TestIsysrootNotDuplicated:
    def test_parse_with_explicit_isysroot(self, tmp_path: Path) -> None:
        """When parse_args already contains ``-isysroot``, it must not be appended again."""
        hpp = tmp_path / "isysroot.hpp"
        hpp.write_text("namespace ns { int foo(); }\n", encoding="utf-8")
        src = SourceConfig(path=str(hpp), parse_args=["-std=c++17", "-isysroot", "/"])
        module = parse_translation_unit(src, ["ns"], "isysroot_test")
        assert module is not None
        assert any(f.name == "foo" for f in module.functions)


# ---------------------------------------------------------------------------
# _type_from_tokens — comprehensive real-libclang tests
#
# Many std:: types are misreported by libclang (typically as 'int') when they
# appear in constructor parameters whose constructor has a member-initialiser
# list.  _type_from_tokens works around this by reconstructing the type from
# the source token stream.
#
# Tests are grouped into:
#   • Primitive / built-in            — not affected by the bug
#   • Pointer / reference             — not affected
#   • std::string variants            — AFFECTED (bug produces 'int')
#   • std::string_view variants       — not affected
#   • Template containers / wrappers  — AFFECTED (bug produces 'int')
#   • std::function / shared_ptr      — not affected
#   • Multi-parameter function        — mixed
#   • Widget constructors (regression)— AFFECTED (the original bug trigger)
#
# Integration path: parse_translation_unit → _parse_parameters →
#   _type_from_tokens → IRParameter.type_spelling
# ---------------------------------------------------------------------------

class TestTypeFromTokens:
    """Verify _type_from_tokens yields correct type spellings via the full IR pipeline.

    The fixture `type_tokens_module` parses type_tokens.hpp which is designed to
    exercise every interesting case including those that trigger the libclang bug.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fn_types(mod, name: str) -> list[str]:
        fn = next(f for f in mod.functions if f.name == name)
        return [p.type_spelling for p in fn.parameters]

    @staticmethod
    def _ctor_types(mod, class_name: str, n_params: int) -> list[str]:
        cls = next(c for c in mod.classes if c.name == class_name)
        ctor = next(c for c in cls.constructors if len(c.parameters) == n_params)
        return [p.type_spelling for p in ctor.parameters]

    # ------------------------------------------------------------------
    # Primitive / built-in — libclang reports these correctly
    # ------------------------------------------------------------------

    def test_int(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_int") == ["int"]

    def test_double(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_double") == ["double"]

    def test_bool(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_bool") == ["bool"]

    def test_unsigned_int(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_unsigned_int") == ["unsigned int"]

    def test_long_long(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_long_long") == ["long long"]

    def test_size_t(self, type_tokens_module: object) -> None:
        # std::size_t spans tokens ['std', '::', 'size_t', name]; :: is normalised
        assert self._fn_types(type_tokens_module, "f_size_t") == ["std::size_t"]

    # ------------------------------------------------------------------
    # Pointer / reference — not affected by the bug
    # ------------------------------------------------------------------

    def test_int_ptr(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_int_ptr") == ["int *"]

    def test_const_char_ptr(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_const_char_ptr") == ["const char *"]

    def test_int_ref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_int_ref") == ["int &"]

    def test_const_int_ref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_const_int_ref") == ["const int &"]

    # ------------------------------------------------------------------
    # std::string — affected by the libclang bug (would return 'int' without fix)
    # ------------------------------------------------------------------

    def test_string_value(self, type_tokens_module: object) -> None:
        # libclang cursor.type.spelling would say 'int'; tokens give 'std::string'
        assert self._fn_types(type_tokens_module, "f_string") == ["std::string"]

    def test_string_ref(self, type_tokens_module: object) -> None:
        # tokens: ['std', '::', 'string', '&', name] → 'std::string &'
        assert self._fn_types(type_tokens_module, "f_string_ref") == ["std::string &"]

    def test_string_cref(self, type_tokens_module: object) -> None:
        # tokens: ['const', 'std', '::', 'string', '&', name] → 'const std::string &'
        assert self._fn_types(type_tokens_module, "f_string_cref") == ["const std::string &"]

    def test_string_rref(self, type_tokens_module: object) -> None:
        # tokens: ['std', '::', 'string', '&&', name] → 'std::string &&'
        assert self._fn_types(type_tokens_module, "f_string_rref") == ["std::string &&"]

    # ------------------------------------------------------------------
    # std::string_view — NOT affected by the bug; token path still correct
    # ------------------------------------------------------------------

    def test_string_view_value(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_sv") == ["std::string_view"]

    def test_string_view_cref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_sv_cref") == ["const std::string_view &"]

    # ------------------------------------------------------------------
    # std::vector — affected by the bug ('int' without fix).
    # Template bracket tokens are joined with spaces (valid C++).
    # ------------------------------------------------------------------

    def test_vec_int(self, type_tokens_module: object) -> None:
        # tokens include '<', 'int', '>'; joined: 'std::vector < int >'
        assert self._fn_types(type_tokens_module, "f_vec_int") == ["std::vector < int >"]

    def test_vec_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_vec_string") == ["std::vector < std::string >"]

    def test_vec_int_cref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_vec_int_cref") == ["const std::vector < int > &"]

    # ------------------------------------------------------------------
    # std::map — affected by the bug
    # ------------------------------------------------------------------

    def test_map_string_int(self, type_tokens_module: object) -> None:
        # comma token has spaces on both sides from join
        assert self._fn_types(type_tokens_module, "f_map_string_int") == [
            "std::map < std::string , int >"
        ]

    # ------------------------------------------------------------------
    # std::optional — affected by the bug
    # ------------------------------------------------------------------

    def test_optional_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_opt_string") == [
            "std::optional < std::string >"
        ]

    # ------------------------------------------------------------------
    # Nested templates — affected by the bug.
    # Note: '>>' is a single token in C++11+ (closes two templates).
    # ------------------------------------------------------------------

    def test_nested_vector_pair(self, type_tokens_module: object) -> None:
        # tokens end with '>>' (single token): 'std::vector < std::pair < int , std::string >>'
        assert self._fn_types(type_tokens_module, "f_nested") == [
            "std::vector < std::pair < int , std::string >>"
        ]

    # ------------------------------------------------------------------
    # std::function — NOT affected by the bug; token path still exercised
    # ------------------------------------------------------------------

    def test_function_void_int(self, type_tokens_module: object) -> None:
        # '(' and ')' are separate tokens, each with surrounding spaces after join
        assert self._fn_types(type_tokens_module, "f_fn_void_int") == [
            "std::function < void ( int ) >"
        ]

    def test_function_int_two_doubles(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_fn_int_two_doubles") == [
            "std::function < int ( double , double ) >"
        ]

    # ------------------------------------------------------------------
    # std::shared_ptr — NOT affected by the bug
    # ------------------------------------------------------------------

    def test_shared_ptr_obj(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "f_shared_obj") == [
            "std::shared_ptr < Obj >"
        ]

    # ------------------------------------------------------------------
    # Multi-parameter function — verifies each positional slot is correct
    # ------------------------------------------------------------------

    def test_multi_param_string(self, type_tokens_module: object) -> None:
        types = self._fn_types(type_tokens_module, "f_multi")
        assert types[0] == "std::string"

    def test_multi_param_int(self, type_tokens_module: object) -> None:
        types = self._fn_types(type_tokens_module, "f_multi")
        assert types[1] == "int"

    def test_multi_param_vec_double_cref(self, type_tokens_module: object) -> None:
        types = self._fn_types(type_tokens_module, "f_multi")
        assert types[2] == "const std::vector < double > &"

    # ------------------------------------------------------------------
    # Widget constructors — regression for the original bug trigger.
    #
    # Widget(std::string name, std::vector<int> ids) uses std::move in its
    # initialiser list. Without _type_from_tokens, libclang reports both
    # parameter types as 'int'.  With the fix, both are correctly extracted
    # from the source token stream.
    # ------------------------------------------------------------------

    def test_widget_ctor_std_move_string_param(self, type_tokens_module: object) -> None:
        """std::string in a constructor with a std::move initialiser list."""
        types = self._ctor_types(type_tokens_module, "Widget", 2)
        assert types[0] == "std::string"

    def test_widget_ctor_std_move_vector_param(self, type_tokens_module: object) -> None:
        """std::vector<int> in a constructor with a std::move initialiser list."""
        types = self._ctor_types(type_tokens_module, "Widget", 2)
        assert types[1] == "std::vector < int >"

    def test_widget_ctor_cref_string_param(self, type_tokens_module: object) -> None:
        """const std::string & in a second constructor (also has initialiser list)."""
        types = self._ctor_types(type_tokens_module, "Widget", 3)
        assert types[0] == "const std::string &"

    def test_widget_ctor_map_param(self, type_tokens_module: object) -> None:
        """std::map<std::string, int> in a constructor — heavily templated arg."""
        types = self._ctor_types(type_tokens_module, "Widget", 3)
        assert types[1] == "std::map < std::string , int >"

    def test_widget_ctor_optional_param(self, type_tokens_module: object) -> None:
        """std::optional<double> in a constructor."""
        types = self._ctor_types(type_tokens_module, "Widget", 3)
        assert types[2] == "std::optional < double >"

    # ------------------------------------------------------------------
    # Direct _type_from_tokens unit tests on raw libclang cursors.
    # These bypass the IR pipeline and call the function directly to verify
    # its behaviour on actual token sequences reported by libclang.
    # ------------------------------------------------------------------

    def test_direct_string_in_init_list_ctor(self, tmp_path: Path) -> None:
        """_type_from_tokens returns 'std::string' even when cursor.type.spelling says 'int'."""
        hpp = tmp_path / "direct_test.hpp"
        hpp.write_text(
            "#include <string>\n"
            "#include <vector>\n"
            "namespace dt {\n"
            "class Foo {\n"
            "public:\n"
            "    std::string s_;\n"
            "    std::vector<int> v_;\n"
            "    Foo(std::string s, std::vector<int> v) : s_(std::move(s)), v_(std::move(v)) {}\n"
            "};\n"
            "}\n",
            encoding="utf-8",
        )
        args = ["-x", "c++", "-std=c++17"]
        if sys.platform == "darwin":
            args += ["-isysroot", "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"]

        index = ci.Index.create()
        tu = index.parse(str(hpp), args=args)

        parm_cursors: list[object] = []
        hpp_path = str(hpp)

        def _collect(cursor: object) -> None:
            loc = cursor.location
            if (
                cursor.kind == CursorKind.CONSTRUCTOR
                and cursor.access_specifier == AccessSpecifier.PUBLIC
                and loc.file is not None
                and loc.file.name == hpp_path
            ):
                parm_cursors.extend(
                    c for c in cursor.get_children() if c.kind == CursorKind.PARM_DECL
                )
            for child in cursor.get_children():
                _collect(child)

        _collect(tu.cursor)

        assert len(parm_cursors) == 2, f"expected 2 PARM_DECLs, got {len(parm_cursors)}"
        s_cursor, v_cursor = parm_cursors

        # Document whether the libclang bug is present on this platform/version.
        # Some libclang builds correctly report the type even in init-list ctors;
        # the token workaround is safe either way and must always return the right type.
        _ = s_cursor.type.spelling  # may be 'int' (bug) or 'std::string' (fixed)

        # _type_from_tokens must return the correct type regardless
        assert _type_from_tokens(s_cursor) == "std::string"
        assert _type_from_tokens(v_cursor) == "std::vector < int >"

    def test_direct_no_name_falls_back_to_cursor_type(self, tmp_path: Path) -> None:
        """Unnamed parameters (no spelling) fall back to cursor.type.spelling."""
        hpp = tmp_path / "unnamed.hpp"
        hpp.write_text(
            "namespace un { void f(int, double); }\n",
            encoding="utf-8",
        )
        import sys
        args = ["-x", "c++", "-std=c++17"]
        if sys.platform == "darwin":
            args += ["-isysroot", "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"]

        index = ci.Index.create()
        tu = index.parse(str(hpp), args=args)

        parm_cursors: list[object] = []

        def _collect(cursor: object) -> None:
            if cursor.kind == CursorKind.FUNCTION_DECL and cursor.spelling == "f":
                parm_cursors.extend(
                    c for c in cursor.get_children() if c.kind == CursorKind.PARM_DECL
                )
            for child in cursor.get_children():
                _collect(child)

        _collect(tu.cursor)
        assert len(parm_cursors) == 2

        # Unnamed parameters have empty spelling; function falls back to cursor.type.spelling
        for p in parm_cursors:
            assert p.spelling == "", f"expected unnamed param, got {p.spelling!r}"
            result = _type_from_tokens(p)
            assert result == p.type.spelling


# ---------------------------------------------------------------------------
# Branch coverage: _type_from_tokens lines 73 and 76 (mock-based)
# ---------------------------------------------------------------------------

class TestTypeFromTokensBranches:
    """Cover the two remaining branches of _type_from_tokens using mocks."""

    def test_name_is_first_token_returns_cursor_type(self) -> None:
        """When the parameter name is the very first token (i == 0), return cursor.type.spelling.

        This safety guard fires when the type and name spellings are identical,
        e.g. ``void f(Foo Foo)``.  Without the guard the type extraction would
        produce an empty string.
        """
        cursor = MagicMock()
        cursor.spelling = "Foo"
        tok = MagicMock()
        tok.spelling = "Foo"
        cursor.get_tokens.return_value = [tok]
        cursor.type.spelling = "Foo"
        assert _type_from_tokens(cursor) == "Foo"

    def test_name_absent_from_tokens_falls_back_to_cursor_type(self) -> None:
        """When cursor.spelling is not found in any token, return cursor.type.spelling.

        This happens with macro-expanded parameter names: get_tokens() returns
        the unexpanded macro identifier while cursor.spelling returns the
        expanded name, so the name is never matched.
        """
        cursor = MagicMock()
        cursor.spelling = "myvar"
        tok_int = MagicMock()
        tok_int.spelling = "int"
        tok_macro = MagicMock()
        tok_macro.spelling = "MYNAME"
        cursor.get_tokens.return_value = [tok_int, tok_macro]
        cursor.type.spelling = "int"
        assert _type_from_tokens(cursor) == "int"


# ---------------------------------------------------------------------------
# _type_from_tokens — namespace and global-qualifier cases (type_tokens.hpp)
#
# All functions below live in ``namespace types`` in type_tokens.hpp, which
# includes type_namespaces.hpp for the outer::inner user types.
#
# Groups:
#   • Global-namespace-qualified std:: types  (::std::...)
#   • Nested-namespace user types             (outer::inner::Type)
#   • Cross-namespace combinations
# ---------------------------------------------------------------------------

class TestTypeFromTokensNamespaces:
    """Verify _type_from_tokens for global-qualifier and nested-namespace types."""

    @staticmethod
    def _fn_types(mod: object, name: str) -> list[str]:
        fn = next(f for f in mod.functions if f.name == name)
        return [p.type_spelling for p in fn.parameters]

    # ------------------------------------------------------------------
    # Global-namespace-qualified std:: types (::std::...)
    # The leading '::' token causes re.sub to strip surrounding spaces,
    # producing 'const::std::string' (no space between const and ::).
    # ------------------------------------------------------------------

    def test_g_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_string") == ["::std::string"]

    def test_g_string_cref(self, type_tokens_module: object) -> None:
        # 'const :: std :: string &' → 'const::std::string &' (no space before ::)
        assert self._fn_types(type_tokens_module, "g_string_cref") == ["const::std::string &"]

    def test_g_string_rref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_string_rref") == ["::std::string &&"]

    def test_g_vec_int(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_vec_int") == ["::std::vector < int >"]

    def test_g_optional_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_optional_string") == [
            "::std::optional <::std::string >"
        ]

    def test_g_map_string_int(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_map_string_int") == [
            "::std::map <::std::string , int >"
        ]

    def test_g_function_void_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "g_function_void_string") == [
            "::std::function < void (::std::string ) >"
        ]

    # ------------------------------------------------------------------
    # Nested-namespace user types (outer::inner::Type)
    # libclang reports these correctly; the token path still exercises
    # the :: normalisation across multiple namespace separators.
    # ------------------------------------------------------------------

    def test_n_nested_value(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "n_nested_value") == ["outer::inner::Nested"]

    def test_n_nested_cref(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "n_nested_cref") == ["const outer::inner::Nested &"]

    def test_n_nested_ptr(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "n_nested_ptr") == ["outer::inner::Nested *"]

    def test_n_mid_unnamed_falls_back_to_cursor_type(self, type_tokens_module: object) -> None:
        # Unnamed parameter (no spelling) → falls back to cursor.type.spelling
        assert self._fn_types(type_tokens_module, "n_mid_value") == ["outer::Mid"]

    def test_n_global_nested(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "n_global_nested") == ["::outer::inner::Nested"]

    def test_n_global_deep_ptr(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "n_global_deep_ptr") == ["::outer::inner::Deep *"]

    # ------------------------------------------------------------------
    # Cross-namespace: std containers holding user types and mixed args
    # ------------------------------------------------------------------

    def test_m_multi_first_param(self, type_tokens_module: object) -> None:
        types = self._fn_types(type_tokens_module, "m_multi")
        assert types[0] == "outer::inner::Nested"

    def test_m_multi_second_param(self, type_tokens_module: object) -> None:
        types = self._fn_types(type_tokens_module, "m_multi")
        assert types[1] == "::std::string"

    def test_m_vec_nested(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "m_vec_nested") == [
            "::std::vector < outer::inner::Nested >"
        ]

    def test_m_map_nested_string(self, type_tokens_module: object) -> None:
        assert self._fn_types(type_tokens_module, "m_map_nested_string") == [
            "::std::map < outer::inner::Nested ,::std::string >"
        ]

    def test_m_function_nested_unnamed(self, type_tokens_module: object) -> None:
        # Unnamed parameter → falls back to cursor.type.spelling (canonical libclang form)
        assert self._fn_types(type_tokens_module, "m_function_nested") == [
            "::std::function<outer::inner::Nested (::std::string, outer::Mid)>"
        ]
