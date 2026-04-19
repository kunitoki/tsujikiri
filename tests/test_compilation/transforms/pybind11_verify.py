"""pybind11 runtime verification for the transforms scenario.

Run with: python pybind11_verify.py
Requires PYTHONPATH to contain the directory with the built transforms extension module.
"""
from __future__ import annotations

import sys

import transforms as trf  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# rename_class
# ---------------------------------------------------------------------------

def test_rename_class() -> None:
    assert hasattr(trf, "Manager"), "rename_class: Manager present"
    assert not hasattr(trf, "WidgetManager"), "rename_class: WidgetManager absent"
    m = trf.Manager()
    assert m.get_count() == 0


# ---------------------------------------------------------------------------
# suppress_class
# ---------------------------------------------------------------------------

def test_suppress_class() -> None:
    assert not hasattr(trf, "WidgetInternal"), "suppress_class: WidgetInternal absent"


# ---------------------------------------------------------------------------
# rename_method / suppress_method / inject_method
# ---------------------------------------------------------------------------

def test_method_transforms() -> None:
    w = trf.Widget(5)
    assert w.get_id() == 5, "rename_method: get_id works"
    assert not hasattr(w, "legacyReset"), "suppress_method: legacyReset absent"
    desc = w.describe()
    assert isinstance(desc, str) and len(desc) > 0, "inject_method: describe returns string"


# ---------------------------------------------------------------------------
# modify_method / modify_argument / exception_policy
# ---------------------------------------------------------------------------

def test_modify_method() -> None:
    w = trf.Widget(10)
    w.process_data(3)
    assert w.get_id() == 13, "modify_method: process_data adds to id"


def test_modify_argument() -> None:
    w = trf.Widget()
    # After modify_argument: rawOption -> option, rawName -> name
    w.configure(option=42, name="hello")
    assert w.get_id() == 42, "modify_argument: keyword arg 'option' works"


# ---------------------------------------------------------------------------
# remove_overload
# ---------------------------------------------------------------------------

def test_remove_overload() -> None:
    w = trf.Widget()
    w.update(7)
    assert w.get_id() == 7, "remove_overload: update(int) works"
    w.update(3.14)
    assert w.get_id() == 3, "remove_overload: update(double) works"


# ---------------------------------------------------------------------------
# overload_priority
# ---------------------------------------------------------------------------

def test_overload_priority() -> None:
    w = trf.Widget()
    assert abs(w.compute(3) - 9.0) < 0.001, "overload_priority: compute(int) = 9"
    assert abs(w.compute(2.5) - 6.25) < 0.001, "overload_priority: compute(double) = 6.25"


# ---------------------------------------------------------------------------
# inject_property
# ---------------------------------------------------------------------------

def test_inject_property() -> None:
    w = trf.Widget(0)
    w.raw_value = 7
    assert w.raw_value == 7, "inject_property: raw_value write/read"
    assert w.get_id() == 7, "inject_property: raw_value aliases id_"


# ---------------------------------------------------------------------------
# modify_constructor / inject_constructor
# ---------------------------------------------------------------------------

def test_constructor_transforms() -> None:
    w = trf.Widget(1, 2)
    assert w.get_id() == 3, "inject_constructor: Widget(1,2).id == 1+2 == 3"


# ---------------------------------------------------------------------------
# modify_field (rename + remove)
# ---------------------------------------------------------------------------

def test_modify_field() -> None:
    w = trf.Widget(99)
    assert w.id == 99, "modify_field rename: id field accessible"
    assert not hasattr(w, "cache_name_"), "modify_field remove: cache_name_ absent"
    w.id = 55
    assert w.id == 55, "modify_field rename: id field writable"


# ---------------------------------------------------------------------------
# rename_enum / rename_enum_value / suppress_enum / suppress_enum_value
# ---------------------------------------------------------------------------

def test_enum_transforms() -> None:
    assert hasattr(trf, "Color"), "rename_enum: Color present"
    assert not hasattr(trf, "OldColor"), "rename_enum: OldColor absent"
    assert trf.Color.Crimson is not None, "rename_enum_value: Crimson present"
    assert not hasattr(trf.Color, "Red"), "rename_enum_value: Red absent"
    assert not hasattr(trf.Color, "Alpha"), "suppress_enum_value: Alpha absent"
    assert not hasattr(trf, "WidgetState"), "suppress_enum: WidgetState absent"


# ---------------------------------------------------------------------------
# rename_function / suppress_function / inject_function / modify_function
# ---------------------------------------------------------------------------

