"""Unit tests for AttributeProcessor and _parse_attribute helper."""

from __future__ import annotations

import pytest

from tsujikiri.attribute_processor import (
    AttributeProcessor,
    _apply_complex_builtin,
    _parse_attribute,
)
from tsujikiri.configurations import AttributeHandlerConfig
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIREnumValue,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
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
    m = TIRModule(name="test")
    m.classes.extend(classes)
    m.functions.extend(functions or [])
    m.enums.extend(enums or [])
    return m


def _make_class(name="MyClass", **kwargs):
    return TIRClass(name=name, qualified_name=name, namespace="ns", **kwargs)


def _make_method(method_name="doSomething", attrs=None):
    return TIRMethod(
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
        field = TIRField(name="x", type_spelling="int", attributes=["tsujikiri::skip"])
        cls = _make_class(fields=[field])
        module = _make_module(cls)
        _processor().apply(module)
        assert field.emit is False

    def test_constructor_suppressed(self):
        ctor = TIRConstructor(attributes=["tsujikiri::skip"])
        cls = _make_class(constructors=[ctor])
        module = _make_module(cls)
        _processor().apply(module)
        assert ctor.emit is False

    def test_function_suppressed(self):
        fn = TIRFunction(
            name="helper", qualified_name="ns::helper", namespace="ns",
            return_type="void", attributes=["tsujikiri::skip"],
        )
        module = _make_module(functions=[fn])
        _processor().apply(module)
        assert fn.emit is False

    def test_enum_suppressed(self):
        enum = TIREnum(name="Color", qualified_name="ns::Color", attributes=["tsujikiri::skip"])
        module = _make_module(enums=[enum])
        _processor().apply(module)
        assert enum.emit is False

    def test_enum_value_suppressed(self):
        val = TIREnumValue(name="Red", value=0, attributes=["tsujikiri::skip"])
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[val])
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
        field = TIRField(name="x_", type_spelling="int", attributes=['tsujikiri::rename("x")'])
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
        enum = TIREnum(name="Color", qualified_name="ns::Foo::Color", attributes=["tsujikiri::skip"])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert enum.emit is False

    def test_nested_enum_value_suppressed(self):
        val = TIREnumValue(name="Red", value=0, attributes=["tsujikiri::skip"])
        enum = TIREnum(name="Color", qualified_name="ns::Foo::Color", values=[val])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert val.emit is False

    def test_nested_enum_value_keep(self):
        val = TIREnumValue(name="Red", value=0, attributes=["tsujikiri::keep"])
        val.emit = False
        enum = TIREnum(name="Color", qualified_name="ns::Foo::Color", values=[val])
        cls = _make_class(enums=[enum])
        module = _make_module(cls)
        _processor().apply(module)
        assert val.emit is True


class TestInnerClasses:
    def test_inner_class_method_suppressed(self):
        inner_method = _make_method(attrs=["tsujikiri::skip"])
        inner = TIRClass(
            name="Inner", qualified_name="ns::MyClass::Inner", namespace="ns",
            methods=[inner_method],  # type: ignore[arg-type]
        )
        outer = _make_class(inner_classes=[inner])
        module = _make_module(outer)
        _processor().apply(module)
        assert inner_method.emit is False


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::readonly
# ---------------------------------------------------------------------------

class TestBuiltinReadonly:
    def test_sets_read_only_on_field(self):
        field = TIRField(name="x", type_spelling="int", attributes=["tsujikiri::readonly"])
        cls = _make_class(fields=[field])
        _processor().apply(_make_module(cls))
        assert field.read_only is True

    def test_no_effect_on_method(self):
        # Method has no read_only attribute — handler is silently a no-op
        method = _make_method(attrs=["tsujikiri::readonly"])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))
        assert method.emit is True  # not suppressed; just no-op

    def test_apply_complex_builtin_readonly_no_attr(self):
        # Node without read_only → no AttributeError
        method = _make_method()
        _apply_complex_builtin("tsujikiri::readonly", [], method)
        assert method.emit is True


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::thread_safe
# ---------------------------------------------------------------------------

class TestBuiltinThreadSafe:
    def test_sets_allow_thread_on_method(self):
        method = _make_method(attrs=["tsujikiri::thread_safe"])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))
        assert method.allow_thread is True

    def test_sets_allow_thread_on_function(self):
        fn = TIRFunction(
            name="heavy", qualified_name="ns::heavy", namespace="ns",
            return_type="void", attributes=["tsujikiri::thread_safe"],
        )
        _processor().apply(_make_module(functions=[fn]))
        assert fn.allow_thread is True

    def test_no_effect_on_field(self):
        field = TIRField(name="x", type_spelling="int", attributes=["tsujikiri::thread_safe"])
        cls = _make_class(fields=[field])
        _processor().apply(_make_module(cls))
        # Field has no allow_thread; handler is silently a no-op
        assert field.emit is True


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::doc
# ---------------------------------------------------------------------------

class TestBuiltinDoc:
    def test_sets_doc_on_method(self):
        method = _make_method(attrs=['tsujikiri::doc("Does something")'])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))
        assert method.doc == "Does something"

    def test_sets_doc_on_class(self):
        cls = _make_class(attributes=['tsujikiri::doc("My class")'])
        _processor().apply(_make_module(cls))
        assert cls.doc == "My class"

    def test_sets_doc_on_field(self):
        field = TIRField(name="x", type_spelling="int", attributes=['tsujikiri::doc("x coord")'])
        cls = _make_class(fields=[field])
        _processor().apply(_make_module(cls))
        assert field.doc == "x coord"

    def test_no_args_is_noop(self):
        method = _make_method(attrs=["tsujikiri::doc"])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))
        assert method.doc is None

    def test_doc_on_node_without_doc_attr_is_noop(self):
        """Node with no ``doc`` field — _apply_complex_builtin must not raise."""
        class _NoDocNode:
            pass

        node = _NoDocNode()
        _apply_complex_builtin("tsujikiri::doc", ["some text"], node)
        assert not hasattr(node, "doc")


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::rename_argument
# ---------------------------------------------------------------------------

