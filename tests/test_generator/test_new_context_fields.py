"""Tests for new context fields added to the generator and template rendering."""

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


def _generate(module: IRModule, output_config) -> str:
    buf = io.StringIO()
    Generator(output_config).generate(module, buf)
    return buf.getvalue()


def _simple_class(
    name: str = "MyClass",
    qname: str = "ns::MyClass",
    methods=None,
    fields=None,
    ctors=None,
) -> IRClass:
    return IRClass(
        name=name,
        qualified_name=qname,
        namespace="ns",
        variable_name=f"class{name}",
        methods=methods or [],
        fields=fields or [],
        constructors=ctors or [],
    )


# ---------------------------------------------------------------------------
# Generator context: parameter emit filtering
# ---------------------------------------------------------------------------

class TestParameterEmitFilter:
    def test_removed_param_absent_from_context(self, luabridge3_output_config):
        param_kept = IRParameter("a", "int")
        param_removed = IRParameter("b", "float")
        param_removed.emit = False
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void",
            parameters=[param_kept, param_removed],
        )
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})

        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]

        assert len(method_ctx["params"]) == 1
        assert method_ctx["params"][0]["name"] == "a"

    def test_all_params_included_when_emit_true(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void",
            parameters=[IRParameter("a", "int"), IRParameter("b", "float")],
        )
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})

        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert len(method_ctx["params"]) == 2


# ---------------------------------------------------------------------------
# Generator context: parameter rename
# ---------------------------------------------------------------------------

class TestParameterRenameInContext:
    def test_renamed_param_uses_new_name(self, luabridge3_output_config):
        param = IRParameter("rawName", "int")
        param.rename = "niceName"
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void", parameters=[param],
        )
        cls = _simple_class(methods=[method])

        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        param_ctx = ctx["method_groups"][0]["methods"][0]["params"][0]
        assert param_ctx["name"] == "niceName"
        assert param_ctx["original_name"] == "rawName"

    def test_type_override_in_context(self, luabridge3_output_config):
        param = IRParameter("x", "int")
        param.type_override = "double"
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void", parameters=[param],
        )
        cls = _simple_class(methods=[method])

        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        param_ctx = ctx["method_groups"][0]["methods"][0]["params"][0]
        assert param_ctx["type"] == "double"
        assert param_ctx["raw_type"] == "double"


# ---------------------------------------------------------------------------
# Generator context: method new fields
# ---------------------------------------------------------------------------

