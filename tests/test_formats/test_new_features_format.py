"""Tests for new-feature coverage in pybind11, pyi, luabridge3 and luals format templates."""

from __future__ import annotations

import io

import pytest

from tsujikiri.generator import Generator
from tsujikiri.ir import IRExceptionRegistration
from tsujikiri.tir import (
    TIRClass,
    TIREnum,
    TIREnumValue,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)


@pytest.fixture(scope="module")
def pybind11_cfg():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pybind11"))


@pytest.fixture(scope="module")
def pyi_cfg():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("pyi"))


@pytest.fixture(scope="module")
def luabridge3_cfg():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luabridge3"))


@pytest.fixture(scope="module")
def luals_cfg():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luals"))


def _gen(module: TIRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Gap 7: In-place operator mappings
# ---------------------------------------------------------------------------

class TestInPlaceOperators:
    def _method(self, op_type: str):
        return TIRMethod(
            name=op_type,
            spelling=op_type,
            qualified_name=f"ns::Foo::{op_type}",
            return_type="ns::Foo &",
            parameters=[TIRParameter(name="rhs", type_spelling="const ns::Foo &")],
            is_operator=True,
            operator_type=op_type,
        )

    def _cls(self, op_type: str) -> TIRClass:
        return TIRClass(
            name="Foo", qualified_name="ns::Foo", namespace="ns",
            variable_name="classFoo",
            methods=[self._method(op_type)],
        )

    def test_iadd(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator+=")]), pybind11_cfg)
        assert '__iadd__' in out

    def test_isub(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator-=")]), pybind11_cfg)
        assert '__isub__' in out

    def test_imul(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator*=")]), pybind11_cfg)
        assert '__imul__' in out

    def test_itruediv(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator/=")]), pybind11_cfg)
        assert '__itruediv__' in out

    def test_iand(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator&=")]), pybind11_cfg)
        assert '__iand__' in out

    def test_ior(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator|=")]), pybind11_cfg)
        assert '__ior__' in out

    def test_ixor(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._cls("operator^=")]), pybind11_cfg)
        assert '__ixor__' in out


# ---------------------------------------------------------------------------
# Gap 1: Scoped enum → no export_values; unscoped → export_values
# ---------------------------------------------------------------------------

class TestScopedEnumTemplate:
    def test_scoped_enum_no_export_values(self, pybind11_cfg):
        enum = TIREnum(name="Status", qualified_name="ns::Status", is_scoped=True,
                      values=[TIREnumValue("Active", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), pybind11_cfg)
        assert ".export_values()" not in out
        assert 'py::enum_<ns::Status>' in out

    def test_unscoped_enum_has_export_values(self, pybind11_cfg):
        enum = TIREnum(name="Dir", qualified_name="ns::Dir", is_scoped=False,
                      values=[TIREnumValue("North", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), pybind11_cfg)
        assert ".export_values();" in out

    def test_scoped_enum_pyi_is_intenum(self, pyi_cfg):
        enum = TIREnum(name="Status", qualified_name="ns::Status", is_scoped=True,
                      values=[TIREnumValue("Active", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), pyi_cfg)
        assert "class Status(enum.IntEnum)" in out

    def test_unscoped_enum_pyi_is_int(self, pyi_cfg):
        enum = TIREnum(name="Dir", qualified_name="ns::Dir", is_scoped=False,
                      values=[TIREnumValue("North", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), pyi_cfg)
        assert "class Dir(int)" in out


# ---------------------------------------------------------------------------
# Gap 2: Static member variables
# ---------------------------------------------------------------------------

class TestStaticFieldTemplate:
    def _static_cls(self, read_only: bool = False):
        f = TIRField(name="kMax", type_spelling="int", is_static=True,
                    is_const=read_only, read_only=read_only)
        return TIRClass(name="Cfg", qualified_name="ns::Cfg", namespace="ns",
                       variable_name="classCfg", fields=[f])

    def test_static_readonly_field_pybind11(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._static_cls(read_only=True)]), pybind11_cfg)
        assert ".def_readonly_static" in out
        assert ".def_readwrite_static" not in out

    def test_static_readwrite_field_pybind11(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._static_cls(read_only=False)]), pybind11_cfg)
        assert ".def_readwrite_static" in out

    def test_static_field_luabridge3(self, luabridge3_cfg):
        out = _gen(TIRModule(name="m", classes=[self._static_cls()]), luabridge3_cfg)
        assert ".addStaticProperty" in out

    def test_static_field_pyi_comment(self, pyi_cfg):
        out = _gen(TIRModule(name="m", classes=[self._static_cls()]), pyi_cfg)
        assert "# static" in out

    def test_static_field_luals_annotation(self, luals_cfg):
        out = _gen(TIRModule(name="m", classes=[self._static_cls()]), luals_cfg)
        assert "(static)" in out


# ---------------------------------------------------------------------------
# Gap 6: Anonymous enums
# ---------------------------------------------------------------------------

class TestAnonymousEnumTemplate:
    def test_anonymous_enum_pybind11_uses_attr(self, pybind11_cfg):
        enum = TIREnum(name="__anon_enum_17", qualified_name="ns::__anon_enum_17",
                      is_anonymous=True,
                      values=[TIREnumValue("MAX_SIZE", 100), TIREnumValue("MIN_SIZE", 1)])
        out = _gen(TIRModule(name="m", enums=[enum]), pybind11_cfg)
        assert 'py::enum_' not in out
        assert 'm.attr("MAX_SIZE")' in out
        assert 'm.attr("MIN_SIZE")' in out

    def test_anonymous_enum_pyi_is_int_const(self, pyi_cfg):
        enum = TIREnum(name="__anon_enum_17", qualified_name="ns::__anon_enum_17",
                      is_anonymous=True,
                      values=[TIREnumValue("MAX_SIZE", 100)])
        out = _gen(TIRModule(name="m", enums=[enum]), pyi_cfg)
        assert "MAX_SIZE: int" in out
        assert "class __anon" not in out


# ---------------------------------------------------------------------------
# Gap 3: Conversion operators
# ---------------------------------------------------------------------------

class TestConversionOperatorTemplate:
    def _conv_cls(self, op_type: str, target_type: str):
        method = TIRMethod(
            name=op_type, spelling=op_type,
            qualified_name=f"ns::Wrapper::{op_type}",
            return_type=target_type,
            parameters=[],
            is_operator=True,
            operator_type=op_type,
            is_conversion_operator=True,
            conversion_target_type=target_type,
            is_const=True,
        )
        return TIRClass(name="Wrapper", qualified_name="ns::Wrapper", namespace="ns",
                       variable_name="classWrapper", methods=[method])

    def test_operator_bool_maps_to_dunder(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._conv_cls("operator bool", "bool")]), pybind11_cfg)
        assert '__bool__' in out

    def test_operator_int_maps_to_dunder(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._conv_cls("operator int", "int")]), pybind11_cfg)
        assert '__int__' in out


# ---------------------------------------------------------------------------
# Gap 5: Deprecated annotations
# ---------------------------------------------------------------------------

class TestDeprecatedAnnotationsTemplate:
    def _deprecated_method_cls(self):
        m = TIRMethod(name="oldMethod", spelling="oldMethod",
                     qualified_name="ns::Foo::oldMethod",
                     return_type="void",
                     is_deprecated=True, deprecation_message="use newMethod")
        return TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                       variable_name="classFoo", methods=[m])

    def test_deprecated_method_pyi_comment(self, pyi_cfg):
        out = _gen(TIRModule(name="m", classes=[self._deprecated_method_cls()]), pyi_cfg)
        assert "# deprecated" in out
        assert "use newMethod" in out

    def test_deprecated_enum_luals(self, luals_cfg):
        enum = TIREnum(name="OldEnum", qualified_name="ns::OldEnum",
                      is_deprecated=True, deprecation_message="use NewEnum",
                      values=[TIREnumValue("A", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), luals_cfg)
        assert "---@deprecated" in out

    def test_deprecated_class_luals(self, luals_cfg):
        cls = TIRClass(name="OldClass", qualified_name="ns::OldClass", namespace="ns",
                      variable_name="classOldClass",
                      is_deprecated=True, deprecation_message="use NewClass")
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "---@deprecated" in out


# ---------------------------------------------------------------------------
# Gap 10: Arithmetic enum flags
# ---------------------------------------------------------------------------

class TestArithmeticEnum:
    def test_arithmetic_pybind11_flag(self, pybind11_cfg):
        enum = TIREnum(name="Flags", qualified_name="ns::Flags",
                      is_arithmetic=True,
                      values=[TIREnumValue("Read", 1), TIREnumValue("Write", 2)])
        out = _gen(TIRModule(name="m", enums=[enum]), pybind11_cfg)
        assert "py::arithmetic()" in out

    def test_non_arithmetic_no_flag(self, pybind11_cfg):
        enum = TIREnum(name="Color", qualified_name="ns::Color",
                      is_arithmetic=False,
                      values=[TIREnumValue("Red", 0)])
        out = _gen(TIRModule(name="m", enums=[enum]), pybind11_cfg)
        assert "py::arithmetic()" not in out


# ---------------------------------------------------------------------------
# Gap 15: __hash__ protocol
# ---------------------------------------------------------------------------

class TestHashProtocol:
    def _hashable_cls(self):
        return TIRClass(name="Key", qualified_name="ns::Key", namespace="ns",
                       variable_name="classKey", generate_hash=True)

    def test_hash_emitted(self, pybind11_cfg):
        out = _gen(TIRModule(name="m", classes=[self._hashable_cls()]), pybind11_cfg)
        assert '__hash__' in out
        assert 'std::hash<ns::Key>' in out

    def test_no_hash_without_flag(self, pybind11_cfg):
        cls = TIRClass(name="Key", qualified_name="ns::Key", namespace="ns",
                      variable_name="classKey", generate_hash=False)
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        assert '__hash__' not in out


# ---------------------------------------------------------------------------
# Gap 18: Free-function operator<< → __repr__
# ---------------------------------------------------------------------------

class TestFreeFunctionRepr:
    def _setup(self):
        fn = TIRFunction(
            name="operator<<", qualified_name="ns::operator<<", namespace="ns",
            return_type="std::ostream &",
            parameters=[
                TIRParameter(name="os", type_spelling="std::ostream &"),
                TIRParameter(name="p", type_spelling="const ns::Point &"),
            ],
            is_operator=True, operator_type="operator<<",
        )
        cls = TIRClass(name="Point", qualified_name="ns::Point", namespace="ns",
                      variable_name="classPoint")
        return cls, fn

    def test_free_ostream_op_triggers_repr(self, pybind11_cfg):
        cls, fn = self._setup()
        mod = TIRModule(name="m", classes=[cls], functions=[fn])
        mod.class_by_name["Point"] = cls
        out = _gen(mod, pybind11_cfg)
        assert '__repr__' in out
        assert 'std::ostringstream' in out


# ---------------------------------------------------------------------------
# Gap 17: std::string_view → std::string type mapping
# ---------------------------------------------------------------------------

class TestStringViewMapping:
    def _method_with_sv(self):
        return TIRMethod(
            name="setLabel", spelling="setLabel",
            qualified_name="ns::Foo::setLabel",
            return_type="void",
            parameters=[TIRParameter(name="label", type_spelling="std::string_view")],
        )

    def test_string_view_not_in_unsupported(self, pybind11_cfg):
        """std::string_view should not be suppressed — it's in type_mappings, not unsupported."""
        cls = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      variable_name="classFoo",
                      methods=[self._method_with_sv()])
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        # Method must appear in output (not suppressed)
        assert 'set_label' in out

    def test_string_view_maps_to_str_in_pyi(self, pyi_cfg):
        """In pyi stubs, std::string_view maps to str via type_mappings."""
        cls = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      variable_name="classFoo",
                      methods=[self._method_with_sv()])
        out = _gen(TIRModule(name="m", classes=[cls]), pyi_cfg)
        assert 'label: str' in out  # std::string_view → str

    def test_string_view_return_not_suppressed(self, pybind11_cfg):
        """Method with std::string_view return type should still appear."""
        m = TIRMethod(
            name="getLabel", spelling="getLabel",
            qualified_name="ns::Foo::getLabel",
            return_type="std::string_view",
        )
        cls = TIRClass(name="Foo", qualified_name="ns::Foo", namespace="ns",
                      variable_name="classFoo", methods=[m])
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        assert 'get_label' in out


