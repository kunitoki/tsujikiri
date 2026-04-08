"""Tests for filters.py — FilterEngine whitelist/blacklist/regex logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import (
    ClassFilter,
    ConstructorFilter,
    EnumFilter,
    FieldFilter,
    FilterConfig,
    FilterPattern,
    FunctionFilter,
    MethodFilter,
    SourceFilter,
)
from tsujikiri.filters import FilterEngine
from tsujikiri.ir import (
    IRClass,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
)

HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_with_classes(*names: str, source_file: str | None = None) -> IRModule:
    classes = [
        IRClass(name=n, qualified_name=f"ns::{n}", namespace="ns",
                source_file=source_file)
        for n in names
    ]
    return IRModule(name="m", classes=classes,
                    class_by_name={c.name: c for c in classes})


def _module_with_methods(*method_names: str) -> tuple[IRModule, IRClass]:
    methods = [
        IRMethod(name=n, spelling=n, qualified_name=f"Cls::{n}", return_type="void")
        for n in method_names
    ]
    cls = IRClass(name="Cls", qualified_name="ns::Cls", namespace="ns", methods=list(methods))
    mod = IRModule(name="m", classes=[cls], class_by_name={"Cls": cls})
    return mod, cls


def _engine(**kwargs) -> FilterEngine:
    return FilterEngine(FilterConfig(**kwargs))


# ---------------------------------------------------------------------------
# Class filtering
# ---------------------------------------------------------------------------

class TestClassBlacklist:
    def test_exact_match_suppresses(self):
        mod = _module_with_classes("Foo", "Bar")
        FilterEngine(FilterConfig(
            classes=ClassFilter(blacklist=[FilterPattern("Bar")])
        )).apply(mod)
        assert mod.classes[0].emit is True
        assert mod.classes[1].emit is False

    def test_regex_match_suppresses(self):
        mod = _module_with_classes("FooImpl", "Bar")
        FilterEngine(FilterConfig(
            classes=ClassFilter(blacklist=[FilterPattern(".*Impl$", is_regex=True)])
        )).apply(mod)
        assert mod.classes[0].emit is False
        assert mod.classes[1].emit is True

    def test_no_match_keeps_all(self):
        mod = _module_with_classes("Foo", "Bar")
        FilterEngine(FilterConfig(
            classes=ClassFilter(blacklist=[FilterPattern("Baz")])
        )).apply(mod)
        assert all(c.emit for c in mod.classes)


class TestClassWhitelist:
    def test_empty_whitelist_keeps_all(self):
        mod = _module_with_classes("Foo", "Bar")
        FilterEngine(FilterConfig(classes=ClassFilter(whitelist=[]))).apply(mod)
        assert all(c.emit for c in mod.classes)

    def test_non_empty_whitelist_suppresses_others(self):
        mod = _module_with_classes("Foo", "Bar", "Baz")
        FilterEngine(FilterConfig(
            classes=ClassFilter(whitelist=[FilterPattern("Foo")])
        )).apply(mod)
        emitted = [c.name for c in mod.classes if c.emit]
        assert emitted == ["Foo"]

    def test_regex_whitelist(self):
        mod = _module_with_classes("MyFoo", "MyBar", "Other")
        FilterEngine(FilterConfig(
            classes=ClassFilter(whitelist=[FilterPattern("My.*", is_regex=True)])
        )).apply(mod)
        emitted = {c.name for c in mod.classes if c.emit}
        assert emitted == {"MyFoo", "MyBar"}


class TestClassInternal:
    def test_internal_suppresses(self):
        mod = _module_with_classes("Public", "BaseHelper")
        FilterEngine(FilterConfig(
            classes=ClassFilter(internal=[FilterPattern("BaseHelper")])
        )).apply(mod)
        assert mod.classes[0].emit is True
        assert mod.classes[1].emit is False


class TestSourceFileFilter:
    def test_exclude_glob_suppresses(self):
        mod = _module_with_classes("Foo", source_file="/path/to/foo.mm")
        FilterEngine(FilterConfig(
            sources=SourceFilter(exclude_patterns=["*.mm"])
        )).apply(mod)
        assert mod.classes[0].emit is False

    def test_non_matching_glob_keeps(self):
        mod = _module_with_classes("Foo", source_file="/path/to/foo.hpp")
        FilterEngine(FilterConfig(
            sources=SourceFilter(exclude_patterns=["*.mm"])
        )).apply(mod)
        assert mod.classes[0].emit is True


# ---------------------------------------------------------------------------
# Method filtering
# ---------------------------------------------------------------------------

class TestMethodFilter:
    def test_global_blacklist(self):
        mod, cls = _module_with_methods("keep", "remove")
        FilterEngine(FilterConfig(
            methods=MethodFilter(global_blacklist=[FilterPattern("remove")])
        )).apply(mod)
        emitted = [m.name for m in cls.methods if m.emit]
        assert emitted == ["keep"]

    def test_global_blacklist_regex(self):
        mod, cls = _module_with_methods("operator+", "getValue", "operator==")
        FilterEngine(FilterConfig(
            methods=MethodFilter(global_blacklist=[FilterPattern("operator.*", is_regex=True)])
        )).apply(mod)
        emitted = [m.name for m in cls.methods if m.emit]
        assert emitted == ["getValue"]

    def test_per_class_blacklist(self):
        mod, cls = _module_with_methods("keep", "perClassOnly")
        FilterEngine(FilterConfig(
            methods=MethodFilter(per_class={"Cls": [FilterPattern("perClassOnly")]})
        )).apply(mod)
        emitted = [m.name for m in cls.methods if m.emit]
        assert emitted == ["keep"]

    def test_per_class_does_not_affect_other_classes(self):
        methods = [
            IRMethod(name="perClassOnly", spelling="perClassOnly",
                     qualified_name="Other::perClassOnly", return_type="void")
        ]
        other_cls = IRClass(name="Other", qualified_name="ns::Other",
                            namespace="ns", methods=methods)
        mod = IRModule(name="m", classes=[other_cls],
                       class_by_name={"Other": other_cls})
        FilterEngine(FilterConfig(
            methods=MethodFilter(per_class={"Cls": [FilterPattern("perClassOnly")]})
        )).apply(mod)
        assert other_cls.methods[0].emit is True


# ---------------------------------------------------------------------------
# Constructor filtering
# ---------------------------------------------------------------------------

class TestConstructorFilter:
    def _cls_with_ctors(self, *param_lists):
        ctors = [IRConstructor(parameters=[IRParameter("x", t) for t in pl])
                 for pl in param_lists]
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns", constructors=ctors)
        mod = IRModule(name="m", classes=[cls], class_by_name={"C": cls})
        return mod, cls

    def test_include_false_suppresses_all(self):
        mod, cls = self._cls_with_ctors([], ["int"])
        FilterEngine(FilterConfig(
            constructors=ConstructorFilter(include=False)
        )).apply(mod)
        assert all(not c.emit for c in cls.constructors)

    def test_include_true_keeps_all(self):
        mod, cls = self._cls_with_ctors([], ["int"])
        FilterEngine(FilterConfig(
            constructors=ConstructorFilter(include=True)
        )).apply(mod)
        assert all(c.emit for c in cls.constructors)

    def test_signature_filter(self):
        mod, cls = self._cls_with_ctors([], ["int"])
        FilterEngine(FilterConfig(
            constructors=ConstructorFilter(
                include=True, signatures=[FilterPattern("int")]
            )
        )).apply(mod)
        emitted = [c for c in cls.constructors if c.emit]
        assert len(emitted) == 1
        assert emitted[0].parameters[0].type_spelling == "int"


# ---------------------------------------------------------------------------
# Field filtering
# ---------------------------------------------------------------------------

class TestFieldFilter:
    def _cls_with_fields(self, *names):
        fields = [IRField(name=n, type_spelling="int") for n in names]
        cls = IRClass(name="C", qualified_name="ns::C", namespace="ns", fields=list(fields))
        mod = IRModule(name="m", classes=[cls], class_by_name={"C": cls})
        return mod, cls

    def test_global_blacklist(self):
        mod, cls = self._cls_with_fields("keep_", "pimpl_")
        FilterEngine(FilterConfig(
            fields=FieldFilter(global_blacklist=[FilterPattern("pimpl_")])
        )).apply(mod)
        emitted = [f.name for f in cls.fields if f.emit]
        assert emitted == ["keep_"]

    def test_per_class_blacklist(self):
        mod, cls = self._cls_with_fields("keep_", "secret_")
        FilterEngine(FilterConfig(
            fields=FieldFilter(per_class={"C": [FilterPattern("secret_")]})
        )).apply(mod)
        emitted = [f.name for f in cls.fields if f.emit]
        assert emitted == ["keep_"]


# ---------------------------------------------------------------------------
# Function filtering
# ---------------------------------------------------------------------------

class TestFunctionFilter:
    def _mod_with_fns(*names):
        fns = [IRFunction(name=n, qualified_name=f"ns::{n}",
                          namespace="ns", return_type="void")
               for n in names]
        return IRModule(name="m", functions=list(fns))

    def test_blacklist(self):
        mod = IRModule(name="m", functions=[
            IRFunction(name="keep", qualified_name="ns::keep", namespace="ns", return_type="void"),
            IRFunction(name="skip", qualified_name="ns::skip", namespace="ns", return_type="void"),
        ])
        FilterEngine(FilterConfig(
            functions=FunctionFilter(blacklist=[FilterPattern("skip")])
        )).apply(mod)
        emitted = [f.name for f in mod.functions if f.emit]
        assert emitted == ["keep"]

    def test_whitelist(self):
        mod = IRModule(name="m", functions=[
            IRFunction(name="foo", qualified_name="ns::foo", namespace="ns", return_type="void"),
            IRFunction(name="bar", qualified_name="ns::bar", namespace="ns", return_type="void"),
        ])
        FilterEngine(FilterConfig(
            functions=FunctionFilter(whitelist=[FilterPattern("foo")])
        )).apply(mod)
        emitted = [f.name for f in mod.functions if f.emit]
        assert emitted == ["foo"]


# ---------------------------------------------------------------------------
# Enum filtering
# ---------------------------------------------------------------------------

class TestEnumFilter:
    def _mod_with_enums(*names):
        enums = [IREnum(name=n, qualified_name=f"ns::{n}") for n in names]
        return IRModule(name="m", enums=list(enums))

    def test_blacklist(self):
        mod = IRModule(name="m", enums=[
            IREnum(name="Keep", qualified_name="ns::Keep"),
            IREnum(name="Skip", qualified_name="ns::Skip"),
        ])
        FilterEngine(FilterConfig(
            enums=EnumFilter(blacklist=[FilterPattern("Skip")])
        )).apply(mod)
        emitted = [e.name for e in mod.enums if e.emit]
        assert emitted == ["Keep"]
