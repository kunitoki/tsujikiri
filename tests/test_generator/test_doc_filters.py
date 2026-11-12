"""Unit tests for the documentation-rendering Jinja filters."""

from __future__ import annotations

from typing import Any, Dict

from tsujikiri.generator_filters import (
    cpp_docstring,
    docstring_body,
    entity_has_doc,
    lua_doc_comment,
)


def _entity(**kwargs: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {"doc": None, "return_doc": None, "params": []}
    base.update(kwargs)
    return base


class TestEntityHasDoc:
    def test_false_when_empty(self):
        assert entity_has_doc(_entity()) is False

    def test_true_with_doc(self):
        assert entity_has_doc(_entity(doc="hi")) is True

    def test_true_with_return_doc(self):
        assert entity_has_doc(_entity(return_doc="r")) is True

    def test_true_with_param_doc(self):
        assert entity_has_doc(_entity(params=[{"name": "a", "doc": "d"}])) is True

    def test_false_with_param_without_doc(self):
        assert entity_has_doc(_entity(params=[{"name": "a", "doc": None}])) is False

    def test_missing_params_key(self):
        assert entity_has_doc({"doc": None}) is False


class TestDocstringBody:
    def test_description_only_single_line(self):
        assert docstring_body(_entity(doc="Does a thing.")) == "Does a thing."

    def test_empty_returns_empty(self):
        assert docstring_body(_entity()) == ""

    def test_args_section(self):
        out = docstring_body(
            _entity(doc="Sets it.", params=[{"name": "v", "doc": "the value"}]),
            indent="    ",
        )
        assert out == "Sets it.\n\n    Args:\n        v: the value\n    "

    def test_returns_section(self):
        out = docstring_body(_entity(doc="Gets it.", return_doc="the value"), indent="")
        assert out == "Gets it.\n\nReturns:\n    the value\n"

    def test_params_without_doc_ignored(self):
        out = docstring_body(
            _entity(doc="x", params=[{"name": "a", "doc": None}, {"name": "b", "doc": "y"}]),
            indent="",
        )
        assert "a:" not in out
        assert "b: y" in out

    def test_no_head_but_param_doc(self):
        out = docstring_body(_entity(params=[{"name": "a", "doc": "y"}]), indent="")
        assert out.startswith("\n\nArgs:")


class TestCppDocstring:
    def test_description_only(self):
        assert cpp_docstring(_entity(doc="Does a thing.")) == "Does a thing."

    def test_empty(self):
        assert cpp_docstring(_entity()) == ""

    def test_escapes_quotes_and_newlines(self):
        out = cpp_docstring(_entity(doc='He said "hi"'))
        assert out == 'He said \\"hi\\"'

    def test_escapes_backslash(self):
        out = cpp_docstring(_entity(doc="a\\b"))
        assert out == "a\\\\b"

    def test_args_and_returns_escaped_newlines(self):
        out = cpp_docstring(
            _entity(
                doc="Sets it.",
                params=[{"name": "v", "doc": "the value"}],
                return_doc="nothing",
            )
        )
        assert out == "Sets it.\\n\\nArgs:\\n    v: the value\\n\\nReturns:\\n    nothing"

    def test_args_without_head(self):
        out = cpp_docstring(_entity(params=[{"name": "v", "doc": "d"}]))
        assert out == "Args:\\n    v: d"

    def test_returns_without_head(self):
        out = cpp_docstring(_entity(return_doc="d"))
        assert out == "Returns:\\n    d"


class TestLuaDocComment:
    def test_empty_returns_empty(self):
        assert lua_doc_comment(_entity()) == ""

    def test_description_only(self):
        assert lua_doc_comment(_entity(doc="Hi."), indent="  ") == "  // Hi."

    def test_full(self):
        out = lua_doc_comment(
            _entity(
                doc="Sets it.",
                params=[{"name": "v", "doc": "value"}],
                return_doc="nothing",
            ),
            indent="",
        )
        assert out == "// Sets it.\n// @param v value\n// @return nothing"

    def test_params_without_description(self):
        out = lua_doc_comment(_entity(params=[{"name": "v", "doc": "value"}]), indent="")
        assert out == "// @param v value"
