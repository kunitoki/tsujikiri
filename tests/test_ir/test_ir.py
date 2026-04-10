"""Tests for ir.py — IR dataclass defaults and construction."""

from __future__ import annotations

import pytest

from tsujikiri.ir import (
    IRBase,
    IRClass,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
    merge_modules,
)


class TestIRParameter:
    def test_basic(self):
        p = IRParameter(name="x", type_spelling="int")
        assert p.name == "x"
        assert p.type_spelling == "int"


class TestIRMethod:
    def test_defaults(self):
        m = IRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void")
        assert m.emit is True
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_virtual is False
        assert m.is_pure_virtual is False
        assert m.is_overload is False
        assert m.rename is None
        assert m.parameters == []
        assert m.source_file is None

    def test_with_params(self):
        m = IRMethod(
            name="add", spelling="add", qualified_name="C::add", return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int")],
            is_overload=True,
        )
        assert len(m.parameters) == 2
        assert m.parameters[0].name == "a"
        assert m.is_overload is True

    def test_emit_suppression(self):
        m = IRMethod(name="f", spelling="f", qualified_name="C::f", return_type="void")
        m.emit = False
        assert m.emit is False

    def test_rename(self):
        m = IRMethod(name="getVal", spelling="getVal", qualified_name="C::getVal", return_type="int")
        m.rename = "get"
        assert m.rename == "get"


class TestIRConstructor:
    def test_defaults(self):
        c = IRConstructor()
        assert c.emit is True
        assert c.is_overload is False
        assert c.parameters == []

    def test_with_params(self):
        c = IRConstructor(parameters=[IRParameter("x", "double")], is_overload=True)
        assert len(c.parameters) == 1
        assert c.is_overload is True


class TestIRField:
    def test_defaults(self):
        f = IRField(name="x_", type_spelling="int")
        assert f.emit is True
        assert f.is_const is False
        assert f.is_static is False
        assert f.rename is None

    def test_const_field(self):
        f = IRField(name="MAX", type_spelling="const int", is_const=True)
        assert f.is_const is True


class TestIREnumValue:
    def test_basic(self):
        v = IREnumValue(name="Red", value=0)
        assert v.name == "Red"
        assert v.value == 0
        assert v.emit is True


class TestIREnum:
    def test_defaults(self):
        e = IREnum(name="Color", qualified_name="ns::Color")
        assert e.emit is True
        assert e.values == []

    def test_with_values(self):
        e = IREnum(
            name="Color", qualified_name="ns::Color",
            values=[IREnumValue("Red", 0), IREnumValue("Green", 1)],
        )
        assert len(e.values) == 2
        assert e.values[0].name == "Red"


class TestIRClass:
    def test_defaults(self):
        c = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns")
        assert c.emit is True
        assert c.rename is None
        assert c.bases == []
        assert c.inner_classes == []
        assert c.constructors == []
        assert c.methods == []
        assert c.fields == []
        assert c.enums == []
        assert c.variable_name == ""
        assert c.parent_class is None
        assert c.source_file is None

    def test_with_base(self):
        c = IRClass(name="Circle", qualified_name="ns::Circle", namespace="ns",
                    bases=[IRBase("Shape")])
        assert len(c.bases) == 1
        assert c.bases[0].qualified_name == "Shape"
        assert c.bases[0].access == "public"

    def test_base_access_specifiers(self):
        c = IRClass(name="D", qualified_name="ns::D", namespace="ns", bases=[
            IRBase("ns::A", "public"),
            IRBase("ns::B", "protected"),
            IRBase("ns::C", "private"),
        ])
        accesses = [b.access for b in c.bases]
        assert accesses == ["public", "protected", "private"]

    def test_emit_suppression(self):
        c = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns")
        c.emit = False
        assert not c.emit


class TestIRFunction:
    def test_defaults(self):
        f = IRFunction(name="compute", qualified_name="ns::compute",
                       namespace="ns", return_type="double")
        assert f.emit is True
        assert f.is_overload is False
        assert f.rename is None
        assert f.parameters == []


class TestIRModule:
    def test_defaults(self):
        m = IRModule(name="mymod")
        assert m.name == "mymod"
        assert m.classes == []
        assert m.functions == []
        assert m.enums == []
        assert m.class_by_name == {}
        assert m.namespaces == []

    def test_make_ir_module_fixture(self, make_ir_module):
        """The shared make_ir_module fixture produces a well-formed module."""
        mod = make_ir_module()
        assert mod.name == "testmod"
        assert len(mod.classes) == 1
        cls = mod.classes[0]
        assert cls.name == "MyClass"
        assert len(cls.methods) == 4
        assert len(cls.constructors) == 2
        assert len(cls.fields) == 2
        assert len(cls.enums) == 1
        assert len(mod.enums) == 1
        assert len(mod.functions) == 1


class TestMergeModules:
    def test_single_module_returned_directly(self):
        m = IRModule(name="a")
        assert merge_modules([m]) is m

    def test_merges_multiple_modules(self):
        cls_a = IRClass(name="A", qualified_name="ns::A", namespace="ns")
        cls_b = IRClass(name="B", qualified_name="ns::B", namespace="ns")
        fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns", return_type="void")
        en = IREnum(name="E", qualified_name="ns::E")
        m1 = IRModule(name="mod", namespaces=["ns"], classes=[cls_a], enums=[en],
                      class_by_name={"A": cls_a})
        m2 = IRModule(name="mod", namespaces=["ns"], classes=[cls_b], functions=[fn],
                      class_by_name={"B": cls_b})
        merged = merge_modules([m1, m2])
        assert merged.name == "mod"
        assert len(merged.classes) == 2
        assert len(merged.functions) == 1
        assert len(merged.enums) == 1
        assert "A" in merged.class_by_name
        assert "B" in merged.class_by_name

    def test_deduplicates_namespaces(self):
        m1 = IRModule(name="mod", namespaces=["ns"])
        m2 = IRModule(name="mod", namespaces=["ns"])
        merged = merge_modules([m1, m2])
        assert merged.namespaces == ["ns"]

    def test_requires_at_least_one_module(self):
        with pytest.raises(ValueError):
            merge_modules([])
