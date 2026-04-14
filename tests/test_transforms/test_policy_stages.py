"""Tests for OverloadPriorityStage and ExceptionPolicyStage."""

from __future__ import annotations

from tsujikiri.ir import IRClass, IRFunction, IRMethod, IRModule
from tsujikiri.configurations import TransformSpec
from tsujikiri.transforms import build_pipeline_from_config


def _make_module_with_overloads() -> IRModule:
    m1 = IRMethod(name="foo", spelling="foo", qualified_name="Cls::foo", return_type="void")
    m2 = IRMethod(name="foo", spelling="foo", qualified_name="Cls::foo", return_type="int",
                  is_overload=True)
    m1.is_overload = True
    cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
    cls.methods = [m1, m2]
    mod = IRModule(name="test")
    mod.classes = [cls]
    return mod


class TestOverloadPriorityStage:
    def test_sets_priority_on_matching_overload(self) -> None:
        mod = _make_module_with_overloads()
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "Cls", "method": "foo", "signature": "int foo()", "priority": 0,
        })]
        build_pipeline_from_config(specs).run(mod)
        m = next(m for m in mod.classes[0].methods if m.return_type == "int")
        assert m.overload_priority == 0

    def test_non_matching_overload_unchanged(self) -> None:
        mod = _make_module_with_overloads()
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "Cls", "method": "foo", "signature": "int foo()", "priority": 0,
        })]
        build_pipeline_from_config(specs).run(mod)
        m = next(m for m in mod.classes[0].methods if m.return_type == "void")
        assert m.overload_priority is None

    def test_defaults_to_none(self) -> None:
        m = IRMethod(name="bar", spelling="bar", qualified_name="X::bar", return_type="void")
        assert m.overload_priority is None

    def test_function_overload_priority_defaults_to_none(self) -> None:
        fn = IRFunction(name="baz", qualified_name="baz", namespace="", return_type="void")
        assert fn.overload_priority is None


class TestExceptionPolicyStage:
    def test_sets_policy_on_method(self) -> None:
        m = IRMethod(name="bar", spelling="bar", qualified_name="Cls::bar", return_type="void")
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "class": "Cls", "method": "bar", "policy": "pass_through",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert mod.classes[0].methods[0].exception_policy == "pass_through"

    def test_sets_policy_on_free_function(self) -> None:
        fn = IRFunction(name="risky", qualified_name="risky", namespace="", return_type="void")
        mod = IRModule(name="test")
        mod.functions = [fn]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "function": "risky", "policy": "abort",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert mod.functions[0].exception_policy == "abort"

    def test_wildcard_class_applies_to_all(self) -> None:
        m1 = IRMethod(name="a", spelling="a", qualified_name="A::a", return_type="void")
        m2 = IRMethod(name="b", spelling="b", qualified_name="B::b", return_type="void")
        cls1 = IRClass(name="A", qualified_name="A", namespace="")
        cls1.methods = [m1]
        cls2 = IRClass(name="B", qualified_name="B", namespace="")
        cls2.methods = [m2]
        mod = IRModule(name="test")
        mod.classes = [cls1, cls2]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "method": "*", "policy": "none",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert cls1.methods[0].exception_policy == "none"
        assert cls2.methods[0].exception_policy == "none"

    def test_method_exception_policy_defaults_to_none(self) -> None:
        m = IRMethod(name="x", spelling="x", qualified_name="X::x", return_type="void")
        assert m.exception_policy is None

    def test_function_exception_policy_defaults_to_none(self) -> None:
        fn = IRFunction(name="y", qualified_name="y", namespace="", return_type="void")
        assert fn.exception_policy is None


