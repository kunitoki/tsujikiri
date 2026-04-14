"""Tests for the luabridge3 output format — holder type and operator metamethods."""

from __future__ import annotations

import io

from tsujikiri.generator import Generator
from tsujikiri.ir import (
    IRBase,
    IRClass,
    IRConstructor,
    IRMethod,
    IRModule,
    IRParameter,
    IRProperty,
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


def _gen(module: IRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _simple_class(
    name: str = "Foo",
    qname: str = "ns::Foo",
    methods=None,
    ctors=None,
    bases=None,
) -> IRClass:
    return IRClass(
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
        ctor = IRConstructor(parameters=[IRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructor<void (*)(int)>()" in out
        assert "addConstructorFrom" not in out

    def test_holder_type_uses_add_constructor_from(self, lua_cfg):
        ctor = IRConstructor(parameters=[IRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void(int)>()" in out
        assert ".addConstructor<" not in out

    def test_holder_type_default_ctor(self, lua_cfg):
        ctor = IRConstructor(parameters=[])
        cls = _simple_class(ctors=[ctor])
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void()>()" in out

    def test_holder_type_multiple_ctors(self, lua_cfg):
        ctor1 = IRConstructor(parameters=[])
        ctor2 = IRConstructor(parameters=[IRParameter("x", "int")])
        cls = _simple_class(ctors=[ctor1, ctor2])
        cls.holder_type = "std::shared_ptr"
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert ".addConstructorFrom<std::shared_ptr<ns::Foo>, void(), void(int)>()" in out


# ---------------------------------------------------------------------------
# Operator metamethods
# ---------------------------------------------------------------------------

class TestOperatorMetamethods:
    def test_operator_plus_binds_to_add_metamethod(self, lua_cfg):
        p = IRParameter("other", "const ns::Foo &")
        method = IRMethod(name="operator+", spelling="operator+",
                          qualified_name="ns::Foo::operator+", return_type="ns::Foo",
                          is_operator=True, operator_type="operator+", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addMetaMethod("__add"' in out
        assert "&ns::Foo::operator+" in out

    def test_operator_eq_binds_to_eq_metamethod(self, lua_cfg):
        p = IRParameter("other", "const ns::Foo &")
        method = IRMethod(name="operator==", spelling="operator==",
                          qualified_name="ns::Foo::operator==", return_type="bool",
                          is_operator=True, operator_type="operator==", parameters=[p])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addMetaMethod("__eq"' in out

    def test_operator_stream_binds_to_tostring_lambda(self, lua_cfg):
        method = IRMethod(name="operator<<", spelling="operator<<",
                          qualified_name="ns::Foo::operator<<", return_type="std::ostream &",
                          is_operator=True, operator_type="operator<<")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addMetaMethod("__tostring"' in out
        assert "std::ostringstream" in out
        assert "&ns::Foo::operator<<" not in out

    def test_operator_minus_unary_binds_to_unm(self, lua_cfg):
        method = IRMethod(name="operator-", spelling="operator-",
                          qualified_name="ns::Foo::operator-", return_type="ns::Foo",
                          is_operator=True, operator_type="operator-unary", parameters=[])
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addMetaMethod("__unm"' in out

    def test_regular_method_not_metamethod(self, lua_cfg):
        method = IRMethod(name="getValue", spelling="getValue",
                          qualified_name="ns::Foo::getValue", return_type="int")
        cls = _simple_class(methods=[method])
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert "addMetaMethod" not in out
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
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addProperty("arrival_message"' in out
        assert "&ns::Foo::getArrivalMessage" in out
        assert "&ns::Foo::setArrivalMessage" in out

    def test_readonly_property_emits_add_property_with_nullptr(self, lua_cfg):
        prop = IRProperty(name="name", getter="getName", type_spelling="std::string")
        cls = _simple_class()
        cls.properties.append(prop)
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert '.addProperty("name"' in out
        assert "&ns::Foo::getName" in out
        assert "nullptr" in out

    def test_no_properties_by_default(self, lua_cfg):
        cls = _simple_class()
        mod = IRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, lua_cfg)
        assert "addProperty" not in out
