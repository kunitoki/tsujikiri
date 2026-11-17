"""Tests for generic (placeholder-based) type mappings."""

from __future__ import annotations

import re
from typing import Dict

import pytest

from tsujikiri.configurations import OutputConfig
from tsujikiri.generator import Generator
from tsujikiri.type_patterns import (
    compile_type_pattern,
    compile_type_patterns,
    is_generic_key,
    split_top_level,
)
from tsujikiri.typesystem import PrimitiveTypeEntry, TypesystemConfig


def _gen(mappings: Dict[str, str], typesystem: TypesystemConfig | None = None) -> Generator:
    return Generator(OutputConfig(format_name="test", type_mappings=mappings, template=""), typesystem=typesystem)


def _identity(spelling: str) -> str:
    return spelling


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("std::optional<{T}>", True),
            ("std::variant<{T...}>", True),
            ("std::string", False),
            ("{ [x]: y }", False),
            ("{}", False),
        ],
    )
    def test_is_generic_key(self, key: str, expected: bool) -> None:
        assert is_generic_key(key) is expected

    def test_split_top_level_respects_nesting(self) -> None:
        assert split_top_level("int, std::map<a, b>, f(x, y), arr[1, 2], {p, q}") == [
            "int",
            "std::map<a, b>",
            "f(x, y)",
            "arr[1, 2]",
            "{p, q}",
        ]

    def test_split_top_level_single_and_empty_pieces(self) -> None:
        assert split_top_level(" int ") == ["int"]
        assert split_top_level("a,,b") == ["a", "", "b"]


# ---------------------------------------------------------------------------
# Compilation errors and ordering
# ---------------------------------------------------------------------------


class TestCompile:
    @pytest.mark.parametrize(
        ("key", "value", "message"),
        [
            ("x<{A}{B}>", "y", "placeholders must be separated by literal text"),
            ("x<{A}, {A}>", "y", "placeholder '{A}' is used more than once"),
            ("x<{A...}, {B...}>", "y", "only one variadic placeholder is allowed"),
            ("{T}", "{T}", "needs literal text besides placeholders"),
            ("{A} {B...}", "{A}", "needs literal text besides placeholders"),
            ("x<{T}>", "{U}", "value placeholder '{U}' does not appear in the key"),
            ("x<{T}>", "{T...|}", "'{T...}' used in the value but '{T}' is not variadic"),
            ("x<{T}>", "{T...}", "'{T...}' used in the value but '{T}' is not variadic"),
        ],
    )
    def test_malformed_patterns_raise(self, key: str, value: str, message: str) -> None:
        with pytest.raises(ValueError, match=re.escape(message)):
            compile_type_pattern(key, value)

    def test_fixed_after_variadic_is_allowed(self) -> None:
        pattern = compile_type_pattern("f<{Args...}; {R}>", "{R}")
        assert pattern.match("f<int, float; bool>") == {"Args": ["int", "float"], "R": "bool"}

    def test_exact_keys_are_skipped(self) -> None:
        assert compile_type_patterns({"int": "integer", "std::string": "string"}) == []

    def test_compile_errors_propagate(self) -> None:
        with pytest.raises(ValueError):
            compile_type_patterns({"x<{T}>": "{U}"})

    def test_ordering_longest_literal_then_declaration(self) -> None:
        patterns = compile_type_patterns(
            {
                "a<{T}>": "1",
                "std::vector<{T}>": "2",
                "b<{T}>": "3",
                "std::vector<std::vector<{T}>>": "4",
            }
        )
        assert [p.key for p in patterns] == [
            "std::vector<std::vector<{T}>>",
            "std::vector<{T}>",
            "a<{T}>",
            "b<{T}>",
        ]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


