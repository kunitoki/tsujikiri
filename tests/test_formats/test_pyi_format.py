"""Tests for the pyi (Python type stubs) output format template."""

from __future__ import annotations

import ast
import io
from typing import Optional

import pytest

from tsujikiri.generator import Generator
from tsujikiri.tir import (
    TIRBase,
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIREnumValue,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pyi_output_config():
    from tsujikiri.configurations import load_output_config
    from tsujikiri.formats import resolve_format_path

    return load_output_config(resolve_format_path("pyi"))


def _gen(module: TIRModule, cfg) -> str:
    buf = io.StringIO()
    Generator(cfg).generate(module, buf)
    return buf.getvalue()


def _simple_class(
    name: str = "Foo",
    qname: str = "ns::Foo",
    methods=None,
    fields=None,
    ctors=None,
    bases=None,
) -> TIRClass:
    return TIRClass(
        name=name,
        qualified_name=qname,
        namespace="ns",
        variable_name=f"class{name}",
        methods=methods or [],
        fields=fields or [],
        constructors=ctors or [],
        bases=bases or [],
    )


# ---------------------------------------------------------------------------
# Module-level prologue
# ---------------------------------------------------------------------------


class TestPrologue:
    def test_auto_generated_comment(self, pyi_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "DO NOT EDIT" in out
        assert "pyi" in out or "mymod" in out

    def test_future_annotations_import(self, pyi_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "from __future__ import annotations" in out

    def test_overload_import(self, pyi_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "from typing import Callable, overload" in out

    def test_api_version_attr_when_set(self, pyi_output_config):
        mod = TIRModule(name="mymod")
        buf = io.StringIO()
        Generator(pyi_output_config).generate(mod, buf, api_version="1.2.3")
        out = buf.getvalue()
        assert "__api_version__: str" in out

    def test_no_api_version_attr_when_absent(self, pyi_output_config):
        mod = TIRModule(name="mymod")
        out = _gen(mod, pyi_output_config)
        assert "__api_version__" not in out


# ---------------------------------------------------------------------------
# Enum binding
# ---------------------------------------------------------------------------


class TestEnumBinding:
    def test_enum_class_inherits_int(self, pyi_output_config):
        enum = TIREnum(
            name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)]
        )
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "class Color(int):" in out

    def test_enum_values_as_class_attrs(self, pyi_output_config):
        enum = TIREnum(
            name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), TIREnumValue("Green", 1)]
        )
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "Red: Color" in out
        assert "Green: Color" in out

    def test_enum_doc(self, pyi_output_config):
        enum = TIREnum(name="Color", qualified_name="ns::Color", doc="Color options", values=[TIREnumValue("Red", 0)])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert '"""Color options"""' in out

    def test_enum_value_doc(self, pyi_output_config):
        val = TIREnumValue("Red", 0, doc="The red color")
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert '"""The red color"""' in out

    def test_suppressed_enum_value_excluded(self, pyi_output_config):
        val = TIREnumValue("Reserved", 99)
        val.emit = False
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0), val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "Reserved" not in out

    def test_renamed_enum_value(self, pyi_output_config):
        val = TIREnumValue("Red", 0, rename="red")
        enum = TIREnum(name="Color", qualified_name="ns::Color", values=[val])
        mod = TIRModule(name="m", enums=[enum])
        out = _gen(mod, pyi_output_config)
        assert "red: Color" in out
        assert "Red: Color" not in out


# ---------------------------------------------------------------------------
# Free function binding
# ---------------------------------------------------------------------------


