"""Tests for ir.py (pure clang data) and tir.py (TIR* augmented types + upgrade helpers)."""

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
    IRUsingDeclaration,
    merge_modules,
)
from tsujikiri.tir import (
    TIRBase,
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIREnumValue,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
    TIRUsingDeclaration,
    merge_tir_modules,
    upgrade_base,
    upgrade_class,
    upgrade_constructor,
    upgrade_enum,
    upgrade_enum_value,
    upgrade_field,
    upgrade_function,
    upgrade_method,
    upgrade_module,
    upgrade_parameter,
    upgrade_using_declaration,
)


# ---------------------------------------------------------------------------
# IR* pure data layer tests (clang-only fields)
# ---------------------------------------------------------------------------


class TestIRParameterPure:
    def test_basic(self):
        p = IRParameter(name="x", type_spelling="int")
        assert p.name == "x"
        assert p.type_spelling == "int"
        assert p.default_value is None
        assert p.attributes == []

    def test_default_value(self):
        p = IRParameter(name="x", type_spelling="int", default_value="42")
        assert p.default_value == "42"

    def test_attributes(self):
        p = IRParameter(name="x", type_spelling="int", attributes=["ns::attr"])
        assert p.attributes == ["ns::attr"]


class TestIRMethodPure:
    def test_defaults(self):
        m = IRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void")
        assert m.name == "foo"
        assert m.spelling == "foo"
        assert m.qualified_name == "C::foo"
        assert m.return_type == "void"
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_virtual is False
        assert m.is_pure_virtual is False
        assert m.is_overload is False
        assert m.is_operator is False
        assert m.parameters == []
        assert m.source_file is None
        assert m.access == "public"
        assert m.is_deprecated is False

    def test_with_params(self):
        m = IRMethod(
            name="add",
            spelling="add",
            qualified_name="C::add",
            return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int")],
            is_overload=True,
        )
        assert len(m.parameters) == 2
        assert m.is_overload is True


class TestIRConstructorPure:
    def test_defaults(self):
        c = IRConstructor()
        assert c.is_overload is False
        assert c.parameters == []
        assert c.is_noexcept is False
        assert c.is_explicit is False
        assert c.is_deleted is False


class TestIRFieldPure:
    def test_defaults(self):
        f = IRField(name="x_", type_spelling="int")
        assert f.name == "x_"
        assert f.type_spelling == "int"
        assert f.is_const is False
        assert f.is_static is False

    def test_const_field(self):
        f = IRField(name="MAX", type_spelling="const int", is_const=True)
        assert f.is_const is True


class TestIREnumValuePure:
    def test_basic(self):
        v = IREnumValue(name="Red", value=0)
        assert v.name == "Red"
        assert v.value == 0
        assert v.attributes == []


class TestIREnumPure:
    def test_defaults(self):
        e = IREnum(name="Color", qualified_name="ns::Color")
        assert e.name == "Color"
        assert e.values == []
        assert e.is_scoped is False
        assert e.is_anonymous is False
        assert e.is_deprecated is False

    def test_with_values(self):
        e = IREnum(
            name="Color",
            qualified_name="ns::Color",
            values=[IREnumValue("Red", 0), IREnumValue("Green", 1)],
        )
        assert len(e.values) == 2


class TestIRClassPure:
    def test_defaults(self):
        c = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns")
        assert c.name == "Foo"
        assert c.qualified_name == "ns::Foo"
        assert c.namespace == "ns"
        assert c.bases == []
        assert c.inner_classes == []
        assert c.constructors == []
        assert c.methods == []
        assert c.fields == []
        assert c.enums == []
        assert c.variable_name == ""
        assert c.parent_class is None
        assert c.source_file is None
        assert c.has_virtual_methods is False
        assert c.is_abstract is False
        assert c.has_deleted_copy_constructor is False
        assert c.has_deleted_move_constructor is False

    def test_with_base(self):
        c = IRClass(name="Circle", qualified_name="ns::Circle", namespace="ns", bases=[IRBase("Shape")])
        assert len(c.bases) == 1
        assert c.bases[0].qualified_name == "Shape"

    def test_base_access_specifiers(self):
        c = IRClass(
            name="D",
            qualified_name="ns::D",
            namespace="ns",
            bases=[
                IRBase("ns::A", "public"),
                IRBase("ns::B", "protected"),
                IRBase("ns::C", "private"),
            ],
        )
        accesses = [b.access for b in c.bases]
        assert accesses == ["public", "protected", "private"]


