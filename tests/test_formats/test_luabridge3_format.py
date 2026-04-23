"""Tests for the luabridge3 output format — holder type and operator metamethods."""

from __future__ import annotations

import io

from tsujikiri.generator import Generator
from tsujikiri.ir import IRProperty
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

import pytest


@pytest.fixture(scope="module")
def lua_cfg():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path
    return load_output_config(resolve_format_path("luabridge3"))


def _gen(module: TIRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _simple_class(
    name: str = "Foo",
    qname: str = "ns::Foo",
    methods=None,
    ctors=None,
    bases=None,
) -> TIRClass:
    return TIRClass(
        name=name,
        qualified_name=qname,
        namespace="ns",
        variable_name=f"class{name}",
        methods=methods or [],
        constructors=ctors or [],
        bases=bases or [],
    )


# ---------------------------------------------------------------------------
# Holder type — addConstructorFrom
# ---------------------------------------------------------------------------

class TestHolderType:
    def test_no_holder_uses_add_constructor(self, lua_cfg):
        ctor = TIRConstructor(parameters=[TIRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructor<void (*)(int)>()" in out
        assert "addConstructorFrom" not in out

    def test_holder_type_uses_add_constructor_from(self, lua_cfg):
        ctor = TIRConstructor(parameters=[TIRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.holder_type = "std::shared_ptr"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void(int)>()" in out
        assert ".addConstructor<" not in out

    def test_holder_type_default_ctor(self, lua_cfg):
        ctor = TIRConstructor(parameters=[])
        cls = _simple_class(ctors=[ctor])
        cls.holder_type = "std::shared_ptr"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void()>()" in out

    def test_holder_type_multiple_ctors(self, lua_cfg):
        ctor1 = TIRConstructor(parameters=[])
        ctor2 = TIRConstructor(parameters=[TIRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor1, ctor2])
        cls.holder_type = "std::shared_ptr"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void(), void(int)>()" in out


# ---------------------------------------------------------------------------
# Operator metamethods
# ---------------------------------------------------------------------------

class TestOperatorMetamethods:
    def test_operator_plus_binds_to_add_metamethod(self, lua_cfg):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(name="operator+", spelling="operator+",
                          qualified_name="ns::Foo::operator+", return_type="ns::Foo",
                          is_operator=True, operator_type="operator+", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__add"' in out
        assert "&ns::Foo::operator+" in out

    def test_operator_eq_binds_to_eq_metamethod(self, lua_cfg):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(name="operator==", spelling="operator==",
                          qualified_name="ns::Foo::operator==", return_type="bool",
                          is_operator=True, operator_type="operator==", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__eq"' in out
        assert "&ns::Foo::operator==" in out

    def test_operator_minus_unary_binds_to_unm(self, lua_cfg):
        method = TIRMethod(name="operator-", spelling="operator-",
                          qualified_name="ns::Foo::operator-", return_type="ns::Foo",
                          is_operator=True, operator_type="operator-unary", parameters=[])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__unm"' in out
        assert "&ns::Foo::operator-" in out

    def test_operator_bitwise_and_binds_to_band(self, lua_cfg):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(name="operator&", spelling="operator&",
                          qualified_name="ns::Foo::operator&", return_type="ns::Foo",
                          is_operator=True, operator_type="operator&", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__band"' in out
        assert "&ns::Foo::operator&" in out

    def test_operator_bitwise_or_binds_to_bor(self, lua_cfg):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(name="operator|", spelling="operator|",
                          qualified_name="ns::Foo::operator|", return_type="ns::Foo",
                          is_operator=True, operator_type="operator|", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__bor"' in out
        assert "&ns::Foo::operator|" in out

    def test_operator_bitwise_xor_binds_to_bxor(self, lua_cfg):
        p = TIRParameter("other", "const ns::Foo &")
        method = TIRMethod(name="operator^", spelling="operator^",
                          qualified_name="ns::Foo::operator^", return_type="ns::Foo",
                          is_operator=True, operator_type="operator^", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__bxor"' in out
        assert "&ns::Foo::operator^" in out

    def test_operator_bitwise_not_binds_to_bnot(self, lua_cfg):
        method = TIRMethod(name="operator~", spelling="operator~",
                          qualified_name="ns::Foo::operator~", return_type="ns::Foo",
                          is_operator=True, operator_type="operator~", parameters=[])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__bnot"' in out
        assert "&ns::Foo::operator~" in out

    def test_operator_left_shift_binds_to_shl(self, lua_cfg):
        method = TIRMethod(name="operator<<", spelling="operator<<",
                          qualified_name="ns::Foo::operator<<", return_type="ns::Foo",
                          is_operator=True, operator_type="operator<<")
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__shl"' in out
        assert "&ns::Foo::operator<<" in out

    def test_operator_right_shift_binds_to_shr(self, lua_cfg):
        p = TIRParameter("n", "int")
        method = TIRMethod(name="operator>>", spelling="operator>>",
                          qualified_name="ns::Foo::operator>>", return_type="ns::Foo",
                          is_operator=True, operator_type="operator>>", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addFunction("__shr"' in out
        assert "&ns::Foo::operator>>" in out

    def test_regular_method_not_metamethod(self, lua_cfg):
        method = TIRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int")
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert "addFunction" in out
        assert '.addFunction("get_value"' in out


# ---------------------------------------------------------------------------
# Synthetic property bindings
# ---------------------------------------------------------------------------

class TestPropertyBinding:
    def test_readwrite_property_emits_add_property_with_setter(self, lua_cfg):
        prop = IRProperty(name="arrivalMessage", getter="getArrivalMessage",
                          setter="setArrivalMessage", type_spelling="std::string")
        cls = _simple_class()
        cls.properties.append(prop)
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addProperty("arrival_message"' in out
        assert "&ns::Foo::getArrivalMessage" in out
        assert "&ns::Foo::setArrivalMessage" in out

    def test_readonly_property_emits_add_property_with_nullptr(self, lua_cfg):
        prop = IRProperty(name="name", getter="getName", type_spelling="std::string")
        cls = _simple_class()
        cls.properties.append(prop)
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addProperty("name"' in out
        assert "&ns::Foo::getName" in out
        assert "nullptr" in out

    def test_no_properties_by_default(self, lua_cfg):
        cls = _simple_class()
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert "addProperty" not in out


# ---------------------------------------------------------------------------
# Free-function wrapper_code support
# ---------------------------------------------------------------------------

class TestFreeFunctionWrapperCode:
    def test_non_overloaded_wrapper_code_emitted(self, lua_cfg) -> None:
        fn = TIRFunction(
            name="myFunc",
            qualified_name="myFunc",
            namespace="",
            return_type="void",
            wrapper_code="+[] (int x) { return myFunc(x * 2); }",
        )
        mod = TIRModule(name="m")
        mod.functions = [fn]
        out = _gen(mod, lua_cfg)
        assert "+[] (int x) { return myFunc(x * 2); }" in out
        assert "&myFunc" not in out

    def test_non_overloaded_no_wrapper_code_uses_address(self, lua_cfg) -> None:
        fn = TIRFunction(
            name="myFunc",
            qualified_name="myFunc",
            namespace="",
            return_type="void",
        )
        mod = TIRModule(name="m")
        mod.functions = [fn]
        out = _gen(mod, lua_cfg)
        assert "&myFunc" in out
