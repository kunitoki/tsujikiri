"""Tests for the pybind11 output format template."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import IRProperty
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pybind11_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path

    return load_output_config(resolve_format_path("pybind11"))


def _gen(module: TIRModule, cfg) -> str:
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
) -> TIRClass:
    return TIRClass(
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
        mod = TIRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "PYBIND11_MODULE(mymod, m)" in out

    def test_pybind11_includes(self, pybind11_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "#include <pybind11/pybind11.h>" in out
        assert "#include <pybind11/stl.h>" in out

    def test_namespace_alias(self, pybind11_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "namespace py = pybind11;" in out

    def test_auto_generated_comment(self, pybind11_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pybind11_output_config)
        assert "DO NOT EDIT" in out
        assert "pybind11" in out


# ---------------------------------------------------------------------------
# Enum binding
# ---------------------------------------------------------------------------


class TestEnumBinding:
    def test_enum_class(self, pybind11_output_config):
        enum = TIREnum(
            name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)]
        )
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert 'py::enum_<ns::Color>(m, "Color")' in out

    def test_enum_values(self, pybind11_output_config):
        enum = TIREnum(
            name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)]
        )
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '.value("Red", ns::Color::Red)' in out
        assert '.value("Green", ns::Color::Green)' in out

    def test_export_values(self, pybind11_output_config):
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0)])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert ".export_values();" in out

    def test_enum_doc(self, pybind11_output_config):
        enum = TIREnum(name="Color", qualified_name="ns::Color", doc="Color options", values=[TIREnumValue("Red", 0)])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '"Color options"' in out

    def test_enum_value_doc(self, pybind11_output_config):
        val = TIREnumValue("Red", 0, doc="The red color")
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '"The red color"' in out

    def test_suppressed_enum_value_excluded(self, pybind11_output_config):
        val = TIREnumValue("Reserved", 99)
        val.emit = False
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert "Reserved" not in out

    def test_renamed_enum_value(self, pybind11_output_config):
        val = TIREnumValue("Red", 0, rename="red")
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pybind11_output_config)
        assert '.value("red", ns::Color::Red)' in out


# ---------------------------------------------------------------------------
# Free function binding
# ---------------------------------------------------------------------------


class TestFunctionBinding:
    def test_simple_function(self, pybind11_output_config):
        fn = TIRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="double")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'm.def("compute", &ns::compute)' in out

    def test_function_with_arg(self, pybind11_output_config):
        fn = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="double",
            parameters=[TIRParameter("x", "double")],
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x")' in out

    def test_function_with_default(self, pybind11_output_config):
        fn = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="double",
            parameters=[TIRParameter("x", "double", default_value="1.0")],
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x") = 1.0' in out

    def test_function_doc(self, pybind11_output_config):
        fn = TIRFunction(
            name="compute", qualified_name="ns::compute", namespace="ns", return_type="double", doc="Computes"
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert '"Computes"' in out

    def test_function_wrapper_code(self, pybind11_output_config):
        fn = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="double",
            wrapper_code="+[]() { return 42.0; }",
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert "+[]() { return 42.0; }" in out
        assert "&ns::compute" not in out

    def test_camel_to_snake_function_name(self, pybind11_output_config):
        fn = TIRFunction(name="computeArea", qualified_name="ns::computeArea", namespace="ns", return_type="double")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pybind11_output_config)
        assert '"compute_area"' in out


# ---------------------------------------------------------------------------
# Class binding
# ---------------------------------------------------------------------------


class TestClassBinding:
    def test_simple_class(self, pybind11_output_config):
        cls = _simple_class()
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'py::class_<ns::Foo>(m, "Foo")' in out

    def test_class_doc(self, pybind11_output_config):
        cls = _simple_class()
        cls.doc = "A great class"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"A great class"' in out

    def test_class_with_single_base(self, pybind11_output_config):
        cls = _simple_class(bases=[TIRBase("ns::Base", "public")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, ns::Base>" in out

    def test_class_with_multiple_public_bases(self, pybind11_output_config):
        cls = _simple_class(bases=[TIRBase("ns::A", "public"), TIRBase("ns::B", "public")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, ns::A, ns::B>" in out

    def test_protected_base_excluded(self, pybind11_output_config):
        cls = _simple_class(bases=[TIRBase("ns::Hidden", "protected")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "Hidden" not in out

    def test_constructor(self, pybind11_output_config):
        ctor = TIRConstructor(parameters=[TIRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def(py::init<int>(), py::arg("v"))' in out

    def test_force_abstract_suppresses_constructor(self, pybind11_output_config):
        ctor = TIRConstructor(parameters=[TIRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::init" not in out

    def test_method(self, pybind11_output_config):
        method = TIRMethod(
            name="getValue", spelling="getValue", qualified_name="ns::Foo::getValue", return_type="int", is_const=True
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("get_value", &ns::Foo::getValue)' in out

    def test_method_doc(self, pybind11_output_config):
        method = TIRMethod(
            name="getValue",
            spelling="getValue",
            qualified_name="ns::Foo::getValue",
            return_type="int",
            doc="Gets the value",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"Gets the value"' in out

    def test_static_method(self, pybind11_output_config):
        method = TIRMethod(
            name="create", spelling="create", qualified_name="ns::Foo::create", return_type="ns::Foo*", is_static=True
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_static("create"' in out

    def test_readwrite_field(self, pybind11_output_config):
        field = TIRField(name="x_", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_readwrite("x_", &ns::Foo::x_)' in out

    def test_readonly_field(self, pybind11_output_config):
        field = TIRField(name="max_", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_readonly("max_"' in out

    def test_field_doc(self, pybind11_output_config):
        field = TIRField(name="x_", type_spelling="int", doc="X field")
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"X field"' in out

    def test_method_with_default_arg(self, pybind11_output_config):
        p = TIRParameter("x", "int", default_value="0")
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", parameters=[p]
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'py::arg("x") = 0' in out

    def test_wrapper_code_method(self, pybind11_output_config):
        method = TIRMethod(
            name="doThing",
            spelling="doThing",
            qualified_name="ns::Foo::doThing",
            return_type="void",
            wrapper_code="+[](Foo& self) { self.doThing(); }",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
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
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "PyFoo" not in out
        assert "PYBIND11_OVERRIDE" not in out

    def test_trampoline_class_generated_for_virtual_method(self, pybind11_output_config):
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", is_virtual=True
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "class PyFoo : public ns::Foo" in out
        assert "using ns::Foo::Foo;" in out
        assert 'PYBIND11_OVERRIDE_NAME(int, ns::Foo, "compute", compute);' in out

    def test_trampoline_uses_override_pure_for_pure_virtual(self, pybind11_output_config):
        method = TIRMethod(
            name="compute",
            spelling="compute",
            qualified_name="ns::Foo::compute",
            return_type="int",
            is_virtual=True,
            is_pure_virtual=True,
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        cls.is_abstract = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert 'PYBIND11_OVERRIDE_PURE_NAME(int, ns::Foo, "compute", compute);' in out

    def test_trampoline_const_method_has_const_qualifier(self, pybind11_output_config):
        method = TIRMethod(
            name="name",
            spelling="name",
            qualified_name="ns::Foo::name",
            return_type="std::string",
            is_virtual=True,
            is_const=True,
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "std::string name(" in out
        assert ") const override" in out

    def test_trampoline_method_with_params(self, pybind11_output_config):
        p = TIRParameter("x", "double")
        method = TIRMethod(
            name="scale",
            spelling="scale",
            qualified_name="ns::Foo::scale",
            return_type="void",
            is_virtual=True,
            parameters=[p],
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "void scale(double x) override" in out
        assert 'PYBIND11_OVERRIDE_NAME(void, ns::Foo, "scale", scale, x);' in out

    def test_class_declaration_includes_trampoline(self, pybind11_output_config):
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", is_virtual=True
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo>" in out

    def test_trampoline_before_base_in_declaration(self, pybind11_output_config):
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", is_virtual=True
        )
        cls = _simple_class(methods=[method], bases=[TIRBase("ns::Base", "public")])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo, ns::Base>" in out

    def test_custom_trampoline_prefix_from_generation_config(self, pybind11_output_config):
        from tsujikiri.configurations import GenerationConfig

        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", is_virtual=True
        )
        cls = _simple_class(methods=[method])
        cls.has_virtual_methods = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
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
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, std::shared_ptr<ns::Foo>>" in out

    def test_holder_type_with_base(self, pybind11_output_config):
        cls = _simple_class(bases=[TIRBase("ns::Base", "public")])
        cls.holder_type = "std::shared_ptr"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, std::shared_ptr<ns::Foo>, ns::Base>" in out

    def test_holder_type_with_trampoline_and_base(self, pybind11_output_config):
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", is_virtual=True
        )
        cls = _simple_class(methods=[method], bases=[TIRBase("ns::Base", "public")])
        cls.has_virtual_methods = True
        cls.holder_type = "std::shared_ptr"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::class_<ns::Foo, PyFoo, std::shared_ptr<ns::Foo>, ns::Base>" in out

    def test_no_holder_by_default(self, pybind11_output_config):
        cls = _simple_class()
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "shared_ptr" not in out


# ---------------------------------------------------------------------------
# Return value policies
# ---------------------------------------------------------------------------


class TestReturnValuePolicy:
    def test_no_rvp_when_ownership_none(self, pybind11_output_config):
        method = TIRMethod(
            name="get", spelling="get", qualified_name="ns::Foo::get", return_type="ns::Bar*", return_ownership="none"
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "return_value_policy" not in out

    def test_rvp_reference_internal_when_cpp(self, pybind11_output_config):
        method = TIRMethod(
            name="get", spelling="get", qualified_name="ns::Foo::get", return_type="ns::Bar*", return_ownership="cpp"
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::reference_internal" in out

    def test_rvp_take_ownership_when_script(self, pybind11_output_config):
        method = TIRMethod(
            name="create",
            spelling="create",
            qualified_name="ns::Foo::create",
            return_type="ns::Bar*",
            return_ownership="script",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::take_ownership" in out


# ---------------------------------------------------------------------------
# keep_alive policy
# ---------------------------------------------------------------------------


class TestKeepAlive:
    def test_keep_alive_for_cpp_owned_param(self, pybind11_output_config):
        p = TIRParameter("item", "ns::Item*", ownership="cpp")
        method = TIRMethod(
            name="add", spelling="add", qualified_name="ns::Foo::add", return_type="void", parameters=[p]
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<1, 2>()" in out

    def test_keep_alive_second_param_uses_index_3(self, pybind11_output_config):
        p1 = TIRParameter("a", "int", ownership="none")
        p2 = TIRParameter("item", "ns::Item*", ownership="cpp")
        method = TIRMethod(
            name="add", spelling="add", qualified_name="ns::Foo::add", return_type="void", parameters=[p1, p2]
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<1, 3>()" in out

    def test_no_keep_alive_for_none_ownership(self, pybind11_output_config):
        p = TIRParameter("item", "ns::Item*", ownership="none")
        method = TIRMethod(
            name="add", spelling="add", qualified_name="ns::Foo::add", return_type="void", parameters=[p]
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "keep_alive" not in out

    def test_return_keep_alive_emits_keep_alive_0_1(self, pybind11_output_config):
        method = TIRMethod(
            name="model",
            spelling="model",
            qualified_name="ns::Foo::model",
            return_type="ns::Model*",
            return_keep_alive=True,
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<0, 1>()" in out

    def test_no_return_keep_alive_by_default(self, pybind11_output_config):
        method = TIRMethod(name="model", spelling="model", qualified_name="ns::Foo::model", return_type="ns::Model*")
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::keep_alive<0, 1>()" not in out

    def test_return_keep_alive_combined_with_return_ownership(self, pybind11_output_config):
        method = TIRMethod(
            name="model",
            spelling="model",
            qualified_name="ns::Foo::model",
            return_type="ns::Model*",
            return_ownership="script",
            return_keep_alive=True,
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::take_ownership" in out
        assert "py::keep_alive<0, 1>()" in out


# ---------------------------------------------------------------------------
# allow_thread / GIL release
# ---------------------------------------------------------------------------


class TestAllowThread:
    def test_allow_thread_emits_call_guard(self, pybind11_output_config):
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="void", allow_thread=True
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::call_guard<py::gil_scoped_release>()" in out

    def test_no_call_guard_when_allow_thread_false(self, pybind11_output_config):
        method = TIRMethod(
            name="compute",
            spelling="compute",
            qualified_name="ns::Foo::compute",
            return_type="void",
            allow_thread=False,
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "call_guard" not in out

    def test_allow_thread_combined_with_return_ownership(self, pybind11_output_config):
        method = TIRMethod(
            name="fetch",
            spelling="fetch",
            qualified_name="ns::Foo::fetch",
            return_type="ns::Bar*",
            return_ownership="cpp",
            allow_thread=True,
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "py::return_value_policy::reference_internal" in out
        assert "py::call_guard<py::gil_scoped_release>()" in out


# ---------------------------------------------------------------------------
# Synthetic property bindings
# ---------------------------------------------------------------------------


class TestPropertyBinding:
    def test_readwrite_property_emits_def_property(self, pybind11_output_config):
        prop = IRProperty(
            name="arrivalMessage", getter="getArrivalMessage", setter="setArrivalMessage", type_spelling="std::string"
        )
        cls = _simple_class()
        cls.properties.append(prop)
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def_property("arrival_message"' in out
        assert "&ns::Foo::getArrivalMessage" in out
        assert "&ns::Foo::setArrivalMessage" in out

    def test_readonly_property_emits_def_property_readonly(self, pybind11_output_config):
        prop = IRProperty(name="name", getter="getName", type_spelling="std::string")
        cls = _simple_class()
        cls.properties.append(prop)
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert ".def_property_readonly(" in out
        assert "&ns::Foo::getName" in out
        assert "def_property(" not in out.replace("def_property_readonly(", "")

    def test_property_doc_string(self, pybind11_output_config):
        prop = IRProperty(name="value", getter="getValue", setter="setValue", type_spelling="int", doc="The value.")
        cls = _simple_class()
        cls.properties.append(prop)
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '"The value."' in out

    def test_no_properties_by_default(self, pybind11_output_config):
        cls = _simple_class()
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert "def_property" not in out


# ---------------------------------------------------------------------------
# Operator bindings
# ---------------------------------------------------------------------------


class TestOperatorBinding:
    def test_operator_plus_binds_to_add(self, pybind11_output_config):
        method = TIRMethod(
            name="operator+",
            spelling="operator+",
            qualified_name="ns::Foo::operator+",
            return_type="ns::Foo",
            is_operator=True,
            operator_type="operator+",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__add__"' in out

    def test_operator_eq_binds_to_eq(self, pybind11_output_config):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(
            name="operator==",
            spelling="operator==",
            qualified_name="ns::Foo::operator==",
            return_type="bool",
            is_operator=True,
            operator_type="operator==",
            parameters=[p],
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__eq__"' in out

    def test_operator_stream_binds_to_repr_lambda(self, pybind11_output_config):
        method = TIRMethod(
            name="operator<<",
            spelling="operator<<",
            qualified_name="ns::Foo::operator<<",
            return_type="std::ostream &",
            is_operator=True,
            operator_type="operator<<",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__repr__"' in out
        assert "std::ostringstream" in out
        assert "&ns::Foo::operator<<" not in out

    def test_unmapped_operator_uses_camel_to_snake_name(self, pybind11_output_config):
        # operator<< is mapped to __repr__, so use an unmapped one to test fallback
        method = TIRMethod(
            name="operator>>",
            spelling="operator>>",
            qualified_name="ns::Foo::operator>>",
            return_type="ns::Foo",
            is_operator=True,
            operator_type="operator>>",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pybind11_output_config)
        assert '.def("__rshift__"' in out