class TestIRFunctionPure:
    def test_defaults(self):
        f = IRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="double")
        assert f.name == "compute"
        assert f.return_type == "double"
        assert f.is_overload is False
        assert f.parameters == []
        assert f.is_deprecated is False


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
        """The shared make_ir_module fixture produces a well-formed TIRModule."""
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
        m1 = IRModule(name="mod", namespaces=["ns"], classes=[cls_a], enums=[en], class_by_name={"A": cls_a})
        m2 = IRModule(name="mod", namespaces=["ns"], classes=[cls_b], functions=[fn], class_by_name={"B": cls_b})
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


# ---------------------------------------------------------------------------
# TIR* augmented layer tests
# ---------------------------------------------------------------------------


class TestTIRParameter:
    def test_basic(self):
        p = TIRParameter(name="x", type_spelling="int")
        assert p.name == "x"
        assert p.type_spelling == "int"
        assert p.emit is True
        assert p.rename is None
        assert p.type_override is None
        assert p.default_override is None
        assert p.default_value is None
        assert p.ownership == "none"
        assert p.origin is None

    def test_binding_name_without_rename(self):
        p = TIRParameter(name="value", type_spelling="int")
        assert p.binding_name == "value"

    def test_binding_name_with_rename(self):
        p = TIRParameter(name="value", type_spelling="int", rename="val")
        assert p.binding_name == "val"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        p = TIRParameter(name="value", type_spelling="int", rename="")
        assert p.binding_name == "value"

    def test_default_value(self):
        p = TIRParameter(name="x", type_spelling="int", default_value="42")
        assert p.default_value == "42"

    def test_default_override_takes_priority(self):
        p = TIRParameter(name="x", type_spelling="int", default_value="1", default_override="0")
        assert p.default_value == "1"
        assert p.default_override == "0"

    def test_index_defaults_to_zero(self):
        p = TIRParameter(name="x", type_spelling="int")
        assert p.index == 0

    def test_index_can_be_set(self):
        p = TIRParameter(name="x", type_spelling="int", index=3)
        assert p.index == 3


class TestTIRMethod:
    def test_defaults(self):
        m = TIRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void")
        assert m.emit is True
        assert m.is_static is False
        assert m.is_const is False
        assert m.is_virtual is False
        assert m.is_pure_virtual is False
        assert m.is_overload is False
        assert m.rename is None
        assert m.parameters == []
        assert m.source_file is None
        assert m.doc is None
        assert m.return_type_override is None
        assert m.return_ownership == "none"
        assert m.allow_thread is False
        assert m.wrapper_code is None
        assert m.origin is None

    def test_binding_name(self):
        m = TIRMethod(name="getVal", spelling="getVal", qualified_name="C::getVal", return_type="int")
        assert m.binding_name == "getVal"
        m.rename = "get"
        assert m.binding_name == "get"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        m = TIRMethod(name="getVal", spelling="getVal", qualified_name="C::getVal", return_type="int", rename="")
        assert m.binding_name == "getVal"

    def test_doc(self):
        m = TIRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void", doc="Returns nothing")
        assert m.doc == "Returns nothing"

    def test_with_params(self):
        m = TIRMethod(
            name="add",
            spelling="add",
            qualified_name="C::add",
            return_type="int",
            parameters=[TIRParameter("a", "int"), TIRParameter("b", "int")],
            is_overload=True,
        )
        assert len(m.parameters) == 2
        assert m.is_overload is True

    def test_emit_suppression(self):
        m = TIRMethod(name="f", spelling="f", qualified_name="C::f", return_type="void")
        m.emit = False
        assert m.emit is False


