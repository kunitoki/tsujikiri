"""Tests for documentation kwargs on transform stages and the modify_class stage."""

from __future__ import annotations

from tsujikiri.tir import (
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
from tsujikiri.transforms import (
    InjectConstructorStage,
    InjectFunctionStage,
    InjectMethodStage,
    ModifyArgumentStage,
    ModifyClassStage,
    ModifyConstructorStage,
    ModifyEnumStage,
    ModifyFieldStage,
    ModifyFunctionStage,
    ModifyMethodStage,
)


def _module() -> TIRModule:
    method = TIRMethod(
        name="setVolume",
        spelling="setVolume",
        qualified_name="ns::Cls::setVolume",
        return_type="void",
        parameters=[TIRParameter("volume", "float")],
    )
    ctor = TIRConstructor(parameters=[TIRParameter("v", "int")])
    field = TIRField(name="data_", type_spelling="int")
    enum = TIREnum(name="Mode", qualified_name="ns::Cls::Mode", values=[TIREnumValue("A", 0)])
    cls = TIRClass(
        name="Cls",
        qualified_name="ns::Cls",
        namespace="ns",
        methods=[method],
        constructors=[ctor],
        fields=[field],
        enums=[enum],
    )
    fn = TIRFunction(
        name="compute",
        qualified_name="ns::compute",
        namespace="ns",
        return_type="double",
        parameters=[TIRParameter("x", "double")],
    )
    top_enum = TIREnum(name="Color", qualified_name="ns::Color", values=[TIREnumValue("Red", 0)])
    return TIRModule(
        name="m",
        classes=[cls],
        functions=[fn],
        enums=[top_enum],
        class_by_name={"Cls": cls},
    )


def _cls(mod: TIRModule) -> TIRClass:
    return mod.classes[0]


def _method(mod: TIRModule) -> TIRMethod:
    return _cls(mod).methods[0]


class TestModifyClassStage:
    def test_sets_doc(self):
        mod = _module()
        ModifyClassStage(**{"class": "Cls", "doc": "A class."}).apply(mod)
        assert _cls(mod).doc == "A class."

    def test_rename_and_remove(self):
        mod = _module()
        ModifyClassStage(**{"class": "Cls", "rename": "Helper", "remove": True}).apply(mod)
        assert _cls(mod).rename == "Helper"
        assert _cls(mod).emit is False

    def test_regex_match(self):
        mod = _module()
        ModifyClassStage(**{"class": "C.*", "class_is_regex": True, "doc": "d"}).apply(mod)
        assert _cls(mod).doc == "d"

    def test_no_match_leaves_unchanged(self):
        mod = _module()
        ModifyClassStage(**{"class": "Other", "doc": "d"}).apply(mod)
        assert _cls(mod).doc is None


class TestModifyMethodDoc:
    def test_doc_and_return_doc(self):
        mod = _module()
        ModifyMethodStage(**{"class": "Cls", "method": "setVolume", "doc": "Sets it.", "return_doc": "nothing"}).apply(
            mod
        )
        assert _method(mod).doc == "Sets it."
        assert _method(mod).return_doc == "nothing"


class TestModifyArgumentDoc:
    def test_sets_param_doc(self):
        mod = _module()
        ModifyArgumentStage(**{"class": "Cls", "method": "setVolume", "argument": "volume", "doc": "in dB"}).apply(mod)
        assert _method(mod).parameters[0].doc == "in dB"


class TestModifyConstructorDoc:
    def test_sets_doc(self):
        mod = _module()
        ModifyConstructorStage(**{"class": "Cls", "signature": "int", "doc": "Builds it."}).apply(mod)
        assert _cls(mod).constructors[0].doc == "Builds it."


class TestModifyFieldDoc:
    def test_sets_doc(self):
        mod = _module()
        ModifyFieldStage(**{"class": "Cls", "field": "data_", "doc": "the data"}).apply(mod)
        assert _cls(mod).fields[0].doc == "the data"


class TestModifyEnumDoc:
    def test_sets_doc(self):
        mod = _module()
        ModifyEnumStage(**{"enum": "Color", "doc": "colors"}).apply(mod)
        assert next(e for e in mod.enums if e.name == "Color").doc == "colors"


class TestModifyFunctionDoc:
    def test_doc_and_return_doc(self):
        mod = _module()
        ModifyFunctionStage(**{"function": "compute", "doc": "Computes.", "return_doc": "a number"}).apply(mod)
        fn = mod.functions[0]
        assert fn.doc == "Computes."
        assert fn.return_doc == "a number"


class TestInjectMethodDoc:
    def test_injects_with_docs(self):
        mod = _module()
        InjectMethodStage(
            **{
                "class": "Cls",
                "name": "Stop",
                "return_type": "void",
                "doc": "Stops it.",
                "return_doc": "nothing",
                "parameters": [{"name": "fadeTime", "type": "float", "doc": "fade seconds"}],
            }
        ).apply(mod)
        injected = next(m for m in _cls(mod).methods if m.name == "Stop")
        assert injected.doc == "Stops it."
        assert injected.return_doc == "nothing"
        assert injected.parameters[0].doc == "fade seconds"


class TestInjectConstructorDoc:
    def test_injects_with_docs(self):
        mod = _module()
        InjectConstructorStage(
            **{
                "class": "Cls",
                "doc": "Builds it.",
                "parameters": [{"name": "size", "type": "int", "doc": "the size"}],
            }
        ).apply(mod)
        injected = _cls(mod).constructors[-1]
        assert injected.doc == "Builds it."
        assert injected.parameters[0].doc == "the size"


class TestInjectFunctionDoc:
    def test_injects_with_docs(self):
        mod = _module()
        InjectFunctionStage(
            **{
                "name": "helper",
                "return_type": "int",
                "namespace": "ns",
                "doc": "Helps.",
                "return_doc": "a code",
                "parameters": [{"name": "n", "type": "int", "doc": "count"}],
            }
        ).apply(mod)
        injected = next(f for f in mod.functions if f.name == "helper")
        assert injected.doc == "Helps."
        assert injected.return_doc == "a code"
        assert injected.parameters[0].doc == "count"
