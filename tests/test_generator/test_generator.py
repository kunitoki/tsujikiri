"""Tests for generator.py — template rendering, topo-sort, emit flags."""

from __future__ import annotations

import io

import pytest
import jinja2
from unittest.mock import MagicMock, patch

import tsujikiri.formats as tsujikiri_formats
from tsujikiri.configurations import OutputConfig
from tsujikiri.generator import Generator, ItemFirstEnvironment, _type_lookup_candidates
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
        assert "addConstructor<void (*)(), void (*)(int)>" in out

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
# Format-level template inheritance (extends field in OutputConfig)
# ---------------------------------------------------------------------------

class TestFormatLevelInheritance:
    def test_format_template_extends_builtin(self, make_ir_module):
        """A format whose template uses {% extends %} renders via Jinja2 inheritance."""
        from tsujikiri.configurations import OutputConfig
        cfg = OutputConfig(
            format_name="myformat",
            extends="luabridge3",
            template=(
                '{% extends "luabridge3.tpl" %}'
                '{% block prologue %}// CUSTOM PROLOGUE\n{% endblock %}'
            ),
        )
        buf = io.StringIO()
        Generator(cfg).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert "// CUSTOM PROLOGUE" in out
        assert "getGlobalNamespace" not in out

    def test_format_template_super_call_includes_parent(self, make_ir_module):
        """{{ super() }} in a format-level block includes parent block content."""
        from tsujikiri.configurations import OutputConfig
        cfg = OutputConfig(
            format_name="myformat",
            extends="luabridge3",
            template=(
                '{% extends "luabridge3.tpl" %}'
                '{% block prologue %}// PREPEND\n{{ super() }}{% endblock %}'
            ),
        )
        buf = io.StringIO()
        Generator(cfg).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert "// PREPEND" in out
        assert "getGlobalNamespace" in out

    def test_format_extra_dirs_loaded_into_dict_loader(self, make_ir_module, tmp_path):
        """Templates from extra_dirs are available for {% extends %} resolution."""
        fmt_content = (
            "format_name: custombase\n"
            "language: cpp\n"
            "template: |\n"
            "  // CUSTOM BASE PROLOGUE\n"
            "  {% for cls in classes %}cls:{{ cls.name }}\n"
            "  {% endfor %}\n"
        )
        (tmp_path / "custombase.output.yml").write_text(fmt_content, encoding="utf-8")

        from tsujikiri.configurations import OutputConfig
        cfg = OutputConfig(
            format_name="myformat",
            template=(
                '{% extends "custombase.tpl" %}'
            ),
        )
        buf = io.StringIO()
        Generator(cfg, extra_dirs=[tmp_path]).generate(make_ir_module(), buf)
        out = buf.getvalue()
        assert "// CUSTOM BASE PROLOGUE" in out

    def test_extra_dirs_skips_format_with_no_template(self, make_ir_module, tmp_path, luabridge3_output_config):
        """A format in extra_dirs with no template is silently skipped (covers empty-template branch)."""
        (tmp_path / "notpl.output.yml").write_text("format_name: notpl\n", encoding="utf-8")
        buf = io.StringIO()
        # Should render normally without crashing despite the no-template format in extra_dirs.
        Generator(luabridge3_output_config, extra_dirs=[tmp_path]).generate(make_ir_module(), buf)
        assert "register_testmod" in buf.getvalue()

    def test_extra_dirs_skips_name_collision_with_builtin(self, make_ir_module, tmp_path, luabridge3_output_config):
        """A format in extra_dirs whose name collides with a built-in is skipped (covers tpl_key-in-dict branch)."""
        (tmp_path / "luabridge3.output.yml").write_text(
            "format_name: luabridge3\ntemplate: '// IMPOSTOR'\n", encoding="utf-8"
        )
        buf = io.StringIO()
        Generator(luabridge3_output_config, extra_dirs=[tmp_path]).generate(make_ir_module(), buf)
        # Built-in luabridge3 template wins; impostor content must not appear.
        assert "// IMPOSTOR" not in buf.getvalue()

    def test_extra_dirs_skips_malformed_format_file(self, make_ir_module, tmp_path, luabridge3_output_config):
        """A malformed .output.yml in extra_dirs is silently skipped (covers except branch)."""
        (tmp_path / "bad.output.yml").write_text("{ invalid yaml: [", encoding="utf-8")
        buf = io.StringIO()
        Generator(luabridge3_output_config, extra_dirs=[tmp_path]).generate(make_ir_module(), buf)
        assert "register_testmod" in buf.getvalue()

    def test_chain_extends_two_custom_levels(self, make_ir_module, tmp_path):
        """Chain: builtin luabridge3 → mid (extra_dir) → top (current format)."""
        mid_tpl_file = tmp_path / "mid.output.tpl"
        mid_tpl_file.write_text(
            '{% extends "luabridge3.tpl" %}'
            '{% block prologue %}// MID\n{% endblock %}',
            encoding="utf-8",
        )
        (tmp_path / "mid.output.yml").write_text(
            "format_name: mid\nlanguage: lua\ntemplate_file: mid.output.tpl\n",
            encoding="utf-8",
        )
        top_tpl = (
            '{% extends "mid.tpl" %}'
            '{% block prologue %}// TOP\n{% endblock %}'
        )
        from tsujikiri.configurations import OutputConfig
        top_cfg = OutputConfig(format_name="top", language="lua", template=top_tpl)
        buf = io.StringIO()
        Generator(top_cfg, extra_dirs=[tmp_path]).generate(make_ir_module(), buf)
        assert "// TOP" in buf.getvalue()
        assert "// MID" not in buf.getvalue()

    def test_chain_extends_with_template_extends_override(self, make_ir_module, tmp_path):
        """Full chain: builtin → mid → top → __override__ via template_extends."""
        mid_tpl_file = tmp_path / "mid.output.tpl"
        mid_tpl_file.write_text(
            '{% extends "luabridge3.tpl" %}'
            '{% block prologue %}// MID\n{% endblock %}',
            encoding="utf-8",
        )
        (tmp_path / "mid.output.yml").write_text(
            "format_name: mid\nlanguage: lua\ntemplate_file: mid.output.tpl\n",
            encoding="utf-8",
        )
        top_tpl_file = tmp_path / "top.output.tpl"
        top_tpl_file.write_text(
            '{% extends "mid.tpl" %}'
            '{% block prologue %}// TOP\n{% endblock %}',
            encoding="utf-8",
        )
        (tmp_path / "top.output.yml").write_text(
            "format_name: top\nlanguage: lua\ntemplate_file: top.output.tpl\n",
            encoding="utf-8",
        )
        top_tpl = top_tpl_file.read_text(encoding="utf-8")
        from tsujikiri.configurations import OutputConfig
        top_cfg = OutputConfig(format_name="top", language="lua", template=top_tpl)
        override = (
            '{% extends "top.tpl" %}'
            '{% block prologue %}// OVERRIDE\n{% endblock %}'
        )
        buf = io.StringIO()
        Generator(top_cfg, extra_dirs=[tmp_path], template_extends=override).generate(make_ir_module(), buf)
        assert "// OVERRIDE" in buf.getvalue()
        assert "// TOP" not in buf.getvalue()

    def test_implicit_template_for_extends_only_format(self, make_ir_module, tmp_path):
        """A format with extends: but no template auto-generates {% extends 'base.tpl' %}."""
        (tmp_path / "passthrough.output.yml").write_text(
            "format_name: passthrough\nextends: luabridge3\n",
            encoding="utf-8",
        )
        override = (
            '{% extends "passthrough.tpl" %}'
            '{% block prologue %}// PT\n{% endblock %}'
        )
        from tsujikiri.configurations import OutputConfig
        pt_cfg = OutputConfig(format_name="passthrough", template="")
        buf = io.StringIO()
        Generator(pt_cfg, extra_dirs=[tmp_path], template_extends=override).generate(make_ir_module(), buf)
        assert "// PT" in buf.getvalue()


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
        with patch("tsujikiri.generator.load_output_config", side_effect=Exception("bad yml")):
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