class TestTIRConstructor:
    def test_defaults(self):
        c = TIRConstructor()
        assert c.emit is True
        assert c.is_overload is False
        assert c.parameters == []
        assert c.doc is None
        assert c.origin is None

    def test_doc(self):
        c = TIRConstructor(doc="Default constructor")
        assert c.doc == "Default constructor"

    def test_with_params(self):
        c = TIRConstructor(parameters=[TIRParameter("x", "double")], is_overload=True)
        assert len(c.parameters) == 1
        assert c.is_overload is True


class TestTIRField:
    def test_defaults(self):
        f = TIRField(name="x_", type_spelling="int")
        assert f.emit is True
        assert f.is_const is False
        assert f.is_static is False
        assert f.rename is None
        assert f.doc is None
        assert f.read_only is False
        assert f.origin is None

    def test_binding_name(self):
        f = TIRField(name="value_", type_spelling="int")
        assert f.binding_name == "value_"
        f.rename = "value"
        assert f.binding_name == "value"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        f = TIRField(name="value_", type_spelling="int", rename="")
        assert f.binding_name == "value_"

    def test_doc(self):
        f = TIRField(name="x_", type_spelling="int", doc="The x coordinate")
        assert f.doc == "The x coordinate"

    def test_type_override(self):
        f = TIRField(name="label", type_spelling="juce::String", type_override="std::string")
        assert f.type_override == "std::string"

    def test_const_field(self):
        f = TIRField(name="MAX", type_spelling="const int", is_const=True)
        assert f.is_const is True


class TestTIREnumValue:
    def test_basic(self):
        v = TIREnumValue(name="Red", value=0)
        assert v.name == "Red"
        assert v.value == 0
        assert v.emit is True
        assert v.rename is None
        assert v.doc is None
        assert v.origin is None

    def test_binding_name(self):
        v = TIREnumValue(name="Red", value=0)
        assert v.binding_name == "Red"
        v.rename = "red"
        assert v.binding_name == "red"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        v = TIREnumValue(name="Red", value=0, rename="")
        assert v.binding_name == "Red"

    def test_rename(self):
        v = TIREnumValue(name="Red", value=0, rename="red")
        assert v.rename == "red"

    def test_doc(self):
        v = TIREnumValue(name="Red", value=0, doc="The red color")
        assert v.doc == "The red color"


class TestTIREnum:
    def test_defaults(self):
        e = TIREnum(name="Color", qualified_name="ns::Color")
        assert e.emit is True
        assert e.values == []
        assert e.rename is None
        assert e.doc is None
        assert e.is_arithmetic is False
        assert e.origin is None

    def test_binding_name(self):
        e = TIREnum(name="Color", qualified_name="ns::Color")
        assert e.binding_name == "Color"
        e.rename = "Colour"
        assert e.binding_name == "Colour"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        e = TIREnum(name="Color", qualified_name="ns::Color", rename="")
        assert e.binding_name == "Color"

    def test_doc(self):
        e = TIREnum(name="Color", qualified_name="ns::Color", doc="Color enumeration")
        assert e.doc == "Color enumeration"

    def test_with_values(self):
        e = TIREnum(
            name="Color",
            qualified_name="ns::Color",
            values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)],
        )
        assert len(e.values) == 2


class TestTIRClass:
    def test_defaults(self):
        c = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns")
        assert c.emit is True
        assert c.rename is None
        assert c.doc is None
        assert c.bases == []
        assert c.inner_classes == []
        assert c.constructors == []
        assert c.methods == []
        assert c.fields == []
        assert c.enums == []
        assert c.variable_name == ""
        assert c.parent_class is None
        assert c.source_file is None
        assert c.copyable is None
        assert c.movable is None
        assert c.force_abstract is False
        assert c.holder_type is None
        assert c.generate_hash is False
        assert c.origin is None

    def test_binding_name(self):
        c = TIRClass(name="MyClass", qualified_name="ns::MyClass", namespace="ns")
        assert c.binding_name == "MyClass"
        c.rename = "My"
        assert c.binding_name == "My"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        c = TIRClass(name="MyClass", qualified_name="ns::MyClass", namespace="ns", rename="")
        assert c.binding_name == "MyClass"

    def test_doc(self):
        c = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns", doc="A foo class")
        assert c.doc == "A foo class"

    def test_emit_suppression(self):
        c = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns")
        c.emit = False
        assert not c.emit


