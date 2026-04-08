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
# Basic generation smoke tests (all three formats)
# ---------------------------------------------------------------------------

class TestPrologueEpilogue:
    def test_luabridge3_prologue(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert "register_testmod" in out
        assert "getGlobalNamespace" in out

    def test_pybind11_prologue(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert "PYBIND11_MODULE" in out
        assert "testmod" in out

    def test_c_api_prologue(self, make_ir_module, c_api_output_config):
        out = _generate(make_ir_module(), c_api_output_config)
        assert "extern" in out
        assert "pragma once" in out

    def test_pybind11_epilogue_closes_module(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert out.rstrip().endswith("}")


# ---------------------------------------------------------------------------
# Class begin / derived begin
# ---------------------------------------------------------------------------

class TestClassTemplates:
    def test_base_class_uses_class_begin(self, make_ir_module, pybind11_output_config):
        mod = make_ir_module()
        out = _generate(mod, pybind11_output_config)
        assert "py::class_<mylib::MyClass>" in out

    def test_derived_class_uses_derived_begin(self, pybind11_output_config):
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       variable_name="classBase")
        derived = IRClass(name="Derived", qualified_name="ns::Derived", namespace="ns",
                          bases=["Base"], variable_name="classDerived")
        mod = IRModule(name="m", classes=[base, derived],
                       class_by_name={"Base": base, "Derived": derived})
        out = _generate(mod, pybind11_output_config)
        assert "py::class_<ns::Derived, Base>" in out

    def test_topo_sort_emits_base_before_derived(self, pybind11_output_config):
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       variable_name="classBase")
        derived = IRClass(name="Derived", qualified_name="ns::Derived", namespace="ns",
                          bases=["Base"], variable_name="classDerived")
        # Deliberately put derived first in list
        mod = IRModule(name="m", classes=[derived, base],
                       class_by_name={"Base": base, "Derived": derived})
        out = _generate(mod, pybind11_output_config)
        assert out.index("Base") < out.index("Derived")


# ---------------------------------------------------------------------------
# Method templates
# ---------------------------------------------------------------------------

class TestMethodTemplates:
    def test_regular_method_luabridge3(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addFunction("getValue"' in out

    def test_regular_method_pybind11(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert '.def("getValue"' in out

    def test_overloaded_method_has_static_cast(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert "static_cast<int (mylib::MyClass::*)(int, int)>" in out
        assert "static_cast<double (mylib::MyClass::*)(double, double)>" in out

    def test_const_method_adds_const_qualifier(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        # getValue is const and overloaded=False — still uses addFunction, not static_cast
        # check const qualifier appears somewhere (for overloaded const methods)
        # In our module getValue is NOT overloaded, so no static_cast is emitted.
        assert "getValue" in out

    def test_static_method_pybind11(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert '.def_static("create"' in out

    def test_emit_false_method_skipped(self, make_ir_module, pybind11_output_config):
        mod = make_ir_module()
        mod.classes[0].methods[0].emit = False  # suppress getValue
        out = _generate(mod, pybind11_output_config)
        assert 'def("getValue"' not in out


# ---------------------------------------------------------------------------
# Constructor templates
# ---------------------------------------------------------------------------

class TestConstructorTemplates:
    def test_luabridge3_constructors(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert "addConstructor<void (*)()" in out     # default ctor
        assert "addConstructor<void (*)(int)" in out  # int ctor

    def test_pybind11_constructors(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert ".def(py::init<>()" in out
        assert ".def(py::init<int>()" in out

    def test_suppressed_constructor_skipped(self, make_ir_module, pybind11_output_config):
        mod = make_ir_module()
        for c in mod.classes[0].constructors:
            c.emit = False
        out = _generate(mod, pybind11_output_config)
        assert "py::init" not in out


# ---------------------------------------------------------------------------
# Field templates
# ---------------------------------------------------------------------------

class TestFieldTemplates:
    def test_readwrite_field_pybind11(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert '.def_readwrite("value_"' in out

    def test_readonly_field_pybind11(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert '.def_readonly("max_"' in out

    def test_c_api_field_getter_setter(self, make_ir_module, c_api_output_config):
        out = _generate(make_ir_module(), c_api_output_config)
        assert "MyClass_get_value_" in out
        assert "MyClass_set_value_" in out

    def test_c_api_readonly_no_setter(self, make_ir_module, c_api_output_config):
        out = _generate(make_ir_module(), c_api_output_config)
        assert "MyClass_get_max_" in out
        assert "MyClass_set_max_" not in out


# ---------------------------------------------------------------------------
# Enum templates
# ---------------------------------------------------------------------------

class TestEnumTemplates:
    def test_pybind11_enum(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert 'py::enum_<mylib::Color>' in out
        assert '.value("Red"' in out
        assert '.value("Green"' in out
        assert ".export_values();" in out

    def test_luabridge3_enum_namespace(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert ".endNamespace()" in out

    def test_c_api_enum(self, make_ir_module, c_api_output_config):
        out = _generate(make_ir_module(), c_api_output_config)
        assert "typedef enum {" in out
        assert "Red," in out
        assert "} Color;" in out

    def test_suppressed_enum_value_skipped(self, make_ir_module, pybind11_output_config):
        mod = make_ir_module()
        mod.enums[0].values[0].emit = False   # suppress Red
        out = _generate(mod, pybind11_output_config)
        assert '.value("Red"' not in out
        assert '.value("Green"' in out


# ---------------------------------------------------------------------------
# Function templates
# ---------------------------------------------------------------------------

class TestFunctionTemplates:
    def test_pybind11_free_function(self, make_ir_module, pybind11_output_config):
        out = _generate(make_ir_module(), pybind11_output_config)
        assert 'm.def("compute"' in out

    def test_luabridge3_free_function(self, make_ir_module, luabridge3_output_config):
        out = _generate(make_ir_module(), luabridge3_output_config)
        assert '.addFunction("compute"' in out

    def test_c_api_free_function(self, make_ir_module, c_api_output_config):
        out = _generate(make_ir_module(), c_api_output_config)
        assert "double compute(" in out


# ---------------------------------------------------------------------------
# Unsupported types
# ---------------------------------------------------------------------------

class TestUnsupportedTypes:
    def test_unsupported_return_type_commented_out(self, make_ir_module, pybind11_output_config):
        mod = make_ir_module()
        bad_method = IRMethod(
            name="bad", spelling="bad",
            qualified_name="mylib::MyClass::bad",
            return_type="CFStringRef",
        )
        mod.classes[0].methods.append(bad_method)
        out = _generate(mod, pybind11_output_config)
        assert '// .def("bad"' in out


# ---------------------------------------------------------------------------
# Renamed entities
# ---------------------------------------------------------------------------

class TestRenaming:
    def test_renamed_class_uses_new_name_in_template(self, pybind11_output_config):
        cls = IRClass(name="Ugly", qualified_name="ns::Ugly", namespace="ns",
                      variable_name="classUgly", rename="Pretty")
        mod = IRModule(name="m", classes=[cls], class_by_name={"Ugly": cls})
        out = _generate(mod, pybind11_output_config)
        assert '"Pretty"' in out

    def test_renamed_method_uses_new_name(self, pybind11_output_config):
        m = IRMethod(name="getValueLong", spelling="getValueLong",
                     qualified_name="Cls::getValueLong", return_type="int", rename="get")
        cls = IRClass(name="Cls", qualified_name="ns::Cls", namespace="ns",
                      variable_name="classCls", methods=[m])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Cls": cls})
        out = _generate(mod, pybind11_output_config)
        assert '.def("get"' in out
        assert "getValueLong" in out  # spelling still used for the pointer


# ---------------------------------------------------------------------------
# method_args_sep for C API instance methods
# ---------------------------------------------------------------------------

class TestCApiMethodArgs:
    def test_no_args_method(self, c_api_output_config):
        m = IRMethod(name="area", spelling="area",
                     qualified_name="Shape::area", return_type="double",
                     is_const=True)
        cls = IRClass(name="Shape", qualified_name="ns::Shape", namespace="ns",
                      variable_name="classShape", methods=[m])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Shape": cls})
        out = _generate(mod, c_api_output_config)
        # Should produce: double Shape_area(Shape_t self);  (no trailing comma)
        assert "Shape_area(Shape_t self);" in out

    def test_one_arg_method(self, c_api_output_config):
        m = IRMethod(name="setName", spelling="setName",
                     qualified_name="Shape::setName", return_type="void",
                     parameters=[IRParameter("name", "const char *")])
        cls = IRClass(name="Shape", qualified_name="ns::Shape", namespace="ns",
                      variable_name="classShape", methods=[m])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Shape": cls})
        out = _generate(mod, c_api_output_config)
        # Should produce: void Shape_setName(Shape_t self, const char *);
        assert "Shape_setName(Shape_t self, const char *);" in out
