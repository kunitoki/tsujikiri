"""Tests for chained/composed transform pipeline stages.

Verifies that output of one stage is correctly fed as input to the next,
including rename→suppress and rename→modify chains.
"""

from __future__ import annotations

import pytest

from tsujikiri.configurations import TransformSpec
from tsujikiri.tir import (
    TIRClass,
    TIREnum,
    TIREnumValue,
    TIRFunction,
    TIRMethod,
    TIRModule,
)
from tsujikiri.transforms import (
    ModifyFunctionStage,
    RenameClassStage,
    RenameEnumStage,
    RenameEnumValueStage,
    RenameMethodStage,
    SuppressClassStage,
    SuppressEnumStage,
    SuppressFunctionStage,
    SuppressMethodStage,
    TransformPipeline,
    build_pipeline_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_class(name: str = "Foo") -> TIRClass:
    return TIRClass(
        name=name,
        qualified_name=f"ns::{name}",
        namespace="ns",
        variable_name=f"var{name}",
    )


def _simple_function(name: str = "compute") -> TIRFunction:
    return TIRFunction(
        name=name,
        qualified_name=f"ns::{name}",
        namespace="ns",
        return_type="int",
    )


def _simple_enum(name: str = "Color") -> TIREnum:
    return TIREnum(
        name=name,
        qualified_name=f"ns::{name}",
        values=[TIREnumValue("A", 0), TIREnumValue("B", 1)],
    )


# ---------------------------------------------------------------------------
# Pipeline basics
# ---------------------------------------------------------------------------


class TestPipelineBasics:
    def test_empty_pipeline_is_noop(self):
        pipeline = TransformPipeline([])
        mod = TIRModule(name="m", functions=[_simple_function()])
        pipeline.run(mod)
        assert mod.functions[0].emit is True

    def test_single_stage_applied(self):
        mod = TIRModule(name="m", functions=[_simple_function("doThing")])
        pipeline = TransformPipeline([RenameFunctionStageHelper("doThing", "do_thing")])
        pipeline.run(mod)
        assert mod.functions[0].rename == "do_thing"

    def test_build_pipeline_from_config_single(self):
        specs = [TransformSpec(stage="suppress_class", kwargs={"pattern": "Foo"})]
        mod = TIRModule(name="m", classes=[_simple_class("Foo")])
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(mod)
        assert mod.classes[0].emit is False

    def test_build_pipeline_unknown_stage_raises(self):
        with pytest.raises(ValueError, match="Unknown transform stage"):
            build_pipeline_from_config([TransformSpec(stage="nonexistent_xyz")])


# ---------------------------------------------------------------------------
# Rename → Suppress chain
# ---------------------------------------------------------------------------


class TestRenameSupressChain:
    def test_rename_class_then_suppress_by_original_name(self):
        """Stage 1: rename Foo → Bar. Stage 2: suppress Foo (original name).
        Suppress matches on the original C++ name, not the rename.
        Result: class is renamed AND suppressed.
        """
        mod = TIRModule(name="m", classes=[_simple_class("Foo")])
        pipeline = TransformPipeline(
            [
                RenameClassStage(**{"from": "Foo", "to": "Bar"}),
                SuppressClassStage(pattern="Foo"),
            ]
        )
        pipeline.run(mod)
        cls = mod.classes[0]
        assert cls.rename == "Bar"
        assert cls.emit is False

    def test_rename_method_then_suppress(self):
        """Rename getValue → get_value, then suppress by original name getValue."""
        method = TIRMethod(
            name="getValue",
            spelling="getValue",
            qualified_name="ns::Foo::getValue",
            return_type="int",
        )
        cls = _simple_class("Foo")
        cls.methods = [method]
        mod = TIRModule(name="m", classes=[cls])
        pipeline = TransformPipeline(
            [
                RenameMethodStage(**{"class": "Foo", "from": "getValue", "to": "get_value"}),
                SuppressMethodStage(**{"class": "Foo", "pattern": "getValue"}),
            ]
        )
        pipeline.run(mod)
        assert mod.classes[0].methods[0].rename == "get_value"
        assert mod.classes[0].methods[0].emit is False

    def test_rename_function_then_suppress(self):
        """Rename computeArea → compute_area, then suppress the renamed function."""
        mod = TIRModule(name="m", functions=[_simple_function("computeArea")])
        pipeline = TransformPipeline(
            [
                RenameFunctionStageHelper("computeArea", "compute_area"),
                SuppressFunctionStage(pattern="computeArea"),  # stage matches original name
            ]
        )
        pipeline.run(mod)
        fn = mod.functions[0]
        assert fn.rename == "compute_area"
        assert fn.emit is False


# ---------------------------------------------------------------------------
# Rename → Rename chain
# ---------------------------------------------------------------------------


class TestDoubleRenameChain:
    def test_rename_class_twice_by_original_name(self):
        """Both rename stages match original name 'Foo'. Last stage wins (sets rename to Baz).
        Stages match on original cls.name, not the previously set rename.
        """
        mod = TIRModule(name="m", classes=[_simple_class("Foo")])
        pipeline = TransformPipeline(
            [
                RenameClassStage(**{"from": "Foo", "to": "Bar"}),
                RenameClassStage(**{"from": "Foo", "to": "Baz"}),
            ]
        )
        pipeline.run(mod)
        # Second stage overwrites rename because both match on original name "Foo"
        assert mod.classes[0].rename == "Baz"

    def test_rename_enum_value_twice_by_original_name(self):
        """Two rename stages for the same enum value (by original name).
        The second stage overwrites the first since both match the original name 'A'.
        """
        mod = TIRModule(name="m", enums=[_simple_enum("Color")])
        pipeline = TransformPipeline(
            [
                RenameEnumValueStage(**{"enum": "Color", "from": "A", "to": "Alpha"}),
                RenameEnumValueStage(**{"enum": "Color", "from": "A", "to": "AlphaFinal"}),
            ]
        )
        pipeline.run(mod)
        val_a = mod.enums[0].values[0]
        assert val_a.rename == "AlphaFinal"


# ---------------------------------------------------------------------------
# Suppress → no-op chain
# ---------------------------------------------------------------------------


class TestSuppressChain:
    def test_suppress_then_rename_skips_suppressed(self):
        """Stage 1 suppresses Foo. Stage 2 tries to rename Foo, but Foo is gone from emit.
        The rename still sets the field (transforms operate on raw IR, not emitted),
        so rename will apply — but the class won't be emitted anyway.
        This tests that the pipeline doesn't crash.
        """
        mod = TIRModule(name="m", classes=[_simple_class("Foo")])
        pipeline = TransformPipeline(
            [
                SuppressClassStage(pattern="Foo"),
                RenameClassStage(**{"from": "Foo", "to": "Bar"}),
            ]
        )
        pipeline.run(mod)  # should not raise
        cls = mod.classes[0]
        assert cls.emit is False
        assert cls.rename == "Bar"  # rename applied even though suppressed


# ---------------------------------------------------------------------------
# Enum chain
# ---------------------------------------------------------------------------


class TestEnumChain:
    def test_rename_enum_then_suppress_by_original(self):
        """Rename Color → Colour, then suppress by original name Color."""
        mod = TIRModule(name="m", enums=[_simple_enum("Color")])
        pipeline = TransformPipeline(
            [
                RenameEnumStage(**{"from": "Color", "to": "Colour"}),
                SuppressEnumStage(pattern="Color"),
            ]
        )
        pipeline.run(mod)
        assert mod.enums[0].rename == "Colour"
        assert mod.enums[0].emit is False

    def test_multiple_enum_operations(self):
        """Rename Color, rename value A, suppress value B. All stages use original names."""
        from tsujikiri.transforms import SuppressEnumValueStage

        mod = TIRModule(name="m", enums=[_simple_enum("Color")])
        pipeline = TransformPipeline(
            [
                RenameEnumStage(**{"from": "Color", "to": "Colour"}),
                RenameEnumValueStage(**{"enum": "Color", "from": "A", "to": "red"}),
                SuppressEnumValueStage(**{"enum": "Color", "pattern": "B"}),
            ]
        )
        pipeline.run(mod)
        enum = mod.enums[0]
        assert enum.rename == "Colour"
        assert enum.values[0].rename == "red"
        assert enum.values[1].emit is False


# ---------------------------------------------------------------------------
# Function chain
# ---------------------------------------------------------------------------


class TestFunctionChain:
    def test_modify_then_suppress(self):
        """Modify function return type, then suppress it."""
        mod = TIRModule(name="m", functions=[_simple_function("doWork")])
        pipeline = TransformPipeline(
            [
                ModifyFunctionStage(**{"function": "doWork", "return_type": "void"}),
                SuppressFunctionStage(pattern="doWork"),
            ]
        )
        pipeline.run(mod)
        fn = mod.functions[0]
        assert fn.return_type_override == "void"
        assert fn.emit is False

    def test_suppress_does_not_affect_other_functions(self):
        """Suppressing 'work' should not affect 'compute'."""
        fn1 = _simple_function("work")
        fn2 = _simple_function("compute")
        mod = TIRModule(name="m", functions=[fn1, fn2])
        pipeline = TransformPipeline([SuppressFunctionStage(pattern="work")])
        pipeline.run(mod)
        assert mod.functions[0].emit is False
        assert mod.functions[1].emit is True


# ---------------------------------------------------------------------------
# Helpers (local stage wrappers for cleaner tests)
# ---------------------------------------------------------------------------


class RenameFunctionStageHelper:
    """Thin adapter wrapping RenameFunctionStage for pipeline tests."""

    def __init__(self, from_name: str, to_name: str) -> None:
        from tsujikiri.transforms import RenameFunctionStage

        self._stage = RenameFunctionStage(**{"from": from_name, "to": to_name})

    def apply(self, module: TIRModule) -> None:
        self._stage.apply(module)
