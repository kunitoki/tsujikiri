"""Tests for pybind11 free-function template: return_ownership, allow_thread, keep_alive, deprecated."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.tir import TIRFunction, TIRModule, TIRParameter


@pytest.fixture(scope="module")
def pybind11_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pybind11"))


def _gen(module: TIRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _module_with_fn(fn: TIRFunction) -> TIRModule:
    mod = TIRModule(name="test")
    mod.functions = [fn]
    return mod


class TestFreeFunctionReturnOwnership:
    def test_return_ownership_cpp_emits_reference_internal(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="getRef",
            qualified_name="getRef",
            namespace="",
            return_type="MyClass &",
            return_ownership="cpp",
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "return_value_policy::reference_internal" in output

    def test_return_ownership_script_emits_take_ownership(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="makeObj",
            qualified_name="makeObj",
            namespace="",
            return_type="MyClass *",
            return_ownership="script",
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "return_value_policy::take_ownership" in output

    def test_no_return_ownership_emits_no_policy(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="doSomething",
            qualified_name="doSomething",
            namespace="",
            return_type="void",
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "return_value_policy" not in output


class TestFreeFunctionAllowThread:
    def test_allow_thread_emits_gil_release(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="longOp",
            qualified_name="longOp",
            namespace="",
            return_type="void",
            allow_thread=True,
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "py::call_guard<py::gil_scoped_release>()" in output

    def test_no_allow_thread_no_gil_release(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="quickOp",
            qualified_name="quickOp",
            namespace="",
            return_type="void",
            allow_thread=False,
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "gil_scoped_release" not in output


class TestFreeFunctionReturnKeepAlive:
    def test_return_keep_alive_emits_keep_alive(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="makeChild",
            qualified_name="makeChild",
            namespace="",
            return_type="Child *",
            return_keep_alive=True,
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "keep_alive" in output

    def test_no_return_keep_alive_no_keep_alive(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="getVal",
            qualified_name="getVal",
            namespace="",
            return_type="int",
            return_keep_alive=False,
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "keep_alive" not in output


class TestFreeFunctionDeprecated:
    def test_deprecated_emits_deprecated_annotation(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="void",
            is_deprecated=True,
            deprecation_message="use newOp instead",
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "deprecated" in output.lower()
        assert "use newOp instead" in output

    def test_not_deprecated_no_annotation(self, pybind11_output_config) -> None:
        fn = TIRFunction(
            name="currentOp",
            qualified_name="currentOp",
            namespace="",
            return_type="void",
            is_deprecated=False,
        )
        output = _gen(_module_with_fn(fn), pybind11_output_config)
        assert "deprecated" not in output.lower()


class TestFreeFunctionOverloadedReturnOwnership:
    def test_overloaded_fn_return_ownership_cpp(self, pybind11_output_config) -> None:
        fn1 = TIRFunction(
            name="getRef",
            qualified_name="getRef",
            namespace="",
            return_type="MyClass &",
            return_ownership="cpp",
            parameters=[TIRParameter(name="idx", type_spelling="int")],
        )
        fn2 = TIRFunction(
            name="getRef",
            qualified_name="getRef",
            namespace="",
            return_type="MyClass &",
            return_ownership="cpp",
            parameters=[TIRParameter(name="key", type_spelling="const char *")],
        )
        mod = TIRModule(name="test")
        mod.functions = [fn1, fn2]
        output = _gen(mod, pybind11_output_config)
        assert "return_value_policy::reference_internal" in output

    def test_overloaded_fn_allow_thread(self, pybind11_output_config) -> None:
        fn1 = TIRFunction(
            name="longOp",
            qualified_name="longOp",
            namespace="",
            return_type="void",
            allow_thread=True,
            parameters=[TIRParameter(name="x", type_spelling="int")],
        )
        fn2 = TIRFunction(
            name="longOp",
            qualified_name="longOp",
            namespace="",
            return_type="void",
            allow_thread=True,
            parameters=[TIRParameter(name="x", type_spelling="float")],
        )
        mod = TIRModule(name="test")
        mod.functions = [fn1, fn2]
        output = _gen(mod, pybind11_output_config)
        assert "gil_scoped_release" in output
