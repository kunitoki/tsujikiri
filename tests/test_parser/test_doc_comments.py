"""Tests for parser Doxygen/doc-comment extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import SourceConfig
from tsujikiri.ir import IRParameter
from tsujikiri.parser import (
    _apply_param_docs,
    _parse_doc_comment,
    _strip_comment_markers,
    parse_translation_unit,
)

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def doc_module():
    src = SourceConfig(path=str(HERE / "doc_comments.hpp"), parse_args=["-std=c++17"])
    return parse_translation_unit(src, ["mylib"], "doc_comments")


# ---------------------------------------------------------------------------
# End-to-end extraction from a real translation unit
# ---------------------------------------------------------------------------


class TestExtractionFromHeader:
    def _container(self, mod):
        return next(c for c in mod.classes if c.name == "Container")

    def test_class_doc(self, doc_module):
        cls = self._container(doc_module)
        assert cls.doc == "A documented container. More detail about the container."

    def test_constructor_param_doc(self, doc_module):
        cls = self._container(doc_module)
        ctor = cls.constructors[0]
        assert ctor.doc == "Constructs a container."
        assert ctor.parameters[0].doc == "The initial size."

    def test_block_comment_method_and_params(self, doc_module):
        cls = self._container(doc_module)
        method = next(m for m in cls.methods if m.name == "setVolume")
        assert method.doc == "Sets the volume."
        by_name = {p.name: p.doc for p in method.parameters}
        assert by_name == {"volume": "Volume in decibels.", "fadeTime": "Fade time in seconds."}

    def test_method_return_doc(self, doc_module):
        cls = self._container(doc_module)
        method = next(m for m in cls.methods if m.name == "getVolume")
        assert method.doc == "Gets the current volume."
        assert method.return_doc == "The volume in decibels."

    def test_field_doc(self, doc_module):
        cls = self._container(doc_module)
        field = next(f for f in cls.fields if f.name == "gain")
        assert field.doc == "A field holding the gain."

    def test_enum_and_value_doc(self, doc_module):
        enum = next(e for e in doc_module.enums if e.name == "Mode")
        assert enum.doc == "A documented enum."
        first = next(v for v in enum.values if v.name == "First")
        assert first.doc == "The first mode."

    def test_function_doc_and_return(self, doc_module):
        fn = next(f for f in doc_module.functions if f.name == "compute")
        assert fn.doc == "A free function."
        assert fn.return_doc == "The computed result."
        assert fn.parameters[0].doc == "The input value."


# ---------------------------------------------------------------------------
# _strip_comment_markers
# ---------------------------------------------------------------------------


class TestStripCommentMarkers:
    def test_triple_slash(self):
        assert _strip_comment_markers("/// hello") == ["hello"]

    def test_bang_line(self):
        assert _strip_comment_markers("//! hello") == ["hello"]

    def test_plain_double_slash(self):
        assert _strip_comment_markers("// hello") == ["hello"]

    def test_block_with_stars(self):
        raw = "/**\n * line one\n * line two\n */"
        assert _strip_comment_markers(raw) == ["", "line one", "line two", ""]

    def test_block_bang(self):
        assert _strip_comment_markers("/*! hi */") == ["hi"]

    def test_block_plain(self):
        assert _strip_comment_markers("/* hi */") == ["hi"]

    def test_block_without_trailing_marker(self):
        assert _strip_comment_markers("/** hi") == ["hi"]

    def test_line_continuation_without_marker(self):
        assert _strip_comment_markers("/// a\nplain") == ["a", "plain"]


# ---------------------------------------------------------------------------
# _parse_doc_comment
# ---------------------------------------------------------------------------


class TestParseDocComment:
    def test_none(self):
        assert _parse_doc_comment(None) == (None, {}, None)

    def test_description_only(self):
        desc, params, ret = _parse_doc_comment("/// Just a description.")
        assert desc == "Just a description."
        assert params == {}
        assert ret is None

    def test_brief_fallback(self):
        desc, _, _ = _parse_doc_comment("/// @brief The brief text.")
        assert desc == "The brief text."

    def test_description_wins_over_brief(self):
        desc, _, _ = _parse_doc_comment("/// Leading text.\n/// @brief Ignored brief.")
        assert desc == "Leading text."

    def test_param_and_return(self):
        raw = "/// Does it.\n/// @param a The a.\n/// @return The result."
        desc, params, ret = _parse_doc_comment(raw)
        assert desc == "Does it."
        assert params == {"a": "The a."}
        assert ret == "The result."

    def test_backslash_commands(self):
        raw = "/// Desc.\n/// \\param a The a.\n/// \\returns R."
        desc, params, ret = _parse_doc_comment(raw)
        assert params == {"a": "The a."}
        assert ret == "R."

    def test_multiline_param_continuation(self):
        raw = "/// Desc.\n/// @param a first part\n/// second part"
        _, params, _ = _parse_doc_comment(raw)
        assert params == {"a": "first part second part"}

    def test_param_with_brackets(self):
        raw = "/// Desc.\n/// @param[in] a The input."
        _, params, _ = _parse_doc_comment(raw)
        assert params == {"a": "The input."}

    def test_param_without_name_resets_target(self):
        raw = "/// Desc.\n/// @param\n/// stray text"
        desc, params, _ = _parse_doc_comment(raw)
        assert params == {}

    def test_unknown_command_stops_accumulation(self):
        raw = "/// Desc.\n/// @note internal\n/// more note"
        desc, params, ret = _parse_doc_comment(raw)
        assert desc == "Desc."
        assert params == {}
        assert ret is None

    def test_blank_line_in_description(self):
        raw = "/// First.\n///\n/// Second."
        desc, _, _ = _parse_doc_comment(raw)
        assert desc == "First. Second."

    def test_blank_line_after_param_resets(self):
        raw = "/// Desc.\n/// @param a The a.\n///\n/// trailing"
        desc, params, _ = _parse_doc_comment(raw)
        assert params == {"a": "The a."}

    def test_empty_param_desc_dropped(self):
        raw = "/// Desc.\n/// @param a"
        _, params, _ = _parse_doc_comment(raw)
        assert params == {}

    def test_brief_continuation(self):
        raw = "/// @brief first\n/// second"
        desc, _, _ = _parse_doc_comment(raw)
        assert desc == "first second"

    def test_brief_empty_then_continuation(self):
        raw = "/// @brief\n/// only text"
        desc, _, _ = _parse_doc_comment(raw)
        assert desc == "only text"

    def test_return_continuation(self):
        raw = "/// Desc.\n/// @return first\n/// second"
        _, _, ret = _parse_doc_comment(raw)
        assert ret == "first second"

    def test_return_empty_then_continuation(self):
        raw = "/// Desc.\n/// @return\n/// only"
        _, _, ret = _parse_doc_comment(raw)
        assert ret == "only"


# ---------------------------------------------------------------------------
# _apply_param_docs
# ---------------------------------------------------------------------------


class TestApplyParamDocs:
    def test_empty_docs_noop(self):
        params = [IRParameter("a", "int")]
        _apply_param_docs(params, {})
        assert params[0].doc is None

    def test_matches_by_name(self):
        params = [IRParameter("a", "int"), IRParameter("b", "int")]
        _apply_param_docs(params, {"b": "doc b"})
        assert params[0].doc is None
        assert params[1].doc == "doc b"
