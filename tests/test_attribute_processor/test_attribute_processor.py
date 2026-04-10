"""Unit tests for AttributeProcessor and _parse_attribute helper."""

from __future__ import annotations

import pytest

from tsujikiri.attribute_processor import AttributeProcessor, _parse_attribute
from tsujikiri.configurations import AttributeHandlerConfig
from tsujikiri.ir import (
    IRClass,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
)


# ---------------------------------------------------------------------------
# _parse_attribute
# ---------------------------------------------------------------------------

class TestParseAttribute:
    def test_empty_string(self):
        # regex requires at least one non-'(' char → no match → fallback branch
        name, args = _parse_attribute("")
        assert name == ""
        assert args == []

    def test_simple_name(self):
        name, args = _parse_attribute("tsujikiri::skip")
        assert name == "tsujikiri::skip"
        assert args == []

    def test_name_with_string_arg(self):
        name, args = _parse_attribute('tsujikiri::rename("newName")')
        assert name == "tsujikiri::rename"
        assert args == ["newName"]

    def test_name_with_multiple_args(self):
        name, args = _parse_attribute('mygame::tag("foo", "bar")')
        assert name == "mygame::tag"
        assert args == ["foo", "bar"]

    def test_empty_parens(self):
        name, args = _parse_attribute("mygame::marker()")
        assert name == "mygame::marker"
        assert args == []

    def test_leading_trailing_whitespace(self):
        name, args = _parse_attribute("  tsujikiri::skip  ")
        assert name == "tsujikiri::skip"
        assert args == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module(*classes, functions=None, enums=None):
    m = IRModule(name="test")
    m.classes.extend(classes)
    m.functions.extend(functions or [])
    m.enums.extend(enums or [])
    return m


def _make_class(name="MyClass", **kwargs):
    return IRClass(name=name, qualified_name=name, namespace="ns", **kwargs)


def _make_method(method_name="doSomething", attrs=None):
    return IRMethod(
        name=method_name,
        spelling=method_name,
        qualified_name=f"ns::MyClass::{method_name}",
        return_type="void",
        attributes=attrs or [],
    )


def _processor(handlers=None):
    return AttributeProcessor(AttributeHandlerConfig(handlers=handlers or {}))


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::skip
# ---------------------------------------------------------------------------

