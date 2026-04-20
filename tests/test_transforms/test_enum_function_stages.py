"""Tests for new transform stages: enum, function, injection, and base-suppression."""

from __future__ import annotations

import pytest

from tsujikiri.tir import (
    TIRBase,
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIREnumValue,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)
from tsujikiri.transforms import (
    InjectConstructorStage,
    InjectFunctionStage,
    ModifyEnumStage,
    ModifyFunctionStage,
    RenameEnumStage,
    RenameEnumValueStage,
    RenameFunctionStage,
    SuppressBaseStage,
    SuppressEnumStage,
    SuppressEnumValueStage,
    SuppressFunctionStage,
    _find_enums,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module() -> TIRModule:
    """Module with two top-level enums, a class with a nested enum, and two free functions."""
    color = TIREnum(
        name="Color", qualified_name="ns::Color",
        values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1), TIREnumValue("Blue", 2)],
    )
    state = TIREnum(
        name="State", qualified_name="ns::State",
        values=[TIREnumValue("On", 1), TIREnumValue("Off", 0)],
    )
    nested_enum = TIREnum(
        name="Flag", qualified_name="ns::Cls::Flag",
        values=[TIREnumValue("A", 0), TIREnumValue("B", 1)],
    )
    cls = TIRClass(
        name="Cls", qualified_name="ns::Cls", namespace="ns",
        enums=[nested_enum],
        bases=[
            TIRBase("ns::Base", "public"),
            TIRBase("ns::Hidden", "public"),
        ],
        constructors=[TIRConstructor(parameters=[TIRParameter("x", "int")])],
    )
    fn1 = TIRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="double",
                     parameters=[TIRParameter("x", "double")])
    fn2 = TIRFunction(name="internal_helper", qualified_name="ns::internal_helper",
                     namespace="ns", return_type="void")
    return TIRModule(
        name="m",
        classes=[cls],
        enums=[color, state],
        functions=[fn1, fn2],
        class_by_name={"Cls": cls},
    )


def _enum(mod: TIRModule, name: str) -> TIREnum:
    return next(e for e in mod.enums if e.name == name)


def _fn(mod: TIRModule, name: str) -> TIRFunction:
    return next(f for f in mod.functions if f.name == name)


def _cls(mod: TIRModule, name: str = "Cls") -> TIRClass:
    return next(c for c in mod.classes if c.name == name)


# ---------------------------------------------------------------------------
# _find_enums helper
# ---------------------------------------------------------------------------

class TestFindEnums:
    def test_top_level_enum(self):
        mod = _make_module()
        result = _find_enums(mod, "Color")
        assert len(result) == 1
        assert result[0].name == "Color"

    def test_nested_enum(self):
        mod = _make_module()
        result = _find_enums(mod, "Flag")
        assert len(result) == 1
        assert result[0].name == "Flag"

    def test_wildcard_matches_all(self):
        mod = _make_module()
        result = _find_enums(mod, "*")
        names = {e.name for e in result}
        assert {"Color", "State", "Flag"} == names

    def test_regex_match(self):
        mod = _make_module()
        result = _find_enums(mod, "Col.*", is_regex=True)
        assert len(result) == 1
        assert result[0].name == "Color"

    def test_deeply_nested_inner_class_enum(self):
        """_find_enums recurses into inner_classes of a class."""
        inner_enum = TIREnum(
            name="Inner", qualified_name="ns::Outer::Inner::Inner",
            values=[TIREnumValue("X", 0)],
        )
        inner_cls = TIRClass(
            name="Inner", qualified_name="ns::Outer::Inner", namespace="ns",
            enums=[inner_enum],
        )
        outer_cls = TIRClass(
            name="Outer", qualified_name="ns::Outer", namespace="ns",
            inner_classes=[inner_cls],
        )
        mod = TIRModule(name="m", classes=[outer_cls])
        result = _find_enums(mod, "Inner")
        assert len(result) == 1
        assert result[0].name == "Inner"


# ---------------------------------------------------------------------------
# RenameEnumStage
# ---------------------------------------------------------------------------

class TestRenameEnumStage:
    def test_renames_top_level(self):
        mod = _make_module()
        RenameEnumStage(**{"from": "Color", "to": "Colour"}).apply(mod)
        assert _enum(mod, "Color").rename == "Colour"

    def test_does_not_rename_other(self):
        mod = _make_module()
        RenameEnumStage(**{"from": "Color", "to": "Colour"}).apply(mod)
        assert _enum(mod, "State").rename is None

    def test_renames_nested(self):
        mod = _make_module()
        RenameEnumStage(**{"from": "Flag", "to": "Flags"}).apply(mod)
        nested = _cls(mod).enums[0]
        assert nested.rename == "Flags"

    def test_regex(self):
        mod = _make_module()
        RenameEnumStage(**{"from": "Col.*", "to": "C", "is_regex": True}).apply(mod)
        assert _enum(mod, "Color").rename == "C"
        assert _enum(mod, "State").rename is None


# ---------------------------------------------------------------------------
# RenameEnumValueStage
# ---------------------------------------------------------------------------

