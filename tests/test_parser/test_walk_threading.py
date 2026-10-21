"""Tests for the parser's single-walk paths: pre-collected children and tokens.

The walk reads each cursor's children and tokens once and threads them to the
helpers.  Each helper must give the same answer whether it receives the
pre-collected data or fetches it itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest
from clang.cindex import CursorKind

import tsujikiri.parser as parser_mod
from tsujikiri.configurations import SourceConfig
from tsujikiri.ir import IRModule
from tsujikiri.parser import (
    _SOURCE_CACHE,
    _get_attributes,
    _is_deleted,
    _is_explicit,
    _iter_scope_decls,
    _parse_parameters,
    _split_children,
    parse_translation_unit_ir,
)

HEADER = """\
#pragma once
namespace walk {

class [[clang::annotate("cls::attr")]] Widget {
public:
    [[clang::annotate("ctor::attr")]]
    explicit Widget(int size, const char* name = "w");
    Widget(const Widget&) = delete;
    Widget(double scale);

    [[clang::annotate("method::attr")]]
    int resize(int width, int height = 2);

    [[clang::annotate("")]]
    void emptyAnnotate(int x);

    void plain(float f);

    enum [[clang::annotate("nested_enum::attr")]] Mode { Fast, Slow [[clang::annotate("value::attr")]] };
};

enum class [[clang::annotate("enum::attr")]] Level { Low, High };

[[clang::annotate("fn::attr")]]
int compute(int a, double b = 1.5);

} // namespace walk
"""


@pytest.fixture
def walk_module(tmp_path: Path) -> IRModule:
    header = tmp_path / "walk.hpp"
    header.write_text(HEADER, encoding="utf-8")
    return parse_translation_unit_ir(SourceConfig(path=str(header), parse_args=["-std=c++17"]), ["walk"], "walk")


def _tok(spelling: str) -> MagicMock:
    tok = MagicMock()
    tok.spelling = spelling
    return tok


def _child(kind: CursorKind, spelling: str = "") -> MagicMock:
    child = MagicMock()
    child.kind = kind
    child.spelling = spelling
    return child


def _no_walk_cursor() -> MagicMock:
    """A cursor whose children and tokens must not be fetched."""
    cursor = MagicMock()
    cursor.get_children.side_effect = AssertionError("children walked again")
    cursor.get_tokens.side_effect = AssertionError("tokens fetched again")
    return cursor


def _source_cursor(tmp_path: Path, children: List[MagicMock]) -> MagicMock:
    f = tmp_path / "src.hpp"
    f.write_text("void f();\n", encoding="utf-8")
    _SOURCE_CACHE.pop(str(f), None)
    cursor = MagicMock()
    cursor.location.file.name = str(f)
    cursor.extent.start.line = 1
    cursor.extent.start.column = 1
    cursor.extent.end.line = 1
    cursor.extent.end.column = 1
    cursor.get_children.return_value = children
    return cursor


# ---------------------------------------------------------------------------
# End-to-end: annotations and parameters on every function-like cursor
# ---------------------------------------------------------------------------


class TestWalkIR:
    def _widget(self, module: IRModule):
        return next(c for c in module.classes if c.name == "Widget")

    def test_class_annotate(self, walk_module: IRModule) -> None:
        assert self._widget(walk_module).attributes == ["cls::attr"]

    def test_method_annotate_and_params(self, walk_module: IRModule) -> None:
        resize = next(m for m in self._widget(walk_module).methods if m.name == "resize")
        assert resize.attributes == ["method::attr"]
        assert [(p.name, p.type_spelling, p.default_value) for p in resize.parameters] == [
            ("width", "int", None),
            ("height", "int", "2"),
        ]

    def test_empty_annotate_is_dropped(self, walk_module: IRModule) -> None:
        method = next(m for m in self._widget(walk_module).methods if m.name == "emptyAnnotate")
        assert method.attributes == []
        assert [p.name for p in method.parameters] == ["x"]

    def test_method_without_annotate(self, walk_module: IRModule) -> None:
        plain = next(m for m in self._widget(walk_module).methods if m.name == "plain")
        assert plain.attributes == []
        assert [p.type_spelling for p in plain.parameters] == ["float"]

    def test_constructors_explicit_deleted_and_annotated(self, walk_module: IRModule) -> None:
        widget = self._widget(walk_module)
        assert widget.has_deleted_copy_constructor
        # The deleted copy constructor is not bound.
        assert len(widget.constructors) == 2
        first, second = widget.constructors
        assert first.is_explicit and not second.is_explicit
        assert first.attributes == ["ctor::attr"]
        assert second.attributes == []
        assert [(p.name, p.type_spelling, p.default_value) for p in first.parameters] == [
            ("size", "int", None),
            ("name", "const char *", '"w"'),
        ]
        assert [p.type_spelling for p in second.parameters] == ["double"]

    def test_nested_enum_and_value_annotate(self, walk_module: IRModule) -> None:
        mode = self._widget(walk_module).enums[0]
        assert mode.attributes == ["nested_enum::attr"]
        assert [(v.name, v.attributes) for v in mode.values] == [("Fast", []), ("Slow", ["value::attr"])]

    def test_top_level_enum_annotate(self, walk_module: IRModule) -> None:
        level = next(e for e in walk_module.enums if e.name == "Level")
        assert level.attributes == ["enum::attr"]
        assert level.is_scoped
        assert [v.name for v in level.values] == ["Low", "High"]

    def test_free_function_annotate_and_params(self, walk_module: IRModule) -> None:
        fn = next(f for f in walk_module.functions if f.name == "compute")
        assert fn.attributes == ["fn::attr"]
        assert [(p.name, p.type_spelling, p.default_value) for p in fn.parameters] == [
            ("a", "int", None),
            ("b", "double", "1.5"),
        ]


# ---------------------------------------------------------------------------
# Token threading
# ---------------------------------------------------------------------------


class TestIsDeletedTokens:
    def test_threaded_tokens_are_used(self) -> None:
        assert _is_deleted(_no_walk_cursor(), tokens=[_tok("X"), _tok("="), _tok("delete")])

    def test_threaded_tokens_without_delete(self) -> None:
        assert not _is_deleted(_no_walk_cursor(), tokens=[_tok("X"), _tok("="), _tok("default")])

    def test_trailing_equals_is_not_deleted(self) -> None:
        assert not _is_deleted(_no_walk_cursor(), tokens=[_tok("X"), _tok("=")])

    def test_empty_threaded_tokens(self) -> None:
        assert not _is_deleted(_no_walk_cursor(), tokens=[])

    def test_fetches_tokens_when_not_given(self) -> None:
        cursor = MagicMock()
        cursor.get_tokens.return_value = iter([_tok("="), _tok("delete")])
        assert _is_deleted(cursor)
        cursor.get_tokens.assert_called_once_with()


class TestIsExplicitTokens:
    def test_threaded_tokens_are_used(self) -> None:
        assert _is_explicit(_no_walk_cursor(), tokens=[_tok("explicit"), _tok("X")])

    def test_threaded_tokens_without_explicit(self) -> None:
        assert not _is_explicit(_no_walk_cursor(), tokens=[_tok("X"), _tok("(")])

    def test_empty_threaded_tokens(self) -> None:
        assert not _is_explicit(_no_walk_cursor(), tokens=[])

    def test_fetches_tokens_when_not_given(self) -> None:
        cursor = MagicMock()
        cursor.get_tokens.return_value = iter([_tok("explicit")])
        assert _is_explicit(cursor)
        cursor.get_tokens.assert_called_once_with()


# ---------------------------------------------------------------------------
# Children threading
# ---------------------------------------------------------------------------


class TestSplitChildren:
    def test_splits_params_and_annotations_in_order(self) -> None:
        p1 = _child(CursorKind.PARM_DECL, "a")
        a1 = _child(CursorKind.ANNOTATE_ATTR, "x")
        other = _child(CursorKind.TYPE_REF)
        p2 = _child(CursorKind.PARM_DECL, "b")
        a2 = _child(CursorKind.ANNOTATE_ATTR, "y")
        cursor = MagicMock()
        cursor.get_children.return_value = [p1, a1, other, p2, a2]
        assert _split_children(cursor) == ([p1, p2], [a1, a2])

    def test_no_children(self) -> None:
        cursor = MagicMock()
        cursor.get_children.return_value = []
        assert _split_children(cursor) == ([], [])


class TestGetAttributesAnnotateAttrs:
    def test_threaded_annotations_skip_the_walk(self, tmp_path: Path) -> None:
        cursor = _source_cursor(tmp_path, [])
        cursor.get_children.side_effect = AssertionError("children walked again")
        attrs = [_child(CursorKind.ANNOTATE_ATTR, "a::b"), _child(CursorKind.ANNOTATE_ATTR, "")]
        assert _get_attributes(cursor, annotate_attrs=attrs) == ["a::b"]

    def test_empty_threaded_annotations(self, tmp_path: Path) -> None:
        cursor = _source_cursor(tmp_path, [])
        cursor.get_children.side_effect = AssertionError("children walked again")
        assert _get_attributes(cursor, annotate_attrs=[]) == []

    def test_walks_and_filters_when_not_given(self, tmp_path: Path) -> None:
        children = [
            _child(CursorKind.PARM_DECL, "p"),
            _child(CursorKind.ANNOTATE_ATTR, "keep"),
            _child(CursorKind.TYPE_REF, "ignored"),
        ]
        cursor = _source_cursor(tmp_path, children)
        assert _get_attributes(cursor) == ["keep"]
        cursor.get_children.assert_called_once_with()

    def test_threaded_and_walked_agree(self, tmp_path: Path) -> None:
        children = [_child(CursorKind.ANNOTATE_ATTR, "one"), _child(CursorKind.PARM_DECL, "p")]
        cursor = _source_cursor(tmp_path, children)
        walked = _get_attributes(cursor)
        threaded = _get_attributes(cursor, annotate_attrs=[children[0]])
        assert walked == threaded == ["one"]

    def test_no_file_ignores_threaded_annotations(self) -> None:
        cursor = MagicMock()
        cursor.location.file = None
        assert _get_attributes(cursor, annotate_attrs=[_child(CursorKind.ANNOTATE_ATTR, "x")]) == []


class TestParseParametersParams:
    def test_threaded_params_skip_the_walk(self) -> None:
        cursor = _no_walk_cursor()
        assert _parse_parameters(cursor, params=[]) == []

    def test_walks_and_filters_when_not_given(self) -> None:
        param = _child(CursorKind.PARM_DECL, "x")
        param.get_tokens.return_value = iter([_tok("int"), _tok("x")])
        param.type.spelling = "int"
        cursor = MagicMock()
        cursor.get_children.return_value = [_child(CursorKind.ANNOTATE_ATTR, "a"), param]
        params = _parse_parameters(cursor)
        assert [(p.name, p.type_spelling, p.default_value) for p in params] == [("x", "int", None)]

    def test_threaded_params_are_used(self) -> None:
        param = _child(CursorKind.PARM_DECL, "y")
        param.get_tokens.return_value = iter([_tok("double"), _tok("y"), _tok("="), _tok("2.0")])
        param.type.spelling = "double"
        params = _parse_parameters(_no_walk_cursor(), params=[param])
        assert [(p.name, p.type_spelling, p.default_value) for p in params] == [("y", "double", "2.0")]


class TestIterScopeDeclsKinds:
    def test_yields_kind_with_each_declaration(self) -> None:
        cls = _child(CursorKind.CLASS_DECL, "C")
        fn = _child(CursorKind.FUNCTION_DECL, "f")
        other = _child(CursorKind.VAR_DECL, "v")
        decls = list(_iter_scope_decls([cls, other, fn], []))
        assert decls == [(cls, CursorKind.CLASS_DECL, ""), (fn, CursorKind.FUNCTION_DECL, "")]

    def test_namespace_path_is_carried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(parser_mod, "_is_inline_namespace", lambda cursor: False)
        enum = _child(CursorKind.ENUM_DECL, "E")
        ns = _child(CursorKind.NAMESPACE, "outer")
        ns.get_children.return_value = [enum]
        decls = list(_iter_scope_decls([ns], ["outer"]))
        assert decls == [(enum, CursorKind.ENUM_DECL, "outer")]
