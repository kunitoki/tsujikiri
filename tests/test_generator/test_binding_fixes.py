"""Generator tests for defaulted-argument expansion, operator grouping and
free-operator attachment."""

from __future__ import annotations

import io
from dataclasses import replace
from typing import Any, Dict, List, Optional

import pytest

from tsujikiri.configurations import OutputConfig
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


def _param(name: str, type_spelling: str, default: Optional[str] = None) -> TIRParameter:
    return TIRParameter(name=name, type_spelling=type_spelling, default_value=default)


def _method(name: str, params: List[TIRParameter], **kwargs: Any) -> TIRMethod:
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"ns::C::{name}",
        return_type=kwargs.pop("return_type", "void"),
        parameters=params,
        **kwargs,
    )


def _class(**kwargs: Any) -> TIRClass:
    return TIRClass(
        name="C",
        qualified_name="ns::C",
        namespace="ns",
        variable_name="classC",
        **kwargs,
    )


def _module(**kwargs: Any) -> TIRModule:
    return TIRModule(name="m", namespaces=["ns"], **kwargs)


def _ctx(module: TIRModule, config: OutputConfig) -> Dict[str, Any]:
    return Generator(config)._build_ir_context(module)


def _cls_ctx(module: TIRModule, config: OutputConfig, name: str = "C") -> Dict[str, Any]:
    return next(c for c in _ctx(module, config)["classes"] if c["name"] == name)


def _group(cls_ctx: Dict[str, Any], name: str) -> Dict[str, Any]:
    return next(g for g in cls_ctx["method_groups"] if g["name"] == name)


@pytest.fixture
def expanding_config(luabridge3_output_config) -> OutputConfig:
    """luabridge3 with expansion on (its shipped setting)."""
    return replace(luabridge3_output_config)


@pytest.fixture
def plain_config(luabridge3_output_config) -> OutputConfig:
    """Same operator table, expansion off — models pybind11/pyi."""
    return replace(luabridge3_output_config, expand_default_arguments=None)


# ---------------------------------------------------------------------------
# Defaulted-argument expansion
# ---------------------------------------------------------------------------


