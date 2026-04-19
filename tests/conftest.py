"""Top-level pytest configuration and shared fixtures."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Shared output-config fixtures (built-in formats)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def luabridge3_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luabridge3"))


@pytest.fixture(scope="session")
def pybind11_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pybind11"))


@pytest.fixture(scope="session")
def luals_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luals"))



# ---------------------------------------------------------------------------
# IR builder helpers (used by multiple test modules)
# ---------------------------------------------------------------------------

@pytest.fixture
def make_ir_module():
    """Factory: build a self-contained TIRModule for generator / filter tests."""
    from tsujikiri.ir import (
        IRClass, IRConstructor, IREnum, IREnumValue, IRField,
        IRFunction, IRMethod, IRModule, IRParameter,
    )
    from tsujikiri.tir import upgrade_module

    def _build(name: str = "testmod"):
        method = IRMethod(
            name="getValue", spelling="getValue",
            qualified_name="mylib::MyClass::getValue",
            return_type="int", is_const=True,
        )
        add_int = IRMethod(
            name="add", spelling="add",
            qualified_name="mylib::MyClass::add",
            return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int")],
            is_overload=True,
        )
        add_dbl = IRMethod(
            name="add", spelling="add",
            qualified_name="mylib::MyClass::add",
            return_type="double",
            parameters=[IRParameter("a", "double"), IRParameter("b", "double")],
            is_overload=True,
        )
        static_m = IRMethod(
            name="create", spelling="create",
            qualified_name="mylib::MyClass::create",
            return_type="int",
            parameters=[IRParameter("v", "int")],
            is_static=True,
        )
        ctor0 = IRConstructor(parameters=[])
        ctor1 = IRConstructor(parameters=[IRParameter("v", "int")], is_overload=True)
        field = IRField(name="value_", type_spelling="int")
        const_field = IRField(name="max_", type_spelling="const int", is_const=True)
        nested_enum = IREnum(
            name="State", qualified_name="mylib::MyClass::State",
            values=[IREnumValue("Off", 0), IREnumValue("On", 1)],
        )
        cls = IRClass(
            name="MyClass", qualified_name="mylib::MyClass", namespace="mylib",
            variable_name="classMyClass",
            constructors=[ctor0, ctor1],
            methods=[method, add_int, add_dbl, static_m],
            fields=[field, const_field],
            enums=[nested_enum],
        )
        color = IREnum(
            name="Color", qualified_name="mylib::Color",
            values=[IREnumValue("Red", 0), IREnumValue("Green", 1)],
        )
        fn = IRFunction(
            name="compute", qualified_name="mylib::compute",
            namespace="mylib", return_type="double",
            parameters=[IRParameter("x", "double")],
        )
        ir_mod = IRModule(
            name=name,
            classes=[cls], enums=[color], functions=[fn],
            class_by_name={"MyClass": cls},
        )
        return upgrade_module(ir_mod)

    return _build


@pytest.fixture
def generate():
    """Helper: generate bindings to a string."""
    from tsujikiri.generator import Generator

    def _gen(module, output_config) -> str:
        buf = io.StringIO()
        Generator(output_config).generate(module, buf)
        return buf.getvalue()

    return _gen
