"""Tests for the luau (.d.luau Luau type definitions) output format template."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import IRCodeInjection
from tsujikiri.tir import (
    TIRBase,
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
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def luau_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path

    return load_output_config(resolve_format_path("luau"))


def _gen(module: TIRModule, cfg, api_version: str = "") -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf, api_version=api_version)
    return buf.getvalue()


def _simple_class(
    name: str = "Foo",
    qname: str = "Foo",
    methods=None,
    fields=None,
    ctors=None,
    bases=None,
    **kwargs,
) -> TIRClass:
    return TIRClass(
        name=name,
        qualified_name=qname,
        namespace="",
        variable_name=f"class{name}",
        methods=methods or [],
        fields=fields or [],
        constructors=ctors or [],
        bases=bases or [],
        **kwargs,
    )


def _module_with_class(cls: TIRClass) -> TIRModule:
    mod = TIRModule(name="demo")
    mod.classes = [cls]
    mod.class_by_name = {cls.qualified_name: cls}
    return mod


def _method(name: str, return_type: str = "void", params=None, **kwargs) -> TIRMethod:
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"Foo::{name}",
        return_type=return_type,
        parameters=params or [],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Format discovery / configuration
# ---------------------------------------------------------------------------


class TestFormatDiscovery:
    def test_luau_in_list_formats(self):
        from tsujikiri.formats import list_builtin_formats

        assert "luau" in list_builtin_formats()

    def test_format_name(self, luau_output_config):
        assert luau_output_config.format_name == "luau"

    def test_language_is_luau(self, luau_output_config):
        assert luau_output_config.language == "luau"

    def test_extension(self, luau_output_config):
        assert luau_output_config.extension == ".d.luau"

    def test_type_mappings_loaded(self, luau_output_config):
        assert luau_output_config.type_mappings["int"] == "number"
        assert luau_output_config.type_mappings["bool"] == "boolean"
        assert luau_output_config.type_mappings["std::string"] == "string"
        assert luau_output_config.type_mappings["void"] == "nil"

    def test_operator_mappings_loaded(self, luau_output_config):
        assert luau_output_config.operator_mappings["operator+"] == "__add"

    def test_expand_default_arguments(self, luau_output_config):
        assert luau_output_config.expand_default_arguments is True


# ---------------------------------------------------------------------------
# Prologue / api version
# ---------------------------------------------------------------------------


class TestPrologue:
    def test_strict_header(self, luau_output_config):
        out = _gen(TIRModule(name="demo"), luau_output_config)
        assert out.startswith("--!strict")

    def test_auto_generated_comment(self, luau_output_config):
        out = _gen(TIRModule(name="mymod"), luau_output_config)
        assert "DO NOT EDIT" in out
        assert "mymod" in out

    def test_api_version_function_when_set(self, luau_output_config):
        out = _gen(TIRModule(name="demo"), luau_output_config, api_version="1.2.3")
        assert "declare function get_api_version(): string" in out

    def test_no_api_version_function_when_absent(self, luau_output_config):
        out = _gen(TIRModule(name="demo"), luau_output_config)
        assert "get_api_version" not in out


# ---------------------------------------------------------------------------
# Class declarations
# ---------------------------------------------------------------------------


class TestClassDeclaration:
    def test_extern_type_emitted(self, luau_output_config):
        cls = _simple_class()
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "declare extern type Foo with" in out
        assert out.rstrip().endswith("end") or "\nend" in out

    def test_empty_class_has_end(self, luau_output_config):
        cls = _simple_class()
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "declare extern type Foo with\nend" in out

    def test_class_doc_comment(self, luau_output_config):
        cls = _simple_class(doc="A nice class")
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "--- A nice class" in out

    def test_class_deprecated(self, luau_output_config):
        cls = _simple_class(is_deprecated=True, deprecation_message="use Bar")
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "--- @deprecated use Bar" in out

    def test_class_deprecated_without_message(self, luau_output_config):
        cls = _simple_class(is_deprecated=True)
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "--- @deprecated" in out

    def test_class_extends_base(self, luau_output_config):
        base = _simple_class(name="Base", qname="Base")
        derived = _simple_class(name="Derived", qname="Derived", bases=[TIRBase("Base", "public")])
        mod = TIRModule(name="demo")
        mod.classes = [base, derived]
        mod.class_by_name = {"Base": base, "Derived": derived}
        out = _gen(mod, luau_output_config)
        assert "declare extern type Derived extends Base with" in out

    def test_class_no_base_no_extends(self, luau_output_config):
        cls = _simple_class()
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "extends" not in out


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


class TestFields:
    def test_instance_field(self, luau_output_config):
        cls = _simple_class(fields=[TIRField(name="x", type_spelling="float")])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    x: number" in out

    def test_instance_field_doc(self, luau_output_config):
        cls = _simple_class(fields=[TIRField(name="x", type_spelling="float", doc="the x coord")])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "--- the x coord" in out

    def test_static_field_in_table(self, luau_output_config):
        cls = _simple_class(fields=[TIRField(name="count", type_spelling="int", is_static=True)])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "declare Foo: {" in out
        assert "    count: number," in out

    def test_static_field_not_in_type_body(self, luau_output_config):
        cls = _simple_class(fields=[TIRField(name="count", type_spelling="int", is_static=True)])
        out = _gen(_module_with_class(cls), luau_output_config)
        body = out.split("declare extern type Foo with", 1)[1].split("end", 1)[0]
        assert "count" not in body


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------


class TestMethods:
    def test_instance_method_self_param(self, luau_output_config):
        cls = _simple_class(methods=[_method("length", "float")])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    function length(self): number" in out

    def test_instance_method_with_params(self, luau_output_config):
        cls = _simple_class(methods=[_method("dot", "float", [TIRParameter("o", "float")])])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    function dot(self, o: number): number" in out

    def test_instance_method_doc(self, luau_output_config):
        cls = _simple_class(methods=[_method("length", "float", doc="compute length")])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "--- compute length" in out

    def test_overloaded_instance_methods_multiple_lines(self, luau_output_config):
        cls = _simple_class(
            methods=[
                _method("set", "void", [TIRParameter("v", "int")]),
                _method("set", "void", [TIRParameter("v", "float")]),
            ]
        )
        out = _gen(_module_with_class(cls), luau_output_config)
        assert out.count("function set(self") == 2

    def test_static_method_in_table(self, luau_output_config):
        cls = _simple_class(methods=[_method("make", "Foo", [TIRParameter("v", "int")], is_static=True)])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "declare Foo: {" in out
        assert "make: ((v: number) -> Foo)," in out

    def test_overloaded_static_method_intersection(self, luau_output_config):
        cls = _simple_class(
            methods=[
                _method("make", "Foo", [TIRParameter("v", "int")], is_static=True),
                _method("make", "Foo", [TIRParameter("v", "float"), TIRParameter("w", "float")], is_static=True),
            ]
        )
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "make: ((v: number) -> Foo) & ((v: number, w: number) -> Foo)," in out

    def test_operator_method_as_metamethod(self, luau_output_config):
        cls = _simple_class(
            methods=[
                _method(
                    "operator+",
                    "Foo",
                    [TIRParameter("o", "Foo")],
                    is_operator=True,
                    operator_type="operator+",
                )
            ]
        )
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    function __add(self, o: Foo): Foo" in out


# ---------------------------------------------------------------------------
# Constructors
# ---------------------------------------------------------------------------


class TestConstructors:
    def test_single_constructor(self, luau_output_config):
        cls = _simple_class(ctors=[TIRConstructor(parameters=[TIRParameter("v", "int")])])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    new: ((v: number) -> Foo)," in out

    def test_default_constructor_no_params(self, luau_output_config):
        cls = _simple_class(ctors=[TIRConstructor(parameters=[])])
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "    new: (() -> Foo)," in out

    def test_overloaded_constructors_intersection(self, luau_output_config):
        cls = _simple_class(
            ctors=[
                TIRConstructor(parameters=[TIRParameter("v", "int")]),
                TIRConstructor(parameters=[TIRParameter("v", "float"), TIRParameter("w", "float")]),
            ]
        )
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "new: ((v: number) -> Foo) & ((v: number, w: number) -> Foo)," in out

    def test_force_abstract_no_constructor(self, luau_output_config):
        cls = _simple_class(ctors=[TIRConstructor(parameters=[])], force_abstract=True)
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "new:" not in out


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_named_enum_type_and_table(self, luau_output_config):
        enum = TIREnum(
            name="Color",
            qualified_name="Color",
            values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)],
        )
        mod = TIRModule(name="demo", enums=[enum])
        out = _gen(mod, luau_output_config)
        assert "export type Color = number" in out
        assert "declare Color: {" in out
        assert "    Red: number," in out
        assert "    Green: number," in out

    def test_named_enum_doc(self, luau_output_config):
        enum = TIREnum(
            name="Color",
            qualified_name="Color",
            values=[TIREnumValue("Red", 0)],
            doc="colors",
        )
        mod = TIRModule(name="demo", enums=[enum])
        out = _gen(mod, luau_output_config)
        assert "--- colors" in out

    def test_anonymous_enum_globals(self, luau_output_config):
        enum = TIREnum(
            name="",
            qualified_name="",
            is_anonymous=True,
            values=[TIREnumValue("ALPHA", 0), TIREnumValue("BETA", 1)],
        )
        mod = TIRModule(name="demo", enums=[enum])
        out = _gen(mod, luau_output_config)
        assert "declare ALPHA: number" in out
        assert "declare BETA: number" in out


# ---------------------------------------------------------------------------
# Free functions
# ---------------------------------------------------------------------------


def _free_fn(name: str, return_type: str = "void", params=None, **kwargs) -> TIRFunction:
    return TIRFunction(
        name=name,
        qualified_name=name,
        namespace="",
        return_type=return_type,
        parameters=params or [],
        **kwargs,
    )


class TestFreeFunctions:
    def test_single_free_function(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [_free_fn("doThing", "int", [TIRParameter("a", "int")])]
        out = _gen(mod, luau_output_config)
        assert "declare function doThing(a: number): number" in out

    def test_free_function_void_returns_nil(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [_free_fn("doThing", "void")]
        out = _gen(mod, luau_output_config)
        assert "declare function doThing(): nil" in out

    def test_free_function_doc(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [_free_fn("doThing", "void", doc="does a thing")]
        out = _gen(mod, luau_output_config)
        assert "--- does a thing" in out

    def test_free_function_deprecated(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [_free_fn("oldFn", "void", is_deprecated=True, deprecation_message="use newFn")]
        out = _gen(mod, luau_output_config)
        assert "--- @deprecated use newFn" in out

    def test_overloaded_free_function_intersection(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [
            _free_fn("mix", "int", [TIRParameter("a", "int")]),
            _free_fn("mix", "int", [TIRParameter("a", "float"), TIRParameter("b", "float")]),
        ]
        out = _gen(mod, luau_output_config)
        assert "declare mix: ((a: number) -> number) & ((a: number, b: number) -> number)" in out

    def test_overloaded_free_function_doc_and_deprecated(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.functions = [
            _free_fn("mix", "int", [TIRParameter("a", "int")], doc="mix things", is_deprecated=True),
            _free_fn("mix", "int", [TIRParameter("a", "float")]),
        ]
        out = _gen(mod, luau_output_config)
        assert "--- mix things" in out
        assert "--- @deprecated" in out


# ---------------------------------------------------------------------------
# Free-function operators attached to a class
# ---------------------------------------------------------------------------


class TestFreeOperators:
    def test_free_operator_as_metamethod(self, luau_output_config):
        cls = _simple_class(name="Vec3", qname="Vec3")
        fn = _free_fn(
            "operator+",
            "Vec3",
            [TIRParameter("a", "Vec3"), TIRParameter("b", "Vec3")],
            is_operator=True,
            operator_type="operator+",
        )
        mod = TIRModule(name="demo")
        mod.classes = [cls]
        mod.class_by_name = {"Vec3": cls}
        mod.functions = [fn]
        out = _gen(mod, luau_output_config)
        assert "    function __add(self, b: Vec3): Vec3" in out


# ---------------------------------------------------------------------------
# Code injections
# ---------------------------------------------------------------------------


class TestCodeInjections:
    def test_module_beginning_injection(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.code_injections = [IRCodeInjection("beginning", "-- injected top")]
        out = _gen(mod, luau_output_config)
        assert "-- injected top" in out

    def test_module_end_injection(self, luau_output_config):
        mod = TIRModule(name="demo")
        mod.code_injections = [IRCodeInjection("end", "-- injected bottom")]
        out = _gen(mod, luau_output_config)
        assert "-- injected bottom" in out

    def test_class_end_injection(self, luau_output_config):
        cls = _simple_class()
        cls.code_injections = [IRCodeInjection("end", "-- class end")]
        out = _gen(_module_with_class(cls), luau_output_config)
        assert "-- class end" in out
