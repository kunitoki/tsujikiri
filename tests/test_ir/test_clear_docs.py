"""Tests for tir.clear_extracted_docs."""

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
    clear_extracted_docs,
)


def _module() -> TIRModule:
    inner = TIRClass(
        name="Inner",
        qualified_name="ns::Cls::Inner",
        namespace="ns",
        doc="inner doc",
        methods=[
            TIRMethod(
                name="go",
                spelling="go",
                qualified_name="ns::Cls::Inner::go",
                return_type="void",
                doc="inner method",
            )
        ],
    )
    method = TIRMethod(
        name="setVolume",
        spelling="setVolume",
        qualified_name="ns::Cls::setVolume",
        return_type="void",
        parameters=[TIRParameter("volume", "float", doc="vol doc")],
        doc="method doc",
        return_doc="ret doc",
    )
    ctor = TIRConstructor(parameters=[TIRParameter("v", "int", doc="ctor param")], doc="ctor doc")
    field = TIRField(name="data_", type_spelling="int", doc="field doc")
    enum = TIREnum(
        name="Mode",
        qualified_name="ns::Cls::Mode",
        values=[TIREnumValue("A", 0, doc="value doc")],
        doc="enum doc",
    )
    cls = TIRClass(
        name="Cls",
        qualified_name="ns::Cls",
        namespace="ns",
        doc="class doc",
        methods=[method],
        constructors=[ctor],
        fields=[field],
        enums=[enum],
        inner_classes=[inner],
    )
    fn = TIRFunction(
        name="compute",
        qualified_name="ns::compute",
        namespace="ns",
        return_type="double",
        parameters=[TIRParameter("x", "double", doc="x doc")],
        doc="fn doc",
        return_doc="fn ret",
    )
    top_enum = TIREnum(
        name="Color",
        qualified_name="ns::Color",
        values=[TIREnumValue("Red", 0, doc="red doc")],
        doc="color doc",
    )
    return TIRModule(
        name="m",
        classes=[cls],
        functions=[fn],
        enums=[top_enum],
        class_by_name={"Cls": cls},
    )


class TestClearExtractedDocs:
    def test_clears_everything(self):
        mod = _module()
        clear_extracted_docs(mod)
        cls = mod.classes[0]
        assert cls.doc is None
        method = cls.methods[0]
        assert method.doc is None
        assert method.return_doc is None
        assert method.parameters[0].doc is None
        assert cls.constructors[0].doc is None
        assert cls.constructors[0].parameters[0].doc is None
        assert cls.fields[0].doc is None
        assert cls.enums[0].doc is None
        assert cls.enums[0].values[0].doc is None
        inner = cls.inner_classes[0]
        assert inner.doc is None
        assert inner.methods[0].doc is None
        fn = mod.functions[0]
        assert fn.doc is None
        assert fn.return_doc is None
        assert fn.parameters[0].doc is None
        assert mod.enums[0].doc is None
        assert mod.enums[0].values[0].doc is None
