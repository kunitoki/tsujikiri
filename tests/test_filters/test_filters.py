"""Tests for filters.py — FilterEngine whitelist/blacklist/regex logic."""

from __future__ import annotations

from pathlib import Path

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
from tsujikiri.tir import (
    TIRBase,
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)

HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_with_classes(*names: str, source_file: str | None = None) -> TIRModule:
    classes = [
        TIRClass(name=n, qualified_name=f"ns::{n}", namespace="ns",
                 source_file=source_file)
        for n in names
    ]
    return TIRModule(name="m", classes=classes,  # type: ignore[arg-type, list-item]
                     class_by_name={c.name: c for c in classes})  # type: ignore[misc]


def _module_with_methods(*method_names: str) -> tuple[TIRModule, TIRClass]:
    methods = [
        TIRMethod(name=n, spelling=n, qualified_name=f"Cls::{n}", return_type="void")
        for n in method_names
    ]
    cls = TIRClass(name="Cls", qualified_name="ns::Cls", namespace="ns",
                   methods=list(methods))  # type: ignore[arg-type]
    mod = TIRModule(name="m", classes=[cls], class_by_name={"Cls": cls})  # type: ignore[arg-type, list-item]
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
            TIRMethod(name="perClassOnly", spelling="perClassOnly",
                      qualified_name="Other::perClassOnly", return_type="void")
        ]
        other_cls = TIRClass(name="Other", qualified_name="ns::Other",
                             namespace="ns", methods=methods)  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[other_cls],
                        class_by_name={"Other": other_cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig(
            methods=MethodFilter(per_class={"Cls": [FilterPattern("perClassOnly")]})
        )).apply(mod)
        assert other_cls.methods[0].emit is True


# ---------------------------------------------------------------------------
# Constructor filtering
# ---------------------------------------------------------------------------