class TestFunctionBinding:
    def test_simple_function(self, pyi_output_config):
        fn = TIRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="int")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute() -> int: ..." in out

    def test_function_type_mapping(self, pyi_output_config):
        fn = TIRFunction(name="compute", qualified_name="ns::compute", namespace="ns", return_type="double")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "-> float: ..." in out

    def test_function_with_arg(self, pyi_output_config):
        fn = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="int",
            parameters=[TIRParameter("x", "double")],
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute(x: float) -> int: ..." in out

    def test_function_with_default(self, pyi_output_config):
        fn = TIRFunction(
            name="compute",
            qualified_name="ns::compute",
            namespace="ns",
            return_type="int",
            parameters=[TIRParameter("x", "double", default_value="1.0")],
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute(x: float = 1.0) -> int: ..." in out

    def test_function_doc(self, pyi_output_config):
        fn = TIRFunction(
            name="compute", qualified_name="ns::compute", namespace="ns", return_type="int", doc="Computes something"
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert '"""Computes something"""' in out

    def test_camel_to_snake_function_name(self, pyi_output_config):
        fn = TIRFunction(name="computeArea", qualified_name="ns::computeArea", namespace="ns", return_type="int")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def compute_area()" in out

    def test_void_return_maps_to_none(self, pyi_output_config):
        fn = TIRFunction(name="reset", qualified_name="ns::reset", namespace="ns", return_type="void")
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "-> None: ..." in out

    def test_function_multiple_params(self, pyi_output_config):
        fn = TIRFunction(
            name="add",
            qualified_name="ns::add",
            namespace="ns",
            return_type="int",
            parameters=[TIRParameter("x", "int"), TIRParameter("y", "int")],
        )
        mod = TIRModule(name="m", functions=[fn])
        out = _gen(mod, pyi_output_config)
        assert "def add(x: int, y: int) -> int: ..." in out


# ---------------------------------------------------------------------------
# Class binding
# ---------------------------------------------------------------------------


class TestClassBinding:
    def test_simple_class(self, pyi_output_config):
        cls = _simple_class()
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo:" in out

    def test_class_doc(self, pyi_output_config):
        cls = _simple_class()
        cls.doc = "A great class"
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""A great class"""' in out

    def test_class_with_single_base(self, pyi_output_config):
        cls = _simple_class(bases=[TIRBase("ns::Base", "public")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo(Base):" in out

    def test_class_with_multiple_public_bases(self, pyi_output_config):
        cls = _simple_class(bases=[TIRBase("ns::A", "public"), TIRBase("ns::B", "public")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "class Foo(A, B):" in out

    def test_protected_base_excluded(self, pyi_output_config):
        cls = _simple_class(bases=[TIRBase("ns::Hidden", "protected")])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "Hidden" not in out
        assert "class Foo:" in out

    def test_constructor_no_args(self, pyi_output_config):
        ctor = TIRConstructor(parameters=[])
        cls = _simple_class(ctors=[ctor])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self) -> None: ..." in out

    def test_constructor_with_args(self, pyi_output_config):
        ctor = TIRConstructor(parameters=[TIRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self, v: int) -> None: ..." in out

    def test_constructor_with_default(self, pyi_output_config):
        ctor = TIRConstructor(parameters=[TIRParameter("v", "int", default_value="0")])
        cls = _simple_class(ctors=[ctor])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def __init__(self, v: int = 0) -> None: ..." in out

    def test_force_abstract_suppresses_constructor(self, pyi_output_config):
        ctor = TIRConstructor(parameters=[TIRParameter("v", "int")])
        cls = _simple_class(ctors=[ctor])
        cls.force_abstract = True
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "__init__" not in out

    def test_method(self, pyi_output_config):
        method = TIRMethod(
            name="getValue", spelling="getValue", qualified_name="ns::Foo::getValue", return_type="int", is_const=True
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def get_value(self) -> int: ..." in out

    def test_method_type_mapping(self, pyi_output_config):
        method = TIRMethod(
            name="getLabel", spelling="getLabel", qualified_name="ns::Foo::getLabel", return_type="std::string"
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "-> str: ..." in out

    def test_method_doc(self, pyi_output_config):
        method = TIRMethod(
            name="getValue",
            spelling="getValue",
            qualified_name="ns::Foo::getValue",
            return_type="int",
            doc="Gets the value",
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""Gets the value"""' in out

    def test_static_method(self, pyi_output_config):
        method = TIRMethod(
            name="create", spelling="create", qualified_name="ns::Foo::create", return_type="ns::Foo*", is_static=True
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "@staticmethod" in out
        assert "def create()" in out

    def test_static_method_no_self(self, pyi_output_config):
        method = TIRMethod(
            name="create",
            spelling="create",
            qualified_name="ns::Foo::create",
            return_type="ns::Foo*",
            is_static=True,
            parameters=[TIRParameter("x", "int")],
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def create(x: int)" in out
        assert "def create(self" not in out

    def test_readwrite_field(self, pyi_output_config):
        field = TIRField(name="x_", type_spelling="int")
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "x_: int" in out
        assert "read-only" not in out

    def test_readonly_field(self, pyi_output_config):
        field = TIRField(name="max_", type_spelling="int", is_const=True)
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "max_: int" in out
        assert "read-only" in out

    def test_field_type_mapping(self, pyi_output_config):
        field = TIRField(name="label_", type_spelling="std::string")
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "label_: str" in out

    def test_field_doc(self, pyi_output_config):
        field = TIRField(name="x_", type_spelling="int", doc="X coordinate")
        cls = _simple_class(fields=[field])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert '"""X coordinate"""' in out

    def test_method_with_default_arg(self, pyi_output_config):
        p = TIRParameter("x", "int", default_value="0")
        method = TIRMethod(
            name="compute", spelling="compute", qualified_name="ns::Foo::compute", return_type="int", parameters=[p]
        )
        cls = _simple_class(methods=[method])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert "def compute(self, x: int = 0) -> int: ..." in out

    def test_overloaded_methods(self, pyi_output_config):
        m1 = TIRMethod(
            name="process",
            spelling="process",
            qualified_name="ns::Foo::process",
            return_type="int",
            parameters=[TIRParameter("x", "int")],
        )
        m2 = TIRMethod(
            name="process",
            spelling="process",
            qualified_name="ns::Foo::process",
            return_type="float",
            parameters=[TIRParameter("x", "double")],
        )
        cls = _simple_class(methods=[m1, m2])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert out.count("@overload") == 2
        assert "def process(self, x: int) -> int: ..." in out
        assert "def process(self, x: float) -> float: ..." in out

    def test_overloaded_static_methods(self, pyi_output_config):
        m1 = TIRMethod(
            name="make",
            spelling="make",
            qualified_name="ns::Foo::make",
            return_type="ns::Foo*",
            is_static=True,
            parameters=[TIRParameter("x", "int")],
        )
        m2 = TIRMethod(
            name="make",
            spelling="make",
            qualified_name="ns::Foo::make",
            return_type="ns::Foo*",
            is_static=True,
            parameters=[TIRParameter("x", "double")],
        )
        cls = _simple_class(methods=[m1, m2])
        mod = TIRModule(name="m", classes=[cls], class_by_name={"Foo": cls})
        out = _gen(mod, pyi_output_config)
        assert out.count("@overload") == 2
        assert out.count("@staticmethod") == 2
        assert "def make(x: int)" in out
        assert "def make(x: float)" in out


# ---------------------------------------------------------------------------
# Format discovery
# ---------------------------------------------------------------------------


class TestPyiFormatDiscovery:
    def test_pyi_in_list_formats(self):
        from tsujikiri.formats import list_builtin_formats

        fmts = list_builtin_formats()
        assert "pyi" in fmts

    def test_pyi_format_name(self, pyi_output_config):
        assert pyi_output_config.format_name == "pyi"

    def test_pyi_language_is_python(self, pyi_output_config):
        assert pyi_output_config.language == "python"

    def test_type_mappings_loaded(self, pyi_output_config):
        assert pyi_output_config.type_mappings["double"] == "float"
        assert pyi_output_config.type_mappings["std::string"] == "str"
        assert pyi_output_config.type_mappings["bool"] == "bool"
        assert pyi_output_config.type_mappings["void"] == "None"


# ---------------------------------------------------------------------------
# Free-function deprecated annotation
# ---------------------------------------------------------------------------


class TestPyiFreeFunctionDeprecated:
    def _mod(self, fn: TIRFunction) -> TIRModule:
        mod = TIRModule(name="test")
        mod.functions = [fn]
        return mod

    def test_deprecated_emits_comment(self, pyi_output_config) -> None:
        fn = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="None",
            is_deprecated=True,
            deprecation_message="use newOp instead",
        )
        buf = io.StringIO()
        Generator(pyi_output_config).generate(self._mod(fn), buf)
        output = buf.getvalue()
        assert "# deprecated" in output
        assert "use newOp instead" in output

    def test_not_deprecated_no_comment(self, pyi_output_config) -> None:
        fn = TIRFunction(
            name="currentOp",
            qualified_name="currentOp",
            namespace="",
            return_type="None",
            is_deprecated=False,
        )
        buf = io.StringIO()
        Generator(pyi_output_config).generate(self._mod(fn), buf)
        output = buf.getvalue()
        assert "# deprecated" not in output

    def test_deprecated_without_message(self, pyi_output_config) -> None:
        fn = TIRFunction(
            name="legacyOp",
            qualified_name="legacyOp",
            namespace="",
            return_type="None",
            is_deprecated=True,
        )
        buf = io.StringIO()
        Generator(pyi_output_config).generate(self._mod(fn), buf)
        output = buf.getvalue()
        assert "# deprecated" in output

    def test_overloaded_deprecated_emits_comment(self, pyi_output_config) -> None:
        fn1 = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="None",
            is_deprecated=True,
            deprecation_message="use newOp",
            parameters=[TIRParameter(name="x", type_spelling="int")],
        )
        fn2 = TIRFunction(
            name="oldOp",
            qualified_name="oldOp",
            namespace="",
            return_type="None",
            is_deprecated=False,
            parameters=[TIRParameter(name="x", type_spelling="float")],
        )
        mod = TIRModule(name="test")
        mod.functions = [fn1, fn2]
        buf = io.StringIO()
        Generator(pyi_output_config).generate(mod, buf)
        output = buf.getvalue()
        assert "# deprecated" in output
        assert "use newOp" in output


# ---------------------------------------------------------------------------
# Docstring placement — a documented stub uses the docstring as its body
# ---------------------------------------------------------------------------


def _method(
    name: str,
    doc: Optional[str] = None,
    is_static: bool = False,
    param_type: str = "int",
    return_doc: Optional[str] = None,
) -> TIRMethod:
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"ns::Foo::{name}",
        return_type="int",
        parameters=[TIRParameter("x", param_type)],
        is_static=is_static,
        doc=doc,
        return_doc=return_doc,
    )


def _function(name: str, doc: Optional[str] = None, param_type: str = "int") -> TIRFunction:
    return TIRFunction(
        name=name,
        qualified_name=f"ns::{name}",
        namespace="ns",
        return_type="int",
        parameters=[TIRParameter("x", param_type)],
        doc=doc,
    )


class TestDocstringPlacement:
    @pytest.fixture(scope="class")
    def output(self, pyi_output_config) -> str:
        cls = _simple_class(
            ctors=[TIRConstructor(parameters=[TIRParameter("w", "int", doc="The width.")], doc="Builds it.")],
            methods=[
                _method("width", doc="Gets the width.", return_doc="The width."),
                _method("plain"),
                _method("make", doc="Makes one.", is_static=True),
                _method("raw", is_static=True),
                _method("set", doc="Sets an int."),
                _method("set", param_type="float"),
                _method("count", doc="Counts ints.", is_static=True),
                _method("count", is_static=True, param_type="float"),
            ],
            fields=[TIRField(name="x_", type_spelling="int", doc="X coordinate")],
        )
        scoped = TIREnum(
            name="Channel",
            qualified_name="ns::Channel",
            is_scoped=True,
            values=[TIREnumValue("Red", 0, doc="Red one."), TIREnumValue("Green", 1)],
        )
        plain = TIREnum(name="Mode", qualified_name="ns::Mode", values=[TIREnumValue("Fast", 0, doc="Fast mode.")])
        mod = TIRModule(
            name="m",
            classes=[cls],
            class_by_name={"Foo": cls},
            enums=[scoped, plain],
            functions=[
                _function("documented", doc="Free fn."),
                _function("bare"),
                _function("over", doc="Over int."),
                _function("over", param_type="float"),
            ],
        )
        return _gen(mod, pyi_output_config)

    def test_output_is_valid_python(self, output: str) -> None:
        ast.parse(output)

    def test_constructor_docstring_is_body(self, output: str) -> None:
        assert '    def __init__(self, w: int) -> None:\n        """Builds it.\n' in output
        assert "-> None: ..." not in output

    def test_method_docstring_is_body(self, output: str) -> None:
        assert '    def width(self, x: int) -> int:\n        """Gets the width.\n' in output

    def test_undocumented_method_keeps_ellipsis(self, output: str) -> None:
        assert "    def plain(self, x: int) -> int: ...\n" in output
        assert "    def raw(x: int) -> int: ...\n" in output

    def test_static_method_docstring_is_body(self, output: str) -> None:
        assert '    @staticmethod\n    def make(x: int) -> int:\n        """Makes one."""\n' in output

    def test_overloaded_method_docstrings(self, output: str) -> None:
        assert '    @overload\n    def set(self, x: int) -> int:\n        """Sets an int."""\n' in output
        assert "    @overload\n    def set(self, x: float) -> int: ...\n" in output

    def test_overloaded_static_method_docstrings(self, output: str) -> None:
        assert '    @overload\n    @staticmethod\n    def count(x: int) -> int:\n        """Counts ints."""\n' in output
        assert "    @overload\n    @staticmethod\n    def count(x: float) -> int: ...\n" in output

    def test_function_docstring_is_body(self, output: str) -> None:
        assert 'def documented(x: int) -> int:\n    """Free fn."""\n' in output
        assert "def bare(x: int) -> int: ...\n" in output

    def test_overloaded_function_docstrings(self, output: str) -> None:
        assert '@overload\ndef over(x: int) -> int:\n    """Over int."""\n' in output
        assert "@overload\ndef over(x: float) -> int: ...\n" in output

    def test_enum_value_docstrings_align_with_value(self, output: str) -> None:
        assert '    Red: int = 0\n    """Red one."""\n    Green: int = 1\n' in output
        assert '    Fast: Mode\n    """Fast mode."""' in output

    def test_field_docstring(self, output: str) -> None:
        assert '    x_: int\n    """X coordinate"""' in output


# ---------------------------------------------------------------------------
# Operators — stubbed as the dunder methods pybind11 binds
# ---------------------------------------------------------------------------


def _op(
    operator_type: str,
    params: Optional[list[TIRParameter]] = None,
    return_type: str = "ns::Foo",
    owner: str = "Foo",
    doc: Optional[str] = None,
) -> TIRMethod:
    name = operator_type.removesuffix("unary")
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"ns::{owner}::{name}",
        return_type=return_type,
        parameters=params or [],
        is_operator=True,
        operator_type=operator_type,
        doc=doc,
    )


