"""Tests for new transform stages: modify_method, modify_argument, modify_field,
modify_constructor, remove_overload, inject_code, set_type_hint."""

from __future__ import annotations

import io

import pytest

from tsujikiri.ir import (
    IRClass,
    IRCodeInjection,
    IRConstructor,
    IRField,
    IRMethod,
    IRModule,
    IRParameter,
)
from tsujikiri.transforms import (
    InjectCodeStage,
    ModifyArgumentStage,
    ModifyConstructorStage,
    ModifyFieldStage,
    ModifyMethodStage,
    RemoveOverloadStage,
    SetTypeHintStage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_module() -> IRModule:
    methods = [
        IRMethod(
            name="getValue", spelling="getValue",
            qualified_name="Cls::getValue", return_type="int",
            parameters=[],
        ),
        IRMethod(
            name="process", spelling="process",
            qualified_name="Cls::process", return_type="void",
            parameters=[IRParameter("x", "int")],
        ),
        IRMethod(
            name="process", spelling="process",
            qualified_name="Cls::process", return_type="void",
            parameters=[IRParameter("x", "float")],
            is_overload=True,
        ),
        IRMethod(
            name="staticHelper", spelling="staticHelper",
            qualified_name="Cls::staticHelper", return_type="int",
            parameters=[IRParameter("a", "int"), IRParameter("b", "float")],
            is_static=True,
        ),
    ]
    ctors = [
        IRConstructor(parameters=[]),
        IRConstructor(parameters=[IRParameter("v", "int")]),
    ]
    fields = [
        IRField(name="data_", type_spelling="int"),
        IRField(name="max_", type_spelling="float", is_const=True),
    ]
    cls = IRClass(
        name="Cls", qualified_name="ns::Cls", namespace="ns",
        methods=list(methods),
        constructors=list(ctors),
        fields=list(fields),
    )
    return IRModule(name="m", classes=[cls], class_by_name={"Cls": cls})


def _get_cls(mod: IRModule, name: str = "Cls") -> IRClass:
    return next(c for c in mod.classes if c.name == name)


def _get_method(mod: IRModule, name: str, cls: str = "Cls") -> IRMethod:
    return next(m for m in _get_cls(mod, cls).methods if m.name == name)


def _get_field(mod: IRModule, name: str, cls: str = "Cls") -> IRField:
    return next(f for f in _get_cls(mod, cls).fields if f.name == name)


# ---------------------------------------------------------------------------
# ModifyMethodStage
# ---------------------------------------------------------------------------

class TestModifyMethodStage:
    def test_rename(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "rename": "get"}).apply(mod)
        assert _get_method(mod, "getValue").rename == "get"

    def test_remove(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "remove": True}).apply(mod)
        assert _get_method(mod, "getValue").emit is False

    def test_return_type_override(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "return_type": "double"}).apply(mod)
        assert _get_method(mod, "getValue").return_type_override == "double"

    def test_return_ownership(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "return_ownership": "cpp"}).apply(mod)
        assert _get_method(mod, "getValue").return_ownership == "cpp"

    def test_allow_thread(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "allow_thread": True}).apply(mod)
        assert _get_method(mod, "getValue").allow_thread is True

    def test_wrapper_code(self):
        mod = _simple_module()
        ModifyMethodStage(**{
            "class": "Cls", "method": "getValue", "wrapper_code": "+[]() { return 42; }"
        }).apply(mod)
        assert _get_method(mod, "getValue").wrapper_code == "+[]() { return 42; }"

    def test_wildcard_method(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "*", "allow_thread": True}).apply(mod)
        for m in _get_cls(mod).methods:
            assert m.allow_thread is True

    def test_does_not_affect_other_class(self):
        other = IRClass(name="Other", qualified_name="ns::Other", namespace="ns",
                        methods=[IRMethod("foo", "foo", "ns::Other::foo", "void")])
        mod = _simple_module()
        mod.classes.append(other)
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "rename": "get"}).apply(mod)
        assert other.methods[0].rename is None

    def test_regex_method_pattern(self):
        mod = _simple_module()
        ModifyMethodStage(**{
            "class": "Cls", "method": "get.*", "method_is_regex": True, "rename": "getter"
        }).apply(mod)
        assert _get_method(mod, "getValue").rename == "getter"
        assert _get_method(mod, "process").rename is None


# ---------------------------------------------------------------------------
# ModifyArgumentStage
# ---------------------------------------------------------------------------

