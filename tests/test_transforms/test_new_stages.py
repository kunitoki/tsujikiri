"""Tests for new transform stages: modify_method, modify_argument, modify_field,
modify_constructor, remove_overload, inject_code, set_type_hint."""

from __future__ import annotations

import re
from typing import Any, List

import pytest

from tsujikiri.configurations import TransformSpec
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIRField,
    TIRMethod,
    TIRModule,
    TIRParameter,
)
from tsujikiri.transforms import (
    InjectCodeStage,
    InjectPropertyStage,
    ModifyArgumentStage,
    ModifyConstructorStage,
    ModifyFieldStage,
    ModifyMethodStage,
    RemoveOverloadStage,
    SetTypeHintStage,
    build_pipeline_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_module() -> TIRModule:
    methods = [
        TIRMethod(
            name="getValue",
            spelling="getValue",
            qualified_name="Cls::getValue",
            return_type="int",
            parameters=[],
        ),
        TIRMethod(
            name="process",
            spelling="process",
            qualified_name="Cls::process",
            return_type="void",
            parameters=[TIRParameter("x", "int")],
        ),
        TIRMethod(
            name="process",
            spelling="process",
            qualified_name="Cls::process",
            return_type="void",
            parameters=[TIRParameter("x", "float")],
            is_overload=True,
        ),
        TIRMethod(
            name="staticHelper",
            spelling="staticHelper",
            qualified_name="Cls::staticHelper",
            return_type="int",
            parameters=[TIRParameter("a", "int"), TIRParameter("b", "float")],
            is_static=True,
        ),
    ]
    ctors = [
        TIRConstructor(parameters=[]),
        TIRConstructor(parameters=[TIRParameter("v", "int")]),
    ]
    fields = [
        TIRField(name="data_", type_spelling="int"),
        TIRField(name="max_", type_spelling="float", is_const=True),
    ]
    cls = TIRClass(
        name="Cls",
        qualified_name="ns::Cls",
        namespace="ns",
        methods=list(methods),
        constructors=list(ctors),
        fields=list(fields),
    )
    return TIRModule(name="m", classes=[cls], class_by_name={"Cls": cls})


def _get_cls(mod: TIRModule, name: str = "Cls") -> TIRClass:
    return next(c for c in mod.classes if c.name == name)


def _get_method(mod: TIRModule, name: str, cls: str = "Cls") -> TIRMethod:
    return next(m for m in _get_cls(mod, cls).methods if m.name == name)


def _get_field(mod: TIRModule, name: str, cls: str = "Cls") -> TIRField:
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

    def test_return_keep_alive(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "return_keep_alive": True}).apply(mod)
        assert _get_method(mod, "getValue").return_keep_alive is True

    def test_allow_thread(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "allow_thread": True}).apply(mod)
        assert _get_method(mod, "getValue").allow_thread is True

    def test_wrapper_code(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "wrapper_code": "+[]() { return 42; }"}).apply(mod)
        assert _get_method(mod, "getValue").wrapper_code == "+[]() { return 42; }"

    def test_wildcard_method(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "*", "allow_thread": True}).apply(mod)
        for m in _get_cls(mod).methods:
            assert m.allow_thread is True

    def test_does_not_affect_other_class(self):
        other = TIRClass(
            name="Other",
            qualified_name="ns::Other",
            namespace="ns",
            methods=[TIRMethod("foo", "foo", "ns::Other::foo", "void")],
        )
        mod = _simple_module()
        mod.classes.append(other)
        ModifyMethodStage(**{"class": "Cls", "method": "getValue", "rename": "get"}).apply(mod)
        assert other.methods[0].rename is None

    def test_regex_method_pattern(self):
        mod = _simple_module()
        ModifyMethodStage(**{"class": "Cls", "method": "get.*", "method_is_regex": True, "rename": "getter"}).apply(mod)
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
        ModifyArgumentStage(**{"class": "Cls", "method": "process", "argument": "nonexistent", "rename": "y"}).apply(
            mod
        )
        process_methods = [m for m in _get_cls(mod).methods if m.name == "process"]
        for m in process_methods:
            assert m.parameters[0].rename is None


def _selector_module() -> TIRModule:
    """A class with multi-parameter methods and overloaded constructors."""
    cls = TIRClass(
        name="Cls",
        qualified_name="ns::Cls",
        namespace="ns",
        methods=[
            TIRMethod(
                name="draw",
                spelling="draw",
                qualified_name="ns::Cls::draw",
                return_type="void",
                parameters=[
                    TIRParameter("ctx_", "void *"),
                    TIRParameter("x_", "int"),
                    TIRParameter("y", "int"),
                    TIRParameter("userData", "void *"),
                ],
            ),
            TIRMethod(
                name="fill",
                spelling="fill",
                qualified_name="ns::Cls::fill",
                return_type="void",
                parameters=[TIRParameter("ctx_", "void *"), TIRParameter("color", "int")],
            ),
        ],
        constructors=[
            TIRConstructor(parameters=[TIRParameter("size_", "int"), TIRParameter("name_", "const char *")]),
            TIRConstructor(parameters=[TIRParameter("size_", "float")]),
        ],
    )
    return TIRModule(name="m", classes=[cls], class_by_name={"Cls": cls})