class TestTIRFunction:
    def test_defaults(self):
        f = TIRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="double")
        assert f.emit is True
        assert f.is_overload is False
        assert f.rename is None
        assert f.parameters == []
        assert f.return_type_override is None
        assert f.return_ownership == "none"
        assert f.allow_thread is False
        assert f.wrapper_code is None
        assert f.doc is None
        assert f.origin is None

    def test_binding_name(self):
        f = TIRFunction(name="computeArea", qualified_name="ns::computeArea", namespace="ns", return_type="float")
        assert f.binding_name == "computeArea"
        f.rename = "compute_area"
        assert f.binding_name == "compute_area"

    def test_binding_name_empty_rename_falls_back_to_name(self):
        f = TIRFunction(
            name="computeArea", qualified_name="ns::computeArea", namespace="ns", return_type="float", rename=""
        )
        assert f.binding_name == "computeArea"

    def test_extended_fields(self):
        f = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="double",
            return_type_override="float",
            return_ownership="cpp",
            allow_thread=True,
            wrapper_code="return 42.0;",
            doc="Computes something",
        )
        assert f.return_type_override == "float"
        assert f.return_ownership == "cpp"
        assert f.allow_thread is True
        assert f.wrapper_code == "return 42.0;"
        assert f.doc == "Computes something"


class TestTIRBase:
    def test_defaults(self):
        b = TIRBase(qualified_name="ns::Base")
        assert b.qualified_name == "ns::Base"
        assert b.access == "public"
        assert b.emit is True
        assert b.origin is None

    def test_emit_false(self):
        b = TIRBase(qualified_name="ns::Base")
        b.emit = False
        assert not b.emit


class TestTIRUsingDeclaration:
    def test_defaults(self):
        u = TIRUsingDeclaration(member_name="foo", base_qualified_name="ns::Base")
        assert u.member_name == "foo"
        assert u.base_qualified_name == "ns::Base"
        assert u.access == "public"
        assert u.emit is True
        assert u.origin is None


# ---------------------------------------------------------------------------
# Upgrade function tests
# ---------------------------------------------------------------------------


class TestUpgradeParameter:
    def test_upgrades_ir_parameter(self):
        ir = IRParameter(name="x", type_spelling="int", default_value="0")
        tir = upgrade_parameter(ir)
        assert isinstance(tir, TIRParameter)
        assert tir.name == "x"
        assert tir.type_spelling == "int"
        assert tir.default_value == "0"
        assert tir.emit is True
        assert tir.rename is None
        assert tir.origin is ir

    def test_origin_is_same_object(self):
        ir = IRParameter(name="x", type_spelling="int")
        tir = upgrade_parameter(ir)
        assert tir.origin is ir

    def test_index_defaults_to_zero(self):
        ir = IRParameter(name="x", type_spelling="int")
        tir = upgrade_parameter(ir)
        assert tir.index == 0

    def test_index_set_from_argument(self):
        ir = IRParameter(name="x", type_spelling="int")
        tir = upgrade_parameter(ir, 3)
        assert tir.index == 3

    def test_unnamed_param_name_forced_to_p0(self):
        ir = IRParameter(name="", type_spelling="int")
        tir = upgrade_parameter(ir, 0)
        assert tir.name == "p0"

    def test_unnamed_param_name_forced_to_p2(self):
        ir = IRParameter(name="", type_spelling="int")
        tir = upgrade_parameter(ir, 2)
        assert tir.name == "p2"

    def test_origin_name_empty_for_unnamed(self):
        ir = IRParameter(name="", type_spelling="int")
        tir = upgrade_parameter(ir, 1)
        assert tir.origin is not None
        assert tir.origin.name == ""

    def test_named_param_name_unchanged(self):
        ir = IRParameter(name="value", type_spelling="int")
        tir = upgrade_parameter(ir, 5)
        assert tir.name == "value"