def _free_op(operator_type: str, params: list[TIRParameter], return_type: str = "ns::Foo") -> TIRFunction:
    return TIRFunction(
        name=operator_type,
        qualified_name=f"ns::{operator_type}",
        namespace="ns",
        return_type=return_type,
        parameters=params,
        is_operator=True,
        operator_type=operator_type,
    )


class TestOperators:
    @pytest.fixture(scope="class")
    def output(self, pyi_output_config) -> str:
        foo = _simple_class(
            methods=[
                _op("operator+", [TIRParameter("o", "const ns::Foo &")], doc="Adds two."),
                _op("operator+", [TIRParameter("o", "int")]),
                _op("operator-unary"),
                _op("operator==", [TIRParameter("o", "const ns::Foo &")], return_type="bool"),
                _op("operator!", return_type="bool"),
                _op("operator bool", return_type="bool"),
                _op("operator=", [TIRParameter("o", "const ns::Foo &")], return_type="ns::Foo &"),
                _op("operator<<", [TIRParameter("os", "std::ostream &")], return_type="std::ostream &"),
                TIRMethod(
                    name="items",
                    spelling="items",
                    qualified_name="ns::Foo::items",
                    return_type="std::vector<ns::Foo>",
                    parameters=[TIRParameter("keys", "const std::vector<std::optional<std::string>> &")],
                ),
            ]
        )
        bare = _simple_class(
            "Bare", "ns::Bare", methods=[_op("operator=", [TIRParameter("o", "int")], "ns::Bare &", owner="Bare")]
        )
        truthy = _simple_class(
            "Truthy",
            "ns::Truthy",
            methods=[_op("operator bool", return_type="bool", owner="Truthy", doc="Is set.")],
        )
        printable = _simple_class("Printable", "ns::Printable")
        mod = TIRModule(
            name="m",
            classes=[foo, bare, truthy, printable],
            class_by_name={c.name: c for c in (foo, bare, truthy, printable)},
            enums=[
                TIREnum(name="Nothing", qualified_name="ns::Nothing", is_scoped=True),
                TIREnum(name="Void", qualified_name="ns::Void"),
            ],
            functions=[
                _free_op("operator*", [TIRParameter("f", "const ns::Foo &"), TIRParameter("k", "int")]),
                _free_op("operator+", [TIRParameter("f", "const ns::Foo &"), TIRParameter("k", "double")]),
                _free_op(
                    "operator<<",
                    [TIRParameter("os", "std::ostream &"), TIRParameter("f", "const ns::Foo &")],
                    "std::ostream &",
                ),
                _free_op(
                    "operator<<",
                    [TIRParameter("os", "std::ostream &"), TIRParameter("p", "const ns::Printable &")],
                    "std::ostream &",
                ),
                _free_op("operator-", [TIRParameter("k", "int"), TIRParameter("f", "const ns::Foo &")]),
                _function("regular"),
            ],
        )
        return _gen(mod, pyi_output_config)

    @staticmethod
    def _class(output: str, name: str) -> str:
        start = output.index(f"class {name}")
        end = output.find("\nclass ", start + 1)
        return output[start : end if end != -1 else len(output)]

    def test_output_is_valid_python(self, output: str) -> None:
        ast.parse(output)

    def test_no_raw_operator_names(self, output: str) -> None:
        assert "def operator" not in output

    def test_member_and_free_overloads_are_contiguous(self, output: str) -> None:
        assert (
            "    @overload\n    def __add__(self, o: Foo) -> Foo:\n"
            '        """Adds two."""\n'
            "    @overload\n    def __add__(self, o: int) -> Foo: ...\n"
            "    @overload\n    def __add__(self, k: float) -> Foo: ...\n"
        ) in output

    def test_unary_operator(self, output: str) -> None:
        assert "    def __neg__(self) -> Foo: ...\n" in output

    def test_single_operator_has_no_overload(self, output: str) -> None:
        assert "    def __eq__(self, o: Foo) -> bool: ...\n" in output
        assert "@overload\n    def __eq__" not in output

    def test_free_operator_drops_self_operand(self, output: str) -> None:
        assert "    def __mul__(self, k: int) -> Foo: ...\n" in output

    def test_bool_conversions_collapse(self, output: str) -> None:
        assert self._class(output, "Foo").count("def __bool__") == 1
        assert "    def __bool__(self) -> bool: ...\n" in output

    def test_single_bool_keeps_docstring(self, output: str) -> None:
        assert '    def __bool__(self) -> bool:\n        """Is set."""' in self._class(output, "Truthy")

    def test_repr_emitted_once(self, output: str) -> None:
        foo = self._class(output, "Foo")
        assert foo.count("def __repr__") == 1
        assert "    def __repr__(self) -> str: ...\n" in foo

    def test_free_ostream_operator_alone_gives_repr(self, output: str) -> None:
        assert self._class(output, "Printable").strip() == "class Printable:\n    def __repr__(self) -> str: ..."

    def test_unmapped_operator_skipped_and_empty_body_is_ellipsis(self, output: str) -> None:
        assert self._class(output, "Bare").strip() == "class Bare:\n    ..."

    def test_unattached_free_operators_not_module_functions(self, output: str) -> None:
        assert "\ndef __" not in output
        assert "def regular(x: int) -> int: ..." in output

    def test_empty_enums_have_ellipsis_body(self, output: str) -> None:
        assert "class Nothing(enum.IntEnum):\n    ...\n" in output
        assert "class Void(int):\n    ...\n" in output

    def test_container_and_namespace_types_are_mapped(self, output: str) -> None:
        assert "    def items(self, keys: list[str | None]) -> list[Foo]: ...\n" in output