# ---------------------------------------------------------------------------
# Branch coverage: format file with no template in the scan loop (line 91->88)
# ---------------------------------------------------------------------------

class TestFormatScanNoTemplate:
    def test_format_scan_skips_config_without_template(self, make_ir_module, luabridge3_output_config, tmp_path):
        """A .output.yml that loads successfully but has no template is skipped gracefully."""
        no_tpl_file = tmp_path / "notpl.output.yml"
        no_tpl_file.write_text("format_name: notpl\nformat_version: '1.0'\n", encoding="utf-8")

        real_files = list(tsujikiri_formats._FORMATS_DIR.glob("*.output.yml"))
        mock_dir = MagicMock()
        mock_dir.glob.return_value = [no_tpl_file] + real_files

        buf = io.StringIO()
        with patch("tsujikiri.generator._FORMATS_DIR", mock_dir):
            Generator(luabridge3_output_config).generate(make_ir_module(), buf)
        assert buf.getvalue()


# ---------------------------------------------------------------------------
# Branch coverage: generator with no cfg.template but template_extends (line 97->102)
# ---------------------------------------------------------------------------

class TestNoCfgTemplateWithExtends:
    def test_generate_with_extends_and_no_cfg_template(self, make_ir_module):
        """cfg.template is empty; template_extends provides the full template via inheritance."""
        cfg = OutputConfig(
            format_name="luabridge3",
            template="",
        )
        extends = '{% extends "luabridge3.tpl" %}'
        buf = io.StringIO()
        Generator(cfg, template_extends=extends).generate(make_ir_module(), buf)
        assert "getGlobalNamespace" in buf.getvalue()