class TestUpgradeBase:
    def test_upgrades_ir_base(self):
        ir = IRBase(qualified_name="ns::Base", access="public")
        tir = upgrade_base(ir)
        assert isinstance(tir, TIRBase)
        assert tir.qualified_name == "ns::Base"
        assert tir.emit is True
        assert tir.origin is ir


class TestUpgradeMethod:
    def test_upgrades_ir_method(self):
        ir = IRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void")
        tir = upgrade_method(ir)
        assert isinstance(tir, TIRMethod)
        assert tir.name == "foo"
        assert tir.emit is True
        assert tir.rename is None
        assert tir.origin is ir

    def test_protected_method_suppressed(self):
        ir = IRMethod(name="bar", spelling="bar", qualified_name="C::bar", return_type="void", access="protected")
        tir = upgrade_method(ir)
        assert tir.emit is False

    def test_public_method_emitted(self):
        ir = IRMethod(name="foo", spelling="foo", qualified_name="C::foo", return_type="void", access="public")
        tir = upgrade_method(ir)
        assert tir.emit is True

    def test_parameters_upgraded(self):
        ir = IRMethod(
            name="add",
            spelling="add",
            qualified_name="C::add",
            return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int")],
        )
        tir = upgrade_method(ir)
        assert len(tir.parameters) == 2
        assert all(isinstance(p, TIRParameter) for p in tir.parameters)

    def test_parameter_indices_set(self):
        ir = IRMethod(
            name="add",
            spelling="add",
            qualified_name="C::add",
            return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int"), IRParameter("c", "int")],
        )
        tir = upgrade_method(ir)
        assert [p.index for p in tir.parameters] == [0, 1, 2]

    def test_unnamed_parameters_forced_in_method(self):
        ir = IRMethod(
            name="foo",
            spelling="foo",
            qualified_name="C::foo",
            return_type="void",
            parameters=[IRParameter("", "int"), IRParameter("", "float")],
        )
        tir = upgrade_method(ir)
        assert tir.parameters[0].name == "p0"
        assert tir.parameters[1].name == "p1"


class TestUpgradeConstructor:
    def test_upgrades_ir_constructor(self):
        ir = IRConstructor(parameters=[IRParameter("x", "int")])
        tir = upgrade_constructor(ir)
        assert isinstance(tir, TIRConstructor)
        assert tir.emit is True
        assert tir.origin is ir
        assert len(tir.parameters) == 1
        assert isinstance(tir.parameters[0], TIRParameter)

    def test_parameter_indices_set(self):
        ir = IRConstructor(parameters=[IRParameter("a", "int"), IRParameter("b", "float")])
        tir = upgrade_constructor(ir)
        assert [p.index for p in tir.parameters] == [0, 1]

    def test_unnamed_parameters_forced_in_constructor(self):
        ir = IRConstructor(parameters=[IRParameter("", "int"), IRParameter("", "float")])
        tir = upgrade_constructor(ir)
        assert tir.parameters[0].name == "p0"
        assert tir.parameters[1].name == "p1"


class TestUpgradeField:
    def test_upgrades_ir_field(self):
        ir = IRField(name="x_", type_spelling="int", is_const=True)
        tir = upgrade_field(ir)
        assert isinstance(tir, TIRField)
        assert tir.name == "x_"
        assert tir.is_const is True
        assert tir.emit is True
        assert tir.origin is ir


class TestUpgradeEnumValue:
    def test_upgrades_ir_enum_value(self):
        ir = IREnumValue(name="Red", value=0)
        tir = upgrade_enum_value(ir)
        assert isinstance(tir, TIREnumValue)
        assert tir.name == "Red"
        assert tir.value == 0
        assert tir.emit is True
        assert tir.origin is ir