class TestBuiltinSkip:
    def test_method_suppressed(self):
        method = _make_method(attrs=["tsujikiri::skip"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is False

    def test_class_suppressed(self):
        cls = _make_class(attributes=["tsujikiri::skip"])
        module = _make_module(cls)
        _processor().apply(module)
        assert cls.emit is False

    def test_field_suppressed(self):
        field = IRField(name="x", type_spelling="int", attributes=["tsujikiri::skip"])
        cls = _make_class(fields=[field])
        module = _make_module(cls)
        _processor().apply(module)
        assert field.emit is False

    def test_constructor_suppressed(self):
        ctor = IRConstructor(attributes=["tsujikiri::skip"])
        cls = _make_class(constructors=[ctor])
        module = _make_module(cls)
        _processor().apply(module)
        assert ctor.emit is False

    def test_function_suppressed(self):
        fn = IRFunction(
            name="helper", qualified_name="ns::helper", namespace="ns",
            return_type="void", attributes=["tsujikiri::skip"],
        )
        module = _make_module(functions=[fn])
        _processor().apply(module)
        assert fn.emit is False

    def test_enum_suppressed(self):
        enum = IREnum(name="Color", qualified_name="ns::Color", attributes=["tsujikiri::skip"])
        module = _make_module(enums=[enum])
        _processor().apply(module)
        assert enum.emit is False

    def test_enum_value_suppressed(self):
        val = IREnumValue(name="Red", value=0, attributes=["tsujikiri::skip"])
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        module = _make_module(enums=[enum])
        _processor().apply(module)
        assert val.emit is False

    def test_no_attributes_leaves_emit_true(self):
        method = _make_method(attrs=[])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is True


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::keep
# ---------------------------------------------------------------------------

class TestBuiltinKeep:
    def test_keep_re_enables_suppressed_method(self):
        method = _make_method(attrs=["tsujikiri::keep"])
        method.emit = False  # pre-suppressed (e.g. by FilterEngine)
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is True

    def test_keep_on_already_emitting_method_is_noop(self):
        method = _make_method(attrs=["tsujikiri::keep"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is True

    def test_keep_overrides_skip_when_both_present(self):
        # Last attribute wins — keep after skip re-enables
        method = _make_method(attrs=["tsujikiri::skip", "tsujikiri::keep"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is True


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::rename
# ---------------------------------------------------------------------------

class TestBuiltinRename:
    def test_method_renamed(self):
        method = _make_method(attrs=['tsujikiri::rename("myNewName")'])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.rename == "myNewName"

    def test_class_renamed(self):
        cls = _make_class(attributes=['tsujikiri::rename("Alias")'])
        module = _make_module(cls)
        _processor().apply(module)
        assert cls.rename == "Alias"

    def test_field_renamed(self):
        field = IRField(name="x_", type_spelling="int", attributes=['tsujikiri::rename("x")'])
        cls = _make_class(fields=[field])
        module = _make_module(cls)
        _processor().apply(module)
        assert field.rename == "x"

    def test_rename_without_arg_is_noop(self):
        method = _make_method(attrs=["tsujikiri::rename"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.rename is None


# ---------------------------------------------------------------------------
# Custom handlers
# ---------------------------------------------------------------------------

class TestCustomHandlers:
    def test_custom_skip(self):
        method = _make_method(attrs=["mygame::no_export"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor(handlers={"mygame::no_export": "skip"}).apply(module)
        assert method.emit is False

    def test_custom_keep(self):
        method = _make_method(attrs=["mygame::force_export"])
        method.emit = False
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor(handlers={"mygame::force_export": "keep"}).apply(module)
        assert method.emit is True

    def test_custom_rename(self):
        method = _make_method(attrs=['mygame::bind_as("luaName")'])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor(handlers={"mygame::bind_as": "rename"}).apply(module)
        assert method.rename == "luaName"

    def test_unknown_attribute_is_ignored(self):
        method = _make_method(attrs=["unknown::attr"])
        method.emit = True
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor().apply(module)
        assert method.emit is True
        assert method.rename is None

    def test_custom_overrides_builtin(self):
        # A custom handler for "tsujikiri::skip" mapped to "keep" would override.
        method = _make_method(attrs=["tsujikiri::skip"])
        cls = _make_class(methods=[method])
        module = _make_module(cls)
        _processor(handlers={"tsujikiri::skip": "keep"}).apply(module)
        assert method.emit is True  # custom "keep" wins over builtin "skip"


# ---------------------------------------------------------------------------
# Inner classes
# ---------------------------------------------------------------------------

class TestClassNestedEnum:
    """Cover _process_class lines that walk cls.enums and their values."""

    def test_nested_enum_suppressed(self):
        enum = IREnum(name="Color", qualified_name="ns::Foo::Color", attributes=["tsujikiri::skip"])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert enum.emit is False

    def test_nested_enum_value_suppressed(self):
        val = IREnumValue(name="Red", value=0, attributes=["tsujikiri::skip"])
        enum = IREnum(name="Color", qualified_name="ns::Foo::Color", values=[val])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert val.emit is False

    def test_nested_enum_value_keep(self):
        val = IREnumValue(name="Red", value=0, attributes=["tsujikiri::keep"])
        val.emit = False
        enum = IREnum(name="Color", qualified_name="ns::Foo::Color", values=[val])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert val.emit is True


class TestInnerClasses:
    def test_inner_class_method_suppressed(self):
        inner_method = _make_method(attrs=["tsujikiri::skip"])
        inner = IRClass(
            name="Inner", qualified_name="ns::MyClass::Inner", namespace="ns",
            methods=[inner_method],
        )
        outer = _make_class(inner_classes=[inner])
        module = _make_module(outer)
        _processor().apply(module)
        assert inner_method.emit is False