class TestMatch:
    def test_single_placeholder(self) -> None:
        assert compile_type_pattern("std::optional<{T}>", "{T}?").match("std::optional<int>") == {"T": "int"}

    def test_nested_capture_kept_whole(self) -> None:
        pattern = compile_type_pattern("std::optional<{T}>", "{T}?")
        assert pattern.match("std::optional<std::map<int, std::vector<float>>>") == {
            "T": "std::map<int, std::vector<float>>"
        }

    def test_whitespace_tolerance(self) -> None:
        pattern = compile_type_pattern("std::map<{K}, {V}>", "x")
        assert pattern.match("  std::map< int ,float >  ") == {"K": "int", "V": "float"}
        assert pattern.match("std::map<int,float>") == {"K": "int", "V": "float"}

    def test_comma_inside_capture_backtracks_to_balanced_split(self) -> None:
        pattern = compile_type_pattern("std::map<{K}, {V}>", "x")
        assert pattern.match("std::map<std::pair<int, int>, float>") == {"K": "std::pair<int, int>", "V": "float"}

    def test_fixed_placeholder_rejects_multiple_arguments(self) -> None:
        assert compile_type_pattern("std::optional<{T}>", "x").match("std::optional<int, float>") is None

    def test_variadic_captures_list(self) -> None:
        pattern = compile_type_pattern("std::variant<{T...}>", "x")
        assert pattern.match("std::variant<int, std::pair<a, b>, float>") == {"T": ["int", "std::pair<a, b>", "float"]}
        assert pattern.match("std::variant<int>") == {"T": ["int"]}

    def test_empty_captures_rejected(self) -> None:
        assert compile_type_pattern("std::optional<{T}>", "x").match("std::optional<>") is None
        assert compile_type_pattern("std::variant<{T...}>", "x").match("std::variant<int, , float>") is None

    def test_unbalanced_capture_rejected(self) -> None:
        assert compile_type_pattern("f<{T}>", "x").match("f<a>>") is None
        assert compile_type_pattern("g<{T}", "x").match("g<a(") is None

    def test_leading_placeholder(self) -> None:
        pattern = compile_type_pattern("{T} *", "{T}?")
        assert pattern.match("Foo *") == {"T": "Foo"}
        assert pattern.match("Foo") is None

    def test_prefix_and_suffix_must_match_fully(self) -> None:
        pattern = compile_type_pattern("vector<{T}>", "x")
        assert pattern.match("std::vector<int>") is None
        assert pattern.match("vector<int> &") is None
        assert pattern.match("list<int>") is None

    def test_missing_following_literal(self) -> None:
        assert compile_type_pattern("f<{A}; {B}>", "x").match("f<int, float>") is None

    def test_backtracking_failure_after_successful_bind(self) -> None:
        # The first "," binds A but the remainder can't match; every later "," fails too.
        assert compile_type_pattern("p<{A}, {B}>!", "x").match("p<a, b>?") is None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRender:
    def test_default_separator(self) -> None:
        pattern = compile_type_pattern("std::tuple<{T...}>", "[{T...}]")
        assert pattern.render({"T": ["a", "b"]}, str.upper) == "[A, B]"

    def test_single_variadic_item_has_no_separator(self) -> None:
        pattern = compile_type_pattern("std::tuple<{T...}>", "[{T...}]")
        assert pattern.render({"T": ["a"]}, _identity) == "[a]"

    def test_custom_separator(self) -> None:
        pattern = compile_type_pattern("std::variant<{T...}>", "{T... | }")
        assert pattern.render({"T": ["a", "b", "c"]}, _identity) == "a | b | c"

    def test_variadic_without_dots_uses_default_separator(self) -> None:
        pattern = compile_type_pattern("std::variant<{T...}>", "({T})")
        assert pattern.render({"T": ["a", "b"]}, _identity) == "(a, b)"

    def test_lua_braces_in_value_are_literal(self) -> None:
        pattern = compile_type_pattern("std::map<{K}, {V}>", "{ [{K}]: {V} }")
        assert pattern.render({"K": "a", "V": "b"}, _identity) == "{ [a]: b }"

    def test_repeated_value_placeholder(self) -> None:
        pattern = compile_type_pattern("std::pair<{T}, {U}>", "{T}|{T}|{U}")
        assert pattern.render({"T": "a", "U": "b"}, _identity) == "a|a|b"