class TestRenameEnumValueStage:
    def test_renames_value(self):
        mod = _make_module()
        RenameEnumValueStage(**{"enum": "Color", "from": "Red", "to": "red"}).apply(mod)
        val = next(v for v in _enum(mod, "Color").values if v.name == "Red")
        assert val.rename == "red"

    def test_does_not_touch_other_enum(self):
        mod = _make_module()
        RenameEnumValueStage(**{"enum": "Color", "from": "On", "to": "ON"}).apply(mod)
        state_on = next(v for v in _enum(mod, "State").values if v.name == "On")
        assert state_on.rename is None

    def test_wildcard_enum_pattern(self):
        mod = _make_module()
        RenameEnumValueStage(**{"enum": "*", "from": "On", "to": "on"}).apply(mod)
        state_on = next(v for v in _enum(mod, "State").values if v.name == "On")
        assert state_on.rename == "on"

    def test_regex_value_pattern(self):
        mod = _make_module()
        RenameEnumValueStage(**{"enum": "Color", "from": "Re.*", "to": "r", "is_regex": True}).apply(mod)
        val = next(v for v in _enum(mod, "Color").values if v.name == "Red")
        assert val.rename == "r"


# ---------------------------------------------------------------------------
# SuppressEnumStage
# ---------------------------------------------------------------------------

class TestSuppressEnumStage:
    def test_suppresses_enum(self):
        mod = _make_module()
        SuppressEnumStage(**{"pattern": "Color"}).apply(mod)
        assert _enum(mod, "Color").emit is False

    def test_does_not_suppress_other(self):
        mod = _make_module()
        SuppressEnumStage(**{"pattern": "Color"}).apply(mod)
        assert _enum(mod, "State").emit is True

    def test_regex(self):
        mod = _make_module()
        SuppressEnumStage(**{"pattern": "Col.*", "is_regex": True}).apply(mod)
        assert _enum(mod, "Color").emit is False
        assert _enum(mod, "State").emit is True


# ---------------------------------------------------------------------------
# SuppressEnumValueStage
# ---------------------------------------------------------------------------

class TestSuppressEnumValueStage:
    def test_suppresses_value(self):
        mod = _make_module()
        SuppressEnumValueStage(**{"enum": "Color", "pattern": "Blue"}).apply(mod)
        blue = next(v for v in _enum(mod, "Color").values if v.name == "Blue")
        assert blue.emit is False

    def test_does_not_suppress_other_values(self):
        mod = _make_module()
        SuppressEnumValueStage(**{"enum": "Color", "pattern": "Blue"}).apply(mod)
        red = next(v for v in _enum(mod, "Color").values if v.name == "Red")
        assert red.emit is True

    def test_regex(self):
        mod = _make_module()
        SuppressEnumValueStage(**{"enum": "Color", "pattern": "Gr.*", "is_regex": True}).apply(mod)
        green = next(v for v in _enum(mod, "Color").values if v.name == "Green")
        assert green.emit is False


# ---------------------------------------------------------------------------
# ModifyEnumStage
# ---------------------------------------------------------------------------

class TestModifyEnumStage:
    def test_rename(self):
        mod = _make_module()
        ModifyEnumStage(**{"enum": "Color", "rename": "Colours"}).apply(mod)
        assert _enum(mod, "Color").rename == "Colours"

    def test_remove(self):
        mod = _make_module()
        ModifyEnumStage(**{"enum": "Color", "remove": True}).apply(mod)
        assert _enum(mod, "Color").emit is False

    def test_no_op(self):
        mod = _make_module()
        ModifyEnumStage(**{"enum": "Color"}).apply(mod)
        assert _enum(mod, "Color").rename is None
        assert _enum(mod, "Color").emit is True


# ---------------------------------------------------------------------------
# RenameFunctionStage
# ---------------------------------------------------------------------------

class TestRenameFunctionStage:
    def test_renames(self):
        mod = _make_module()
        RenameFunctionStage(**{"from": "compute", "to": "calc"}).apply(mod)
        assert _fn(mod, "compute").rename == "calc"

    def test_does_not_rename_other(self):
        mod = _make_module()
        RenameFunctionStage(**{"from": "compute", "to": "calc"}).apply(mod)
        assert _fn(mod, "internal_helper").rename is None

    def test_regex(self):
        mod = _make_module()
        RenameFunctionStage(**{"from": "com.*", "to": "calc", "is_regex": True}).apply(mod)
        assert _fn(mod, "compute").rename == "calc"


# ---------------------------------------------------------------------------
# SuppressFunctionStage
# ---------------------------------------------------------------------------

class TestSuppressFunctionStage:
    def test_suppresses(self):
        mod = _make_module()
        SuppressFunctionStage(**{"pattern": "internal_helper"}).apply(mod)
        assert _fn(mod, "internal_helper").emit is False

    def test_does_not_suppress_other(self):
        mod = _make_module()
        SuppressFunctionStage(**{"pattern": "internal_helper"}).apply(mod)
        assert _fn(mod, "compute").emit is True

    def test_regex(self):
        mod = _make_module()
        SuppressFunctionStage(**{"pattern": "internal_.*", "is_regex": True}).apply(mod)
        assert _fn(mod, "internal_helper").emit is False