def test_function_transforms() -> None:
    assert hasattr(trf, "compute_score"), "rename_function: compute_score present"
    assert trf.compute_score(3) == 9, "rename_function: compute_score(3) == 9"
    assert not hasattr(trf, "computeWidgetScore"), "rename_function: computeWidgetScore absent"

    assert not hasattr(trf, "internal_utility"), "suppress_function: internalUtility absent"

    assert hasattr(trf, "make_widget"), "inject_function: make_widget present"
    w = trf.make_widget(5)
    assert w.get_id() == 5, "inject_function: make_widget creates Widget with id 5"

    assert hasattr(trf, "process_widget"), "modify_function: process_widget present"
    assert abs(trf.process_widget(2.0) - 4.0) < 0.001, "modify_function: process_widget(2.0) == 4.0"


# ---------------------------------------------------------------------------
# suppress_base
# ---------------------------------------------------------------------------

def test_suppress_base() -> None:
    dw = trf.DerivedWidget(3)
    assert dw.get_id() == 3, "suppress_base: DerivedWidget inherits Widget methods"
    assert not hasattr(dw, "helperMethod"), "suppress_base: BaseHelper methods not exposed"


# ---------------------------------------------------------------------------
# set_type_hint: SharedNode with shared_ptr holder
# ---------------------------------------------------------------------------

def test_set_type_hint() -> None:
    n = trf.SharedNode(10)
    assert n.get_value() == 10, "set_type_hint: SharedNode.get_value works"
    n2 = n.clone()
    assert n2.get_value() == 10, "set_type_hint: SharedNode.clone() returns SharedNode"


# ---------------------------------------------------------------------------
# expose_protected: Widget.on_render callable from Python subclass
# ---------------------------------------------------------------------------

def test_expose_protected_widget() -> None:
    class MyWidget(trf.Widget):
        def on_render(self) -> None:
            MyWidget._called = True

    MyWidget._called = False
    w = MyWidget(1)
    w.on_render()
    assert MyWidget._called, "expose_protected Widget: on_render override called"


# ---------------------------------------------------------------------------
# expose_protected: SharedNode.compute_value callable from Python subclass
# ---------------------------------------------------------------------------

def test_expose_protected_shared_node() -> None:
    class MyNode(trf.SharedNode):
        def compute_value(self) -> int:
            return 99

    n = MyNode(5)
    assert n.compute_value() == 99, "expose_protected SharedNode: compute_value override works"


# ---------------------------------------------------------------------------
# resolve_using_declarations
# ---------------------------------------------------------------------------

def test_resolve_using_declarations() -> None:
    ew = trf.ExtendedWidget()
    assert hasattr(ew, "extended_method"), "resolve_using_declarations: extended_method present"
    assert hasattr(ew, "extended_value"), "resolve_using_declarations: extended_value present"
    assert ew.extended_value() == 0, "resolve_using_declarations: initial extended_value == 0"
    ew.extended_method(7)
    assert ew.extended_value() == 7, "resolve_using_declarations: extended_value after method call"


# ---------------------------------------------------------------------------
# mark_deprecated: increment still callable (metadata only)
# ---------------------------------------------------------------------------

def test_mark_deprecated() -> None:
    m = trf.Manager()
    m.increment()
    assert m.get_count() == 1, "mark_deprecated: increment still callable"


# ---------------------------------------------------------------------------
# register_exception: TransformError catchable as Python exception
# ---------------------------------------------------------------------------

def test_register_exception() -> None:
    assert hasattr(trf, "TransformError"), "register_exception: TransformError class present"
    try:
        trf.throw_transform_error("test error")
        assert False, "throw_transform_error should have raised"
    except trf.TransformError:
        pass  # expected — register_exception wired correctly


# ---------------------------------------------------------------------------
# expand_spaceship: Score comparison operators via __lt__, __le__, __eq__, etc.
# ---------------------------------------------------------------------------

def test_expand_spaceship() -> None:
    s1 = trf.Score(1)
    s2 = trf.Score(2)
    assert s1 < s2, "expand_spaceship: s1 < s2"
    assert s1 <= s2, "expand_spaceship: s1 <= s2"
    assert s2 > s1, "expand_spaceship: s2 > s1"
    assert s2 >= s1, "expand_spaceship: s2 >= s1"
    assert s1 == s1, "expand_spaceship: s1 == s1"
    assert s1 != s2, "expand_spaceship: s1 != s2"


if __name__ == "__main__":
    test_rename_class()
    test_suppress_class()
    test_method_transforms()
    test_modify_method()
    test_modify_argument()
    test_remove_overload()
    test_overload_priority()
    test_inject_property()
    test_constructor_transforms()
    test_modify_field()
    test_enum_transforms()
    test_function_transforms()
    test_suppress_base()
    test_set_type_hint()
    test_expose_protected_widget()
    test_expose_protected_shared_node()
    test_resolve_using_declarations()
    test_mark_deprecated()
    test_register_exception()
    test_expand_spaceship()
    print("transforms pybind11 bindings: all checks passed")
    sys.exit(0)