# ---------------------------------------------------------------------------
# Gap 12: Exception registration
# ---------------------------------------------------------------------------

class TestExceptionRegistration:
    def test_exception_in_pybind11(self, pybind11_cfg):
        mod = TIRModule(name="m", exception_registrations=[
            IRExceptionRegistration(
                cpp_exception_type="ns::ParseError",
                python_exception_name="ParseError",
                base_python_exception="Exception",
            )
        ])
        out = _gen(mod, pybind11_cfg)
        assert 'py::register_exception<ns::ParseError>' in out
        assert '"ParseError"' in out

    def test_exception_in_pyi(self, pyi_cfg):
        mod = TIRModule(name="m", exception_registrations=[
            IRExceptionRegistration(
                cpp_exception_type="ns::ParseError",
                python_exception_name="ParseError",
                base_python_exception="ValueError",
            )
        ])
        out = _gen(mod, pyi_cfg)
        assert 'class ParseError(ValueError)' in out

    def test_multiple_exceptions(self, pybind11_cfg):
        mod = TIRModule(name="m", exception_registrations=[
            IRExceptionRegistration("ns::ErrA", "ErrA"),
            IRExceptionRegistration("ns::ErrB", "ErrB", "RuntimeError"),
        ])
        out = _gen(mod, pybind11_cfg)
        assert 'register_exception<ns::ErrA>' in out
        assert 'register_exception<ns::ErrB>' in out

    def test_no_exceptions_no_block(self, pybind11_cfg):
        mod = TIRModule(name="m")
        out = _gen(mod, pybind11_cfg)
        assert 'register_exception' not in out


