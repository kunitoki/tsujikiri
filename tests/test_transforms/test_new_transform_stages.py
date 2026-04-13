"""Tests for new transform stages: MarkDeprecatedStage, ExpandSpaceshipStage,
ExposeProtectedStage, ResolveUsingDeclarationsStage, RegisterExceptionStage,
and extensions to ModifyEnumStage and SetTypeHintStage."""

from __future__ import annotations

import pytest

from tsujikiri.ir import (
    IRBase,
    IRClass,
    IREnum,
    IREnumValue,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
    IRUsingDeclaration,
)
from tsujikiri.transforms import (
    ExpandSpaceshipStage,
    ExposeProtectedStage,
    MarkDeprecatedStage,
    ModifyEnumStage,
    RegisterExceptionStage,
    ResolveUsingDeclarationsStage,
    SetTypeHintStage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_with_class(methods=None, enums=None) -> IRModule:
    cls = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                  methods=methods or [], enums=enums or [])
    enum = IREnum(name="Color", qualified_name="ns::Color",
                  values=[IREnumValue("Red", 0), IREnumValue("Green", 1)])
    fn = IRFunction(name="helper", qualified_name="ns::helper", namespace="ns",
                    return_type="void")
    mod = IRModule(name="m", classes=[cls], enums=[enum], functions=[fn])
    mod.class_by_name["Foo"] = cls
    return mod


# ---------------------------------------------------------------------------
# MarkDeprecatedStage
# ---------------------------------------------------------------------------

class TestMarkDeprecatedStage:
    def test_mark_method_deprecated(self):
        mod = _module_with_class(methods=[
            IRMethod(name="oldMethod", spelling="oldMethod",
                     qualified_name="ns::Foo::oldMethod", return_type="void"),
        ])
        MarkDeprecatedStage(target="method", **{"class": "Foo", "method": "oldMethod",
                                                 "message": "use newMethod"}).apply(mod)
        m = next(m for m in mod.classes[0].methods if m.name == "oldMethod")
        assert m.is_deprecated is True
        assert m.deprecation_message == "use newMethod"

    def test_mark_class_deprecated(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="class", **{"class": "Foo",
                                                "message": "use NewFoo"}).apply(mod)
        assert mod.classes[0].is_deprecated is True
        assert mod.classes[0].deprecation_message == "use NewFoo"

    def test_mark_function_deprecated(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="function", function="helper",
                            message="use betterHelper").apply(mod)
        fn = next(f for f in mod.functions if f.name == "helper")
        assert fn.is_deprecated is True
        assert fn.deprecation_message == "use betterHelper"

    def test_mark_enum_deprecated(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="enum", enum="Color",
                            message="use NewColor").apply(mod)
        enum = next(e for e in mod.enums if e.name == "Color")
        assert enum.is_deprecated is True
        assert enum.deprecation_message == "use NewColor"

    def test_mark_without_message(self):
        mod = _module_with_class(methods=[
            IRMethod(name="m", spelling="m", qualified_name="ns::Foo::m",
                     return_type="void"),
        ])
        MarkDeprecatedStage(target="method", **{"class": "Foo", "method": "m"}).apply(mod)
        method = mod.classes[0].methods[0]
        assert method.is_deprecated is True
        assert method.deprecation_message is None

    def test_mark_class_without_message(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="class", **{"class": "Foo"}).apply(mod)
        assert mod.classes[0].is_deprecated is True
        assert mod.classes[0].deprecation_message is None

    def test_mark_function_without_message(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="function", function="helper").apply(mod)
        fn = next(f for f in mod.functions if f.name == "helper")
        assert fn.is_deprecated is True
        assert fn.deprecation_message is None

    def test_mark_enum_without_message(self):
        mod = _module_with_class()
        MarkDeprecatedStage(target="enum", enum="Color").apply(mod)
        enum = next(e for e in mod.enums if e.name == "Color")
        assert enum.is_deprecated is True
        assert enum.deprecation_message is None

    def test_mark_method_no_match(self):
        """Method pattern doesn't match — no method is marked deprecated (978->977 branch)."""
        mod = _module_with_class(methods=[
            IRMethod(name="keep", spelling="keep", qualified_name="ns::Foo::keep",
                     return_type="void"),
        ])
        MarkDeprecatedStage(target="method", **{"class": "Foo", "method": "nonexistent"}).apply(mod)
        assert mod.classes[0].methods[0].is_deprecated is False

    def test_mark_function_no_match(self):
        """Function pattern doesn't match — no function is marked deprecated (984->983 branch)."""
        mod = _module_with_class()
        MarkDeprecatedStage(target="function", function="nonexistent").apply(mod)
        fn = next(f for f in mod.functions if f.name == "helper")
        assert fn.is_deprecated is False

    def test_mark_unknown_target_is_noop(self):
        """Unknown target — none of the elif branches match (988->exit branch)."""
        mod = _module_with_class()
        MarkDeprecatedStage(target="unknown").apply(mod)
        assert mod.classes[0].is_deprecated is False