class TestPyiTypeMappings:
    @pytest.mark.parametrize(
        ("cpp", "py"),
        [
            ("const ns::Foo &", "Foo"),
            ("ns::Foo &&", "Foo"),
            ("ns::Foo *", "Foo | None"),
            ("const ns::Outer::Inner *", "Inner | None"),
            ("const std::vector<ns::Foo> &", "list[Foo]"),
            ("std::array<int, 4>", "list[int]"),
            ("std::list<double>", "list[float]"),
            ("std::deque<bool>", "list[bool]"),
            ("std::set<std::string>", "set[str]"),
            ("std::unordered_set<int>", "set[int]"),
            ("std::map<std::string, std::vector<int>>", "dict[str, list[int]]"),
            ("std::unordered_map<int, const ns::Foo *>", "dict[int, Foo | None]"),
            ("std::pair<int, float>", "tuple[int, float]"),
            ("std::tuple<int, std::string, bool>", "tuple[int, str, bool]"),
            ("std::tuple<>", "tuple[()]"),
            ("std::optional<ns::Foo>", "Foo | None"),
            ("std::variant<int, std::string>", "int | str"),
            ("std::function<void()>", "Callable[[], None]"),
            ("std::function<ns::Foo &(const ns::Foo &, int)>", "Callable[[Foo, int], Foo]"),
            ("std::shared_ptr<ns::Foo>", "Foo"),
            ("std::unique_ptr<ns::Foo>", "Foo"),
            ("unsigned char", "int"),
            ("signed char", "int"),
            ("long long", "int"),
            ("std::size_t", "int"),
            ("const char *", "str"),
            ("void *", "object"),
            ("char", "str"),
        ],
    )
    def test_mapping(self, pyi_output_config, cpp: str, py: str) -> None:
        assert Generator(pyi_output_config)._map_type(cpp) == py
