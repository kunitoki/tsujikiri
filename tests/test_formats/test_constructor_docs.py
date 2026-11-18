"""Constructor documentation (doc, @param, @return) across output formats."""

from __future__ import annotations

import io
from typing import List, Optional

import pytest

from tsujikiri.configurations import OutputConfig, load_output_config
from tsujikiri.formats import resolve_format_path
from tsujikiri.generator import Generator
from tsujikiri.tir import TIRClass, TIRConstructor, TIRModule, TIRParameter


def _config(name: str) -> OutputConfig:
    return load_output_config(resolve_format_path(name))


def _ctor(params: List[TIRParameter], doc: Optional[str] = None, return_doc: Optional[str] = None) -> TIRConstructor:
    return TIRConstructor(parameters=params, doc=doc, return_doc=return_doc)


def _render(fmt: str, ctors: List[TIRConstructor], force_abstract: bool = False) -> str:
    cls = TIRClass(
        name="Foo",
        qualified_name="Foo",
        namespace="",
        variable_name="classFoo",
        constructors=ctors,
        force_abstract=force_abstract,
    )
    module = TIRModule(name="mymod", classes=[cls], class_by_name={"Foo": cls})
    buf = io.StringIO()
    Generator(_config(fmt)).generate(module, buf)
    return buf.getvalue()


def _documented_single() -> List[TIRConstructor]:
    return [
        _ctor(
            [TIRParameter("size", "int", doc="The size."), TIRParameter("flag", "bool")],
            doc="Builds a Foo.",
            return_doc="A new Foo.",
        )
    ]


# ---------------------------------------------------------------------------
# LuaLS
# ---------------------------------------------------------------------------


class TestLuaLSConstructorDocs:
    def test_single_constructor_doc_params_and_return(self) -> None:
        out = _render("luals", _documented_single())
        assert (
            "---Builds a Foo.\n"
            "---@param size integer The size.\n"
            "---@param flag boolean\n"
            "---@return Foo # A new Foo.\n"
            "function Foo.new(size, flag) end\n"
        ) in out

    def test_single_constructor_without_docs_unchanged(self) -> None:
        out = _render("luals", [_ctor([TIRParameter("size", "int")])])
        assert "\n---@param size integer\n---@return Foo\nfunction Foo.new(size) end\n" in out
        assert "# " not in out

    def test_overloads_documented_only_on_first_use_compact_form(self) -> None:
        out = _render(
            "luals",
            [
                _ctor([TIRParameter("size", "int", doc="The size.")], doc="Builds a Foo.", return_doc="A new Foo."),
                _ctor([TIRParameter("scale", "float")]),
            ],
        )
        assert (
            "---Builds a Foo.\n"
            "---@param size integer The size.\n"
            "---@return Foo # A new Foo.\n"
            "---@overload fun(scale: number): Foo\n"
            "function Foo.new(size) end\n"
        ) in out
        assert "duplicate-set-field" not in out

    def test_overloads_without_docs_use_compact_form(self) -> None:
        out = _render("luals", [_ctor([]), _ctor([TIRParameter("scale", "float")])])
        assert "---@return Foo\n---@overload fun(scale: number): Foo\nfunction Foo.new() end\n" in out
        assert out.count("function Foo.new(") == 1

    @pytest.mark.parametrize(
        "second",
        [
            _ctor([TIRParameter("scale", "float")], doc="Scaled."),
            _ctor([TIRParameter("scale", "float", doc="The scale.")]),
            _ctor([TIRParameter("scale", "float")], return_doc="Scaled Foo."),
        ],
    )
    def test_documented_later_overload_expands_each_definition(self, second: TIRConstructor) -> None:
        out = _render("luals", [_ctor([]), second])
        assert out.count("function Foo.new(") == 2
        assert "---@overload" not in out
        assert "---@return Foo\nfunction Foo.new() end\n\n" in out
        assert "---@diagnostic disable-next-line: duplicate-set-field\nfunction Foo.new(scale) end" in out

    def test_expanded_overloads_render_all_docs(self) -> None:
        out = _render(
            "luals",
            [
                _ctor([TIRParameter("size", "int", doc="The size.")], doc="Sized.", return_doc="Sized Foo."),
                _ctor([TIRParameter("scale", "float", doc="The scale.")], doc="Scaled.", return_doc="Scaled Foo."),
                _ctor([TIRParameter("other", "Foo")]),
            ],
        )
        assert (
            "---Sized.\n"
            "---@param size integer The size.\n"
            "---@return Foo # Sized Foo.\n"
            "function Foo.new(size) end\n"
            "\n"
            "---Scaled.\n"
            "---@param scale number The scale.\n"
            "---@return Foo # Scaled Foo.\n"
            "---@diagnostic disable-next-line: duplicate-set-field\n"
            "function Foo.new(scale) end\n"
            "\n"
            "---@param other Foo\n"
            "---@return Foo\n"
            "---@diagnostic disable-next-line: duplicate-set-field\n"
            "function Foo.new(other) end\n"
        ) in out

    def test_abstract_class_has_no_constructor(self) -> None:
        out = _render("luals", _documented_single(), force_abstract=True)
        assert "Foo.new" not in out
        assert "Builds a Foo." not in out