class TestMethodNewFieldsInContext:
    def test_return_type_override(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="int", return_type_override="double",
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert method_ctx["return_type"] == "double"

    def test_return_ownership_in_context(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="int", return_ownership="cpp",
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert method_ctx["return_ownership"] == "cpp"

    def test_allow_thread_in_context(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void", allow_thread=True,
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert method_ctx["allow_thread"] is True

    def test_wrapper_code_in_context(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="int", wrapper_code="+[]() { return 42; }",
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert method_ctx["wrapper_code"] == "+[]() { return 42; }"

    def test_method_code_injections_in_context(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void",
            code_injections=[IRCodeInjection("beginning", "// injected")],
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        method_ctx = ctx["method_groups"][0]["methods"][0]
        assert method_ctx["code_injections"] == [{"position": "beginning", "code": "// injected"}]


# ---------------------------------------------------------------------------
# Generator context: field read_only
# ---------------------------------------------------------------------------

class TestFieldReadOnlyInContext:
    def test_read_only_from_is_const(self, luabridge3_output_config):
        field = IRField(name="x", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["fields"][0]["read_only"] is True

    def test_read_only_from_field_flag(self, luabridge3_output_config):
        field = IRField(name="x", type_spelling="int", is_const=False, read_only=True)
        cls = _simple_class(fields=[field])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["fields"][0]["read_only"] is True

    def test_not_read_only_by_default(self, luabridge3_output_config):
        field = IRField(name="x", type_spelling="int")
        cls = _simple_class(fields=[field])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["fields"][0]["read_only"] is False


# ---------------------------------------------------------------------------
# Generator context: class new fields
# ---------------------------------------------------------------------------

class TestClassNewFieldsInContext:
    def test_force_abstract_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        cls.force_abstract = True
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["force_abstract"] is True

    def test_copyable_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        cls.copyable = False
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["copyable"] is False

    def test_movable_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        cls.movable = True
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["movable"] is True

    def test_class_code_injections_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        cls.code_injections = [IRCodeInjection("end", "// cls end")]
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["code_injections"] == [{"position": "end", "code": "// cls end"}]

    def test_defaults_are_neutral(self, luabridge3_output_config):
        cls = _simple_class()
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["force_abstract"] is False
        assert ctx["copyable"] is None
        assert ctx["movable"] is None
        assert ctx["code_injections"] == []


# ---------------------------------------------------------------------------
# Generator context: module code_injections
# ---------------------------------------------------------------------------

class TestModuleCodeInjectionsInContext:
    def test_module_code_injections_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        mod = IRModule(
            name="m", classes=[cls], class_by_name={"MyClass": cls},
            code_injections=[IRCodeInjection("beginning", "// global start")],
        )
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["code_injections"] == [{"position": "beginning", "code": "// global start"}]

    def test_empty_by_default(self, luabridge3_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["code_injections"] == []


# ---------------------------------------------------------------------------
# Template rendering: wrapper_code
# ---------------------------------------------------------------------------

class TestWrapperCodeRendering:
    def test_wrapper_code_replaces_function_pointer_luabridge3(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="int", wrapper_code="+[]() { return 42; }",
        )
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert '+[]() { return 42; }' in out
        assert '&ns::MyClass::foo' not in out

    def test_without_wrapper_code_uses_function_pointer(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="int",
        )
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert '&ns::MyClass::foo' in out

    def test_static_wrapper_code_replaces_function_pointer(self, luabridge3_output_config):
        method = IRMethod(
            name="create", spelling="create", qualified_name="ns::MyClass::create",
            return_type="int", is_static=True,
            wrapper_code="+[]() { return MyClass::create(); }",
        )
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert '+[]() { return MyClass::create(); }' in out
        assert '&ns::MyClass::create' not in out


# ---------------------------------------------------------------------------
# Template rendering: code injections
# ---------------------------------------------------------------------------

class TestCodeInjectionRendering:
    def test_module_beginning_injection_luabridge3(self, luabridge3_output_config):
        cls = _simple_class()
        mod = IRModule(
            name="m", classes=[cls], class_by_name={"MyClass": cls},
            code_injections=[IRCodeInjection("beginning", "// MODULE_BEGINNING")],
        )
        out = _generate(mod, luabridge3_output_config)
        assert "// MODULE_BEGINNING" in out

    def test_module_end_injection_luabridge3(self, luabridge3_output_config):
        cls = _simple_class()
        mod = IRModule(
            name="m", classes=[cls], class_by_name={"MyClass": cls},
            code_injections=[IRCodeInjection("end", "// MODULE_END")],
        )
        out = _generate(mod, luabridge3_output_config)
        assert "// MODULE_END" in out

    def test_class_beginning_injection_luabridge3(self, luabridge3_output_config):
        cls = _simple_class()
        cls.code_injections = [IRCodeInjection("beginning", "// CLASS_BEGINNING")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "// CLASS_BEGINNING" in out

    def test_class_end_injection_luabridge3(self, luabridge3_output_config):
        cls = _simple_class()
        cls.code_injections = [IRCodeInjection("end", "// CLASS_END")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "// CLASS_END" in out

    def test_module_beginning_injection_luals(self, luals_output_config):
        cls = _simple_class()
        mod = IRModule(
            name="m", classes=[cls], class_by_name={"MyClass": cls},
            code_injections=[IRCodeInjection("beginning", "-- MODULE_BEGIN")],
        )
        out = _generate(mod, luals_output_config)
        assert "-- MODULE_BEGIN" in out

    def test_class_end_injection_luals(self, luals_output_config):
        cls = _simple_class()
        cls.code_injections = [IRCodeInjection("end", "-- CLASS_END")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert "-- CLASS_END" in out


# ---------------------------------------------------------------------------
# Template rendering: force_abstract
# ---------------------------------------------------------------------------

class TestForceAbstractRendering:
    def test_force_abstract_suppresses_constructor_luabridge3(self, luabridge3_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "addConstructor" not in out

    def test_without_force_abstract_constructor_present(self, luabridge3_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "addConstructor" in out

    def test_force_abstract_suppresses_new_luals(self, luals_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert ".new(" not in out

    def test_without_force_abstract_new_present_luals(self, luals_output_config):
        ctor = IRConstructor(parameters=[IRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert ".new(" in out


# ---------------------------------------------------------------------------
# Template rendering: read_only field
# ---------------------------------------------------------------------------

class TestReadOnlyFieldRendering:
    def test_read_only_true_emits_nullptr_setter_luabridge3(self, luabridge3_output_config):
        field = IRField(name="data_", type_spelling="int", read_only=True)
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "nullptr" in out

    def test_const_field_emits_nullptr_setter_luabridge3(self, luabridge3_output_config):
        field = IRField(name="max_", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "nullptr" in out

    def test_mutable_field_omits_nullptr_setter(self, luabridge3_output_config):
        field = IRField(name="data_", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "nullptr" not in out

    def test_read_only_annotation_luals(self, luals_output_config):
        field = IRField(name="x", type_spelling="int", read_only=True)
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert "(readonly)" in out

    def test_mutable_field_no_readonly_annotation_luals(self, luals_output_config):
        field = IRField(name="x", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert "(readonly)" not in out


# ---------------------------------------------------------------------------
# Generator context: doc fields
# ---------------------------------------------------------------------------

class TestDocInContext:
    def test_class_doc_in_context(self, luabridge3_output_config):
        cls = _simple_class()
        cls.doc = "A great class"
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["doc"] == "A great class"

    def test_class_no_doc_is_none(self, luabridge3_output_config):
        cls = _simple_class()
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["doc"] is None

    def test_method_doc_in_context(self, luabridge3_output_config):
        method = IRMethod(
            name="foo", spelling="foo", qualified_name="ns::MyClass::foo",
            return_type="void", doc="Does foo",
        )
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["method_groups"][0]["methods"][0]["doc"] == "Does foo"

    def test_field_doc_in_context(self, luabridge3_output_config):
        field = IRField(name="x", type_spelling="int", doc="The x value")
        cls = _simple_class(fields=[field])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["fields"][0]["doc"] == "The x value"

    def test_constructor_doc_in_context(self, luabridge3_output_config):
        ctor = IRConstructor(parameters=[], doc="Default ctor")
        cls = _simple_class(ctors=[ctor])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["constructor_group"]["constructors"][0]["doc"] == "Default ctor"

    def test_enum_doc_in_context(self, luabridge3_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color", doc="Color enum",
                      values=[IREnumValue("Red", 0, doc="The red")])
        mod = IRModule(name="m", enums=[enum])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        enum_ctx = ctx["enums"][0]
        assert enum_ctx["doc"] == "Color enum"
        assert enum_ctx["values"][0]["doc"] == "The red"

    def test_function_doc_in_context(self, luabridge3_output_config):
        fn = IRFunction(name="compute", qualified_name="ns::compute",
                        namespace="ns", return_type="void", doc="Computes")
        mod = IRModule(name="m", functions=[fn])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["function_groups"][0]["functions"][0]["doc"] == "Computes"


# ---------------------------------------------------------------------------
# Generator context: enum rename
# ---------------------------------------------------------------------------

class TestEnumRenameInContext:
    def test_enum_rename_used_in_context(self, luabridge3_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color", rename="Colour",
                      values=[IREnumValue("Red", 0)])
        mod = IRModule(name="m", enums=[enum])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["enums"][0]["name"] == "Colour"

    def test_enum_value_rename_used_in_context(self, luabridge3_output_config):
        val = IREnumValue("Red", 0, rename="red")
        enum = IREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = IRModule(name="m", enums=[enum])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["enums"][0]["values"][0]["name"] == "red"


# ---------------------------------------------------------------------------
# Generator context: public_bases
# ---------------------------------------------------------------------------

class TestPublicBasesInContext:
    def test_only_public_emit_bases_in_public_bases(self, luabridge3_output_config):
        cls = _simple_class()
        cls.bases = [
            IRBase("ns::A", "public"),
            IRBase("ns::B", "protected"),
            IRBase("ns::C", "private"),
        ]
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert len(ctx["public_bases"]) == 1
        assert ctx["public_bases"][0]["qualified_name"] == "ns::A"

    def test_suppressed_public_base_excluded(self, luabridge3_output_config):
        base = IRBase("ns::A", "public")
        base.emit = False
        cls = _simple_class()
        cls.bases = [base]
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["public_bases"] == []
        assert ctx["base_name"] == ""

    def test_multiple_public_bases(self, luabridge3_output_config):
        cls = _simple_class()
        cls.bases = [IRBase("ns::A", "public"), IRBase("ns::B", "public")]
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert len(ctx["public_bases"]) == 2


# ---------------------------------------------------------------------------
# Generator context: default_value fallback
# ---------------------------------------------------------------------------

class TestDefaultValueFallbackInContext:
    def test_default_override_takes_priority(self, luabridge3_output_config):
        p = IRParameter("x", "int", default_value="1", default_override="0")
        method = IRMethod(name="f", spelling="f", qualified_name="ns::C::f",
                          return_type="void", parameters=[p])
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["method_groups"][0]["methods"][0]["params"][0]["default"] == "0"

    def test_default_value_used_when_no_override(self, luabridge3_output_config):
        p = IRParameter("x", "int", default_value="42")
        method = IRMethod(name="f", spelling="f", qualified_name="ns::C::f",
                          return_type="void", parameters=[p])
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["method_groups"][0]["methods"][0]["params"][0]["default"] == "42"

    def test_no_default_is_none(self, luabridge3_output_config):
        p = IRParameter("x", "int")
        method = IRMethod(name="f", spelling="f", qualified_name="ns::C::f",
                          return_type="void", parameters=[p])
        cls = _simple_class(methods=[method])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["method_groups"][0]["methods"][0]["params"][0]["default"] is None


# ---------------------------------------------------------------------------
# Generator context: function extended fields
# ---------------------------------------------------------------------------

class TestFunctionExtendedContextFields:
    def test_return_type_override_in_function_ctx(self, luabridge3_output_config):
        fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns",
                        return_type="int", return_type_override="double")
        mod = IRModule(name="m", functions=[fn])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        fn_ctx = ctx["function_groups"][0]["functions"][0]
        assert fn_ctx["return_type"] == "double"
        assert fn_ctx["raw_return_type"] == "double"

    def test_allow_thread_in_function_ctx(self, luabridge3_output_config):
        fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns",
                        return_type="void", allow_thread=True)
        mod = IRModule(name="m", functions=[fn])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["function_groups"][0]["functions"][0]["allow_thread"] is True

    def test_wrapper_code_in_function_ctx(self, luabridge3_output_config):
        fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns",
                        return_type="void", wrapper_code="+[](){}")
        mod = IRModule(name="m", functions=[fn])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        assert ctx["function_groups"][0]["functions"][0]["wrapper_code"] == "+[](){}"

    def test_function_param_rename_in_context(self, luabridge3_output_config):
        p = IRParameter("rawName", "int")
        p.rename = "nice"
        fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns",
                        return_type="void", parameters=[p])
        mod = IRModule(name="m", functions=[fn])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_ir_context(mod)
        param_ctx = ctx["function_groups"][0]["functions"][0]["params"][0]
        assert param_ctx["name"] == "nice"
        assert param_ctx["original_name"] == "rawName"

    def test_field_type_override_in_context(self, luabridge3_output_config):
        field = IRField(name="label", type_spelling="juce::String",
                        type_override="std::string")
        cls = _simple_class(fields=[field])
        gen = Generator(luabridge3_output_config)
        ctx = gen._build_class_ctx(cls)
        assert ctx["fields"][0]["type"] == "std::string"
        assert ctx["fields"][0]["raw_type"] == "std::string"


# ---------------------------------------------------------------------------
# Template rendering: multiple inheritance (luabridge3)
# ---------------------------------------------------------------------------

class TestMultipleInheritanceLuaBridge3:
    def test_single_public_base_uses_derive_class(self, luabridge3_output_config):
        cls = _simple_class()
        cls.bases = [IRBase("ns::Base", "public")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert ".deriveClass<ns::MyClass, ns::Base>" in out

    def test_two_public_bases_in_derive_class(self, luabridge3_output_config):
        cls = _simple_class()
        cls.bases = [IRBase("ns::A", "public"), IRBase("ns::B", "public")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert ".deriveClass<ns::MyClass, ns::A, ns::B>" in out

    def test_protected_base_excluded(self, luabridge3_output_config):
        cls = _simple_class()
        cls.bases = [IRBase("ns::Hidden", "protected")]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert ".beginClass<ns::MyClass>" in out
        assert "deriveClass" not in out

    def test_suppressed_base_excluded(self, luabridge3_output_config):
        base = IRBase("ns::A", "public")
        base.emit = False
        cls = _simple_class()
        cls.bases = [base]
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luabridge3_output_config)
        assert ".beginClass<ns::MyClass>" in out


# ---------------------------------------------------------------------------
# Template rendering: doc strings (luals)
# ---------------------------------------------------------------------------

class TestDocStringLuaLS:
    def test_class_doc_emitted(self, luals_output_config):
        cls = _simple_class()
        cls.doc = "Represents a widget"
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert "---Represents a widget" in out

    def test_field_doc_emitted(self, luals_output_config):
        field = IRField(name="x", type_spelling="int", doc="The x coordinate")
        cls = _simple_class(fields=[field])
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        assert "---The x coordinate" in out

    def test_enum_doc_emitted(self, luals_output_config):
        enum = IREnum(name="Color", qualified_name="ns::Color", doc="Color options",
                      values=[IREnumValue("Red", 0)])
        mod = IRModule(name="m", enums=[enum])
        out = _generate(mod, luals_output_config)
        assert "---Color options" in out

    def test_no_doc_no_extra_comment(self, luals_output_config):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"MyClass": cls})
        out = _generate(mod, luals_output_config)
        # Only the standard header comment should appear
        lines = [l for l in out.splitlines() if l.startswith("---")]
        assert all("@" in l or l == "---" for l in lines)


class TestApiVersionGating:
    def _gen(self, module: IRModule, output_config, api_version: str) -> str:
        buf = io.StringIO()
        Generator(output_config).generate(module, buf, api_version=api_version)
        return buf.getvalue()

    def test_method_excluded_before_since_version(self, pybind11_output_config) -> None:
        m = IRMethod(name="newOp", spelling="newOp", qualified_name="Cls::newOp",
                     return_type="void", api_since="2.0")
        cls = _simple_class()
        cls.methods = [m]
        mod = IRModule(name="t", classes=[cls], class_by_name={"MyClass": cls})
        out = self._gen(mod, pybind11_output_config, api_version="1.0")
        assert "newOp" not in out

    def test_method_included_at_since_version(self, pybind11_output_config) -> None:
        m = IRMethod(name="newOp", spelling="newOp", qualified_name="Cls::newOp",
                     return_type="void", api_since="2.0")
        cls = _simple_class()
        cls.methods = [m]
        mod = IRModule(name="t", classes=[cls], class_by_name={"MyClass": cls})
        out = self._gen(mod, pybind11_output_config, api_version="2.0")
        assert "newOp" in out

    def test_method_excluded_at_or_after_until_version(self, pybind11_output_config) -> None:
        m = IRMethod(name="oldOp", spelling="oldOp", qualified_name="Cls::oldOp",
                     return_type="void", api_until="2.0")
        cls = _simple_class()
        cls.methods = [m]
        mod = IRModule(name="t", classes=[cls], class_by_name={"MyClass": cls})
        out = self._gen(mod, pybind11_output_config, api_version="2.0")
        assert "oldOp" not in out

    def test_function_excluded_before_since_version(self, pybind11_output_config) -> None:
        fn = IRFunction(name="futureFunc", qualified_name="futureFunc",
                        namespace="", return_type="void", api_since="3.0")
        mod = IRModule(name="t", functions=[fn])
        out = self._gen(mod, pybind11_output_config, api_version="2.0")
        assert "futureFunc" not in out

    def test_no_api_version_includes_all(self, pybind11_output_config) -> None:
        m = IRMethod(name="withSince", spelling="withSince", qualified_name="Cls::withSince",
                     return_type="void", api_since="5.0")
        cls = _simple_class()
        cls.methods = [m]
        mod = IRModule(name="t", classes=[cls], class_by_name={"MyClass": cls})
        out = self._gen(mod, pybind11_output_config, api_version="")
        assert "withSince" in out


class TestVersionInRangeBranches:
    """Cover generator.py _version_in_range exception path (lines 536-537)."""

    def test_unparseable_api_version_includes_by_default(self) -> None:
        """Lines 536-537: invalid semver string → exception → return True (include)."""
        from tsujikiri.generator import Generator
        result = Generator._version_in_range("not-a-version!!", "1.0", None)
        assert result is True

    def test_unparseable_since_includes_by_default(self) -> None:
        """Lines 536-537: invalid since string → exception → return True."""
        from tsujikiri.generator import Generator
        result = Generator._version_in_range("1.0", "not-valid-since!!!", None)
        assert result is True


class TestTypesystemTypeMappingBranches:
    """Cover generator.py type-mapping branches 550->549, 553->552 and 565->564."""

    def test_primitive_type_loop_continues_past_non_match(self) -> None:
        """Branch 550->549: primitive_types has entries but first doesn't match — loop continues."""
        from tsujikiri.configurations import TypesystemConfig, PrimitiveTypeEntry
        from tsujikiri.configurations import OutputConfig
        ts = TypesystemConfig(
            primitive_types=[
                PrimitiveTypeEntry(cpp_name="int64_t", python_name="int"),
                PrimitiveTypeEntry(cpp_name="float32_t", python_name="float"),
            ]
        )
        cfg = OutputConfig(format_name="test", template="")
        gen = Generator(cfg, typesystem=ts)
        # "float32_t" is the second entry; "int64_t" doesn't match → loop continues to next
        assert gen._map_type("float32_t") == "float"

    def test_typedef_type_loop_continues_past_non_match(self) -> None:
        """Branch 553->552: typedef_types has entries but first doesn't match — loop continues."""
        from tsujikiri.configurations import TypesystemConfig, TypedefTypeEntry
        from tsujikiri.configurations import OutputConfig
        ts = TypesystemConfig(
            typedef_types=[
                TypedefTypeEntry(cpp_name="MyString", source="std::string"),
                TypedefTypeEntry(cpp_name="MyBuffer", source="std::vector<uint8_t>"),
            ]
        )
        cfg = OutputConfig(format_name="test", template="")
        gen = Generator(cfg, typesystem=ts)
        # "MyBuffer" is second; "MyString" doesn't match → loop continues
        assert gen._map_type("MyBuffer") == "std::vector<uint8_t>"

    def test_custom_type_loop_continues_past_non_match(self) -> None:
        """Branch 565->564: custom_types has entries but first doesn't match — loop continues."""
        from tsujikiri.configurations import TypesystemConfig, CustomTypeEntry
        from tsujikiri.configurations import OutputConfig
        ts = TypesystemConfig(
            custom_types=[
                CustomTypeEntry(cpp_name="QObject"),
                CustomTypeEntry(cpp_name="PyObject"),
            ]
        )
        cfg = OutputConfig(
            format_name="test",
            unsupported_types=["PyObject"],
            template="",
        )
        gen = Generator(cfg, typesystem=ts)
        # "PyObject" is second; "QObject" doesn't match first, loop continues to PyObject → not unsupported
        assert not gen._is_unsupported("PyObject")
