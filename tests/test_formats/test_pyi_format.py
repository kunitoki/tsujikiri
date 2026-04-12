"""Tests for the pyi (Python type stubs) output format template."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import (
    IRBase,
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pyi_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pyi"))


def _gen(module: IRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _simple_class(
    name: str = "Foo",
    qname: str = "ns::Foo",
    methods=None,
    fields=None,
    ctors=None,
    bases=None,
) -> IRClass:
    return IRClass(
        name=name,
        qualified_name=qname,
        namespace="ns",
        variable_name=f"class{name}",
        methods=methods or [],
        fields=fields or [],
        constructors=ctors or [],
        bases=bases or [],
    )


# ---------------------------------------------------------------------------
# Module-level prologue
# ---------------------------------------------------------------------------

class TestPrologue:
    def test_auto_generated_comment(self, pyi_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "DO NOT EDIT" in out
        assert "pyi" in out or "mymod" in out

    def test_future_annotations_import(self, pyi_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "from __future__ import annotations" in out

    def test_overload_import(self, pyi_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "from typing import overload" in out

    def test_api_version_attr_when_set(self, pyi_output_config):
        mod = IRModule(name="mymod")
        buf = io.StringIO()
        Generator(pyi_output_config).generate(mod, buf, api_version="1.2.3")
        out = buf.getvalue()
        assert "__api_version__: str" in out

    def test_no_api_version_attr_when_absent(self, pyi_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "__api_version__" not in out


# ---------------------------------------------------------------------------
# Enum binding
# ---------------------------------------------------------------------------

class TestEnumBinding:
    def test_enum_class_inherits_int(self, pyi_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), IREnumValue("Green", 1)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "class Color(int):" in out

    def test_enum_values_as_class_attrs(self, pyi_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), IREnumValue("Green", 1)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "Red: Color" in out
        assert "Green: Color" in out

    def test_enum_doc(self, pyi_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color", doc="Color options",
                      values=[IREnumValue("Red", 0)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert '"""Color options"""' in out

    def test_enum_value_doc(self, pyi_output_config):
        val = IREnumValue("Red", 0, doc="The red color")
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert '"""The red color"""' in out

    def test_suppressed_enum_value_excluded(self, pyi_output_config):
        val = IREnumValue("Reserved", 99)
        val.emit = False
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "Reserved" not in out

    def test_renamed_enum_value(self, pyi_output_config):
        val = IREnumValue("Red", 0, rename="red")
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "red: Color" in out
        assert "Red: Color" not in out


# ---------------------------------------------------------------------------
# Free function binding
# ---------------------------------------------------------------------------

class TestFunctionBinding:
    def test_simple_function(self, pyi_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="int")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute() -> int: ..." in out

    def test_function_type_mapping(self, pyi_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "-> float: ..." in out

    def test_function_with_arg(self, pyi_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="int",
                        parameters=[IRParameter("x", "double")])
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute(x: float) -> int: ..." in out

    def test_function_with_default(self, pyi_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="int",
                        parameters=[IRParameter("x", "double", default_value="1.0")])
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute(x: float = 1.0) -> int: ..." in out

    def test_function_doc(self, pyi_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="int", doc="Computes something")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert '"""Computes something"""' in out

    def test_camel_to_snake_function_name(self, pyi_output_config):
        fn = IRFunction(name="computeArea", qualified_name="ns::computeArea",
                        namespace="ns", return_type="int")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute_area()" in out

    def test_void_return_maps_to_none(self, pyi_output_config):
        fn = IRFunction(name="reset", qualified_name="ns::reset",
                        namespace="ns", return_type="void")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "-> None: ..." in out

    def test_function_multiple_params(self, pyi_output_config):
        fn = IRFunction(name="add", qualified_name="ns::add",
                        namespace="ns", return_type="int",
                        parameters=[IRParameter("x", "int"), IRParameter("y", "int")])
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def add(x: int, y: int) -> int: ..." in out


# ---------------------------------------------------------------------------
# Class binding
# ---------------------------------------------------------------------------

class TestClassBinding:
    def test_simple_class(self, pyi_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo:" in out

    def test_class_doc(self, pyi_output_config):
        cls = _simple_class()
        cls.doc = "A great class"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""A great class"""' in out

    def test_class_with_single_base(self, pyi_output_config):
        cls = _simple_class(bases=[IRBase("ns::Base", "public")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo(Base):" in out

    def test_class_with_multiple_public_bases(self, pyi_output_config):
        cls = _simple_class(bases=[IRBase("ns::A", "public"), IRBase("ns::B", "public")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo(A, B):" in out

    def test_protected_base_excluded(self, pyi_output_config):
        cls = _simple_class(bases=[IRBase("ns::Hidden", "protected")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "Hidden" not in out
        assert "class Foo:" in out

    def test_constructor_no_args(self, pyi_output_config):
        ctor = IRConstructor(parameters=[])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self) -> None: ..." in out

    def test_constructor_with_args(self, pyi_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self, v: int) -> None: ..." in out

    def test_constructor_with_default(self, pyi_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int", default_value="0")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self, v: int = 0) -> None: ..." in out

    def test_force_abstract_suppresses_constructor(self, pyi_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "__init__" not in out

    def test_method(self, pyi_output_config):
        method = IRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int", is_const=True)
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def get_value(self) -> int: ..." in out

    def test_method_type_mapping(self, pyi_output_config):
        method = IRMethod(name="getLabel", spelling="getLabel",
                          qualified_name="ns::Foo::getLabel", return_type="std::string")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "-> str: ..." in out

    def test_method_doc(self, pyi_output_config):
        method = IRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int",
                          doc="Gets the value")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""Gets the value"""' in out

    def test_static_method(self, pyi_output_config):
        method = IRMethod(name="create", spelling="create",
                          qualified_name="ns::Foo::create", return_type="ns::Foo*",
                          is_static=True)
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "@staticmethod" in out
        assert "def create()" in out

    def test_static_method_no_self(self, pyi_output_config):
        method = IRMethod(name="create", spelling="create",
                          qualified_name="ns::Foo::create", return_type="ns::Foo*",
                          is_static=True,
                          parameters=[IRParameter("x", "int")])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def create(x: int)" in out
        assert "def create(self" not in out

    def test_readwrite_field(self, pyi_output_config):
        field = IRField(name="x_", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "x_: int" in out
        assert "read-only" not in out

    def test_readonly_field(self, pyi_output_config):
        field = IRField(name="max_", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "max_: int" in out
        assert "read-only" in out

    def test_field_type_mapping(self, pyi_output_config):
        field = IRField(name="label_", type_spelling="std::string")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "label_: str" in out

    def test_field_doc(self, pyi_output_config):
        field = IRField(name="x_", type_spelling="int", doc="X coordinate")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""X coordinate"""' in out

    def test_method_with_default_arg(self, pyi_output_config):
        p = IRParameter("x", "int", default_value="0")
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def compute(self, x: int = 0) -> int: ..." in out

    def test_overloaded_methods(self, pyi_output_config):
        m1 = IRMethod(name="process", spelling="process",
                      qualified_name="ns::Foo::process", return_type="int",
                      parameters=[IRParameter("x", "int")])
        m2 = IRMethod(name="process", spelling="process",
                      qualified_name="ns::Foo::process", return_type="float",
                      parameters=[IRParameter("x", "double")])
        cls = _simple_class(methods=[m1, m2])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert out.count("@overload") == 2
        assert "def process(self, x: int) -> int: ..." in out
        assert "def process(self, x: float) -> float: ..." in out

    def test_overloaded_static_methods(self, pyi_output_config):
        m1 = IRMethod(name="make", spelling="make",
                      qualified_name="ns::Foo::make", return_type="ns::Foo*",
                      is_static=True, parameters=[IRParameter("x", "int")])
        m2 = IRMethod(name="make", spelling="make",
                      qualified_name="ns::Foo::make", return_type="ns::Foo*",
                      is_static=True, parameters=[IRParameter("x", "double")])
        cls = _simple_class(methods=[m1, m2])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert out.count("@overload") == 2
        assert out.count("@staticmethod") == 2
        assert "def make(x: int)" in out
        assert "def make(x: float)" in out


# ---------------------------------------------------------------------------
# Format discovery
# ---------------------------------------------------------------------------

class TestPyiFormatDiscovery:
    def test_pyi_in_list_formats(self):
        from tsujikiri.formats import list_builtin_formats
        fmts = list_builtin_formats()
        assert "pyi" in fmts

    def test_pyi_format_name(self, pyi_output_config):
        assert pyi_output_config.format_name == "pyi"

    def test_pyi_language_is_python(self, pyi_output_config):
        assert pyi_output_config.language == "python"

    def test_type_mappings_loaded(self, pyi_output_config):
        assert pyi_output_config.type_mappings["double"] == "float"
        assert pyi_output_config.type_mappings["std::string"] == "str"
        assert pyi_output_config.type_mappings["bool"] == "bool"
        assert pyi_output_config.type_mappings["void"] == "None"