class TestUnmatchedStages:
    def test_unmatched_suppress_method_reported(self) -> None:
        mod = IRModule(name="test")
        specs = [TransformSpec(stage="suppress_method", kwargs={
            "class": "NonExistentClass", "pattern": "foo",
        })]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(mod)
        unmatched = pipeline.unmatched_stages()
        assert len(unmatched) == 1
        assert "suppress_method" in unmatched[0].lower() or "SuppressMethod" in unmatched[0]

    def test_matched_stage_not_reported(self) -> None:
        m = IRMethod(name="foo", spelling="foo", qualified_name="Cls::foo", return_type="void")
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="suppress_method", kwargs={
            "class": "Cls", "pattern": "foo",
        })]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(mod)
        unmatched = pipeline.unmatched_stages()
        assert len(unmatched) == 0

    def test_multiple_stages_only_unmatched_reported(self) -> None:
        m = IRMethod(name="doWork", spelling="doWork", qualified_name="Cls::doWork", return_type="void")
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [
            TransformSpec(stage="suppress_method", kwargs={"class": "Cls", "pattern": "doWork"}),
            TransformSpec(stage="suppress_method", kwargs={"class": "Ghost", "pattern": "missing"}),
        ]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(mod)
        unmatched = pipeline.unmatched_stages()
        assert len(unmatched) == 1

    def test_empty_module_all_stages_unmatched(self) -> None:
        mod = IRModule(name="test")
        specs = [
            TransformSpec(stage="suppress_method", kwargs={"class": "*", "pattern": "anything"}),
            TransformSpec(stage="suppress_class", kwargs={"pattern": "anything"}),
        ]
        pipeline = build_pipeline_from_config(specs)
        pipeline.run(mod)
        unmatched = pipeline.unmatched_stages()
        assert len(unmatched) == 2


class TestOverloadPriorityBranches:
    """Cover missing lines 515 and 518 in OverloadPriorityStage.apply."""

    def test_non_matching_class_skipped(self) -> None:
        """Line 515: class_name filter doesn't match → continue taken."""
        m = IRMethod(name="foo", spelling="foo", qualified_name="Cls::foo",
                     return_type="void", is_overload=True)
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "OtherClass", "method": "foo", "signature": "void foo()", "priority": 0,
        })]
        build_pipeline_from_config(specs).run(mod)
        assert m.overload_priority is None

    def test_non_matching_method_name_skipped(self) -> None:
        """Line 518: method name doesn't match → continue taken."""
        m = IRMethod(name="foo", spelling="foo", qualified_name="Cls::foo",
                     return_type="void", is_overload=True)
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="OverloadPriority", kwargs={
            "class": "Cls", "method": "bar", "signature": "void bar()", "priority": 1,
        })]
        build_pipeline_from_config(specs).run(mod)
        assert m.overload_priority is None


class TestExceptionPolicyBranches:
    """Cover missing lines 541, 550 and branches 552->551, 555->554."""

    def test_invalid_policy_raises(self) -> None:
        """Line 541: invalid policy value raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="exception_policy must be one of"):
            from tsujikiri.transforms import ExceptionPolicyStage
            ExceptionPolicyStage(policy="invalid_policy")

    def test_non_matching_class_skipped(self) -> None:
        """Line 550: class name filter doesn't match → continue taken."""
        m = IRMethod(name="work", spelling="work", qualified_name="Cls::work",
                     return_type="void")
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "class": "OtherClass", "method": "work", "policy": "abort",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert m.exception_policy is None

    def test_non_matching_method_loop_continues(self) -> None:
        """Branch 552->551: method name doesn't match → loop continues to next method."""
        m1 = IRMethod(name="doWork", spelling="doWork", qualified_name="Cls::doWork",
                      return_type="void")
        m2 = IRMethod(name="otherWork", spelling="otherWork", qualified_name="Cls::otherWork",
                      return_type="void")
        cls = IRClass(name="Cls", qualified_name="Cls", namespace="")
        cls.methods = [m1, m2]
        mod = IRModule(name="test")
        mod.classes = [cls]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "class": "Cls", "method": "doWork", "policy": "pass_through",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert m1.exception_policy == "pass_through"
        assert m2.exception_policy is None  # m2 didn't match → loop continued past it

    def test_non_matching_function_loop_continues(self) -> None:
        """Branch 555->554: function name doesn't match → loop continues to next function."""
        fn1 = IRFunction(name="alpha", qualified_name="alpha", namespace="", return_type="void")
        fn2 = IRFunction(name="beta", qualified_name="beta", namespace="", return_type="void")
        mod = IRModule(name="test")
        mod.functions = [fn1, fn2]
        specs = [TransformSpec(stage="ExceptionPolicy", kwargs={
            "function": "alpha", "policy": "none",
        })]
        build_pipeline_from_config(specs).run(mod)
        assert fn1.exception_policy == "none"
        assert fn2.exception_policy is None  # beta didn't match → loop continued past it