class TestModifyArgumentStage:
    def test_rename_by_name(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "x", "rename": "val"}).apply(mod)
        # Both process overloads have param "x"
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].rename == "val"

    def test_rename_by_index(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "staticHelper", "argument": 0, "rename": "first"}).apply(mod)
        helper = _get_method(mod, "staticHelper")
        assert helper.parameters[0].rename == "first"
        assert helper.parameters[1].rename is None

    def test_remove_param(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "staticHelper", "argument": "b", "remove": True}).apply(mod)
        helper = _get_method(mod, "staticHelper")
        assert helper.parameters[1].emit is False
        assert helper.parameters[0].emit is True

    def test_type_override(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "x", "type": "double"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].type_override == "double"

    def test_default_override(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "x", "default": "0"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].default_override == "0"

    def test_ownership(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "x", "ownership": "cpp"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].ownership == "cpp"

    def test_index_out_of_range_is_noop(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "getValue", "argument": 5, "rename": "x"}).apply(mod)
        assert _get_method(mod, "getValue").parameters == []

    def test_name_not_found_is_noop(self):
        mod = _simple_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "nonexistent", "rename": "y"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].rename is None


# ---------------------------------------------------------------------------
# ModifyFieldStage
# ---------------------------------------------------------------------------

class TestModifyFieldStage:
    def test_rename(self):
        mod = _simple_module()
        ModifyFieldStage(**{"class": "Cls", "field": "data_", "rename": "data"}).apply(mod)
        assert _get_field(mod, "data_").rename == "data"

    def test_remove(self):
        mod = _simple_module()
        ModifyFieldStage(**{"class": "Cls", "field": "data_", "remove": True}).apply(mod)
        assert _get_field(mod, "data_").emit is False

    def test_read_only(self):
        mod = _simple_module()
        ModifyFieldStage(**{"class": "Cls", "field": "data_", "read_only": True}).apply(mod)
        assert _get_field(mod, "data_").read_only is True

    def test_wildcard_field(self):
        mod = _simple_module()
        ModifyFieldStage(**{"class": "Cls", "field": "*", "read_only": True}).apply(mod)
        for f in _get_cls(mod).fields:
            assert f.read_only is True

    def test_does_not_affect_other_field(self):
        mod = _simple_module()
        ModifyFieldStage(**{"class": "Cls", "field": "data_", "rename": "data"}).apply(mod)
        assert _get_field(mod, "max_").rename is None


# ---------------------------------------------------------------------------
# ModifyConstructorStage
# ---------------------------------------------------------------------------

class TestModifyConstructorStage:
    def test_remove_default_ctor(self):
        mod = _simple_module()
        ModifyConstructorStage(**{"class": "Cls", "signature": "", "remove": True}).apply(mod)
        cls = _get_cls(mod)
        default_ctors = [c for c in cls.constructors if not c.parameters]
        assert all(c.emit is False for c in default_ctors)

    def test_remove_parameterized_ctor(self):
        mod = _simple_module()
        ModifyConstructorStage(**{"class": "Cls", "signature": "int", "remove": True}).apply(mod)
        cls = _get_cls(mod)
        int_ctors = [c for c in cls.constructors if c.parameters and c.parameters[0].type_spelling == "int"]
        assert all(c.emit is False for c in int_ctors)

    def test_no_match_is_noop(self):
        mod = _simple_module()
        ModifyConstructorStage(**{"class": "Cls", "signature": "double", "remove": True}).apply(mod)
        cls = _get_cls(mod)
        assert all(c.emit is True for c in cls.constructors)

    def test_does_not_affect_wrong_class(self):
        mod = _simple_module()
        ModifyConstructorStage(**{"class": "Other", "signature": "int", "remove": True}).apply(mod)
        cls = _get_cls(mod)
        assert all(c.emit is True for c in cls.constructors)


# ---------------------------------------------------------------------------
# RemoveOverloadStage
# ---------------------------------------------------------------------------

