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
        assert '.def(py::init<int>(), py::arg("v"))' in out

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


# ---------------------------------------------------------------------------
# Trampoline class generation
# ---------------------------------------------------------------------------

class TestTrampolineGeneration:
    def test_no_trampoline_for_nonvirtual_class(self, pybind11_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "PyFoo" not in out
        assert "PYBIND11_OVERRIDE" not in out

    def test_trampoline_class_generated_for_virtual_method(self, pybind11_output_config):
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True)
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "class PyFoo : public ns::Foo" in out
        assert "using ns::Foo::Foo;" in out
        assert 'PYBIND11_OVERRIDE_NAME(int, ns::Foo, "compute", compute);' in out

    def test_trampoline_uses_override_pure_for_pure_virtual(self, pybind11_output_config):
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True, is_pure_virtual=True)
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        cls.is_abstract = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'PYBIND11_OVERRIDE_PURE_NAME(int, ns::Foo, "compute", compute);' in out

    def test_trampoline_const_method_has_const_qualifier(self, pybind11_output_config):
        method = IRMethod(name="name", spelling="name",
                          qualified_name="ns::Foo::name", return_type="std::string",
                          is_virtual=True, is_const=True)
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "std::string name(" in out
        assert ") const override" in out

    def test_trampoline_method_with_params(self, pybind11_output_config):
        p = IRParameter("x", "double")
        method = IRMethod(name="scale", spelling="scale",
                          qualified_name="ns::Foo::scale", return_type="void",
                          is_virtual=True, parameters=[p])
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "void scale(double x) override" in out
        assert 'PYBIND11_OVERRIDE_NAME(void, ns::Foo, "scale", scale, x);' in out

    def test_class_declaration_includes_trampoline(self, pybind11_output_config):
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True)
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo>" in out

    def test_trampoline_before_base_in_declaration(self, pybind11_output_config):
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True)
        cls = _simple_class(methods=[method], bases=[IRBase("ns::Base", "public")])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo, ns::Base>" in out

    def test_custom_trampoline_prefix_from_generation_config(self, pybind11_output_config):
        from tsujikiri.configurations import GenerationConfig
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True)
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        gen_cfg = GenerationConfig(trampoline_prefix="Wrap")
        buf = io.StringIO()
        from tsujikiri.generator import Generator
        Generator(pybind11_output_config, generation=gen_cfg).generate(mod, buf)
        out = buf.getvalue()
        assert "class WrapFoo : public ns::Foo" in out
        assert "py::class_<ns::Foo, WrapFoo>" in out


# ---------------------------------------------------------------------------
# Holder type in class declaration
# ---------------------------------------------------------------------------

class TestHolderType:
    def test_holder_type_in_class_declaration(self, pybind11_output_config):
        cls = _simple_class()
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, std::shared_ptr<ns::Foo>>" in out

    def test_holder_type_with_base(self, pybind11_output_config):
        cls = _simple_class(bases=[IRBase("ns::Base", "public")])
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, std::shared_ptr<ns::Foo>, ns::Base>" in out

    def test_holder_type_with_trampoline_and_base(self, pybind11_output_config):
        method = IRMethod(name="compute", spelling="compute",
                          qualified_name="ns::Foo::compute", return_type="int",
                          is_virtual=True)
        cls = _simple_class(methods=[method], bases=[IRBase("ns::Base", "public")])
        cls.has_virtual_methods = True
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo, std::shared_ptr<ns::Foo>, ns::Base>" in out

    def test_no_holder_by_default(self, pybind11_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "shared_ptr" not in out


# ---------------------------------------------------------------------------
# Return value policies
# ---------------------------------------------------------------------------

class TestReturnValuePolicy:
    def test_no_rvp_when_ownership_none(self, pybind11_output_config):
        method = IRMethod(name="get", spelling="get",
                          qualified_name="ns::Foo::get", return_type="ns::Bar*",
                          return_ownership="none")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "return_value_policy" not in out

    def test_rvp_reference_internal_when_cpp(self, pybind11_output_config):
        method = IRMethod(name="get", spelling="get",
                          qualified_name="ns::Foo::get", return_type="ns::Bar*",
                          return_ownership="cpp")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::reference_internal" in out

    def test_rvp_take_ownership_when_script(self, pybind11_output_config):
        method = IRMethod(name="create", spelling="create",
                          qualified_name="ns::Foo::create", return_type="ns::Bar*",
                          return_ownership="script")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::take_ownership" in out


# ---------------------------------------------------------------------------
# keep_alive policy
# ---------------------------------------------------------------------------

class TestKeepAlive:
    def test_keep_alive_for_cpp_owned_param(self, pybind11_output_config):
        p = IRParameter("item", "ns::Item*", ownership="cpp")
        method = IRMethod(name="add", spelling="add",
                          qualified_name="ns::Foo::add", return_type="void",
                          parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<1, 2>()" in out

    def test_keep_alive_second_param_uses_index_3(self, pybind11_output_config):
        p1 = IRParameter("a", "int", ownership="none")
        p2 = IRParameter("item", "ns::Item*", ownership="cpp")
        method = IRMethod(name="add", spelling="add",
                          qualified_name="ns::Foo::add", return_type="void",
                          parameters=[p1, p2])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<1, 3>()" in out

    def test_no_keep_alive_for_none_ownership(self, pybind11_output_config):
        p = IRParameter("item", "ns::Item*", ownership="none")
        method = IRMethod(name="add", spelling="add",
                          qualified_name="ns::Foo::add", return_type="void",
                          parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "keep_alive" not in out


# ---------------------------------------------------------------------------
# Operator bindings
# ---------------------------------------------------------------------------

class TestOperatorBinding:
    def test_operator_plus_binds_to_add(self, pybind11_output_config):
        method = IRMethod(name="operator+", spelling="operator+",
                          qualified_name="ns::Foo::operator+", return_type="ns::Foo",
                          is_operator=True, operator_type="operator+")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__add__"' in out

    def test_operator_eq_binds_to_eq(self, pybind11_output_config):
        p = IRParameter("other", "const ns::Foo &")
        method = IRMethod(name="operator==", spelling="operator==",
                          qualified_name="ns::Foo::operator==", return_type="bool",
                          is_operator=True, operator_type="operator==",
                          parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__eq__"' in out

    def test_operator_stream_binds_to_repr_lambda(self, pybind11_output_config):
        method = IRMethod(name="operator<<", spelling="operator<<",
                          qualified_name="ns::Foo::operator<<", return_type="std::ostream &",
                          is_operator=True, operator_type="operator<<")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__repr__"' in out
        assert "std::ostringstream" in out
        assert "&ns::Foo::operator<<" not in out

    def test_unmapped_operator_uses_camel_to_snake_name(self, pybind11_output_config):
        # operator<< is mapped to __repr__, so use an unmapped one to test fallback
        method = IRMethod(name="operator>>", spelling="operator>>",
                          qualified_name="ns::Foo::operator>>", return_type="ns::Foo",
                          is_operator=True, operator_type="operator>>")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__rshift__"' in out
