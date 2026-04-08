"""Tests for transforms.py — TransformPipeline and built-in stages."""

from __future__ import annotations

import pytest

from tsujikiri.configurations import TransformSpec
from tsujikiri.ir import IRClass, IRMethod, IRModule, IRParameter
from tsujikiri.transforms import (
    AddTypeMappingStage,
    InjectMethodStage,
    RenameClassStage,
    RenameMethodStage,
    SuppressClassStage,
    SuppressMethodStage,
    TransformPipeline,
    build_pipeline_from_config,
    register_stage,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_module() -> IRModule:
    """One class with a few methods."""
    methods = [
        IRMethod(name="getValue", spelling="getValue",
                 qualified_name="Cls::getValue", return_type="int"),
        IRMethod(name="setValue", spelling="setValue",
                 qualified_name="Cls::setValue", return_type="void",
                 parameters=[IRParameter("v", "int")]),
        IRMethod(name="operator+", spelling="operator+",
                 qualified_name="Cls::operator+", return_type="Cls"),
    ]
    cls = IRClass(name="Cls", qualified_name="ns::Cls", namespace="ns",
                  methods=list(methods))
    return IRModule(name="m", classes=[cls], class_by_name={"Cls": cls})


def _get_cls(mod: IRModule, name: str = "Cls") -> IRClass:
    return next(c for c in mod.classes if c.name == name)


# ---------------------------------------------------------------------------
# RenameMethodStage
# ---------------------------------------------------------------------------

class TestRenameMethodStage:
    def test_renames_target_method(self):
        mod = _simple_module()
        stage = RenameMethodStage(**{"class": "Cls", "from": "getValue", "to": "get"})
        stage.apply(mod)
        m = next(m for m in _get_cls(mod).methods if m.spelling == "getValue")
        assert m.rename == "get"

    def test_does_not_rename_others(self):
        mod = _simple_module()
        stage = RenameMethodStage(**{"class": "Cls", "from": "getValue", "to": "get"})
        stage.apply(mod)
        m = next(m for m in _get_cls(mod).methods if m.spelling == "setValue")
        assert m.rename is None

    def test_wildcard_class(self):
        mod = _simple_module()
        stage = RenameMethodStage(**{"class": "*", "from": "getValue", "to": "get"})
        stage.apply(mod)
        m = next(m for m in _get_cls(mod).methods if m.spelling == "getValue")
        assert m.rename == "get"

    def test_regex_from(self):
        mod = _simple_module()
        stage = RenameMethodStage(**{
            "class": "Cls", "from": "get.*", "to": "getter", "is_regex": True
        })
        stage.apply(mod)
        m = next(m for m in _get_cls(mod).methods if m.spelling == "getValue")
        assert m.rename == "getter"


# ---------------------------------------------------------------------------
# RenameClassStage
# ---------------------------------------------------------------------------

class TestRenameClassStage:
    def test_renames_class(self):
        mod = _simple_module()
        stage = RenameClassStage(**{"from": "Cls", "to": "Widget"})
        stage.apply(mod)
        assert _get_cls(mod).rename == "Widget"

    def test_regex_rename(self):
        methods = [IRMethod(name="f", spelling="f", qualified_name="Foo::f", return_type="void")]
        foo = IRClass(name="FooWidget", qualified_name="ns::FooWidget", namespace="ns",
                      methods=methods)
        mod = IRModule(name="m", classes=[foo], class_by_name={"FooWidget": foo})
        stage = RenameClassStage(**{"from": "Foo.*", "to": "W", "is_regex": True})
        stage.apply(mod)
        assert foo.rename == "W"


# ---------------------------------------------------------------------------
# SuppressMethodStage
# ---------------------------------------------------------------------------

class TestSuppressMethodStage:
    def test_suppresses_by_name(self):
        mod = _simple_module()
        stage = SuppressMethodStage(**{"class": "Cls", "pattern": "getValue"})
        stage.apply(mod)
        m = next(m for m in _get_cls(mod).methods if m.spelling == "getValue")
        assert m.emit is False

    def test_suppresses_by_regex(self):
        mod = _simple_module()
        stage = SuppressMethodStage(**{
            "class": "*", "pattern": "operator.*", "is_regex": True
        })
        stage.apply(mod)
        op = next(m for m in _get_cls(mod).methods if m.spelling == "operator+")
        assert op.emit is False
        gv = next(m for m in _get_cls(mod).methods if m.spelling == "getValue")
        assert gv.emit is True


# ---------------------------------------------------------------------------
# SuppressClassStage
# ---------------------------------------------------------------------------

class TestSuppressClassStage:
    def test_suppresses_matching_class(self):
        mod = _simple_module()
        stage = SuppressClassStage(**{"pattern": "Cls"})
        stage.apply(mod)
        assert _get_cls(mod).emit is False

    def test_regex_suppression(self):
        mod = _simple_module()
        stage = SuppressClassStage(**{"pattern": ".*Detail.*", "is_regex": True})
        stage.apply(mod)
        assert _get_cls(mod).emit is True  # "Cls" doesn't match

    def test_wildcard_suppresses_all(self):
        mod = _simple_module()
        stage = SuppressClassStage(**{"pattern": "*"})
        stage.apply(mod)
        assert _get_cls(mod).emit is False


# ---------------------------------------------------------------------------
# InjectMethodStage
# ---------------------------------------------------------------------------

class TestInjectMethodStage:
    def test_injects_method(self):
        mod = _simple_module()
        initial_count = len(_get_cls(mod).methods)
        stage = InjectMethodStage(**{
            "class": "Cls",
            "name": "create",
            "return_type": "int",
            "parameters": [{"name": "v", "type": "int"}],
            "is_static": True,
        })
        stage.apply(mod)
        cls = _get_cls(mod)
        assert len(cls.methods) == initial_count + 1
        injected = next(m for m in cls.methods if m.name == "create")
        assert injected.is_static is True
        assert injected.return_type == "int"
        assert injected.parameters[0].name == "v"

    def test_injects_no_params_method(self):
        mod = _simple_module()
        stage = InjectMethodStage(**{"class": "Cls", "name": "reset", "return_type": "void"})
        stage.apply(mod)
        injected = next(m for m in _get_cls(mod).methods if m.name == "reset")
        assert injected.parameters == []


# ---------------------------------------------------------------------------
# AddTypeMappingStage
# ---------------------------------------------------------------------------

class TestAddTypeMappingStage:
    def test_remaps_return_type(self):
        mod = _simple_module()
        # setValue returns void; let's add a method with a target type
        m = IRMethod(name="getString", spelling="getString",
                     qualified_name="Cls::getString", return_type="juce::String")
        _get_cls(mod).methods.append(m)
        stage = AddTypeMappingStage(**{"from": "juce::String", "to": "std::string"})
        stage.apply(mod)
        assert m.return_type == "std::string"

    def test_remaps_parameter_type(self):
        mod = _simple_module()
        m = IRMethod(name="setString", spelling="setString",
                     qualified_name="Cls::setString", return_type="void",
                     parameters=[IRParameter("s", "juce::String")])
        _get_cls(mod).methods.append(m)
        stage = AddTypeMappingStage(**{"from": "juce::String", "to": "std::string"})
        stage.apply(mod)
        assert m.parameters[0].type_spelling == "std::string"


# ---------------------------------------------------------------------------
# Pipeline and registry
# ---------------------------------------------------------------------------

class TestTransformPipeline:
    def test_applies_stages_in_order(self):
        mod = _simple_module()
        ops = []

        class StageA:
            name = "stage_a"
            def apply(self, m):
                ops.append("A")

        class StageB:
            name = "stage_b"
            def apply(self, m):
                ops.append("B")

        pipeline = TransformPipeline([StageA(), StageB()])
        pipeline.run(mod)
        assert ops == ["A", "B"]

    def test_empty_pipeline(self):
        mod = _simple_module()
        TransformPipeline([]).run(mod)  # should not raise

    def test_build_pipeline_from_specs(self):
        specs = [
            TransformSpec(stage="rename_class", kwargs={"from": "Cls", "to": "Widget"}),
        ]
        pipeline = build_pipeline_from_config(specs)
        mod = _simple_module()
        pipeline.run(mod)
        assert _get_cls(mod).rename == "Widget"

    def test_unknown_stage_raises(self):
        specs = [TransformSpec(stage="nonexistent_stage_xyz", kwargs={})]
        with pytest.raises(ValueError, match="Unknown transform stage"):
            build_pipeline_from_config(specs)

    def test_third_party_registration(self):
        class MyStage:
            name = "my_custom_stage"
            called = False
            def apply(self, module):
                MyStage.called = True

        register_stage("my_custom_stage", MyStage)
        specs = [TransformSpec(stage="my_custom_stage", kwargs={})]
        pipeline = build_pipeline_from_config(specs)
        mod = _simple_module()
        pipeline.run(mod)
        assert MyStage.called is True