class TestConstructorFilter:
    def _cls_with_ctors(self, *param_lists):
        ctors = [TIRConstructor(parameters=[TIRParameter("x", t) for t in pl])
                 for pl in param_lists]
        cls = TIRClass(name="C", qualified_name="ns::C", namespace="ns",
                       constructors=ctors)  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"C": cls})  # type: ignore[arg-type, list-item]
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
        fields = [TIRField(name=n, type_spelling="int") for n in names]
        cls = TIRClass(name="C", qualified_name="ns::C", namespace="ns",
                       fields=list(fields))  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"C": cls})  # type: ignore[arg-type, list-item]
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
        fns = [TIRFunction(name=n, qualified_name=f"ns::{n}",
                           namespace="ns", return_type="void")
               for n in names]
        return TIRModule(name="m", functions=list(fns))  # type: ignore[arg-type, list-item]

    def test_blacklist(self):
        mod = TIRModule(name="m", functions=[  # type: ignore[arg-type, list-item]
            TIRFunction(name="keep", qualified_name="ns::keep", namespace="ns", return_type="void"),
            TIRFunction(name="skip", qualified_name="ns::skip", namespace="ns", return_type="void"),
        ])
        FilterEngine(FilterConfig(
            functions=FunctionFilter(blacklist=[FilterPattern("skip")])
        )).apply(mod)
        emitted = [f.name for f in mod.functions if f.emit]
        assert emitted == ["keep"]

    def test_whitelist(self):
        mod = TIRModule(name="m", functions=[  # type: ignore[arg-type, list-item]
            TIRFunction(name="foo", qualified_name="ns::foo", namespace="ns", return_type="void"),
            TIRFunction(name="bar", qualified_name="ns::bar", namespace="ns", return_type="void"),
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
        enums = [TIREnum(name=n, qualified_name=f"ns::{n}") for n in names]
        return TIRModule(name="m", enums=list(enums))  # type: ignore[arg-type, list-item]

    def test_blacklist(self):
        mod = TIRModule(name="m", enums=[  # type: ignore[arg-type, list-item]
            TIREnum(name="Keep", qualified_name="ns::Keep"),
            TIREnum(name="Skip", qualified_name="ns::Skip"),
        ])
        FilterEngine(FilterConfig(
            enums=EnumFilter(blacklist=[FilterPattern("Skip")])
        )).apply(mod)
        emitted = [e.name for e in mod.enums if e.emit]
        assert emitted == ["Keep"]

    def test_whitelist_suppresses_non_matching(self):
        mod = TIRModule(name="m", enums=[  # type: ignore[arg-type, list-item]
            TIREnum(name="Keep", qualified_name="ns::Keep"),
            TIREnum(name="Other", qualified_name="ns::Other"),
        ])
        FilterEngine(FilterConfig(
            enums=EnumFilter(whitelist=[FilterPattern("Keep")])
        )).apply(mod)
        emitted = [e.name for e in mod.enums if e.emit]
        assert emitted == ["Keep"]


# ---------------------------------------------------------------------------
# Pre-suppressed node handling
# ---------------------------------------------------------------------------

class TestPreSuppressedNodes:
    def test_pre_suppressed_class_skips_filter_class(self):
        cls = TIRClass(name="X", qualified_name="ns::X", namespace="ns")
        cls.emit = False
        mod = TIRModule(name="m", classes=[cls], class_by_name={"X": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert cls.emit is False

    def test_pre_suppressed_method_skips_filter(self):
        method = TIRMethod(name="f", spelling="f", qualified_name="C::f", return_type="void")
        method.emit = False
        cls = TIRClass(name="C", qualified_name="ns::C", namespace="ns",
                       methods=[method])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"C": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert method.emit is False

    def test_pre_suppressed_field_skips_filter(self):
        f = TIRField(name="x_", type_spelling="int")
        f.emit = False
        cls = TIRClass(name="C", qualified_name="ns::C", namespace="ns",
                       fields=[f])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"C": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert f.emit is False

    def test_pre_suppressed_function_skips_filter(self):
        fn = TIRFunction(name="g", qualified_name="ns::g", namespace="ns", return_type="void")
        fn.emit = False
        mod = TIRModule(name="m", functions=[fn])  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert fn.emit is False

    def test_pre_suppressed_enum_skips_filter(self):
        en = TIREnum(name="E", qualified_name="ns::E")
        en.emit = False
        mod = TIRModule(name="m", enums=[en])  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert en.emit is False

    def test_inner_class_recursive_filter(self):
        inner = TIRClass(name="Inner", qualified_name="ns::Outer::Inner", namespace="ns")
        outer = TIRClass(name="Outer", qualified_name="ns::Outer", namespace="ns",
                         inner_classes=[inner])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[outer], class_by_name={"Outer": outer})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig(
            classes=ClassFilter(blacklist=[FilterPattern("Inner")])
        )).apply(mod)
        assert inner.emit is False


# ---------------------------------------------------------------------------
# Varargs suppression (Gap 16)
# ---------------------------------------------------------------------------

class TestVarargsFilter:
    def test_varargs_method_suppressed(self):
        varargs_m = TIRMethod(
            name="log", spelling="log", qualified_name="ns::Foo::log",
            return_type="void", is_varargs=True,
        )
        normal_m = TIRMethod(
            name="info", spelling="info", qualified_name="ns::Foo::info",
            return_type="void", is_varargs=False,
        )
        cls = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                       methods=[varargs_m, normal_m])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert varargs_m.emit is False
        assert normal_m.emit is True

    def test_varargs_function_suppressed(self):
        vfn = TIRFunction(
            name="printf", qualified_name="ns::printf", namespace="ns",
            return_type="int", is_varargs=True,
        )
        normal_fn = TIRFunction(
            name="puts", qualified_name="ns::puts", namespace="ns",
            return_type="int", is_varargs=False,
        )
        mod = TIRModule(name="m", functions=[vfn, normal_fn])  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert vfn.emit is False
        assert normal_fn.emit is True

    def test_non_varargs_not_affected(self):
        m = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute",
            return_type="int", is_varargs=False,
        )
        cls = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                       methods=[m])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert m.emit is True


class TestBaseFilter:
    def test_base_outside_namespace_suppressed(self) -> None:
        base = TIRBase("std::runtime_error", "public")
        cls = TIRClass(name="MyError", qualified_name="ns::MyError", namespace="ns",
                       bases=[base])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"MyError": cls})  # type: ignore[arg-type, list-item]
        cfg = FilterConfig(namespaces=["ns"])
        FilterEngine(cfg).apply(mod)
        assert base.emit is False

    def test_base_inside_namespace_kept(self) -> None:
        base = TIRBase("ns::Base", "public")
        cls = TIRClass(name="Child", qualified_name="ns::Child", namespace="ns",
                       bases=[base])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Child": cls})  # type: ignore[arg-type, list-item]
        cfg = FilterConfig(namespaces=["ns"])
        FilterEngine(cfg).apply(mod)
        assert base.emit is True

    def test_base_no_namespace_filter_kept(self) -> None:
        base = TIRBase("std::runtime_error", "public")
        cls = TIRClass(name="MyError", qualified_name="ns::MyError", namespace="ns",
                       bases=[base])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"MyError": cls})  # type: ignore[arg-type, list-item]
        FilterEngine(FilterConfig()).apply(mod)
        assert base.emit is True

    def test_pre_suppressed_base_skipped(self) -> None:
        base = TIRBase("std::runtime_error", "public")
        base.emit = False
        cls = TIRClass(name="MyError", qualified_name="ns::MyError", namespace="ns",
                       bases=[base])  # type: ignore[arg-type]
        mod = TIRModule(name="m", classes=[cls], class_by_name={"MyError": cls})  # type: ignore[arg-type, list-item]
        cfg = FilterConfig(namespaces=["ns"])
        FilterEngine(cfg).apply(mod)
        assert base.emit is False