# ---------------------------------------------------------------------------
# ModifyFunctionStage
# ---------------------------------------------------------------------------

class TestModifyFunctionStage:
    def test_rename(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "rename": "calc"}).apply(mod)
        assert _fn(mod, "compute").rename == "calc"

    def test_remove(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "remove": True}).apply(mod)
        assert _fn(mod, "compute").emit is False

    def test_return_type_override(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "return_type": "float"}).apply(mod)
        assert _fn(mod, "compute").return_type_override == "float"

    def test_return_ownership(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "return_ownership": "cpp"}).apply(mod)
        assert _fn(mod, "compute").return_ownership == "cpp"

    def test_return_keep_alive(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "return_keep_alive": True}).apply(mod)
        assert _fn(mod, "compute").return_keep_alive is True

    def test_allow_thread(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "allow_thread": True}).apply(mod)
        assert _fn(mod, "compute").allow_thread is True

    def test_wrapper_code(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute", "wrapper_code": "return 0.0;"}).apply(mod)
        assert _fn(mod, "compute").wrapper_code == "return 0.0;"

    def test_no_op(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "compute"}).apply(mod)
        fn = _fn(mod, "compute")
        assert fn.rename is None
        assert fn.emit is True
        assert fn.return_type_override is None

    def test_wildcard(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "*", "allow_thread": True}).apply(mod)
        assert _fn(mod, "compute").allow_thread is True
        assert _fn(mod, "internal_helper").allow_thread is True

    def test_regex(self):
        mod = _make_module()
        ModifyFunctionStage(**{"function": "int.*", "remove": True, "function_is_regex": True}).apply(mod)
        assert _fn(mod, "internal_helper").emit is False
        assert _fn(mod, "compute").emit is True


# ---------------------------------------------------------------------------
# InjectConstructorStage
# ---------------------------------------------------------------------------

class TestInjectConstructorStage:
    def test_injects_ctor(self):
        mod = _make_module()
        InjectConstructorStage(**{
            "class": "Cls",
            "parameters": [{"name": "a", "type": "float"}],
        }).apply(mod)
        cls = _cls(mod)
        assert len(cls.constructors) == 2
        injected = cls.constructors[-1]
        assert len(injected.parameters) == 1
        assert injected.parameters[0].type_spelling == "float"

    def test_marks_as_overload(self):
        mod = _make_module()
        InjectConstructorStage(**{"class": "Cls", "parameters": []}).apply(mod)
        cls = _cls(mod)
        assert all(c.is_overload for c in cls.constructors)

    def test_injects_into_empty_class(self):
        cls = TIRClass(name="Empty", qualified_name="ns::Empty", namespace="ns")
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Empty": cls})
        InjectConstructorStage(**{"class": "Empty", "parameters": []}).apply(mod)
        assert len(cls.constructors) == 1
        assert cls.constructors[0].is_overload is False


# ---------------------------------------------------------------------------
# InjectFunctionStage
# ---------------------------------------------------------------------------

class TestInjectFunctionStage:
    def test_injects_function(self):
        mod = _make_module()
        InjectFunctionStage(**{
            "name": "create",
            "namespace": "ns",
            "return_type": "int",
            "parameters": [{"name": "v", "type": "int"}],
        }).apply(mod)
        injected = next(f for f in mod.functions if f.name == "create")
        assert injected.return_type == "int"
        assert injected.qualified_name == "ns::create"
        assert len(injected.parameters) == 1

    def test_no_namespace(self):
        mod = _make_module()
        InjectFunctionStage(**{"name": "helper", "return_type": "void"}).apply(mod)
        injected = next(f for f in mod.functions if f.name == "helper")
        assert injected.qualified_name == "helper"
        assert injected.namespace == ""


# ---------------------------------------------------------------------------
# SuppressBaseStage
# ---------------------------------------------------------------------------

class TestSuppressBaseStage:
    def test_suppresses_named_base(self):
        mod = _make_module()
        SuppressBaseStage(**{"class": "Cls", "base": "ns::Hidden"}).apply(mod)
        hidden = next(b for b in _cls(mod).bases if b.qualified_name == "ns::Hidden")
        assert hidden.emit is False

    def test_does_not_suppress_other_base(self):
        mod = _make_module()
        SuppressBaseStage(**{"class": "Cls", "base": "ns::Hidden"}).apply(mod)
        base = next(b for b in _cls(mod).bases if b.qualified_name == "ns::Base")
        assert base.emit is True

    def test_regex(self):
        mod = _make_module()
        SuppressBaseStage(**{"class": "Cls", "base": ".*Hidden", "is_regex": True}).apply(mod)
        hidden = next(b for b in _cls(mod).bases if b.qualified_name == "ns::Hidden")
        assert hidden.emit is False

    def test_wildcard_class(self):
        mod = _make_module()
        SuppressBaseStage(**{"class": "*", "base": "ns::Hidden"}).apply(mod)
        hidden = next(b for b in _cls(mod).bases if b.qualified_name == "ns::Hidden")
        assert hidden.emit is False