# ---------------------------------------------------------------------------
# ExpandSpaceshipStage
# ---------------------------------------------------------------------------

class TestExpandSpaceshipStage:
    def _spaceship_module(self):
        spaceship = IRMethod(
            name="operator<=>", spelling="operator<=>",
            qualified_name="ns::Foo::operator<=>",
            return_type="auto",
            parameters=[IRParameter(name="rhs", type_spelling="const ns::Foo &")],
            is_operator=True, operator_type="operator<=>", is_const=True,
        )
        cls = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      methods=[spaceship])
        mod = IRModule(name="m", classes=[cls])
        mod.class_by_name["Foo"] = cls
        return mod

    def test_spaceship_expands_to_six(self):
        mod = self._spaceship_module()
        ExpandSpaceshipStage(**{"class": "Foo"}).apply(mod)
        cls = mod.classes[0]
        active = [m for m in cls.methods if m.emit]
        op_types = {m.operator_type for m in active}
        assert "operator<" in op_types
        assert "operator<=" in op_types
        assert "operator>" in op_types
        assert "operator>=" in op_types
        assert "operator==" in op_types
        assert "operator!=" in op_types

    def test_original_spaceship_suppressed(self):
        mod = self._spaceship_module()
        ExpandSpaceshipStage(**{"class": "Foo"}).apply(mod)
        original = next(m for m in mod.classes[0].methods
                        if m.operator_type == "operator<=>")
        assert original.emit is False

    def test_synthesized_use_wrapper_code(self):
        mod = self._spaceship_module()
        ExpandSpaceshipStage(**{"class": "Foo"}).apply(mod)
        lt = next(m for m in mod.classes[0].methods
                  if m.operator_type == "operator<" and m.emit)
        assert lt.wrapper_code is not None
        assert "std::is_lt" in lt.wrapper_code

    def test_mixed_class_non_spaceship_method_unchanged(self):
        """Regular methods in a class with spaceship should be left emit=True."""
        spaceship = IRMethod(
            name="operator<=>", spelling="operator<=>",
            qualified_name="ns::Foo::operator<=>",
            return_type="auto",
            parameters=[IRParameter(name="rhs", type_spelling="const ns::Foo &")],
            is_operator=True, operator_type="operator<=>", is_const=True,
        )
        regular = IRMethod(
            name="getValue", spelling="getValue",
            qualified_name="ns::Foo::getValue",
            return_type="int",
        )
        cls = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      methods=[spaceship, regular])
        mod = IRModule(name="m", classes=[cls])
        mod.class_by_name["Foo"] = cls
        ExpandSpaceshipStage(**{"class": "Foo"}).apply(mod)
        get_value = next(m for m in cls.methods if m.name == "getValue")
        assert get_value.emit is True  # untouched


# ---------------------------------------------------------------------------
# ModifyEnumStage: arithmetic extension
# ---------------------------------------------------------------------------

class TestModifyEnumArithmetic:
    def test_set_arithmetic_true(self):
        mod = _module_with_class()
        ModifyEnumStage(enum="Color", arithmetic=True).apply(mod)
        enum = next(e for e in mod.enums if e.name == "Color")
        assert enum.is_arithmetic is True

    def test_set_arithmetic_false(self):
        mod = _module_with_class()
        # First mark it arithmetic, then unset
        enum = next(e for e in mod.enums if e.name == "Color")
        enum.is_arithmetic = True
        ModifyEnumStage(enum="Color", arithmetic=False).apply(mod)
        assert enum.is_arithmetic is False

    def test_arithmetic_default_is_false(self):
        mod = _module_with_class()
        enum = next(e for e in mod.enums if e.name == "Color")
        assert enum.is_arithmetic is False


# ---------------------------------------------------------------------------
# SetTypeHintStage: new fields
# ---------------------------------------------------------------------------

