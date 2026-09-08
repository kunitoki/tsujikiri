"""Tests for anonymous union/struct member flattening in parser.py."""

from __future__ import annotations

from typing import List

import pytest

from tsujikiri.ir import IRClass, IRField


def _field(ir_class: IRClass, name: str) -> IRField:
    matches = [f for f in ir_class.fields if f.name == name]
    assert matches, f"field {name!r} not found in {[f.name for f in ir_class.fields]}"
    return matches[0]


def _field_names(ir_class: IRClass) -> List[str]:
    return [f.name for f in ir_class.fields]


@pytest.fixture(scope="module")
def container(anonymous_records_module) -> IRClass:
    return next(c for c in anonymous_records_module.classes if c.name == "AnonymousContainer")


@pytest.fixture(scope="module")
def outer(anonymous_records_module) -> IRClass:
    return next(c for c in anonymous_records_module.classes if c.name == "Outer")


class TestAnonymousMemberFlattening:
    def test_anonymous_union_member_becomes_field(self, container: IRClass) -> None:
        assert "v" in _field_names(container)

    def test_anonymous_union_member_keeps_array_type(self, container: IRClass) -> None:
        assert _field(container, "v").type_spelling == "int[2]"

    def test_nested_anonymous_struct_members_become_fields(self, container: IRClass) -> None:
        assert "x" in _field_names(container)
        assert "y" in _field_names(container)

    def test_nested_anonymous_struct_members_keep_type(self, container: IRClass) -> None:
        assert _field(container, "x").type_spelling == "int"
        assert _field(container, "y").type_spelling == "int"

    def test_flattened_names_are_single_components(self, container: IRClass) -> None:
        assert all("." not in f.name and "::" not in f.name for f in container.fields)

    def test_named_record_inside_anonymous_member_is_not_flattened(self, container: IRClass) -> None:
        assert "inner_field" not in _field_names(container)

    def test_anonymous_struct_at_class_scope_is_flattened(self, container: IRClass) -> None:
        assert "direct" in _field_names(container)

    def test_ordinary_field_still_present(self, container: IRClass) -> None:
        assert "plain" in _field_names(container)

    def test_private_anonymous_union_is_excluded(self, container: IRClass) -> None:
        assert "secret" not in _field_names(container)

    def test_anonymous_union_inside_nested_class_is_flattened(self, outer: IRClass) -> None:
        nested = next(c for c in outer.inner_classes if c.name == "Nested")
        assert _field_names(nested) == ["nested_anon", "nested_anon_d"]


class TestNamedUnnamedTypeFields:
    """``union {...} u;`` declares a real field — it must not be flattened."""

    def test_named_union_field_stays_a_single_field(self, container: IRClass) -> None:
        assert "u" in _field_names(container)
        assert "a" not in _field_names(container)
        assert "b" not in _field_names(container)

    def test_named_struct_field_stays_a_single_field(self, container: IRClass) -> None:
        assert "named_s" in _field_names(container)
        assert "q" not in _field_names(container)


class TestAnonymousRecordsAreNotInnerClasses:
    def test_no_anonymous_inner_classes(self, container: IRClass) -> None:
        assert container.inner_classes == []

    def test_named_inner_class_still_collected(self, outer: IRClass) -> None:
        assert [c.name for c in outer.inner_classes] == ["Nested"]
