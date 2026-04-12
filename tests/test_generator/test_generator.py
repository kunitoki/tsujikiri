"""Tests for generator.py — template rendering, topo-sort, emit flags."""

from __future__ import annotations

import io

import pytest
import jinja2
from unittest.mock import patch

from tsujikiri.generator import Generator, ItemFirstEnvironment
from tsujikiri.ir import IRBase, IRClass, IRConstructor, IREnumValue, IRField, IRFunction, IRMethod, IRModule, IRParameter


def _generate(module: IRModule, output_config) -> str:
    buf = io.StringIO()
    Generator(output_config).generate(module, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Prologue / epilogue
# ---------------------------------------------------------------------------

class TestPrologueEpilogue:
    def test_luabridge3_prologue(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert "register_testmod" in out
        assert "getGlobalNamespace" in out

    def test_luabridge3_epilogue(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert out.rstrip().endswith("}")


# ---------------------------------------------------------------------------
# Class begin / derived begin
# ---------------------------------------------------------------------------

class TestClassTemplates:
    def test_base_class_uses_class_begin(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        out = _generate(mod, luabridge3_output_config)
        assert '.beginClass<mylib::MyClass>("MyClass")' in out

    def test_derived_class_uses_derived_begin(self, luabridge3_output_config):
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       variable_name="classBase")
        derived = IRClass(name="Derived", qualified_name="ns::Derived", namespace="ns",
                          bases=[IRBase("ns::Base")], variable_name="classDerived")
        mod = IRModule(name="m", classes=[base, derived],
                       class_by_name={"Base": base, "Derived": derived})
        out = _generate(mod, luabridge3_output_config)
        assert '.deriveClass<ns::Derived, ns::Base>("Derived")' in out

    def test_topo_sort_emits_base_before_derived(self, luabridge3_output_config):
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       variable_name="classBase")
        derived = IRClass(name="Derived", qualified_name="ns::Derived", namespace="ns",
                          bases=[IRBase("ns::Base")], variable_name="classDerived")
        # Deliberately put derived first in list; topo sort should fix ordering
        mod = IRModule(name="m", classes=[derived, base],
                       class_by_name={"Base": base, "Derived": derived})
        gen = Generator(luabridge3_output_config)
        sorted_names = [c.name for c in gen._topo_sort(mod.classes, mod.class_by_name)]
        assert sorted_names == ["Base", "Derived"]


# ---------------------------------------------------------------------------
# Method templates
# ---------------------------------------------------------------------------

class TestMethodTemplates:
    def test_regular_method(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addFunction("get_value"' in out

    def test_overloaded_method_uses_overload_cast(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert "luabridge::overload<int, int>(&mylib::MyClass::add)" in out
        assert "luabridge::overload<double, double>(&mylib::MyClass::add)" in out

    def test_static_method(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addStaticFunction("create"' in out

    def test_emit_false_method_skipped(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        mod.classes[0].methods[0].emit = False  # suppress getValue
        out = _generate(mod, luabridge3_output_config)
        assert 'addFunction("get_value"' not in out


# ---------------------------------------------------------------------------
# Constructor templates
# ---------------------------------------------------------------------------

class TestConstructorTemplates:
    def test_constructors(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert "addConstructor<void (*)()" in out
        assert "addConstructor<void (*)(int)" in out

    def test_suppressed_constructor_skipped(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        for c in mod.classes[0].constructors:
            c.emit = False
        out = _generate(mod, luabridge3_output_config)
        assert "addConstructor" not in out


# ---------------------------------------------------------------------------
# Field templates
# ---------------------------------------------------------------------------

class TestFieldTemplates:
    def test_readwrite_field(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addProperty("value_"' in out

    def test_readonly_field_has_nullptr(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addProperty("max_"' in out
        # readonly property uses nullptr as setter
        assert "nullptr" in out


# ---------------------------------------------------------------------------
# Enum templates
# ---------------------------------------------------------------------------

class TestEnumTemplates:
    def test_luabridge3_enum_namespace(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert ".endNamespace()" in out

    def test_suppressed_enum_value_skipped(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        mod.enums[0].values[0].emit = False   # suppress Red
        out = _generate(mod, luabridge3_output_config)
        assert '"Red"' not in out
        assert '"Green"' in out


# ---------------------------------------------------------------------------
# Function templates
# ---------------------------------------------------------------------------

class TestFunctionTemplates:
    def test_free_function(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addFunction("compute"' in out


# ---------------------------------------------------------------------------
# Unsupported types
# ---------------------------------------------------------------------------

class TestUnsupportedTypes:
    def test_unsupported_return_type_excluded(self, make_ir_module, luabridge3_output_config):
        from tsujikiri.ir import IRMethod
        mod = make_ir_module()
        bad_method = IRMethod(
            name="bad", spelling="bad",
            qualified_name="mylib::MyClass::bad",
            return_type="CFStringRef",
        )
        mod.classes[0].methods.append(bad_method)
        out = _generate(mod, luabridge3_output_config)
        assert '.addFunction("bad"' not in out


# ---------------------------------------------------------------------------
# Generation config
# ---------------------------------------------------------------------------

class TestGenerationConfig:
    def test_extra_unsupported_types_not_present(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        bad = IRMethod(
            name="doThing", spelling="doThing",
            qualified_name="mylib::MyClass::doThing",
            return_type="MyOpaqueType",
        )
        mod.classes[0].methods.append(bad)
        buf = io.StringIO()
        Generator(
            luabridge3_output_config,
            extra_unsupported_types=["MyOpaqueType"],
        ).generate(mod, buf)
        out = buf.getvalue()
        assert '.addFunction("doThing"' not in out

    def test_include_rendered_in_prologue(self, make_ir_module, luabridge3_output_config):
        from tsujikiri.configurations import GenerationConfig
        gen_cfg = GenerationConfig(includes=["<myheader.h>"])
        buf = io.StringIO()
        Generator(luabridge3_output_config, generation=gen_cfg).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert "#include <myheader.h>" in out

    def test_generation_prefix_written(self, make_ir_module, luabridge3_output_config):
        from tsujikiri.configurations import GenerationConfig
        gen_cfg = GenerationConfig(prefix="// MY PREFIX\n")
        buf = io.StringIO()
        Generator(luabridge3_output_config, generation=gen_cfg).generate(make_ir_module(), buf)
        assert buf.getvalue().startswith("// MY PREFIX\n")

    def test_generation_postfix_written(self, make_ir_module, luabridge3_output_config):
        from tsujikiri.configurations import GenerationConfig
        gen_cfg = GenerationConfig(postfix="// MY POSTFIX\n")
        buf = io.StringIO()
        Generator(luabridge3_output_config, generation=gen_cfg).generate(make_ir_module(), buf)
        assert buf.getvalue().endswith("// MY POSTFIX\n")


# ---------------------------------------------------------------------------
# Type mappings
# ---------------------------------------------------------------------------

class TestTypeMappings:
    def test_luals_return_types_mapped(self, make_ir_module, luals_output_config):
        out = _generate(make_ir_module(), luals_output_config)
        # C++ types must be converted to Lua types; check whole-word by including newline
        assert "---@return number\n" in out   # double → number
        assert "---@return integer\n" in out  # int → integer
        assert "---@return double\n" not in out
        assert "---@return int\n" not in out  # "integer" ends differently

    def test_luals_param_types_mapped(self, make_ir_module, luals_output_config):
        out = _generate(make_ir_module(), luals_output_config)
        # overload fun args use name: type format; double → number
        assert "fun(self: MyClass, a: number, b: number): number" in out
        # non-overloaded static method param: int → integer
        assert "---@param v integer\n" in out

    def test_luals_field_types_mapped(self, make_ir_module, luals_output_config):
        out = _generate(make_ir_module(), luals_output_config)
        assert "---@field value_ integer\n" in out  # int field → integer via ---@field
        assert "---@type int\n" not in out           # no bare "int" type annotation


# ---------------------------------------------------------------------------
# Renamed entities
# ---------------------------------------------------------------------------

class TestRenaming:
    def test_renamed_class_uses_new_name_in_template(self, luabridge3_output_config):
        cls = IRClass(name="Ugly", qualified_name="ns::Ugly", namespace="ns",
                      variable_name="classUgly", rename="Pretty")
        mod = IRModule(name="m", classes=[cls], class_by_name={"Ugly": cls})
        out = _generate(mod, luabridge3_output_config)
        assert '"Pretty"' in out

    def test_renamed_method_uses_new_name(self, luabridge3_output_config):
        m = IRMethod(name="getValueLong", spelling="getValueLong",
                     qualified_name="Cls::getValueLong", return_type="int", rename="get")
        cls = IRClass(name="Cls", qualified_name="ns::Cls", namespace="ns",
                      variable_name="classCls", methods=[m])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Cls": cls})
        out = _generate(mod, luabridge3_output_config)
        assert '.addFunction("get"' in out
        assert "getValueLong" in out  # spelling still used for the pointer


# ---------------------------------------------------------------------------
# Inner classes
# ---------------------------------------------------------------------------

class TestInnerClasses:
    def test_inner_class_emitted(self, luabridge3_output_config):
        inner = IRClass(name="Inner", qualified_name="ns::Outer::Inner", namespace="ns",
                        variable_name="classOuterInner")
        outer = IRClass(name="Outer", qualified_name="ns::Outer", namespace="ns",
                        variable_name="classOuter", inner_classes=[inner])
        mod = IRModule(name="m", classes=[outer], class_by_name={"Outer": outer})
        out = _generate(mod, luabridge3_output_config)
        assert "Inner" in out

    def test_suppressed_inner_class_skipped(self, luabridge3_output_config):
        inner = IRClass(name="Inner", qualified_name="ns::Outer::Inner", namespace="ns",
                        variable_name="classOuterInner")
        inner.emit = False
        outer = IRClass(name="Outer", qualified_name="ns::Outer", namespace="ns",
                        variable_name="classOuter", inner_classes=[inner])
        mod = IRModule(name="m", classes=[outer], class_by_name={"Outer": outer})
        out = _generate(mod, luabridge3_output_config)
        assert "Inner" not in out


# ---------------------------------------------------------------------------
# Const/non-const overload cast
# ---------------------------------------------------------------------------

class TestConstNonConstOverload:
    def test_const_nonconst_overload_uses_cast(self, luabridge3_output_config):
        m_const = IRMethod(name="get", spelling="get", qualified_name="C::get",
                           return_type="int", is_const=True, is_overload=True)
        m_nonconst = IRMethod(name="get", spelling="get", qualified_name="C::get",
                              return_type="int", is_const=False, is_overload=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", methods=[m_const, m_nonconst])
        mod = IRModule(name="m", classes=[cls], class_by_name={"C": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "C::get" in out


# ---------------------------------------------------------------------------
# Suppressed fields and unsupported field types
# ---------------------------------------------------------------------------

class TestFieldEdgeCases:
    def test_suppressed_field_skipped_in_emit(self, luabridge3_output_config):
        f = IRField(name="secret_", type_spelling="int")
        f.emit = False
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", fields=[f])
        mod = IRModule(name="m", classes=[cls], class_by_name={"C": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "secret_" not in out

    def test_suppressed_field_skipped_in_annotation(self, make_ir_module, luals_output_config):
        mod = make_ir_module()
        mod.classes[0].fields[0].emit = False
        out = _generate(mod, luals_output_config)
        assert "---@field value_" not in out

    def test_unsupported_field_type_excluded(self, luabridge3_output_config):
        f = IRField(name="data_", type_spelling="CFStringRef")
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", fields=[f])
        mod = IRModule(name="m", classes=[cls], class_by_name={"C": cls})
        out = _generate(mod, luabridge3_output_config)
        assert "data_" not in out


# ---------------------------------------------------------------------------
# Function with unsupported return type
# ---------------------------------------------------------------------------

class TestFunctionUnsupportedType:
    def test_unsupported_function_return_excluded(self, luabridge3_output_config):
        fn = IRFunction(name="badFn", qualified_name="ns::badFn",
                        namespace="ns", return_type="CFStringRef")
        mod = IRModule(name="m", functions=[fn])
        out = _generate(mod, luabridge3_output_config)
        assert "badFn" not in out


# ---------------------------------------------------------------------------
# Topo-sort with cycle (leftover append path)
# ---------------------------------------------------------------------------

class TestTopoSortCycle:
    def test_cycle_classes_still_emitted(self, luabridge3_output_config):
        cls_a = IRClass(name="A", qualified_name="ns::A", namespace="ns",
                        variable_name="classA", bases=[IRBase("ns::B")])
        cls_b = IRClass(name="B", qualified_name="ns::B", namespace="ns",
                        variable_name="classB", bases=[IRBase("ns::A")])
        mod = IRModule(name="m", classes=[cls_a, cls_b],
                       class_by_name={"A": cls_a, "B": cls_b})
        gen = Generator(luabridge3_output_config)
        sorted_classes = gen._topo_sort(mod.classes, mod.class_by_name)
        assert len(sorted_classes) == 2


# ---------------------------------------------------------------------------
# Template inheritance (template_extends)
# ---------------------------------------------------------------------------

class TestTemplateExtends:
    def test_extends_overrides_prologue(self, make_ir_module, luabridge3_output_config):
        child = (
            '{% extends "luabridge3.tpl" %}'
            '{% block prologue %}// CUSTOM PROLOGUE\n{% endblock %}'
        )
        buf = io.StringIO()
        Generator(luabridge3_output_config, template_extends=child).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert "// CUSTOM PROLOGUE" in out
        assert "getGlobalNamespace" not in out

    def test_extends_overrides_class_block(self, make_ir_module, luabridge3_output_config):
        child = (
            '{% extends "luabridge3.tpl" %}'
            '{% block class scoped %}.myClass("{{ cls.name }}")\n{% endblock %}'
        )
        buf = io.StringIO()
        Generator(luabridge3_output_config, template_extends=child).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert '.myClass("MyClass")' in out
        assert ".beginClass" not in out


# ---------------------------------------------------------------------------
# ItemFirstEnvironment.getattr fallback paths
# ---------------------------------------------------------------------------

class TestItemFirstEnvironment:
    def test_getattr_falls_back_to_python_attr(self):
        env = ItemFirstEnvironment(
            loader=jinja2.DictLoader({"t.tpl": "{{ s.upper() }}"}),
            undefined=jinja2.StrictUndefined,
        )
        assert env.get_template("t.tpl").render(s="hello") == "HELLO"

    def test_getattr_returns_undefined_for_missing_attr(self):
        env = ItemFirstEnvironment(
            loader=jinja2.DictLoader({"t.tpl": "{{ s.nonexistent_attr }}"}),
            undefined=jinja2.StrictUndefined,
        )
        with pytest.raises(jinja2.UndefinedError):
            env.get_template("t.tpl").render(s="hello")


# ---------------------------------------------------------------------------
# Broken format file silently ignored (lines 94-95)
# ---------------------------------------------------------------------------

class TestBrokenFormatFile:
    def test_load_output_config_exception_silently_ignored(self, make_ir_module, luabridge3_output_config):
        buf = io.StringIO()
        with patch("tsujikiri.configurations.load_output_config", side_effect=Exception("bad yml")):
            Generator(luabridge3_output_config).generate(make_ir_module(), buf)
        assert buf.getvalue()


# ---------------------------------------------------------------------------
# IR metadata in context (virtual, noexcept, explicit, abstract)
# ---------------------------------------------------------------------------

class TestIRMetadataInContext:
    """Verify that virtual/noexcept/explicit/abstract metadata reaches the template context."""

    def _ctx_class(self, ir_class):
        from tsujikiri.configurations import OutputConfig
        cfg = OutputConfig(
            format_name="test", format_version="1", description="",
            template="{% for cls in classes %}{{ cls.name }}{% endfor %}",
        )
        gen = Generator(cfg)
        mod = IRModule(name="m", classes=[ir_class], class_by_name={ir_class.name: ir_class})
        return gen._build_class_ctx(ir_class)

    def test_method_is_virtual_in_context(self):
        m = IRMethod(name="fn", spelling="fn", qualified_name="C::fn",
                     return_type="void", is_virtual=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", methods=[m], has_virtual_methods=True)
        ctx = self._ctx_class(cls)
        assert ctx["has_virtual_methods"] is True
        assert ctx["method_groups"][0]["methods"][0]["is_virtual"] is True

    def test_method_is_pure_virtual_in_context(self):
        m = IRMethod(name="fn", spelling="fn", qualified_name="C::fn",
                     return_type="void", is_virtual=True, is_pure_virtual=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", methods=[m],
                      has_virtual_methods=True, is_abstract=True)
        ctx = self._ctx_class(cls)
        assert ctx["is_abstract"] is True
        assert ctx["method_groups"][0]["methods"][0]["is_pure_virtual"] is True

    def test_method_is_noexcept_in_context(self):
        m = IRMethod(name="fn", spelling="fn", qualified_name="C::fn",
                     return_type="void", is_noexcept=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", methods=[m])
        ctx = self._ctx_class(cls)
        assert ctx["method_groups"][0]["methods"][0]["is_noexcept"] is True

    def test_method_not_noexcept_by_default(self):
        m = IRMethod(name="fn", spelling="fn", qualified_name="C::fn", return_type="void")
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", methods=[m])
        ctx = self._ctx_class(cls)
        assert ctx["method_groups"][0]["methods"][0]["is_noexcept"] is False

    def test_constructor_is_noexcept_in_context(self):
        ctor = IRConstructor(parameters=[], is_noexcept=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", constructors=[ctor])
        ctx = self._ctx_class(cls)
        assert ctx["constructor_group"]["constructors"][0]["is_noexcept"] is True

    def test_constructor_is_explicit_in_context(self):
        ctor = IRConstructor(parameters=[IRParameter("x", "int")], is_explicit=True)
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", constructors=[ctor])
        ctx = self._ctx_class(cls)
        assert ctx["constructor_group"]["constructors"][0]["is_explicit"] is True

    def test_constructor_not_explicit_by_default(self):
        ctor = IRConstructor(parameters=[])
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC", constructors=[ctor])
        ctx = self._ctx_class(cls)
        assert ctx["constructor_group"]["constructors"][0]["is_explicit"] is False

    def test_class_not_abstract_by_default(self):
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC")
        ctx = self._ctx_class(cls)
        assert ctx["is_abstract"] is False
        assert ctx["has_virtual_methods"] is False

    def test_bases_in_context(self):
        cls = IRClass(name="D", qualified_name="ns::D", namespace="ns",
                      variable_name="classD",
                      bases=[IRBase("ns::A", "public"), IRBase("ns::B", "protected")])
        ctx = self._ctx_class(cls)
        assert ctx["bases"] == [
            {"qualified_name": "ns::A", "access": "public", "emit": True},
            {"qualified_name": "ns::B", "access": "protected", "emit": True},
        ]
        assert ctx["base_name"] == "ns::A"

    def test_public_bases_in_context(self):
        cls = IRClass(name="D", qualified_name="ns::D", namespace="ns",
                      variable_name="classD",
                      bases=[IRBase("ns::A", "public"), IRBase("ns::B", "protected")])
        ctx = self._ctx_class(cls)
        assert ctx["public_bases"] == [
            {"qualified_name": "ns::A", "short_name": "A"},
        ]

    def test_suppressed_base_excluded_from_public_bases(self):
        base = IRBase("ns::A", "public")
        base.emit = False
        cls = IRClass(name="D", qualified_name="ns::D", namespace="ns",
                      variable_name="classD", bases=[base])
        ctx = self._ctx_class(cls)
        assert ctx["public_bases"] == []
        assert ctx["base_name"] == ""

    def test_no_bases_context(self):
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                      variable_name="classC")
        ctx = self._ctx_class(cls)
        assert ctx["bases"] == []
        assert ctx["base_name"] == ""

    def test_function_is_noexcept_in_context(self):
        from tsujikiri.configurations import OutputConfig
        fn = IRFunction(name="foo", qualified_name="ns::foo",
                        namespace="ns", return_type="void", is_noexcept=True)
        cfg = OutputConfig(
            format_name="test", format_version="1", description="", template="",
        )
        gen = Generator(cfg)
        groups = gen._build_function_group_ctxs([fn])
        assert groups[0]["functions"][0]["is_noexcept"] is True

    def test_function_not_noexcept_by_default(self):
        from tsujikiri.configurations import OutputConfig
        fn = IRFunction(name="foo", qualified_name="ns::foo",
                        namespace="ns", return_type="void")
        cfg = OutputConfig(
            format_name="test", format_version="1", description="", template="",
        )
        gen = Generator(cfg)
        groups = gen._build_function_group_ctxs([fn])
        assert groups[0]["functions"][0]["is_noexcept"] is False
