"""Tests for new context fields added to the generator and template rendering."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import (
    IRClass,
    IRCodeInjection,
    IRConstructor,
    IRField,
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
