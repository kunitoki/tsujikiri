"""Tests for Jinja2 filters and helpers in generator_filters.py."""

from __future__ import annotations

from tsujikiri.generator_filters import camel_to_snake, code_at, param_pairs, snake_to_camel


# ---------------------------------------------------------------------------
# camel_to_snake
# ---------------------------------------------------------------------------


class TestCamelToSnake:
    def test_simple_camel(self):
        assert camel_to_snake("getValue") == "get_value"

    def test_uppercase_acronym(self):
        assert camel_to_snake("getHTTPResponse") == "get_http_response"

    def test_already_snake(self):
        assert camel_to_snake("compute_area") == "compute_area"

    def test_single_word_lowercase(self):
        assert camel_to_snake("compute") == "compute"

    def test_single_word_uppercase(self):
        assert camel_to_snake("Compute") == "compute"

    def test_multiple_words(self):
        assert camel_to_snake("getComputedValue") == "get_computed_value"

    def test_consecutive_capitals(self):
        assert camel_to_snake("XMLParser") == "xml_parser"

    def test_empty_string(self):
        assert camel_to_snake("") == ""

    def test_number_boundary(self):
        assert camel_to_snake("get2DArea") == "get2_d_area"

    def test_class_name_style(self):
        assert camel_to_snake("MyClassName") == "my_class_name"


# ---------------------------------------------------------------------------
# snake_to_camel
# ---------------------------------------------------------------------------


class TestSnakeToCamel:
    def test_simple_snake(self) -> None:
        assert snake_to_camel("get_value") == "GetValue"

    def test_uppercase_first_default(self) -> None:
        assert snake_to_camel("my_class_name") == "MyClassName"

    def test_lowercase_first(self) -> None:
        assert snake_to_camel("get_value", uppercase_first=False) == "getValue"

    def test_lowercase_first_multiple_words(self) -> None:
        assert snake_to_camel("my_class_name", uppercase_first=False) == "myClassName"

    def test_single_word_uppercase_first(self) -> None:
        assert snake_to_camel("compute") == "Compute"

    def test_single_word_lowercase_first(self) -> None:
        assert snake_to_camel("compute", uppercase_first=False) == "compute"

    def test_empty_string(self) -> None:
        assert snake_to_camel("") == ""

    def test_already_no_underscores(self) -> None:
        assert snake_to_camel("value") == "Value"

    def test_trailing_underscore(self) -> None:
        assert snake_to_camel("get_value_") == "GetValue"

    def test_leading_underscore(self) -> None:
        assert snake_to_camel("_get_value") == "GetValue"

    def test_multiple_consecutive_underscores(self) -> None:
        assert snake_to_camel("get__value") == "GetValue"


# ---------------------------------------------------------------------------
# param_pairs
# ---------------------------------------------------------------------------


class TestParamPairs:
    def _make_params(self, *name_type_pairs):
        return [{"name": n, "type": t} for n, t in name_type_pairs]

    def test_single_param(self):
        params = self._make_params(("x", "int"))
        result = param_pairs(params, "name", ": ", "type", ", ")
        assert result == "x: int"

    def test_two_params(self):
        params = self._make_params(("x", "int"), ("y", "float"))
        result = param_pairs(params, "name", ": ", "type", ", ")
        assert result == "x: int, y: float"

    def test_empty_params(self):
        result = param_pairs([], "name", ": ", "type", ", ")
        assert result == ""

    def test_custom_separator(self):
        params = self._make_params(("a", "str"), ("b", "bool"))
        result = param_pairs(params, "name", " :: ", "type", " | ")
        assert result == "a :: str | b :: bool"

    def test_different_key_names(self):
        params = [{"n": "x", "t": "int"}, {"n": "y", "t": "float"}]
        result = param_pairs(params, "n", ": ", "t", ", ")
        assert result == "x: int, y: float"


# ---------------------------------------------------------------------------
# code_at
# ---------------------------------------------------------------------------


class TestCodeAt:
    def _make_injections(self, *pos_code_pairs):
        return [{"position": pos, "code": code} for pos, code in pos_code_pairs]

    def test_empty_injections(self):
        assert code_at([], "beginning") == ""

    def test_matching_position(self):
        injections = self._make_injections(("beginning", "// start"))
        assert code_at(injections, "beginning") == "// start"

    def test_non_matching_position(self):
        injections = self._make_injections(("beginning", "// start"))
        assert code_at(injections, "end") == ""

    def test_multiple_at_same_position(self):
        injections = self._make_injections(
            ("beginning", "// line1"),
            ("beginning", "// line2"),
        )
        result = code_at(injections, "beginning")
        assert "// line1" in result
        assert "// line2" in result
        assert result == "// line1\n// line2"

    def test_mixed_positions(self):
        injections = self._make_injections(
            ("beginning", "// begin"),
            ("end", "// end"),
            ("beginning", "// begin2"),
        )
        result = code_at(injections, "beginning")
        assert "// begin" in result
        assert "// begin2" in result
        assert "// end" not in result

    def test_end_position(self):
        injections = self._make_injections(
            ("beginning", "// b"),
            ("end", "// e"),
        )
        assert code_at(injections, "end") == "// e"

    def test_unknown_position_returns_empty(self):
        injections = self._make_injections(("beginning", "// b"))
        assert code_at(injections, "middle") == ""