class TestDefaultArgumentExpansion:
    @staticmethod
    def _one_defaulted_module() -> TIRModule:
        m = _method("scaled", [_param("f", "double"), _param("bias", "double", "0.0")], is_const=True)
        return _module(classes=[_class(methods=[m])])

    def test_expansion_adds_truncated_arity(self, expanding_config) -> None:
        group = _group(_cls_ctx(self._one_defaulted_module(), expanding_config), "scaled")
        assert [len(mth["params"]) for mth in group["methods"]] == [2, 1]

    def test_expansion_is_descending_arity(self, expanding_config) -> None:
        m = _method(
            "f",
            [_param("a", "int"), _param("b", "int", "1"), _param("c", "int", "2")],
        )
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "f")
        assert [len(mth["params"]) for mth in group["methods"]] == [3, 2, 1]

    def test_synthetic_entries_are_flagged(self, expanding_config) -> None:
        group = _group(_cls_ctx(self._one_defaulted_module(), expanding_config), "scaled")
        assert [mth["is_default_expansion"] for mth in group["methods"]] == [False, True]

    def test_synthetic_entry_records_omitted_params(self, expanding_config) -> None:
        group = _group(_cls_ctx(self._one_defaulted_module(), expanding_config), "scaled")
        omitted = group["methods"][1]["omitted_params"]
        assert [(p["name"], p["raw_type"], p["default"]) for p in omitted] == [("bias", "double", "0.0")]

    def test_expansion_flips_single_method_to_overloaded(self, expanding_config) -> None:
        """A previously non-overloaded method now takes the overloaded template path."""
        group = _group(_cls_ctx(self._one_defaulted_module(), expanding_config), "scaled")
        assert group["is_overloaded"] is True

    def test_overload_separators_are_restamped(self, expanding_config) -> None:
        group = _group(_cls_ctx(self._one_defaulted_module(), expanding_config), "scaled")
        assert [mth["overload_separator"] for mth in group["methods"]] == [",", ""]

    def test_overload_indices_are_restamped(self, expanding_config) -> None:
        m = _method("f", [_param("a", "int"), _param("b", "int", "1"), _param("c", "int", "2")])
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "f")
        assert [mth["overload_index"] for mth in group["methods"]] == [0, 1, 2]

    def test_no_expansion_when_flag_is_off(self, plain_config) -> None:
        group = _group(_cls_ctx(self._one_defaulted_module(), plain_config), "scaled")
        assert len(group["methods"]) == 1
        assert group["is_overloaded"] is False

    def test_method_without_defaults_is_untouched(self, expanding_config) -> None:
        m = _method("plain", [_param("a", "int")])
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "plain")
        assert len(group["methods"]) == 1

    def test_leading_default_stops_at_first_non_default(self, expanding_config) -> None:
        """Only the trailing run of defaulted parameters can be dropped."""
        m = _method("f", [_param("a", "int", "1"), _param("b", "int")])
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "f")
        assert len(group["methods"]) == 1

    def test_dedup_skips_colliding_truncation(self, expanding_config) -> None:
        """``void f(int); void f(int, float = 1.0f);`` — the 1-arity form already exists."""
        one = _method("f", [_param("x", "int")], is_overload=True)
        two = _method("f", [_param("x", "int"), _param("y", "float", "1.0f")], is_overload=True)
        group = _group(_cls_ctx(_module(classes=[_class(methods=[one, two])]), expanding_config), "f")
        assert [len(mth["params"]) for mth in group["methods"]] == [1, 2]
        assert all(not mth["is_default_expansion"] for mth in group["methods"])

    def test_dedup_skips_collision_with_another_synthetic(self, expanding_config) -> None:
        """Two overloads whose truncations coincide yield only one synthetic entry."""
        one = _method("f", [_param("x", "int"), _param("y", "float", "1.0f")], is_overload=True)
        two = _method("f", [_param("x", "int"), _param("z", "float", "2.0f")], is_overload=True)
        group = _group(_cls_ctx(_module(classes=[_class(methods=[one, two])]), expanding_config), "f")
        assert sum(1 for mth in group["methods"] if mth["is_default_expansion"]) == 1

    def test_const_qualifier_separates_colliding_signatures(self, expanding_config) -> None:
        """A const/non-const pair with the same arity is not deduplicated away."""
        nc = _method("f", [_param("x", "int")], is_overload=True)
        c = _method("f", [_param("x", "int"), _param("y", "int", "0")], is_const=True, is_overload=True)
        group = _group(_cls_ctx(_module(classes=[_class(methods=[nc, c])]), expanding_config), "f")
        assert [(len(mth["params"]), mth["is_const"]) for mth in group["methods"]] == [
            (1, False),
            (2, True),
            (1, True),
        ]

    def test_expansion_does_not_perturb_overload_kind(self, expanding_config) -> None:
        """Synthetics must not make a real entry look like it has a const partner."""
        nc = _method("get", [_param("i", "int")], is_overload=True)
        c = _method("get", [_param("i", "int"), _param("j", "int", "0")], is_const=True, is_overload=True)
        group = _group(_cls_ctx(_module(classes=[_class(methods=[nc, c])]), expanding_config), "get")
        assert [mth["overload_kind"] for mth in group["methods"]] == ["overload", "overload", "overload"]

    def test_static_method_expansion(self, expanding_config) -> None:
        m = _method("make", [_param("a", "int"), _param("b", "int", "3")], is_static=True)
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "make")
        assert group["is_static"] is True
        assert [len(mth["params"]) for mth in group["methods"]] == [2, 1]

    def test_free_function_expansion(self, expanding_config) -> None:
        fn = TIRFunction(
            name="freeFn",
            qualified_name="ns::freeFn",
            namespace="ns",
            return_type="double",
            parameters=[_param("a", "double"), _param("b", "double", "2.0")],
        )
        ctx = _ctx(_module(functions=[fn]), expanding_config)
        group = ctx["function_groups"][0]
        assert group["is_overloaded"] is True
        assert [len(f["params"]) for f in group["functions"]] == [2, 1]

    def test_constructor_truncation(self, expanding_config) -> None:
        ctor = TIRConstructor(parameters=[_param("w", "double"), _param("h", "double", "1.0")])
        ctors = _cls_ctx(_module(classes=[_class(constructors=[ctor])]), expanding_config)["constructor_group"]
        assert [len(c["params"]) for c in ctors["constructors"]] == [2, 1]

    def test_constructor_group_is_overloaded_after_expansion(self, expanding_config) -> None:
        """luals only renders extra arities when the group reports itself overloaded."""
        ctor = TIRConstructor(parameters=[_param("w", "double"), _param("h", "double", "1.0")])
        ctors = _cls_ctx(_module(classes=[_class(constructors=[ctor])]), expanding_config)["constructor_group"]
        assert ctors["is_overloaded"] is True

    def test_constructor_not_expanded_when_flag_off(self, plain_config) -> None:
        ctor = TIRConstructor(parameters=[_param("w", "double"), _param("h", "double", "1.0")])
        ctors = _cls_ctx(_module(classes=[_class(constructors=[ctor])]), plain_config)["constructor_group"]
        assert len(ctors["constructors"]) == 1
        assert ctors["is_overloaded"] is False