class TestUpgradeEnum:
    def test_upgrades_ir_enum(self):
        ir = IREnum(
            name="Color",
            qualified_name="ns::Color",
            values=[IREnumValue("Red", 0), IREnumValue("Green", 1)],
        )
        tir = upgrade_enum(ir)
        assert isinstance(tir, TIREnum)
        assert tir.name == "Color"
        assert tir.emit is True
        assert tir.origin is ir
        assert len(tir.values) == 2
        assert all(isinstance(v, TIREnumValue) for v in tir.values)


class TestUpgradeUsingDeclaration:
    def test_upgrades_ir_using_declaration(self):
        from tsujikiri.ir import IRUsingDeclaration

        ir = IRUsingDeclaration(member_name="foo", base_qualified_name="ns::Base")
        tir = upgrade_using_declaration(ir)
        assert isinstance(tir, TIRUsingDeclaration)
        assert tir.member_name == "foo"
        assert tir.emit is True
        assert tir.origin is ir


class TestUpgradeClass:
    def test_upgrades_ir_class(self):
        ir = IRClass(
            name="MyClass",
            qualified_name="ns::MyClass",
            namespace="ns",
            variable_name="myVar",
        )
        tir = upgrade_class(ir)
        assert isinstance(tir, TIRClass)
        assert tir.name == "MyClass"
        assert tir.variable_name == "myVar"
        assert tir.emit is True
        assert tir.rename is None
        assert tir.copyable is None
        assert tir.origin is ir

    def test_deleted_copy_sets_copyable_false(self):
        ir = IRClass(
            name="Foo",
            qualified_name="ns::Foo",
            namespace="ns",
            has_deleted_copy_constructor=True,
        )
        tir = upgrade_class(ir)
        assert tir.copyable is False

    def test_deleted_move_sets_movable_false(self):
        ir = IRClass(
            name="Foo",
            qualified_name="ns::Foo",
            namespace="ns",
            has_deleted_move_constructor=True,
        )
        tir = upgrade_class(ir)
        assert tir.movable is False

    def test_both_deleted_sets_both_false(self):
        ir = IRClass(
            name="Foo",
            qualified_name="ns::Foo",
            namespace="ns",
            has_deleted_copy_constructor=True,
            has_deleted_move_constructor=True,
        )
        tir = upgrade_class(ir)
        assert tir.copyable is False
        assert tir.movable is False

    def test_nested_members_upgraded(self):
        inner = IRClass(name="Inner", qualified_name="ns::Outer::Inner", namespace="ns")
        ir = IRClass(
            name="Outer",
            qualified_name="ns::Outer",
            namespace="ns",
            methods=[IRMethod(name="f", spelling="f", qualified_name="Outer::f", return_type="void")],
            fields=[IRField(name="x", type_spelling="int")],
            constructors=[IRConstructor()],
            enums=[IREnum(name="E", qualified_name="Outer::E")],
            bases=[IRBase(qualified_name="ns::Base")],
            inner_classes=[inner],
            using_declarations=[IRUsingDeclaration(member_name="method", base_qualified_name="ns::Base")],
        )
        tir = upgrade_class(ir)
        assert all(isinstance(m, TIRMethod) for m in tir.methods)
        assert all(isinstance(f, TIRField) for f in tir.fields)
        assert all(isinstance(c, TIRConstructor) for c in tir.constructors)
        assert all(isinstance(e, TIREnum) for e in tir.enums)
        assert all(isinstance(b, TIRBase) for b in tir.bases)
        assert all(isinstance(ic, TIRClass) for ic in tir.inner_classes)
        assert all(isinstance(u, TIRUsingDeclaration) for u in tir.using_declarations)