# ---------------------------------------------------------------------------
# Gap 4: Protected members / trampoline using declaration
# ---------------------------------------------------------------------------

class TestProtectedMethodsTemplate:
    def _virtual_cls_with_exposed_protected(self):
        virtual_m = TIRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Base::compute",
            return_type="int",
            is_virtual=True, is_pure_virtual=True,
        )
        protected_m = TIRMethod(
            name="helper", spelling="helper",
            qualified_name="ns::Base::helper",
            return_type="void",
            access="public_via_trampoline",
            emit=True,
        )
        cls = TIRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                      variable_name="classBase",
                      methods=[virtual_m, protected_m],
                      has_virtual_methods=True, is_abstract=True)
        return cls

    def test_trampoline_using_emitted(self, pybind11_cfg):
        cls = self._virtual_cls_with_exposed_protected()
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        assert 'using ns::Base::helper' in out

    def test_trampoline_using_not_emitted_without_expose(self, pybind11_cfg):
        virtual_m = TIRMethod(
            name="compute", spelling="compute",
            qualified_name="ns::Base::compute",
            return_type="int", is_virtual=True, is_pure_virtual=True,
        )
        cls = TIRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                      variable_name="classBase",
                      methods=[virtual_m],
                      has_virtual_methods=True, is_abstract=True)
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        # No exposed protected methods — no method-level using declarations
        # (constructor forwarding `using Base::Base;` is always emitted and that's OK)
        assert 'using ns::Base::compute' not in out
        assert 'using ns::Base::helper' not in out

    def test_virtual_method_emit_false_not_in_trampoline(self, pybind11_cfg):
        """Virtual method with emit=False must not appear in trampoline (263->281 branch)."""
        virtual_m = TIRMethod(
            name="internal", spelling="internal",
            qualified_name="ns::Base::internal",
            return_type="void", is_virtual=True, is_pure_virtual=False,
            emit=False,
        )
        cls = TIRClass(name="Base", qualified_name="ns::Base", namespace="ns",
                      variable_name="classBase",
                      methods=[virtual_m],
                      has_virtual_methods=True, is_abstract=False)
        out = _gen(TIRModule(name="m", classes=[cls]), pybind11_cfg)
        assert 'internal' not in out