# ---------------------------------------------------------------------------
# Operator-aware grouping
# ---------------------------------------------------------------------------


def _op(name: str, op_type: str, params: List[TIRParameter], **kwargs: Any) -> TIRMethod:
    return _method(name, params, is_operator=True, operator_type=op_type, **kwargs)


class TestOperatorGrouping:
    @staticmethod
    def _unary_and_binary() -> TIRModule:
        unary = _op("operator-", "operator-unary", [], is_const=True, is_overload=True, return_type="ns::C")
        binary = _op(
            "operator-",
            "operator-",
            [_param("s", "double")],
            is_const=True,
            is_overload=True,
            return_type="ns::C",
        )
        return _module(classes=[_class(methods=[unary, binary])])

    def test_unary_and_binary_are_separate_groups(self, expanding_config) -> None:
        groups = _cls_ctx(self._unary_and_binary(), expanding_config)["method_groups"]
        assert [g["methods"][0]["operator_type"] for g in groups] == ["operator-unary", "operator-"]

    def test_each_split_group_holds_one_method(self, expanding_config) -> None:
        groups = _cls_ctx(self._unary_and_binary(), expanding_config)["method_groups"]
        assert [len(g["methods"]) for g in groups] == [1, 1]

    def test_split_groups_map_to_distinct_metamethods(self, expanding_config) -> None:
        groups = _cls_ctx(self._unary_and_binary(), expanding_config)["method_groups"]
        assert [g["methods"][0]["operator_name"] for g in groups] == ["__unm", "__sub"]

    def test_split_group_carries_cpp_overloaded_flag(self, expanding_config) -> None:
        groups = _cls_ctx(self._unary_and_binary(), expanding_config)["method_groups"]
        assert all(g["methods"][0]["is_cpp_overloaded"] for g in groups)

    def test_non_operator_methods_group_unchanged(self, expanding_config) -> None:
        a = _method("add", [_param("x", "int")], is_overload=True)
        b = _method("add", [_param("x", "double")], is_overload=True)
        groups = _cls_ctx(_module(classes=[_class(methods=[a, b])]), expanding_config)["method_groups"]
        assert len(groups) == 1
        assert len(groups[0]["methods"]) == 2

    def test_non_operator_is_cpp_overloaded_is_false_when_unique(self, expanding_config) -> None:
        m = _method("solo", [])
        group = _group(_cls_ctx(_module(classes=[_class(methods=[m])]), expanding_config), "solo")
        assert group["methods"][0]["is_cpp_overloaded"] is False

    def test_static_and_instance_same_name_still_split(self, expanding_config) -> None:
        inst = _method("f", [])
        stat = _method("g", [], is_static=True)
        groups = _cls_ctx(_module(classes=[_class(methods=[inst, stat])]), expanding_config)["method_groups"]
        assert [g["is_static"] for g in groups] == [False, True]

    def test_free_function_operators_split_by_operator_type(self, expanding_config) -> None:
        """Free operators of the same spelling but different arity get separate groups."""
        unary = TIRFunction(
            name="operator+",
            qualified_name="other::operator+",
            namespace="other",
            return_type="other::V",
            parameters=[_param("a", "const V &")],
            is_operator=True,
            operator_type="operator+unary",
            is_overload=True,
        )
        binary = TIRFunction(
            name="operator+",
            qualified_name="other::operator+",
            namespace="other",
            return_type="other::V",
            parameters=[_param("a", "const V &"), _param("b", "const V &")],
            is_operator=True,
            operator_type="operator+",
            is_overload=True,
        )
        # No bound class named V, so neither attaches and both stay module-level.
        groups = _ctx(_module(functions=[unary, binary]), expanding_config)["function_groups"]
        assert len(groups) == 2
        assert all(len(g["functions"]) == 1 for g in groups)

    def test_free_function_operator_carries_cpp_overloaded_flag(self, expanding_config) -> None:
        fn = TIRFunction(
            name="operator+",
            qualified_name="other::operator+",
            namespace="other",
            return_type="other::V",
            parameters=[_param("a", "const V &")],
            is_operator=True,
            operator_type="operator+unary",
            is_overload=True,
        )
        group = _ctx(_module(functions=[fn]), expanding_config)["function_groups"][0]
        assert group["functions"][0]["is_operator"] is True
        assert group["functions"][0]["is_cpp_overloaded"] is True


# ---------------------------------------------------------------------------
# Free-operator attachment
# ---------------------------------------------------------------------------