class TestRemoveOverloadStage:
    def test_removes_only_matching_overload(self):
        mod = _simple_module()
        RemoveOverloadStage(**{"class": "Cls", "method": "process", "signature": "int"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        int_overloads = [m for m in process_methods if m.parameters[0].type_spelling == "int"]
        float_overloads = [m for m in process_methods if m.parameters[0].type_spelling == "float"]
        assert all(m.emit is False for m in int_overloads)
        assert all(m.emit is True for m in float_overloads)

    def test_no_match_is_noop(self):
        mod = _simple_module()
        RemoveOverloadStage(**{"class": "Cls", "method": "process", "signature": "double"}).apply(mod)
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        assert all(m.emit is True for m in process_methods)

    def test_does_not_affect_other_methods(self):
        mod = _simple_module()
        RemoveOverloadStage(**{"class": "Cls", "method": "process", "signature": "int"}).apply(mod)
        assert _get_method(mod, "getValue").emit is True


# ---------------------------------------------------------------------------
# InjectCodeStage
# ---------------------------------------------------------------------------

class TestInjectCodeStage:
    def test_inject_module_beginning(self):
        mod = _simple_module()
        InjectCodeStage(**{"target": "module", "position": "beginning", "code": "// module start"}).apply(mod)
        assert len(mod.code_injections) == 1
        assert mod.code_injections[0].position == "beginning"
        assert mod.code_injections[0].code == "// module start"

    def test_inject_module_end(self):
        mod = _simple_module()
        InjectCodeStage(**{"target": "module", "position": "end", "code": "// module end"}).apply(mod)
        assert mod.code_injections[0].position == "end"

    def test_inject_class_beginning(self):
        mod = _simple_module()
        InjectCodeStage(**{"target": "class", "class": "Cls", "position": "beginning", "code": "// cls start"}).apply(mod)
        cls = _get_cls(mod)
        assert len(cls.code_injections) == 1
        assert cls.code_injections[0].position == "beginning"
        assert cls.code_injections[0].code == "// cls start"

    def test_inject_class_end(self):
        mod = _simple_module()
        InjectCodeStage(**{"target": "class", "class": "Cls", "position": "end", "code": "// cls end"}).apply(mod)
        cls = _get_cls(mod)
        assert cls.code_injections[0].position == "end"

    def test_inject_method(self):
        mod = _simple_module()
        InjectCodeStage(**{
            "target": "method", "class": "Cls", "method": "getValue",
            "position": "end", "code": "// after getValue"
        }).apply(mod)
        m = _get_method(mod, "getValue")
        assert len(m.code_injections) == 1
        assert m.code_injections[0].code == "// after getValue"

    def test_inject_method_wildcard(self):
        mod = _simple_module()
        InjectCodeStage(**{
            "target": "method", "class": "Cls", "method": "*",
            "position": "beginning", "code": "// all methods"
        }).apply(mod)
        for m in _get_cls(mod).methods:
            assert any(inj.code == "// all methods" for inj in m.code_injections)

    def test_inject_constructor_no_signature(self):
        mod = _simple_module()
        InjectCodeStage(**{
            "target": "constructor", "class": "Cls",
            "position": "beginning", "code": "// all ctors"
        }).apply(mod)
        cls = _get_cls(mod)
        for ctor in cls.constructors:
            assert any(inj.code == "// all ctors" for inj in ctor.code_injections)

    def test_inject_constructor_with_signature(self):
        mod = _simple_module()
        InjectCodeStage(**{
            "target": "constructor", "class": "Cls",
            "signature": "int",
            "position": "end", "code": "// int ctor only"
        }).apply(mod)
        cls = _get_cls(mod)
        int_ctor = next(c for c in cls.constructors if c.parameters and c.parameters[0].type_spelling == "int")
        default_ctor = next(c for c in cls.constructors if not c.parameters)
        assert any(inj.code == "// int ctor only" for inj in int_ctor.code_injections)
        assert not any(inj.code == "// int ctor only" for inj in default_ctor.code_injections)

    def test_multiple_injections_accumulate(self):
        mod = _simple_module()
        InjectCodeStage(**{"target": "module", "position": "beginning", "code": "// first"}).apply(mod)
        InjectCodeStage(**{"target": "module", "position": "beginning", "code": "// second"}).apply(mod)
        assert len(mod.code_injections) == 2


# ---------------------------------------------------------------------------
# SetTypeHintStage
# ---------------------------------------------------------------------------

class TestSetTypeHintStage:
    def test_copyable_false(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "copyable": False}).apply(mod)
        assert _get_cls(mod).copyable is False

    def test_copyable_true(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "copyable": True}).apply(mod)
        assert _get_cls(mod).copyable is True

    def test_movable(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "movable": True}).apply(mod)
        assert _get_cls(mod).movable is True

    def test_force_abstract(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "force_abstract": True}).apply(mod)
        assert _get_cls(mod).force_abstract is True

    def test_all_hints_at_once(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "copyable": False, "movable": True, "force_abstract": True}).apply(mod)
        cls = _get_cls(mod)
        assert cls.copyable is False
        assert cls.movable is True
        assert cls.force_abstract is True

    def test_does_not_affect_unmentioned_hints(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Cls", "copyable": False}).apply(mod)
        cls = _get_cls(mod)
        assert cls.movable is None          # unchanged default
        assert cls.force_abstract is False  # unchanged default

    def test_no_match_is_noop(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Other", "force_abstract": True}).apply(mod)
        assert _get_cls(mod).force_abstract is False