# ---------------------------------------------------------------------------
# Generator: free-function operator<< branch coverage
# ---------------------------------------------------------------------------

class TestFreeFunctionReprBranches:
    def test_ostream_op_one_param_no_repr(self, pybind11_cfg):
        """operator<< with only 1 param → len(params) != 2 → no __repr__ (413->410 branch)."""
        fn = TIRFunction(
            name="operator<<", qualified_name="ns::operator<<", namespace="ns",
            return_type="std::ostream &",
            parameters=[TIRParameter(name="os", type_spelling="std::ostream &")],
            is_operator=True, operator_type="operator<<",
        )
        cls = TIRClass(name="Point", qualified_name="ns::Point", namespace="ns",
                      variable_name="classPoint")
        mod = TIRModule(name="m", classes=[cls], functions=[fn])
        mod.class_by_name["Point"] = cls
        out = _gen(mod, pybind11_cfg)
        assert '__repr__' not in out

    def test_ostream_op_second_param_wrong_class_no_repr(self, pybind11_cfg):
        """operator<< second param doesn't match class → no __repr__ (415->410 branch)."""
        fn = TIRFunction(
            name="operator<<", qualified_name="ns::operator<<", namespace="ns",
            return_type="std::ostream &",
            parameters=[
                TIRParameter(name="os", type_spelling="std::ostream &"),
                TIRParameter(name="x", type_spelling="const ns::Other &"),
            ],
            is_operator=True, operator_type="operator<<",
        )
        cls = TIRClass(name="Point", qualified_name="ns::Point", namespace="ns",
                      variable_name="classPoint")
        mod = TIRModule(name="m", classes=[cls], functions=[fn])
        mod.class_by_name["Point"] = cls
        out = _gen(mod, pybind11_cfg)
        assert '__repr__' not in out