# ---------------------------------------------------------------------------
# custom_data template context
# ---------------------------------------------------------------------------

class TestCustomData:
    def _cfg(self, template: str) -> OutputConfig:
        return OutputConfig(
            format_name="test", format_version="1", description="", template=template,
        )

    def _mod(self) -> IRModule:
        return IRModule(name="m")

    def test_custom_data_empty_by_default(self):
        cfg = self._cfg("{{ custom_data }}")
        buf = io.StringIO()
        Generator(cfg).generate(self._mod(), buf)
        assert buf.getvalue() == "{}"

    def test_custom_data_scalar_int(self):
        cfg = self._cfg("{{ custom_data.xyz }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"xyz": 1}).generate(self._mod(), buf)
        assert buf.getvalue() == "1"

    def test_custom_data_scalar_float(self):
        cfg = self._cfg("{{ custom_data.ratio }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"ratio": 42.1337}).generate(self._mod(), buf)
        assert "42.1337" in buf.getvalue()

    def test_custom_data_scalar_bool(self):
        cfg = self._cfg("{{ custom_data.flag }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"flag": True}).generate(self._mod(), buf)
        assert buf.getvalue() == "True"

    def test_custom_data_scalar_string(self):
        cfg = self._cfg("{{ custom_data.label }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"label": "hello"}).generate(self._mod(), buf)
        assert buf.getvalue() == "hello"

    def test_custom_data_list_index(self):
        cfg = self._cfg("{{ custom_data.abc[1] }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"abc": ["a", "b", "c"]}).generate(self._mod(), buf)
        assert buf.getvalue() == "b"

    def test_custom_data_list_with_filter(self):
        cfg = self._cfg("{{ custom_data.abc[0] | camel_to_snake }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"abc": ["camelCaseValue", "b"]}).generate(self._mod(), buf)
        assert buf.getvalue() == "camel_case_value"

    def test_custom_data_nested_dict(self):
        cfg = self._cfg("{{ custom_data.nested.x }}")
        buf = io.StringIO()
        Generator(cfg, custom_data={"nested": {"x": 99}}).generate(self._mod(), buf)
        assert buf.getvalue() == "99"

    def test_custom_data_none_treated_as_empty(self):
        cfg = self._cfg("{{ custom_data }}")
        buf = io.StringIO()
        Generator(cfg, custom_data=None).generate(self._mod(), buf)
        assert buf.getvalue() == "{}"

    def test_custom_data_full_example(self):
        template = (
            "{{ custom_data.xyz }},"
            "{{ custom_data.abc[1] | camel_to_snake }},"
            "{{ custom_data.something_else }},"
            "{{ custom_data.something_new }}"
        )
        cfg = self._cfg(template)
        buf = io.StringIO()
        Generator(cfg, custom_data={
            "xyz": 1,
            "abc": ["a", "myValue", "c"],
            "something_else": True,
            "something_new": 42.1337,
        }).generate(self._mod(), buf)
        out = buf.getvalue()
        assert out.startswith("1,")
        assert "my_value" in out
        assert "True" in out
        assert "42.1337" in out


# ---------------------------------------------------------------------------
# Branch coverage: suppressed class in _build_ir_context loop (line 137->136)
# ---------------------------------------------------------------------------

class TestSuppressedClassInContext:
    def test_emit_false_class_excluded_from_flat_classes(self, make_ir_module, luabridge3_output_config):
        """When _topo_sort returns a class with emit=False, it must not appear in the context."""
        mod = make_ir_module()
        mod.classes[0].emit = False

        gen = Generator(luabridge3_output_config)
        # Force _topo_sort to return the suppressed class so the branch at 137 is reached.
        with patch.object(gen, "_topo_sort", return_value=list(mod.classes)):
            buf = io.StringIO()
            gen.generate(mod, buf)
        assert "MyClass" not in buf.getvalue()


# ---------------------------------------------------------------------------
# Branch coverage: topo-sort diamond dependency (line 422->420)
# ---------------------------------------------------------------------------

class TestTopoSortDiamond:
    def test_diamond_dependency_base_first(self, luabridge3_output_config):
        """A -> B and A -> C: processing B decrements in_degree[A] to 1 (not 0),
        covering the False branch of ``if in_degree[dep_qname] == 0``."""
        base_b = IRClass(name="B", qualified_name="ns::B", namespace="ns",
                         variable_name="classB")
        base_c = IRClass(name="C", qualified_name="ns::C", namespace="ns",
                         variable_name="classC")
        child_a = IRClass(
            name="A", qualified_name="ns::A", namespace="ns",
            variable_name="classA",
            bases=[IRBase("ns::B"), IRBase("ns::C")],
        )

        class_by_name: dict = {"A": child_a, "B": base_b, "C": base_c}
        nodes = [child_a, base_b, base_c]

        gen = Generator(luabridge3_output_config)
        result = gen._topo_sort(nodes, class_by_name)
        names = [c.name for c in result]

        assert names.index("A") > names.index("B")
        assert names.index("A") > names.index("C")


# ---------------------------------------------------------------------------
# Typesystem-aware type mapping and unsupported-type logic
# ---------------------------------------------------------------------------

class TestTypesystemGenerator:
    def test_typesystem_primitive_mapping_fallback(self, luabridge3_output_config: OutputConfig) -> None:
        from tsujikiri.configurations import TypesystemConfig, PrimitiveTypeEntry
        ts = TypesystemConfig(
            primitive_types=[PrimitiveTypeEntry(cpp_name="int64_t", python_name="int")]
        )
        gen = Generator(luabridge3_output_config, typesystem=ts)
        assert gen._map_type("int64_t") == "int"

    def test_output_config_type_mapping_wins_over_typesystem(self) -> None:
        from tsujikiri.configurations import TypesystemConfig, PrimitiveTypeEntry
        ts = TypesystemConfig(
            primitive_types=[PrimitiveTypeEntry(cpp_name="MyType", python_name="from_typesystem")]
        )
        cfg = OutputConfig(
            format_name="test",
            type_mappings={"MyType": "from_output_config"},
            template="",
        )
        gen = Generator(cfg, typesystem=ts)
        assert gen._map_type("MyType") == "from_output_config"

    def test_typesystem_typedef_mapping_fallback(self, luabridge3_output_config: OutputConfig) -> None:
        from tsujikiri.configurations import TypesystemConfig, TypedefTypeEntry
        ts = TypesystemConfig(
            typedef_types=[TypedefTypeEntry(cpp_name="MyString", source="std::string")]
        )
        gen = Generator(luabridge3_output_config, typesystem=ts)
        assert gen._map_type("MyString") == "std::string"

    def test_custom_type_overrides_unsupported(self) -> None:
        from tsujikiri.configurations import TypesystemConfig, CustomTypeEntry
        ts = TypesystemConfig(
            custom_types=[CustomTypeEntry(cpp_name="QObject")]
        )
        cfg = OutputConfig(
            format_name="test",
            unsupported_types=["QObject"],
            template="",
        )
        gen = Generator(cfg, typesystem=ts)
        assert not gen._is_unsupported("QObject")

    def test_no_typesystem_unchanged_behaviour(self, luabridge3_output_config: OutputConfig) -> None:
        gen = Generator(luabridge3_output_config)
        assert gen._map_type("unknown_type") == "unknown_type"

    def test_conversion_rules_in_template_context(self) -> None:
        from tsujikiri.configurations import TypesystemConfig, ConversionRuleEntry
        ts = TypesystemConfig(
            conversion_rules=[
                ConversionRuleEntry(
                    cpp_type="MyColor",
                    native_to_target="convert_color(%%in)",
                    target_to_native="from_color(%%in)",
                ),
            ]
        )
        cfg = OutputConfig(
            format_name="test",
            template="{{ conversion_rules[0].cpp_type }}",
        )
        gen = Generator(cfg, typesystem=ts)
        buf = io.StringIO()
        gen.generate(IRModule(name="test"), buf)
        assert buf.getvalue() == "MyColor"

    def test_conversion_rules_empty_without_typesystem(self) -> None:
        cfg = OutputConfig(
            format_name="test",
            template="{{ conversion_rules | length }}",
        )
        gen = Generator(cfg)
        buf = io.StringIO()
        gen.generate(IRModule(name="test"), buf)
        assert buf.getvalue() == "0"


# ---------------------------------------------------------------------------
# _type_lookup_candidates
# ---------------------------------------------------------------------------

class TestTypeLookupCandidates:
    def test_exact_type_returns_single_candidate(self) -> None:
        assert _type_lookup_candidates("std::string") == ["std::string"]

    def test_const_ref_expands_to_four_candidates(self) -> None:
        result = _type_lookup_candidates("const std::string &")
        assert result == ["const std::string &", "const std::string", "std::string &", "std::string"]

    def test_ref_only_expands_to_two_candidates(self) -> None:
        assert _type_lookup_candidates("std::string &") == ["std::string &", "std::string"]

    def test_const_only_expands_to_two_candidates(self) -> None:
        assert _type_lookup_candidates("const std::string") == ["const std::string", "std::string"]

    def test_rvalue_ref_expands(self) -> None:
        assert _type_lookup_candidates("std::string &&") == ["std::string &&", "std::string"]

    def test_const_rvalue_ref_expands(self) -> None:
        result = _type_lookup_candidates("const std::string &&")
        assert result == ["const std::string &&", "const std::string", "std::string &&", "std::string"]

    def test_pointer_type_no_fallback(self) -> None:
        assert _type_lookup_candidates("char *") == ["char *"]

    def test_const_pointer_type_no_fallback(self) -> None:
        assert _type_lookup_candidates("const char *") == ["const char *"]

    def test_pointer_to_pointer_no_fallback(self) -> None:
        assert _type_lookup_candidates("char **") == ["char **"]


# ---------------------------------------------------------------------------
# _map_type — specificity-based fallback
# ---------------------------------------------------------------------------

class TestMapTypeSpecificityFallback:
    def test_base_type_mapping_covers_const_ref(self) -> None:
        cfg = OutputConfig(format_name="test", type_mappings={"std::string": "string"}, template="")
        gen = Generator(cfg)
        assert gen._map_type("const std::string &") == "string"

    def test_base_type_mapping_covers_ref(self) -> None:
        cfg = OutputConfig(format_name="test", type_mappings={"std::string": "string"}, template="")
        gen = Generator(cfg)
        assert gen._map_type("std::string &") == "string"

    def test_base_type_mapping_covers_const(self) -> None:
        cfg = OutputConfig(format_name="test", type_mappings={"std::string": "string"}, template="")
        gen = Generator(cfg)
        assert gen._map_type("const std::string") == "string"

    def test_more_specific_mapping_wins_over_base(self) -> None:
        cfg = OutputConfig(
            format_name="test",
            type_mappings={"std::string": "string", "const std::string &": "const_string_ref"},
            template="",
        )
        gen = Generator(cfg)
        assert gen._map_type("const std::string &") == "const_string_ref"
        assert gen._map_type("std::string &") == "string"

    def test_pointer_types_do_not_fall_back_to_base(self) -> None:
        cfg = OutputConfig(format_name="test", type_mappings={"char": "char_mapped"}, template="")
        gen = Generator(cfg)
        assert gen._map_type("char *") == "char *"
        assert gen._map_type("const char *") == "const char *"

    def test_pointer_types_use_exact_mapping(self) -> None:
        cfg = OutputConfig(
            format_name="test",
            type_mappings={"char *": "str", "const char *": "str"},
            template="",
        )
        gen = Generator(cfg)
        assert gen._map_type("char *") == "str"
        assert gen._map_type("const char *") == "str"
        assert gen._map_type("char") == "char"  # no mapping → unchanged