# ---------------------------------------------------------------------------
# Generator._map_type integration
# ---------------------------------------------------------------------------


class TestMapTypeGeneric:
    def test_recursive_mapping(self) -> None:
        gen = _gen(
            {
                "int": "integer",
                "std::string": "string",
                "std::optional<{T}>": "{T}?",
                "std::vector<{T}>": "{T}[]",
                "std::map<{K}, {V}>": "table<{K}, {V}>",
                "std::variant<{T...}>": "{T...|}",
            }
        )
        assert gen._map_type("std::optional<int>") == "integer?"
        assert gen._map_type("std::optional<std::vector<std::string>>") == "string[]?"
        assert gen._map_type("std::map<std::string, std::optional<int>>") == "table<string, integer?>"
        assert gen._map_type("std::variant<int, std::string, double>") == "integer|string|double"

    def test_const_ref_wrapped_generic(self) -> None:
        gen = _gen({"int": "integer", "std::optional<{T}>": "{T}?"})
        assert gen._map_type("const std::optional<int> &") == "integer?"
        assert gen._map_type("std::optional<int> &&") == "integer?"

    def test_capture_const_ref_is_mapped(self) -> None:
        gen = _gen({"std::string": "string", "std::reference_wrapper<{T}>": "{T}"})
        assert gen._map_type("std::reference_wrapper<const std::string &>") == "string"

    def test_pointer_generic_requires_pointer_pattern(self) -> None:
        gen = _gen({"Foo": "Foo", "std::optional<{T}>": "{T}?", "{T} *": "{T}?"})
        assert gen._map_type("std::optional<int> *") == "int??"
        assert gen._map_type("Foo *") == "Foo?"

    def test_exact_entry_beats_pattern(self) -> None:
        gen = _gen({"std::optional<{T}>": "{T}?", "std::optional<bool>": "boolean|nil"})
        assert gen._map_type("std::optional<bool>") == "boolean|nil"
        assert gen._map_type("const std::optional<bool> &") == "boolean|nil"

    def test_more_specific_pattern_wins_regardless_of_order(self) -> None:
        gen = _gen({"std::vector<{T}>": "{T}[]", "std::vector<std::vector<{T}>>": "matrix<{T}>"})
        assert gen._map_type("std::vector<std::vector<int>>") == "matrix<int>"
        assert gen._map_type("std::vector<int>") == "int[]"

    def test_declaration_order_breaks_ties(self) -> None:
        gen = _gen({"a<{T}>": "first", "{T}<b>": "second"})
        assert gen._map_type("a<b>") == "first"

    def test_typesystem_exact_beats_pattern(self) -> None:
        ts = TypesystemConfig(primitive_types=[PrimitiveTypeEntry(cpp_name="std::optional<int>", target_name="maybe")])
        gen = _gen({"std::optional<{T}>": "{T}?"}, typesystem=ts)
        assert gen._map_type("std::optional<int>") == "maybe"

    def test_typesystem_used_inside_captures(self) -> None:
        ts = TypesystemConfig(primitive_types=[PrimitiveTypeEntry(cpp_name="int64_t", target_name="integer")])
        gen = _gen({"std::optional<{T}>": "{T}?"}, typesystem=ts)
        assert gen._map_type("std::optional<int64_t>") == "integer?"

    def test_unmatched_passes_through(self) -> None:
        gen = _gen({"std::optional<{T}>": "{T}?"})
        assert gen._map_type("std::vector<int>") == "std::vector<int>"
        assert gen._map_type("std::optional<int, int>") == "std::optional<int, int>"

    def test_unmapped_capture_passes_through(self) -> None:
        gen = _gen({"std::optional<{T}>": "{T}?"})
        assert gen._map_type("std::optional<Widget>") == "Widget?"

    def test_malformed_pattern_fails_generator_construction(self) -> None:
        with pytest.raises(ValueError, match="does not appear in the key"):
            _gen({"x<{T}>": "{U}"})