# ---------------------------------------------------------------------------
# LuaLS operator metamethods
# ---------------------------------------------------------------------------

class TestLuaLSOperatorMetamethods:
    def _op_cls(self, operator_type: str, params: list | None = None) -> TIRClass:
        method = TIRMethod(
            name=operator_type,
            spelling=operator_type,
            qualified_name=f"ns::Foo::{operator_type}",
            return_type="ns::Foo",
            parameters=params if params is not None else [],
            is_operator=True,
            operator_type=operator_type,
        )
        return TIRClass(
            name="Foo", qualified_name="ns::Foo", namespace="ns",
            variable_name="classFoo", methods=[method],
        )

    def test_add_operator_emits_add_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator+", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__add(" in out
        assert "function Foo:operator+" not in out

    def test_sub_operator_emits_sub_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator-", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__sub(" in out

    def test_unary_minus_emits_unm_metamethod(self, luals_cfg) -> None:
        cls = self._op_cls("operator-unary", [])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__unm(" in out

    def test_mul_operator_emits_mul_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator*", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__mul(" in out

    def test_div_operator_emits_div_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator/", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__div(" in out

    def test_mod_operator_emits_mod_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator%", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__mod(" in out

    def test_eq_operator_emits_eq_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator==", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__eq(" in out

    def test_lt_operator_emits_lt_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator<", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__lt(" in out

    def test_le_operator_emits_le_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator<=", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__le(" in out

    def test_call_operator_emits_call_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("x", "int")
        cls = self._op_cls("operator()", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__call(" in out

    def test_stream_operator_emits_tostring_metamethod(self, luals_cfg) -> None:
        method = TIRMethod(
            name="operator<<", spelling="operator<<",
            qualified_name="ns::Foo::operator<<",
            return_type="std::ostream &",
            parameters=[],
            is_operator=True, operator_type="operator<<",
        )
        cls = TIRClass(
            name="Foo", qualified_name="ns::Foo", namespace="ns",
            variable_name="classFoo", methods=[method],
        )
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__tostring() end" in out
        assert "---@return string" in out

    def test_band_operator_emits_band_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator&", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__band(" in out

    def test_bor_operator_emits_bor_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator|", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__bor(" in out

    def test_bxor_operator_emits_bxor_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("other", "ns::Foo")
        cls = self._op_cls("operator^", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__bxor(" in out

    def test_bnot_operator_emits_bnot_metamethod(self, luals_cfg) -> None:
        cls = self._op_cls("operator~", [])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__bnot(" in out

    def test_shr_operator_emits_shr_metamethod(self, luals_cfg) -> None:
        p = TIRParameter("n", "int")
        cls = self._op_cls("operator>>", [p])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:__shr(" in out

    def test_unmapped_operator_not_emitted(self, luals_cfg) -> None:
        cls = self._op_cls("operator++prefix", [])
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "operator++" not in out

    def test_regular_method_unaffected(self, luals_cfg) -> None:
        method = TIRMethod(
            name="getValue", spelling="getValue",
            qualified_name="ns::Foo::getValue", return_type="integer",
        )
        cls = TIRClass(
            name="Foo", qualified_name="ns::Foo", namespace="ns",
            variable_name="classFoo", methods=[method],
        )
        out = _gen(TIRModule(name="m", classes=[cls]), luals_cfg)
        assert "function Foo:getValue() end" in out