# ---------------------------------------------------------------------------
# Luau
# ---------------------------------------------------------------------------


class TestLuauConstructorDocs:
    def test_single_constructor_docs(self) -> None:
        out = _render("luau", _documented_single())
        assert (
            "declare Foo: {\n"
            "    --- Builds a Foo.\n"
            "    --- @param size The size.\n"
            "    --- @return A new Foo.\n"
            "    new: ((size: number, flag: boolean) -> Foo),\n"
        ) in out
        assert "--- new(" not in out

    def test_overloaded_docs_get_signature_headers(self) -> None:
        out = _render(
            "luau",
            [
                _ctor([TIRParameter("size", "int")], doc="Sized."),
                _ctor([]),
                _ctor([TIRParameter("scale", "float", doc="The scale.")]),
                _ctor([TIRParameter("other", "Foo")], return_doc="A copy."),
            ],
        )
        assert (
            "declare Foo: {\n"
            "    --- new(size: number)\n"
            "    --- Sized.\n"
            "    --- new(scale: number)\n"
            "    --- @param scale The scale.\n"
            "    --- new(other: Foo)\n"
            "    --- @return A copy.\n"
            "    new: ((size: number) -> Foo) & (() -> Foo) & ((scale: number) -> Foo) & ((other: Foo) -> Foo),\n"
        ) in out
        assert "--- new()" not in out

    def test_undocumented_constructors_unchanged(self) -> None:
        out = _render("luau", [_ctor([TIRParameter("v", "int")])])
        assert "declare Foo: {\n    new: ((v: number) -> Foo),\n" in out
        assert "    ---" not in out

    def test_abstract_class_has_no_constructor_docs(self) -> None:
        out = _render("luau", _documented_single(), force_abstract=True)
        assert "Builds a Foo." not in out


# ---------------------------------------------------------------------------
# Python formats
# ---------------------------------------------------------------------------


class TestPythonConstructorReturnDoc:
    def test_pyi_returns_section(self) -> None:
        out = _render("pyi", _documented_single())
        assert "Args:\n            size: The size.\n\n        Returns:\n            A new Foo.\n" in out

    def test_pybind11_returns_section(self) -> None:
        out = _render("pybind11", _documented_single())
        assert '"Builds a Foo.\\n\\nArgs:\\n    size: The size.\\n\\nReturns:\\n    A new Foo."' in out

    def test_pybind11_return_doc_only(self) -> None:
        out = _render("pybind11", [_ctor([], return_doc="A new Foo.")])
        assert '"Returns:\\n    A new Foo."' in out