class TestBuiltinRenameArgument:
    def test_renames_parameter(self):
        param = TIRParameter(name="x", type_spelling="int")
        method = TIRMethod(
            name="set", spelling="set", qualified_name="ns::Cls::set", return_type="void",
            parameters=[param], attributes=['tsujikiri::rename_argument("x", "value")'],
        )
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert param.rename == "value"

    def test_wrong_name_leaves_unchanged(self):
        param = TIRParameter(name="y", type_spelling="int")
        method = TIRMethod(
            name="set", spelling="set", qualified_name="ns::Cls::set", return_type="void",
            parameters=[param], attributes=['tsujikiri::rename_argument("x", "value")'],
        )
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert param.rename is None

    def test_single_arg_is_noop(self):
        method = _make_method(attrs=['tsujikiri::rename_argument("x")'])
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))  # no crash

    def test_on_function(self):
        param = TIRParameter(name="radius", type_spelling="double")
        fn = TIRFunction(
            name="f", qualified_name="ns::f", namespace="ns", return_type="void",
            parameters=[param], attributes=['tsujikiri::rename_argument("radius", "r")'],
        )
        _processor().apply(_make_module(functions=[fn]))
        assert param.rename == "r"


# ---------------------------------------------------------------------------
# Built-in: tsujikiri::type_map
# ---------------------------------------------------------------------------

class TestBuiltinTypeMap:
    def test_overrides_param_type(self):
        param = TIRParameter(name="x", type_spelling="juce::String")
        method = TIRMethod(
            name="set", spelling="set", qualified_name="ns::Cls::set", return_type="void",
            parameters=[param],
            attributes=['tsujikiri::type_map("juce::String", "std::string")'],
        )
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert param.type_override == "std::string"

    def test_overrides_return_type(self):
        method = TIRMethod(
            name="get", spelling="get", qualified_name="ns::Cls::get",
            return_type="juce::String", parameters=[],
            attributes=['tsujikiri::type_map("juce::String", "std::string")'],
        )
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert method.return_type_override == "std::string"

    def test_overrides_field_type(self):
        field = TIRField(
            name="label", type_spelling="juce::String",
            attributes=['tsujikiri::type_map("juce::String", "std::string")'],
        )
        cls = _make_class(fields=[field])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert field.type_override == "std::string"

    def test_non_matching_type_unchanged(self):
        param = TIRParameter(name="x", type_spelling="int")
        method = TIRMethod(
            name="set", spelling="set", qualified_name="ns::Cls::set", return_type="void",
            parameters=[param],
            attributes=['tsujikiri::type_map("juce::String", "std::string")'],
        )
        cls = _make_class(methods=[method])  # type: ignore[arg-type]
        _processor().apply(_make_module(cls))
        assert param.type_override is None

    def test_single_arg_is_noop(self):
        method = _make_method(attrs=['tsujikiri::type_map("only_one")'])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))  # no crash


# ---------------------------------------------------------------------------
# tsujikiri::arithmetic and tsujikiri::hashable (Gap 10 / Gap 15)
# ---------------------------------------------------------------------------

class TestArithmeticAttribute:
    def test_arithmetic_sets_flag_on_enum(self):
        enum = TIREnum(name="Flags", qualified_name="ns::Flags",
                       attributes=["tsujikiri::arithmetic"])
        mod = TIRModule(name="m", enums=[enum])  # type: ignore[arg-type, list-item]
        _processor().apply(mod)
        assert enum.is_arithmetic is True

    def test_arithmetic_noop_on_node_without_flag(self):
        """Applying arithmetic to a node that lacks is_arithmetic is a no-op."""
        method = _make_method(attrs=["tsujikiri::arithmetic"])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))  # no crash, no attribute set
        # TIRMethod has no is_arithmetic attribute — no side effects expected
        assert method.is_deprecated is False  # unrelated field unchanged

    def test_arithmetic_via_apply_complex_builtin_false_branch(self):
        """Direct call: node without is_arithmetic should not raise."""
        method = _make_method()
        _apply_complex_builtin("tsujikiri::arithmetic", [], method)
        # No is_arithmetic on TIRMethod — should be a no-op


class TestHashableAttribute:
    def test_hashable_sets_flag_on_class(self):
        cls = _make_class(attributes=["tsujikiri::hashable"])
        _processor().apply(_make_module(cls))
        assert cls.generate_hash is True

    def test_hashable_noop_on_node_without_flag(self):
        """Applying hashable to a node that lacks generate_hash is a no-op."""
        method = _make_method(attrs=["tsujikiri::hashable"])
        cls = _make_class(methods=[method])
        _processor().apply(_make_module(cls))  # no crash
        # TIRMethod has no generate_hash attribute — no side effects
        assert method.is_deprecated is False  # unrelated field unchanged

    def test_hashable_via_apply_complex_builtin_false_branch(self):
        """Direct call: node without generate_hash should not raise."""
        method = _make_method()
        _apply_complex_builtin("tsujikiri::hashable", [], method)
        # No generate_hash on TIRMethod — should be a no-op