class TestUpgradeFunction:
    def test_upgrades_ir_function(self):
        ir = IRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="double",
            parameters=[IRParameter("x", "double")],
        )
        tir = upgrade_function(ir)
        assert isinstance(tir, TIRFunction)
        assert tir.name == "compute"
        assert tir.emit is True
        assert tir.origin is ir
        assert len(tir.parameters) == 1
        assert isinstance(tir.parameters[0], TIRParameter)

    def test_parameter_indices_set(self):
        ir = IRFunction(
            name="f",
            qualified_name="ns::f",
            namespace="ns",
            return_type="void",
            parameters=[IRParameter("a", "int"), IRParameter("b", "int"), IRParameter("c", "int")],
        )
        tir = upgrade_function(ir)
        assert [p.index for p in tir.parameters] == [0, 1, 2]

    def test_unnamed_parameters_forced_in_function(self):
        ir = IRFunction(
            name="f",
            qualified_name="ns::f",
            namespace="ns",
            return_type="void",
            parameters=[IRParameter("", "int"), IRParameter("", "float")],
        )
        tir = upgrade_function(ir)
        assert tir.parameters[0].name == "p0"
        assert tir.parameters[1].name == "p1"


class TestUpgradeModule:
    def test_upgrades_ir_module(self):
        ir = IRModule(name="mod")
        tir = upgrade_module(ir)
        assert isinstance(tir, TIRModule)
        assert tir.name == "mod"
        assert tir.origin is ir

    def test_nested_objects_upgraded(self):
        ir_cls = IRClass(name="A", qualified_name="ns::A", namespace="ns")
        ir_fn = IRFunction(name="f", qualified_name="ns::f", namespace="ns", return_type="void")
        ir_en = IREnum(name="E", qualified_name="ns::E")
        ir = IRModule(
            name="mod",
            namespaces=["ns"],
            classes=[ir_cls],
            functions=[ir_fn],
            enums=[ir_en],
            class_by_name={"A": ir_cls},
        )
        tir = upgrade_module(ir)
        assert len(tir.classes) == 1
        assert isinstance(tir.classes[0], TIRClass)
        assert len(tir.functions) == 1
        assert isinstance(tir.functions[0], TIRFunction)
        assert len(tir.enums) == 1
        assert isinstance(tir.enums[0], TIREnum)
        assert "A" in tir.class_by_name
        assert isinstance(tir.class_by_name["A"], TIRClass)


class TestMergeTIRModules:
    def test_single_module_returned_directly(self):
        m = TIRModule(name="a")
        assert merge_tir_modules([m]) is m

    def test_merges_multiple_modules(self):
        from tsujikiri.ir import IRExceptionRegistration, IRCodeInjection

        cls_a = TIRClass(name="A", qualified_name="ns::A", namespace="ns")
        cls_b = TIRClass(name="B", qualified_name="ns::B", namespace="ns")
        fn = TIRFunction(name="f", qualified_name="ns::f", namespace="ns", return_type="void")
        en = TIREnum(name="E", qualified_name="ns::E")
        inj = IRCodeInjection(position="end", code="// code")
        exc = IRExceptionRegistration(cpp_exception_type="MyEx", target_exception_name="MyEx")
        m1 = TIRModule(name="mod", namespaces=["ns"])
        m1.classes.append(cls_a)  # type: ignore[arg-type]
        m1.enums.append(en)  # type: ignore[arg-type]
        m1.class_by_name["A"] = cls_a  # type: ignore[assignment]
        m1.code_injections.append(inj)
        m2 = TIRModule(name="mod", namespaces=["ns"])
        m2.classes.append(cls_b)  # type: ignore[arg-type]
        m2.functions.append(fn)  # type: ignore[arg-type]
        m2.class_by_name["B"] = cls_b  # type: ignore[assignment]
        m2.exception_registrations.append(exc)
        merged = merge_tir_modules([m1, m2])
        assert merged.name == "mod"
        assert len(merged.classes) == 2
        assert len(merged.functions) == 1
        assert len(merged.enums) == 1
        assert "A" in merged.class_by_name
        assert "B" in merged.class_by_name
        assert len(merged.code_injections) == 1
        assert len(merged.exception_registrations) == 1

    def test_deduplicates_namespaces(self):
        m1 = TIRModule(name="mod", namespaces=["ns"])
        m2 = TIRModule(name="mod", namespaces=["ns"])
        merged = merge_tir_modules([m1, m2])
        assert merged.namespaces == ["ns"]

    def test_requires_at_least_one_module(self):
        with pytest.raises(ValueError):
            merge_tir_modules([])