def _free_op(
    name: str,
    op_type: str,
    params: List[TIRParameter],
    namespace: str = "ns",
    **kwargs: Any,
) -> TIRFunction:
    return TIRFunction(
        name=name,
        qualified_name=f"{namespace}::{name}" if namespace else name,
        namespace=namespace,
        return_type=kwargs.pop("return_type", "ns::C"),
        parameters=params,
        is_operator=True,
        operator_type=op_type,
        **kwargs,
    )


class TestFreeOperatorAttachment:
    @staticmethod
    def _attached_module(param_type: str = "const C &") -> TIRModule:
        fn = _free_op("operator+", "operator+", [_param("a", param_type), _param("b", param_type)])
        return _module(classes=[_class()], functions=[fn])

    def test_attaches_to_first_operand_class(self, expanding_config) -> None:
        groups = _cls_ctx(self._attached_module(), expanding_config)["free_operator_groups"]
        assert [g["operator_name"] for g in groups] == ["__add"]

    def test_attached_function_uses_qualified_free_name(self, expanding_config) -> None:
        groups = _cls_ctx(self._attached_module(), expanding_config)["free_operator_groups"]
        assert groups[0]["functions"][0]["spelling"] == "ns::operator+"

    def test_attached_function_is_removed_from_function_groups(self, expanding_config) -> None:
        assert _ctx(self._attached_module(), expanding_config)["function_groups"] == []

    def test_fully_qualified_operand_spelling_resolves(self, expanding_config) -> None:
        groups = _cls_ctx(self._attached_module("const ns::C &"), expanding_config)["free_operator_groups"]
        assert [g["operator_name"] for g in groups] == ["__add"]

    def test_non_const_operand_spelling_resolves(self, expanding_config) -> None:
        groups = _cls_ctx(self._attached_module("C &"), expanding_config)["free_operator_groups"]
        assert [g["operator_name"] for g in groups] == ["__add"]

    def test_global_namespace_operator_attaches(self, expanding_config) -> None:
        cls = TIRClass(name="G", qualified_name="G", namespace="", variable_name="classG")
        fn = _free_op("operator+", "operator+", [_param("a", "const G &"), _param("b", "const G &")], namespace="")
        ctx = _ctx(_module(classes=[cls], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"][0]["operator_name"] == "__add"
        assert ctx["function_groups"] == []

    def test_unmapped_operator_is_left_in_function_groups(self, expanding_config) -> None:
        """luabridge3 has no ``operator+unary`` mapping — the function stays module-level."""
        fn = _free_op("operator+", "operator+unary", [_param("a", "const C &")])
        ctx = _ctx(_module(classes=[_class()], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"] == []
        assert len(ctx["function_groups"]) == 1

    def test_unknown_operand_class_is_left_in_function_groups(self, expanding_config) -> None:
        fn = _free_op("operator+", "operator+", [_param("a", "const Nope &"), _param("b", "const Nope &")])
        ctx = _ctx(_module(classes=[_class()], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"] == []
        assert len(ctx["function_groups"]) == 1

    def test_ostream_operator_never_attaches(self, expanding_config) -> None:
        """operator<< takes std::ostream& first, so it cannot match a bound class."""
        fn = _free_op(
            "operator<<",
            "operator<<",
            [_param("os", "std::ostream &"), _param("v", "const C &")],
            return_type="std::ostream &",
        )
        ctx = _ctx(_module(classes=[_class()], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"] == []
        assert len(ctx["function_groups"]) == 1

    def test_parameterless_operator_is_skipped(self, expanding_config) -> None:
        fn = _free_op("operator+", "operator+", [])
        ctx = _ctx(_module(classes=[_class()], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"] == []

    def test_non_operator_function_is_never_attached(self, expanding_config) -> None:
        fn = TIRFunction(
            name="combine",
            qualified_name="ns::combine",
            namespace="ns",
            return_type="ns::C",
            parameters=[_param("a", "const C &")],
        )
        ctx = _ctx(_module(classes=[_class()], functions=[fn]), expanding_config)
        assert ctx["classes"][0]["free_operator_groups"] == []
        assert len(ctx["function_groups"]) == 1

    def test_overloaded_free_operators_share_one_group(self, expanding_config) -> None:
        a = _free_op("operator+", "operator+", [_param("a", "const C &"), _param("b", "const C &")], is_overload=True)
        b = _free_op("operator+", "operator+", [_param("a", "const C &"), _param("s", "double")], is_overload=True)
        groups = _cls_ctx(_module(classes=[_class()], functions=[a, b]), expanding_config)["free_operator_groups"]
        assert len(groups) == 1
        assert groups[0]["is_overloaded"] is True
        assert [f["overload_separator"] for f in groups[0]["functions"]] == [",", ""]

    def test_distinct_operators_get_distinct_groups(self, expanding_config) -> None:
        add = _free_op("operator+", "operator+", [_param("a", "const C &"), _param("b", "const C &")])
        mul = _free_op("operator*", "operator*", [_param("a", "const C &"), _param("s", "double")])
        groups = _cls_ctx(_module(classes=[_class()], functions=[add, mul]), expanding_config)["free_operator_groups"]
        assert [g["operator_name"] for g in groups] == ["__add", "__mul"]

    def test_inner_class_operand_matches_only_its_own_qualified_name(self, expanding_config) -> None:
        """A bare ``Inner`` must not false-match an inner class of another scope."""
        inner = TIRClass(
            name="Inner",
            qualified_name="ns::Outer::Inner",
            namespace="ns",
            variable_name="classOuterInner",
        )
        outer = TIRClass(
            name="Outer",
            qualified_name="ns::Outer",
            namespace="ns",
            variable_name="classOuter",
            inner_classes=[inner],
        )
        fn = _free_op(
            "operator+",
            "operator+",
            [_param("a", "const Outer::Inner &"), _param("b", "const Outer::Inner &")],
            return_type="ns::Outer::Inner",
        )
        ctx = _ctx(_module(classes=[outer], functions=[fn]), expanding_config)
        by_name = {c["name"]: c for c in ctx["classes"]}
        assert by_name["Inner"]["free_operator_groups"][0]["operator_name"] == "__add"
        assert by_name["Outer"]["free_operator_groups"] == []


# ---------------------------------------------------------------------------
# Array fields
# ---------------------------------------------------------------------------


class TestArrayFieldSkip:
    def _fields(self, type_spelling: str, config) -> List[str]:
        cls = _class(fields=[TIRField(name="v", type_spelling=type_spelling)])
        return [f["name"] for f in _cls_ctx(_module(classes=[cls]), config)["fields"]]

    def test_sized_array_field_is_skipped(self, expanding_config) -> None:
        assert self._fields("int[2]", expanding_config) == []

    def test_unsized_array_field_is_skipped(self, expanding_config) -> None:
        assert self._fields("const char *[]", expanding_config) == []

    def test_spaced_array_field_is_skipped(self, expanding_config) -> None:
        assert self._fields("int [ 4 ]", expanding_config) == []

    def test_scalar_field_is_kept(self, expanding_config) -> None:
        assert self._fields("int", expanding_config) == ["v"]

    def test_template_field_with_brackets_is_kept(self, expanding_config) -> None:
        assert self._fields("std::array<int, 2>", expanding_config) == ["v"]

    def test_type_override_to_non_array_is_kept(self, expanding_config) -> None:
        cls = _class(fields=[TIRField(name="v", type_spelling="int[2]")])
        cls.fields[0].type_override = "std::array<int, 2>"
        assert [f["name"] for f in _cls_ctx(_module(classes=[cls]), expanding_config)["fields"]] == ["v"]


# ---------------------------------------------------------------------------
# Rendered output smoke checks
# ---------------------------------------------------------------------------


def _render(module: TIRModule, config: OutputConfig) -> str:
    buf = io.StringIO()
    Generator(config).generate(module, buf)
    return buf.getvalue()


class TestRenderedOutput:
    def test_luabridge3_emits_lambda_for_expansion(self, luabridge3_output_config) -> None:
        m = _method("scaled", [_param("f", "double"), _param("bias", "double", "0.0")], is_const=True)
        out = _render(_module(classes=[_class(methods=[m])]), luabridge3_output_config)
        assert "[](ns::C const* self, double f) -> decltype(auto) { return self->scaled(f); }" in out

    def test_luabridge3_lambda_names_unnamed_parameters(self, luabridge3_output_config) -> None:
        m = _method("at", [_param("i", "int"), _param("", "int", "0")])
        out = _render(_module(classes=[_class(methods=[m])]), luabridge3_output_config)
        assert "luabridge::overload<int, int>(&ns::C::at)" in out
        assert "[](ns::C* self, int i) -> decltype(auto) { return self->at(i); }" in out

    def test_luabridge3_zero_arity_lambda_has_no_trailing_comma(self, luabridge3_output_config) -> None:
        m = _method("f", [_param("a", "int", "1")], is_const=True)
        out = _render(_module(classes=[_class(methods=[m])]), luabridge3_output_config)
        assert "[](ns::C const* self) -> decltype(auto) { return self->f(); }" in out