def _names(params: List[TIRParameter]) -> List[str]:
    return [p.rename or p.name for p in params if p.emit]


class TestModifyArgumentSelectors:
    def test_list_of_names(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "method": "draw", "argument": ["ctx_", "userData"], "remove": True}
        ).apply(mod)
        assert _names(_get_method(mod, "draw").parameters) == ["x_", "y"]
        assert _names(_get_method(mod, "fill").parameters) == ["ctx_", "color"]

    def test_mixed_names_indices_and_digit_strings(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "draw", "argument": [0, "2", "userData"], "doc": "d"}).apply(
            mod
        )
        assert [p.doc for p in _get_method(mod, "draw").parameters] == ["d", None, "d", "d"]

    def test_digit_string_scalar_is_index(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "fill", "argument": "1", "rename": "c"}).apply(mod)
        assert _names(_get_method(mod, "fill").parameters) == ["ctx_", "c"]

    def test_regex_names_across_methods(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "argument": "ctx_|userData", "argument_is_regex": True, "remove": True}
        ).apply(mod)
        assert _names(_get_method(mod, "draw").parameters) == ["x_", "y"]
        assert _names(_get_method(mod, "fill").parameters) == ["color"]

    def test_regex_is_full_match(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "method": "draw", "argument": "x", "argument_is_regex": True, "remove": True}
        ).apply(mod)
        assert _names(_get_method(mod, "draw").parameters) == ["ctx_", "x_", "y", "userData"]

    def test_list_of_regexes(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "method": "draw", "argument": [".*_", "^y$"], "argument_is_regex": True, "doc": "d"}
        ).apply(mod)
        assert [p.doc for p in _get_method(mod, "draw").parameters] == ["d", "d", "d", None]

    def test_wildcard_selects_all(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "fill", "argument": "*", "ownership": "cpp"}).apply(mod)
        assert [p.ownership for p in _get_method(mod, "fill").parameters] == ["cpp", "cpp"]

    def test_partial_matches_and_out_of_range_entries(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "method": "fill", "argument": [9, "nope", "color"], "rename": "c"}
        ).apply(mod)
        assert _names(_get_method(mod, "fill").parameters) == ["ctx_", "c"]

    def test_duplicate_selectors_apply_once(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "fill", "argument": [1, "color", "*"], "doc": "d"}).apply(mod)
        assert [p.doc for p in _get_method(mod, "fill").parameters] == ["d", "d"]

    def test_scalar_name_still_works(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "method": "draw", "argument": "y", "rename": "yy"}).apply(mod)
        assert _names(_get_method(mod, "draw").parameters) == ["ctx_", "x_", "yy", "userData"]

    def test_constructor_all_overloads(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(**{"class": "Cls", "constructor": True, "argument": "size_", "rename": "size"}).apply(mod)
        ctors = _get_cls(mod).constructors
        assert _names(ctors[0].parameters) == ["size", "name_"]
        assert _names(ctors[1].parameters) == ["size"]
        assert _names(_get_method(mod, "draw").parameters) == ["ctx_", "x_", "y", "userData"]

    def test_constructor_signature_restricts(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{
                "class": "Cls",
                "constructor": True,
                "signature": "int, const char *",
                "argument": ["size_", "name_"],
                "argument_is_regex": False,
                "doc": "d",
            }
        ).apply(mod)
        ctors = _get_cls(mod).constructors
        assert [p.doc for p in ctors[0].parameters] == ["d", "d"]
        assert [p.doc for p in ctors[1].parameters] == [None]

    def test_constructor_signature_without_match_is_noop(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "constructor": True, "signature": "double", "argument": "*", "remove": True}
        ).apply(mod)
        assert all(p.emit for c in _get_cls(mod).constructors for p in c.parameters)

    def test_constructor_false_targets_methods(self) -> None:
        mod = _selector_module()
        ModifyArgumentStage(
            **{"class": "Cls", "constructor": False, "method": "fill", "argument": 0, "remove": True}
        ).apply(mod)
        assert _names(_get_method(mod, "fill").parameters) == ["color"]
        assert all(p.emit for c in _get_cls(mod).constructors for p in c.parameters)

    def test_constructor_param_rename_via_pipeline(self) -> None:
        mod = _selector_module()
        pipeline = build_pipeline_from_config(
            [
                TransformSpec(
                    stage="modify_argument",
                    kwargs={"class": "Cls", "constructor": True, "signature": "float", "argument": 0, "rename": "f"},
                )
            ]
        )
        pipeline.run(mod)
        assert _names(_get_cls(mod).constructors[1].parameters) == ["f"]
        assert _names(_get_cls(mod).constructors[0].parameters) == ["size_", "name_"]

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"argument": []}, "must not be an empty list"),
            ({"argument": True}, "entries must be names or integer indices, got True"),
            ({"argument": [0, None]}, "got None"),
            ({"argument": [{"a": 1}]}, "got {'a': 1}"),
            ({"argument": 1.5}, "got 1.5"),
            (
                {"argument": 0, "constructor": True, "method": "draw"},
                "'constructor' and 'method' are mutually exclusive",
            ),
            ({"argument": 0, "signature": "int"}, "'signature' requires 'constructor: true'"),
        ],
    )
    def test_invalid_options_raise(self, kwargs: dict[str, Any], message: str) -> None:
        with pytest.raises(ValueError, match=re.escape(message)):
            ModifyArgumentStage(**{"class": "Cls", **kwargs})

    def test_invalid_options_reported_by_pipeline(self) -> None:
        with pytest.raises(ValueError, match="transform stage 'modify_argument'.*mutually exclusive"):
            build_pipeline_from_config(
                [
                    TransformSpec(
                        stage="modify_argument",
                        kwargs={"class": "Cls", "constructor": True, "method": "draw", "argument": 0},
                    )
                ]
            )


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

    def test_matching_signature_remove_false_is_noop(self):
        """Signature matches but remove=False — emit must stay True."""
        mod = _simple_module()
        ModifyConstructorStage(**{"class": "Cls", "signature": "", "remove": False}).apply(mod)
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
        InjectCodeStage(**{"target": "class", "class": "Cls", "position": "beginning", "code": "// cls start"}).apply(
            mod
        )
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
        InjectCodeStage(
            **{"target": "method", "class": "Cls", "method": "getValue", "position": "end", "code": "// after getValue"}
        ).apply(mod)
        m = _get_method(mod, "getValue")
        assert len(m.code_injections) == 1
        assert m.code_injections[0].code == "// after getValue"

    def test_inject_method_wildcard(self):
        mod = _simple_module()
        InjectCodeStage(
            **{"target": "method", "class": "Cls", "method": "*", "position": "beginning", "code": "// all methods"}
        ).apply(mod)
        for m in _get_cls(mod).methods:
            assert any(inj.code == "// all methods" for inj in m.code_injections)

    def test_inject_constructor_no_signature(self):
        mod = _simple_module()
        InjectCodeStage(
            **{"target": "constructor", "class": "Cls", "position": "beginning", "code": "// all ctors"}
        ).apply(mod)
        cls = _get_cls(mod)
        for ctor in cls.constructors:
            assert any(inj.code == "// all ctors" for inj in ctor.code_injections)

    def test_inject_constructor_with_signature(self):
        mod = _simple_module()
        InjectCodeStage(
            **{
                "target": "constructor",
                "class": "Cls",
                "signature": "int",
                "position": "end",
                "code": "// int ctor only",
            }
        ).apply(mod)
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

    def test_unknown_target_is_noop(self):
        """An unrecognised target silently does nothing (final elif is False → exit)."""
        mod = _simple_module()
        before_injections = len(mod.code_injections)
        InjectCodeStage(**{"target": "unknown_target", "position": "end", "code": "// noop"}).apply(mod)
        assert len(mod.code_injections) == before_injections


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
        assert cls.movable is None  # unchanged default
        assert cls.force_abstract is False  # unchanged default

    def test_no_match_is_noop(self):
        mod = _simple_module()
        SetTypeHintStage(**{"class": "Other", "force_abstract": True}).apply(mod)
        assert _get_cls(mod).force_abstract is False


