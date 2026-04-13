"""Tests for new parser features: scoped/anonymous enums, static members,
conversion operators, deprecated annotations, deleted constructors."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import SourceConfig
from tsujikiri.parser import parse_translation_unit

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def new_features_module():
    src = SourceConfig(path=str(HERE / "new_features.hpp"), parse_args=["-std=c++17"])
    return parse_translation_unit(src, ["mylib"], "new_features")


# ---------------------------------------------------------------------------
# Scoped enums
# ---------------------------------------------------------------------------

class TestScopedEnum:
    def test_scoped_enum_detected(self, new_features_module):
        status = next(e for e in new_features_module.enums if e.name == "Status")
        assert status.is_scoped is True

    def test_unscoped_enum_not_scoped(self, new_features_module):
        direction = next(e for e in new_features_module.enums if e.name == "Direction")
        assert direction.is_scoped is False

    def test_scoped_enum_values_present(self, new_features_module):
        status = next(e for e in new_features_module.enums if e.name == "Status")
        names = {v.name for v in status.values}
        assert names == {"Active", "Inactive", "Pending"}


# ---------------------------------------------------------------------------
# Anonymous enums
# ---------------------------------------------------------------------------

class TestAnonymousEnum:
    def test_anonymous_enum_detected(self, new_features_module):
        anon = next((e for e in new_features_module.enums if e.is_anonymous), None)
        assert anon is not None, "Expected at least one anonymous enum"

    def test_anonymous_enum_name_synthetic(self, new_features_module):
        anon = next(e for e in new_features_module.enums if e.is_anonymous)
        assert anon.name.startswith("__anon_enum_")

    def test_anonymous_enum_values_present(self, new_features_module):
        anon = next(e for e in new_features_module.enums if e.is_anonymous)
        names = {v.name for v in anon.values}
        assert "MAX_SIZE" in names
        assert "MIN_SIZE" in names


# ---------------------------------------------------------------------------
# Static member variables
# ---------------------------------------------------------------------------

class TestStaticMembers:
    def _config(self, mod):
        return next(c for c in mod.classes if c.name == "Config")

    def test_static_field_detected(self, new_features_module):
        cls = self._config(new_features_module)
        static_fields = [f for f in cls.fields if f.is_static]
        assert len(static_fields) >= 1

    def test_static_max_retries(self, new_features_module):
        cls = self._config(new_features_module)
        field = next((f for f in cls.fields if f.name == "maxRetries"), None)
        assert field is not None
        assert field.is_static is True

    def test_static_const_version(self, new_features_module):
        cls = self._config(new_features_module)
        field = next((f for f in cls.fields if f.name == "version"), None)
        assert field is not None
        assert field.is_static is True
        assert field.is_const is True

    def test_instance_field_not_static(self, new_features_module):
        cls = self._config(new_features_module)
        field = next((f for f in cls.fields if f.name == "timeout"), None)
        assert field is not None
        assert field.is_static is False


# ---------------------------------------------------------------------------
# Conversion operators
# ---------------------------------------------------------------------------

class TestConversionOperators:
    def _wrapper(self, mod):
        return next(c for c in mod.classes if c.name == "Wrapper")

    def test_conversion_bool_detected(self, new_features_module):
        cls = self._wrapper(new_features_module)
        conv = next((m for m in cls.methods if m.is_conversion_operator
                     and "bool" in m.conversion_target_type), None)
        assert conv is not None

    def test_conversion_int_detected(self, new_features_module):
        cls = self._wrapper(new_features_module)
        conv = next((m for m in cls.methods if m.is_conversion_operator
                     and m.conversion_target_type == "int"), None)
        assert conv is not None

    def test_conversion_is_operator(self, new_features_module):
        cls = self._wrapper(new_features_module)
        conv = next(m for m in cls.methods if m.is_conversion_operator)
        assert conv.is_operator is True

    def test_conversion_operator_type_spelling(self, new_features_module):
        cls = self._wrapper(new_features_module)
        conv = next(m for m in cls.methods if m.is_conversion_operator
                    and "bool" in m.conversion_target_type)
        assert "operator bool" in conv.operator_type


# ---------------------------------------------------------------------------
# Deprecated annotations
# ---------------------------------------------------------------------------

class TestDeprecatedAnnotations:
    def test_deprecated_function_no_message(self, new_features_module):
        """[[deprecated]] with no message string → deprecation_message is None."""
        fn = next((f for f in new_features_module.functions if f.name == "legacyOp"), None)
        assert fn is not None
        assert fn.is_deprecated is True
        assert fn.deprecation_message is None

    def test_deprecated_function(self, new_features_module):
        fn = next((f for f in new_features_module.functions if f.name == "computeOld"), None)
        assert fn is not None
        assert fn.is_deprecated is True

    def test_deprecated_function_message(self, new_features_module):
        fn = next(f for f in new_features_module.functions if f.name == "computeOld")
        assert fn.deprecation_message == "use newCompute instead"

    def test_deprecated_class(self, new_features_module):
        cls = next((c for c in new_features_module.classes if c.name == "OldWidget"), None)
        assert cls is not None
        assert cls.is_deprecated is True

    def test_deprecated_class_message(self, new_features_module):
        cls = next(c for c in new_features_module.classes if c.name == "OldWidget")
        assert cls.deprecation_message == "use NewWidget instead"

    def test_deprecated_method(self, new_features_module):
        srv = next(c for c in new_features_module.classes if c.name == "Server")
        method = next((m for m in srv.methods if m.name == "startLegacy"), None)
        assert method is not None
        assert method.is_deprecated is True

    def test_deprecated_method_message(self, new_features_module):
        srv = next(c for c in new_features_module.classes if c.name == "Server")
        method = next(m for m in srv.methods if m.name == "startLegacy")
        assert method.deprecation_message == "use startWithConfig instead"

    def test_non_deprecated_method_not_deprecated(self, new_features_module):
        srv = next(c for c in new_features_module.classes if c.name == "Server")
        method = next(m for m in srv.methods if m.name == "start")
        assert method.is_deprecated is False


# ---------------------------------------------------------------------------
# Move-only types (deleted copy constructor)
# ---------------------------------------------------------------------------

class TestMoveOnlyTypes:
    def test_deleted_copy_constructor_detected(self, new_features_module):
        cls = next(c for c in new_features_module.classes if c.name == "UniqueResource")
        assert cls.has_deleted_copy_constructor is True

    def test_copyable_set_false(self, new_features_module):
        cls = next(c for c in new_features_module.classes if c.name == "UniqueResource")
        assert cls.copyable is False

    def test_movable_class_not_flagged(self, new_features_module):
        cls = next(c for c in new_features_module.classes if c.name == "UniqueResource")
        # Move constructor is NOT deleted
        assert cls.has_deleted_move_constructor is False

    def test_explicit_non_deleted_copy_ctor_not_flagged(self, new_features_module):
        """Copyable class with default copy ctor must NOT set has_deleted_copy_constructor."""
        cls = next((c for c in new_features_module.classes if c.name == "Copyable"), None)
        assert cls is not None
        assert cls.has_deleted_copy_constructor is False
        assert cls.copyable is None  # not forced either way

    def test_deleted_move_constructor_detected(self, new_features_module):
        """MoveDeleted class must have has_deleted_move_constructor=True."""
        cls = next((c for c in new_features_module.classes if c.name == "MoveDeleted"), None)
        assert cls is not None
        assert cls.has_deleted_move_constructor is True
        assert cls.movable is False


# ---------------------------------------------------------------------------
# Free-function operator<< detection in generator
# ---------------------------------------------------------------------------

class TestFreeFunctionOstream:
    def test_ostream_operator_parsed(self, new_features_module):
        fn = next((f for f in new_features_module.functions
                   if f.is_operator and f.operator_type == "operator<<"), None)
        assert fn is not None

    def test_ostream_operator_has_point_param(self, new_features_module):
        fn = next(f for f in new_features_module.functions
                  if f.is_operator and f.operator_type == "operator<<")
        param_types = [p.type_spelling for p in fn.parameters]
        assert any("Point" in t for t in param_types)


# ---------------------------------------------------------------------------
# Varargs detection (Gap 16)
# ---------------------------------------------------------------------------

class TestVarargsDetection:
    def test_varargs_free_function_detected(self, new_features_module):
        fn = next((f for f in new_features_module.functions if f.name == "formatString"), None)
        assert fn is not None
        assert fn.is_varargs is True

    def test_non_varargs_function_not_flagged(self, new_features_module):
        fn = next((f for f in new_features_module.functions
                   if f.is_operator and f.operator_type == "operator<<"), None)
        assert fn is not None
        assert fn.is_varargs is False

    def test_varargs_method_detected(self, new_features_module):
        logger = next((c for c in new_features_module.classes if c.name == "Logger"), None)
        assert logger is not None
        log_method = next((m for m in logger.methods if m.name == "log"), None)
        assert log_method is not None
        assert log_method.is_varargs is True

    def test_non_varargs_method_not_flagged(self, new_features_module):
        logger = next(c for c in new_features_module.classes if c.name == "Logger")
        info_method = next(m for m in logger.methods if m.name == "info")
        assert info_method.is_varargs is False


# ---------------------------------------------------------------------------
# Protected member collection (Gap 4)
# ---------------------------------------------------------------------------

class TestProtectedMemberCollection:
    def test_protected_method_in_methods_list(self, new_features_module):
        animal = next((c for c in new_features_module.classes if c.name == "Animal"), None)
        assert animal is not None
        # protected method should be in the list but emit=False
        breathe = next((m for m in animal.methods if m.name == "breathe"), None)
        assert breathe is not None

    def test_protected_method_has_protected_access(self, new_features_module):
        animal = next(c for c in new_features_module.classes if c.name == "Animal")
        breathe = next(m for m in animal.methods if m.name == "breathe")
        assert breathe.access == "protected"

    def test_protected_method_emit_false(self, new_features_module):
        animal = next(c for c in new_features_module.classes if c.name == "Animal")
        breathe = next(m for m in animal.methods if m.name == "breathe")
        assert breathe.emit is False

    def test_public_virtual_method_emit_true(self, new_features_module):
        animal = next(c for c in new_features_module.classes if c.name == "Animal")
        speak = next((m for m in animal.methods if m.name == "speak"), None)
        assert speak is not None
        assert speak.access == "public"
        assert speak.emit is True


# ---------------------------------------------------------------------------
# Using declarations (Gap 14)
# ---------------------------------------------------------------------------

class TestUsingDeclarations:
    def test_using_declaration_parsed(self, new_features_module):
        dog = next((c for c in new_features_module.classes if c.name == "Dog"), None)
        assert dog is not None
        assert len(dog.using_declarations) >= 1

    def test_using_declaration_member_name(self, new_features_module):
        dog = next(c for c in new_features_module.classes if c.name == "Dog")
        ud = next((u for u in dog.using_declarations if u.member_name == "breathe"), None)
        assert ud is not None

    def test_using_declaration_access(self, new_features_module):
        dog = next(c for c in new_features_module.classes if c.name == "Dog")
        ud = next(u for u in dog.using_declarations if u.member_name == "breathe")
        assert ud.access == "public"
