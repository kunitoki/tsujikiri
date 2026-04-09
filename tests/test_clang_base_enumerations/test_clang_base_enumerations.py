"""Tests for clang_base_enumerations.py — enum __eq__ NotImplemented branches."""

from __future__ import annotations

import clang.cindex

from tsujikiri.clang_base_enumerations import (
    AccessSpecifier,
    AvailabilityKind,
    CursorKind,
    ExceptionSpecificationKind,
    LinkageKind,
    RefQualifierKind,
    TemplateArgumentKind,
    TLSKind,
    TypeKind,
)


class TestCursorKindEq:
    def test_not_implemented_for_non_clang_type(self):
        assert CursorKind.STRUCT_DECL.__eq__(42) is NotImplemented


class TestTemplateArgumentKindEq:
    def test_eq_with_clang_type(self):
        assert TemplateArgumentKind.NULL == clang.cindex.TemplateArgumentKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert TemplateArgumentKind.NULL.__eq__(42) is NotImplemented


class TestExceptionSpecificationKindEq:
    def test_eq_with_clang_type(self):
        assert ExceptionSpecificationKind.NONE == clang.cindex.ExceptionSpecificationKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert ExceptionSpecificationKind.NONE.__eq__(42) is NotImplemented


class TestAvailabilityKindEq:
    def test_eq_with_clang_type(self):
        assert AvailabilityKind.AVAILABLE == clang.cindex.AvailabilityKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert AvailabilityKind.AVAILABLE.__eq__(42) is NotImplemented


class TestAccessSpecifierEq:
    def test_not_implemented_for_non_clang_type(self):
        assert AccessSpecifier.PUBLIC.__eq__(42) is NotImplemented


class TestTypeKindEq:
    def test_eq_with_clang_type(self):
        assert TypeKind.ATOMIC == clang.cindex.TypeKind.from_id(177)

    def test_not_implemented_for_non_clang_type(self):
        assert TypeKind.ATOMIC.__eq__(42) is NotImplemented


class TestRefQualifierKindEq:
    def test_eq_with_clang_type(self):
        assert RefQualifierKind.NONE == clang.cindex.RefQualifierKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert RefQualifierKind.NONE.__eq__(42) is NotImplemented


class TestLinkageKindEq:
    def test_eq_with_clang_type(self):
        assert LinkageKind.INVALID == clang.cindex.LinkageKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert LinkageKind.INVALID.__eq__(42) is NotImplemented


class TestTLSKindEq:
    def test_eq_with_clang_type(self):
        assert TLSKind.NONE == clang.cindex.TLSKind.from_id(0)

    def test_not_implemented_for_non_clang_type(self):
        assert TLSKind.NONE.__eq__(42) is NotImplemented