# ---------------------------------------------------------------------------
# InjectPropertyStage
# ---------------------------------------------------------------------------


class TestInjectPropertyStage:
    def test_inject_readwrite_property(self):
        mod = _simple_module()
        InjectPropertyStage(
            **{
                "class": "Cls",
                "name": "arrivalMessage",
                "getter": "getArrivalMessage",
                "setter": "setArrivalMessage",
                "type": "std::string",
            }
        ).apply(mod)
        cls = _get_cls(mod)
        assert len(cls.properties) == 1
        prop = cls.properties[0]
        assert prop.name == "arrivalMessage"
        assert prop.getter == "getArrivalMessage"
        assert prop.setter == "setArrivalMessage"
        assert prop.type_spelling == "std::string"
        assert prop.emit is True

    def test_inject_readonly_property(self):
        mod = _simple_module()
        InjectPropertyStage(
            **{
                "class": "Cls",
                "name": "label",
                "getter": "getLabel",
            }
        ).apply(mod)
        prop = _get_cls(mod).properties[0]
        assert prop.setter is None
        assert prop.getter == "getLabel"

    def test_inject_property_no_match_is_noop(self):
        mod = _simple_module()
        InjectPropertyStage(
            **{
                "class": "Other",
                "name": "x",
                "getter": "getX",
            }
        ).apply(mod)
        assert len(_get_cls(mod).properties) == 0

    def test_inject_multiple_properties(self):
        mod = _simple_module()
        InjectPropertyStage(**{"class": "Cls", "name": "a", "getter": "getA"}).apply(mod)
        InjectPropertyStage(**{"class": "Cls", "name": "b", "getter": "getB", "setter": "setB"}).apply(mod)
        props = _get_cls(mod).properties
        assert len(props) == 2
        assert props[0].name == "a"
        assert props[1].name == "b"