class TestSetTypeHintExtended:
    def test_generate_hash(self):
        mod = _module_with_class()
        SetTypeHintStage(**{"class": "Foo", "generate_hash": True}).apply(mod)
        assert mod.classes[0].generate_hash is True

    def test_smart_pointer_kind(self):
        mod = _module_with_class()
        SetTypeHintStage(**{"class": "Foo", "smart_pointer_kind": "shared"}).apply(mod)
        assert mod.classes[0].smart_pointer_kind == "shared"

    def test_smart_pointer_managed_type(self):
        mod = _module_with_class()
        SetTypeHintStage(**{"class": "Foo",
                            "smart_pointer_kind": "unique",
                            "smart_pointer_managed_type": "ns::Foo"}).apply(mod)
        assert mod.classes[0].smart_pointer_managed_type == "ns::Foo"

    def test_existing_hints_unchanged_when_not_specified(self):
        mod = _module_with_class()
        mod.classes[0].holder_type = "std::shared_ptr"
        SetTypeHintStage(**{"class": "Foo", "generate_hash": True}).apply(mod)
        assert mod.classes[0].holder_type == "std::shared_ptr"


# ---------------------------------------------------------------------------
# ExposeProtectedStage (Gap 4)
# ---------------------------------------------------------------------------

class TestExposeProtectedStage:
    def _module_with_protected(self) -> IRModule:
        protected = IRMethod(
            name="helper", spelling="helper",
            qualified_name="ns::Foo::helper",
            return_type="void", access="protected", emit=False,
        )
        public = IRMethod(
            name="doWork", spelling="doWork",
            qualified_name="ns::Foo::doWork",
            return_type="void", access="public", emit=True,
        )
        cls = IRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      methods=[protected, public])
        mod = IRModule(name="m", classes=[cls])
        mod.class_by_name["Foo"] = cls
        return mod

    def test_expose_changes_access(self):
        mod = self._module_with_protected()
        ExposeProtectedStage(**{"class": "Foo", "method": "helper"}).apply(mod)
        method = next(m for m in mod.classes[0].methods if m.name == "helper")
        assert method.access == "public_via_trampoline"
        assert method.emit is True

    def test_expose_does_not_touch_public(self):
        mod = self._module_with_protected()
        ExposeProtectedStage(**{"class": "Foo"}).apply(mod)
        public = next(m for m in mod.classes[0].methods if m.name == "doWork")
        assert public.access == "public"

    def test_expose_all_protected_via_wildcard(self):
        mod = self._module_with_protected()
        ExposeProtectedStage(**{"class": "Foo", "method": "*"}).apply(mod)
        exposed = [m for m in mod.classes[0].methods if m.access == "public_via_trampoline"]
        assert len(exposed) == 1
        assert exposed[0].name == "helper"

    def test_no_match_leaves_emit_false(self):
        mod = self._module_with_protected()
        ExposeProtectedStage(**{"class": "Foo", "method": "nonexistent"}).apply(mod)
        protected = next(m for m in mod.classes[0].methods if m.name == "helper")
        assert protected.emit is False


# ---------------------------------------------------------------------------
# ResolveUsingDeclarationsStage (Gap 14)
# ---------------------------------------------------------------------------

