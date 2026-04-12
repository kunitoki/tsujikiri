"""Tests for the pybind11 output format template."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import (
    IRBase,
    IRClass,
    IRCodeInjection,
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
def pybind11_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pybind11"))


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
    def test_pybind11_module_macro(self, pybind11_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "PYBIND11_MODULE(mymod, m)" in out

    def test_pybind11_includes(self, pybind11_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "#include <pybind11/pybind11.h>" in out
        assert "#include <pybind11/stl.h>" in out

    def test_namespace_alias(self, pybind11_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "namespace py = pybind11;" in out

    def test_auto_generated_comment(self, pybind11_output_config):
        mod = IRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "DO NOT EDIT" in out
        assert "pybind11" in out


# ---------------------------------------------------------------------------
# Enum binding
# ---------------------------------------------------------------------------

class TestEnumBinding:
    def test_enum_class(self, pybind11_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), IREnumValue("Green", 1)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert 'py::enum_<ns::Color>(m, "Color")' in out

    def test_enum_values(self, pybind11_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), IREnumValue("Green", 1)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '.value("Red", ns::Color::Red)' in out
        assert '.value("Green", ns::Color::Green)' in out

    def test_export_values(self, pybind11_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert ".export_values();" in out

    def test_enum_doc(self, pybind11_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color", doc="Color options",
                      values=[IREnumValue("Red", 0)])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '"Color options"' in out

    def test_enum_value_doc(self, pybind11_output_config):
        val = IREnumValue("Red", 0, doc="The red color")
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '"The red color"' in out

    def test_suppressed_enum_value_excluded(self, pybind11_output_config):
        val = IREnumValue("Reserved", 99)
        val.emit = False
        enum = IREnum(name="Color", qualified_name="ns::Color",
                      values=[IREnumValue("Red", 0), val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert "Reserved" not in out

    def test_renamed_enum_value(self, pybind11_output_config):
        val = IREnumValue("Red", 0, rename="red")
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = IRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '.value("red", ns::Color::Red)' in out


# ---------------------------------------------------------------------------
# Free function binding
# ---------------------------------------------------------------------------

class TestFunctionBinding:
    def test_simple_function(self, pybind11_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'm.def("compute", &ns::compute)' in out

    def test_function_with_arg(self, pybind11_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double",
                        parameters=[IRParameter("x", "double")])
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x")' in out

    def test_function_with_default(self, pybind11_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double",
                        parameters=[IRParameter("x", "double", default_value="1.0")])
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x") = 1.0' in out

    def test_function_doc(self, pybind11_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double", doc="Computes")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert '"Computes"' in out

    def test_function_wrapper_code(self, pybind11_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="double",
                        wrapper_code="+[]() { return 42.0; }")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert "+[]() { return 42.0; }" in out
        assert "&ns::compute" not in out

    def test_camel_to_snake_function_name(self, pybind11_output_config):
        fn = IRFunction(name="computeArea", qualified_name="ns::computeArea",
                        namespace="ns", return_type="double")
        mod = IRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert '"compute_area"' in out


# ---------------------------------------------------------------------------
# Class binding
# ---------------------------------------------------------------------------

class TestClassBinding:
    def test_simple_class(self, pybind11_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'py::class_<ns::Foo>(m, "Foo")' in out

    def test_class_doc(self, pybind11_output_config):
        cls = _simple_class()
        cls.doc = "A great class"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"A great class"' in out

    def test_class_with_single_base(self, pybind11_output_config):
        cls = _simple_class(bases=[IRBase("ns::Base", "public")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, ns::Base>" in out

    def test_class_with_multiple_public_bases(self, pybind11_output_config):
        cls = _simple_class(bases=[IRBase("ns::A", "public"), IRBase("ns::B", "public")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, ns::A, ns::B>" in out

    def test_protected_base_excluded(self, pybind11_output_config):
        cls = _simple_class(bases=[IRBase("ns::Hidden", "protected")])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "Hidden" not in out

    def test_constructor(self, pybind11_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert ".def(py::init<int>())" in out

    def test_force_abstract_suppresses_constructor(self, pybind11_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::init" not in out

    def test_method(self, pybind11_output_config):
        method = IRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int", is_const=True)
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("get_value", &ns::Foo::getValue)' in out

    def test_method_doc(self, pybind11_output_config):
        method = IRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int",
                          doc="Gets the value")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"Gets the value"' in out

    def test_static_method(self, pybind11_output_config):
        method = IRMethod(name="create", spelling="create",
                          qualified_name="ns::Foo::create", return_type="ns::Foo*",
                          is_static=True)
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_static("create"' in out

    def test_readwrite_field(self, pybind11_output_config):
        field = IRField(name="x_", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_readwrite("x_", &ns::Foo::x_)' in out

    def test_readonly_field(self, pybind11_output_config):
        field = IRField(name="max_", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_readonly("max_"' in out

    def test_field_doc(self, pybind11_output_config):
        field = IRField(name="x_", type_spelling="int", doc="X field")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"X field"' in out

    def test_method_with_default_arg(self, pybind11_output_config):
        p = IRParameter("x", "int", default_value="0")
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x") = 0' in out

    def test_wrapper_code_method(self, pybind11_output_config):
        method = IRMethod(name="doThing", spelling="doThing",
                          qualified_name="ns::Foo::doThing", return_type="void",
                          wrapper_code="+[](Foo& self) { self.doThing(); }")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "+[](Foo& self) { self.doThing(); }" in out


# ---------------------------------------------------------------------------
# Format discovery
# ---------------------------------------------------------------------------

class TestPybind11FormatDiscovery:
    def test_pybind11_in_list_formats(self):
        from tsujikiri.formats import list_builtin_formats
        fmts = list_builtin_formats()
        assert "pybind11" in fmts

    def test_pybind11_format_name(self, pybind11_output_config):
        assert pybind11_output_config.format_name == "pybind11"

    def test_pybind11_language_is_cpp(self, pybind11_output_config):
        assert pybind11_output_config.language == "cpp"
