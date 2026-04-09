"""Tests for generator.py — template rendering, topo-sort, emit flags."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import IRClass, IREnum, IREnumValue, IRField, IRFunction, IRMethod, IRModule, IRParameter, IRConstructor


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
                          bases=["ns::Base"], variable_name="classDerived")
        mod = IRModule(name="m", classes=[base, derived],
                       class_by_name={"Base": base, "Derived": derived})
        out = _generate(mod, luabridge3_output_config)
        assert '.deriveClass<ns::Derived, ns::Base>("Derived")' in out

    def test_topo_sort_emits_base_before_derived(self, luabridge3_output_config):
        from tsujikiri.generator import Generator
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       variable_name="classBase")
        derived = IRClass(name="Derived", qualified_name="ns::Derived", namespace="ns",
                          bases=["ns::Base"], variable_name="classDerived")
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
        assert '.addFunction("getValue"' in out

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
        assert 'addFunction("getValue"' not in out


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
    def test_unsupported_return_type_commented_out(self, make_ir_module, luabridge3_output_config):
        mod = make_ir_module()
        bad_method = IRMethod(
            name="bad", spelling="bad",
            qualified_name="mylib::MyClass::bad",
            return_type="CFStringRef",
        )
        mod.classes[0].methods.append(bad_method)
        out = _generate(mod, luabridge3_output_config)
        assert '// .addFunction("bad"' in out


# ---------------------------------------------------------------------------
# Renamed entities
# ---------------------------------------------------------------------------

class TestTemplateOverrides:
    def test_override_replaces_template(self, make_ir_module, luabridge3_output_config):
        overrides = {"class_begin": ".custom(\"{{ qualified_class_name }}\")\n"}
        buf = io.StringIO()
        Generator(luabridge3_output_config, template_overrides=overrides).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert '.custom("mylib::MyClass")' in out
        assert ".beginClass" not in out

    def test_override_super_wraps_base(self, make_ir_module, luabridge3_output_config):
        overrides = {"prologue": "// PRE\n{{ super }}// POST\n"}
        buf = io.StringIO()
        Generator(luabridge3_output_config, template_overrides=overrides).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert out.startswith("// PRE\n")
        assert "getGlobalNamespace" in out  # base prologue content
        assert "// POST\n" in out

    def test_extra_unsupported_types_comment_out(self, make_ir_module, luabridge3_output_config):
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
        assert '// .addFunction("doThing"' in out

    def test_override_empty_string_suppresses_template(self, make_ir_module, luabridge3_output_config):
        overrides = {"class_end": ""}
        buf = io.StringIO()
        Generator(luabridge3_output_config, template_overrides=overrides).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert ".endClass()" not in out

    def test_include_directive_override(self, make_ir_module, luabridge3_output_config):
        from tsujikiri.configurations import GenerationConfig
        overrides = {"include_directive": "import {{ include }};\n"}
        gen_cfg = GenerationConfig(includes=["<foo.h>"])
        buf = io.StringIO()
        Generator(
            luabridge3_output_config,
            generation=gen_cfg,
            template_overrides=overrides,
        ).generate(make_ir_module(), buf)
        out = buf.getvalue()
        # custom directive is used for generation.includes entries
        assert "import <foo.h>;" in out
        # the custom include appears before the prologue (which has its own #include lines)
        assert out.index("import <foo.h>;") < out.index("getGlobalNamespace")


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
