"""Tests for luals free-function template: deprecated annotation."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.tir import TIRFunction, TIRModule, TIRParameter


@pytest.fixture(scope="module")
def luals_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luals"))


def _gen(module: TIRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _module_with_fn(fn: TIRFunction) -> TIRModule:
    mod = TIRModule(name="test")
    mod.functions = [fn]
    return mod


class TestLuaLSFreeFunctionDeprecated:
    def test_deprecated_emits_at_deprecated_annotation(self, luals_output_config) -> None:
        fn = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="void",
            is_deprecated=True,
            deprecation_message="use newOp instead",
        )
        output = _gen(_module_with_fn(fn), luals_output_config)
        assert "---@deprecated" in output
        assert "use newOp instead" in output

    def test_not_deprecated_no_annotation(self, luals_output_config) -> None:
        fn = TIRFunction(
            name="currentOp",
            qualified_name="currentOp",
            namespace="",
            return_type="void",
            is_deprecated=False,
        )
        output = _gen(_module_with_fn(fn), luals_output_config)
        assert "---@deprecated" not in output

    def test_deprecated_without_message(self, luals_output_config) -> None:
        fn = TIRFunction(
            name="legacyOp",
            qualified_name="legacyOp",
            namespace="",
            return_type="void",
            is_deprecated=True,
        )
        output = _gen(_module_with_fn(fn), luals_output_config)
        assert "---@deprecated" in output

    def test_overloaded_deprecated_emits_annotation(self, luals_output_config) -> None:
        fn1 = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="void",
            is_deprecated=True,
            deprecation_message="use newOp",
            parameters=[TIRParameter(name="x", type_spelling="int")],
        )
        fn2 = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="void",
            is_deprecated=True,
            deprecation_message="use newOp",
            parameters=[TIRParameter(name="x", type_spelling="float")],
        )
        mod = TIRModule(name="test")
        mod.functions = [fn1, fn2]
        output = _gen(mod, luals_output_config)
        assert "---@deprecated" in output
        assert "use newOp" in output
