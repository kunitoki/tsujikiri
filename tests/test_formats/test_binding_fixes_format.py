"""Golden-text assertions per output format for the three binding fixes:
defaulted-argument expansion, operator arity, anonymous-record fields."""

from __future__ import annotations

import io
from typing import Optional

import pytest

from tsujikiri.generator import Generator
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)


def _p(name: str, type_spelling: str, default: Optional[str] = None) -> TIRParameter:
    return TIRParameter(name=name, type_spelling=type_spelling, default_value=default)


def _render(module: TIRModule, config) -> str:
    buf = io.StringIO()
    Generator(config).generate(module, buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def vec_module() -> TIRModule:
    """A Vec2 carrying every construct the three fixes touch."""
    unary = TIRMethod(
        name="operator-",
        spelling="operator-",
        qualified_name="geo::Vec2::operator-",
        return_type="geo::Vec2",
        parameters=[],
        is_const=True,
        is_operator=True,
        operator_type="operator-unary",
        is_overload=True,
    )
    binary = TIRMethod(
        name="operator-",
        spelling="operator-",
        qualified_name="geo::Vec2::operator-",
        return_type="geo::Vec2",
        parameters=[_p("s", "double")],
        is_const=True,
        is_operator=True,
        operator_type="operator-",
        is_overload=True,
    )
    offset = TIRMethod(
        name="offset",
        spelling="offset",
        qualified_name="geo::Vec2::offset",
        return_type="geo::Vec2",
        parameters=[_p("dx", "double"), _p("dy", "double", "0.0"), _p("scale", "double", "1.0")],
        is_const=True,
    )
    cls = TIRClass(
        name="Vec2",
        qualified_name="geo::Vec2",
        namespace="geo",
        variable_name="classVec2",
        constructors=[TIRConstructor(parameters=[_p("x", "double"), _p("y", "double", "1.0")])],
        methods=[unary, binary, offset],
        # `width` is flattened out of an anonymous struct; `raw` is a C array.
        fields=[TIRField(name="raw", type_spelling="double[2]"), TIRField(name="width", type_spelling="double")],
    )
    free_add = TIRFunction(
        name="operator+",
        qualified_name="geo::operator+",
        namespace="geo",
        return_type="geo::Vec2",
        parameters=[_p("a", "const Vec2 &"), _p("b", "const Vec2 &")],
        is_operator=True,
        operator_type="operator+",
    )
    return TIRModule(name="geo", namespaces=["geo"], classes=[cls], functions=[free_add])


# ---------------------------------------------------------------------------
# luabridge3
# ---------------------------------------------------------------------------


class TestLuaBridge3Golden:
    @pytest.fixture(scope="class")
    def out(self, vec_module, luabridge3_output_config) -> str:
        return _render(vec_module, luabridge3_output_config)

    def test_unary_operator_binds_to_unm(self, out: str) -> None:
        assert '.addFunction("__unm", luabridge::overload<>(&geo::Vec2::operator-))' in out

    def test_binary_operator_binds_to_sub(self, out: str) -> None:
        assert '.addFunction("__sub", luabridge::overload<double>(&geo::Vec2::operator-))' in out

    def test_defaulted_method_emits_one_callable_per_arity(self, out: str) -> None:
        assert "luabridge::overload<double, double, double>(&geo::Vec2::offset)," in out
        assert (
            "[](geo::Vec2 const* self, double dx, double dy) -> decltype(auto) { return self->offset(dx, dy); }," in out
        )
        assert "[](geo::Vec2 const* self, double dx) -> decltype(auto) { return self->offset(dx); }\n" in out

    def test_constructor_signatures_are_truncated(self, out: str) -> None:
        assert ".addConstructor<void (*)(double, double), void (*)(double)>()" in out

    def test_free_operator_binds_as_metamethod(self, out: str) -> None:
        assert '.addFunction("__add", &geo::operator+)' in out

    def test_free_operator_is_not_a_module_function(self, out: str) -> None:
        assert '.addFunction("operator+"' not in out

    def test_array_field_is_not_bound(self, out: str) -> None:
        assert '"raw"' not in out

    def test_flattened_field_is_bound(self, out: str) -> None:
        assert '.addProperty("width", [](const geo::Vec2& o) { return o.width; }' in out


# ---------------------------------------------------------------------------
# luals
# ---------------------------------------------------------------------------


class TestLuaLSGolden:
    @pytest.fixture(scope="class")
    def out(self, vec_module, luals_output_config) -> str:
        return _render(vec_module, luals_output_config)

    def test_unary_operator_annotated_as_unm(self, out: str) -> None:
        assert "function Vec2:__unm() end" in out

    def test_binary_operator_annotated_as_sub(self, out: str) -> None:
        assert "function Vec2:__sub(s) end" in out

    def test_truncated_arities_become_overload_annotations(self, out: str) -> None:
        assert "---@overload fun(self: Vec2, dx: number, dy: number): geo::Vec2" in out
        assert "---@overload fun(self: Vec2, dx: number): geo::Vec2" in out

    def test_full_arity_stays_the_primary_signature(self, out: str) -> None:
        assert "function Vec2:offset(dx, dy, scale) end" in out

    def test_no_optional_param_syntax_is_used(self, out: str) -> None:
        assert "---@param dy? " not in out

    def test_constructor_truncation_is_annotated(self, out: str) -> None:
        assert "---@overload fun(x: number): Vec2" in out  # constructors return the class name

    def test_free_operator_annotated_without_self_operand(self, out: str) -> None:
        assert "---@param b const Vec2 &" in out
        assert "function Vec2:__add(b) end" in out

    def test_free_operator_is_not_a_module_function(self, out: str) -> None:
        assert "function operator+" not in out

    def test_array_field_is_not_annotated(self, out: str) -> None:
        assert "---@field raw" not in out

    def test_flattened_field_is_annotated(self, out: str) -> None:
        assert "---@field width number" in out


# ---------------------------------------------------------------------------
# pybind11
# ---------------------------------------------------------------------------


class TestPybind11Golden:
    @pytest.fixture(scope="class")
    def out(self, vec_module, pybind11_output_config) -> str:
        return _render(vec_module, pybind11_output_config)

    def test_unary_operator_binds_to_neg(self, out: str) -> None:
        assert '.def("__neg__", py::overload_cast<>(&geo::Vec2::operator-, py::const_))' in out

    def test_binary_operator_binds_to_sub(self, out: str) -> None:
        assert '.def("__sub__", py::overload_cast<double>(&geo::Vec2::operator-, py::const_)' in out

    def test_defaults_stay_native_py_args(self, out: str) -> None:
        assert '.def("offset", &geo::Vec2::offset, py::arg("dx"), py::arg("dy") = 0.0, py::arg("scale") = 1.0)' in out

    def test_no_expansion_lambda_is_emitted(self, out: str) -> None:
        assert "decltype(auto)" not in out

    def test_constructor_is_not_truncated(self, out: str) -> None:
        assert '.def(py::init<double, double>(), py::arg("x"), py::arg("y") = 1.0)' in out
        assert "py::init<double>()" not in out

    def test_free_operator_binds_as_dunder(self, out: str) -> None:
        assert '.def("__add__", &geo::operator+)' in out

    def test_free_operator_is_not_a_module_function(self, out: str) -> None:
        assert 'm.def("operator+"' not in out

    def test_array_field_is_not_bound(self, out: str) -> None:
        assert '"raw"' not in out

    def test_flattened_field_is_bound(self, out: str) -> None:
        assert '.def_readwrite("width", &geo::Vec2::width)' in out


# ---------------------------------------------------------------------------
# pyi
# ---------------------------------------------------------------------------


class TestPyiGolden:
    @pytest.fixture(scope="class")
    def out(self, vec_module) -> str:
        from tsujikiri.configurations import load_output_config
        from tsujikiri.formats import resolve_format_path

        return _render(vec_module, load_output_config(resolve_format_path("pyi")))

    def test_defaults_stay_native_python_defaults(self, out: str) -> None:
        assert "def offset(self, dx: float, dy: float = 0.0, scale: float = 1.0) -> geo::Vec2: ..." in out

    def test_constructor_is_not_truncated(self, out: str) -> None:
        assert "def __init__(self, x: float, y: float = 1.0) -> None: ..." in out

    def test_operators_remain_unmapped(self, out: str) -> None:
        assert "__neg__" not in out
        assert "__add__" not in out

    def test_array_field_is_not_declared(self, out: str) -> None:
        assert "raw:" not in out

    def test_flattened_field_is_declared(self, out: str) -> None:
        assert "width: float" in out