class TestResolveUsingDeclarationsStage:
    def _module(self) -> IRModule:
        base_method = IRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Base::compute",
            return_type="int", access="public", emit=True,
        )
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       methods=[base_method])
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            bases=[IRBase(qualified_name="ns::Base", access="public")],
            using_declarations=[
                IRUsingDeclaration(member_name="compute", base_qualified_name="ns::Base"),
            ],
        )
        mod = IRModule(name="m", classes=[base, derived])
        mod.class_by_name["Base"] = base
        mod.class_by_name["Derived"] = derived
        return mod

    def test_method_copied_to_derived(self):
        mod = self._module()
        ResolveUsingDeclarationsStage().apply(mod)
        derived = next(c for c in mod.classes if c.name == "Derived")
        names = [m.name for m in derived.methods]
        assert "compute" in names

    def test_method_access_set_public(self):
        mod = self._module()
        ResolveUsingDeclarationsStage().apply(mod)
        derived = next(c for c in mod.classes if c.name == "Derived")
        m = next(m for m in derived.methods if m.name == "compute")
        assert m.access == "public"
        assert m.emit is True

    def test_no_duplicate_if_already_present(self):
        mod = self._module()
        # Pre-populate derived with the method
        derived = next(c for c in mod.classes if c.name == "Derived")
        derived.methods.append(IRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Derived::compute",
            return_type="int",
        ))
        ResolveUsingDeclarationsStage().apply(mod)
        count = sum(1 for m in derived.methods if m.name == "compute")
        assert count == 1  # should not duplicate

    def test_unknown_base_graceful(self):
        """Should not raise when base class is not in the module."""
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            using_declarations=[
                IRUsingDeclaration(member_name="foo", base_qualified_name="ns::Unknown"),
            ],
        )
        mod = IRModule(name="m", classes=[derived])
        mod.class_by_name["Derived"] = derived
        ResolveUsingDeclarationsStage().apply(mod)  # should not raise

    def test_suppressed_using_declaration_skipped(self):
        """IRUsingDeclaration with emit=False should not trigger resolution."""
        base_method = IRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Base::compute",
            return_type="int", access="public", emit=True,
        )
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       methods=[base_method])
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            bases=[IRBase(qualified_name="ns::Base", access="public")],
            using_declarations=[
                IRUsingDeclaration(member_name="compute", base_qualified_name="ns::Base", emit=False),
            ],
        )
        mod = IRModule(name="m", classes=[base, derived])
        mod.class_by_name["Base"] = base
        mod.class_by_name["Derived"] = derived
        ResolveUsingDeclarationsStage().apply(mod)
        # Method should NOT be copied since using_declaration.emit is False
        names = [m.name for m in derived.methods]
        assert "compute" not in names

    def test_fallback_base_search_when_qname_empty(self):
        """When base_qualified_name is empty, stage falls back to searching bases."""
        base_method = IRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Base::compute",
            return_type="int", access="public", emit=True,
        )
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       methods=[base_method])
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            bases=[IRBase(qualified_name="ns::Base", access="public")],
            using_declarations=[
                # empty base_qualified_name → triggers fallback search
                IRUsingDeclaration(member_name="compute", base_qualified_name=""),
            ],
        )
        mod = IRModule(name="m", classes=[base, derived])
        mod.class_by_name["Base"] = base
        mod.class_by_name["Derived"] = derived
        ResolveUsingDeclarationsStage().apply(mod)
        names = [m.name for m in derived.methods]
        assert "compute" in names

    def test_fallback_no_match_in_base(self):
        """Fallback search when no base has matching method name."""
        base = IRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                       methods=[])  # no matching method
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            bases=[IRBase(qualified_name="ns::Base", access="public")],
            using_declarations=[
                IRUsingDeclaration(member_name="compute", base_qualified_name=""),
            ],
        )
        mod = IRModule(name="m", classes=[base, derived])
        mod.class_by_name["Base"] = base
        mod.class_by_name["Derived"] = derived
        ResolveUsingDeclarationsStage().apply(mod)
        # Nothing copied — no method "compute" in base
        names = [m.name for m in derived.methods]
        assert "compute" not in names

    def test_fallback_base_not_in_module(self):
        """Base class listed in cls.bases but NOT in module.classes → candidate is None."""
        derived = IRClass(
            name="Derived", qualified_name="ns::Derived", namespace="ns",
            bases=[IRBase(qualified_name="ns::ExternalBase", access="public")],
            using_declarations=[
                IRUsingDeclaration(member_name="compute", base_qualified_name=""),
            ],
        )
        mod = IRModule(name="m", classes=[derived])
        mod.class_by_name["Derived"] = derived
        ResolveUsingDeclarationsStage().apply(mod)
        # ExternalBase not in module → nothing copied
        names = [m.name for m in derived.methods]
        assert "compute" not in names


# ---------------------------------------------------------------------------
# RegisterExceptionStage (Gap 12)
# ---------------------------------------------------------------------------

class TestRegisterExceptionStage:
    def test_registers_exception(self):
        mod = IRModule(name="m")
        RegisterExceptionStage(cpp_type="ns::ParseError", python_name="ParseError").apply(mod)
        assert len(mod.exception_registrations) == 1
        exc = mod.exception_registrations[0]
        assert exc.cpp_exception_type == "ns::ParseError"
        assert exc.python_exception_name == "ParseError"
        assert exc.base_python_exception == "Exception"

    def test_custom_base(self):
        mod = IRModule(name="m")
        RegisterExceptionStage(
            cpp_type="ns::IoError",
            python_name="IoError",
            base="OSError",
        ).apply(mod)
        assert mod.exception_registrations[0].base_python_exception == "OSError"

    def test_default_python_name_from_cpp_type(self):
        mod = IRModule(name="m")
        RegisterExceptionStage(cpp_type="ns::MyError").apply(mod)
        assert mod.exception_registrations[0].python_exception_name == "MyError"

    def test_multiple_registrations(self):
        mod = IRModule(name="m")
        RegisterExceptionStage(cpp_type="ns::ErrA", python_name="ErrA").apply(mod)
        RegisterExceptionStage(cpp_type="ns::ErrB", python_name="ErrB").apply(mod)
        assert len(mod.exception_registrations) == 2
