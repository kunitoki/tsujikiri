"""Transformation pipeline for the IR.

Transforms are applied after parsing and filtering, and before generation.
They mutate IRModule nodes in-place (renaming, suppressing, injecting, etc.)

Built-in stages:
  rename_method    — rename a method for the binding output
  rename_class     — rename a class for the binding output
  suppress_method  — set emit=False on matching methods
  suppress_class   — set emit=False on matching classes
  inject_method    — append a synthetic IRMethod to a class
  add_type_mapping — rewrite type spellings in method signatures

Third-party code can register custom stages via::

    from tsujikiri.transforms import register_stage
    register_stage("my_stage", MyStageClass)
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Type

from tsujikiri.configurations import TransformSpec
from tsujikiri.ir import IRClass, IRMethod, IRModule, IRParameter


# ---------------------------------------------------------------------------
# Stage protocol and registry
# ---------------------------------------------------------------------------

class TransformStage:
    """Base class for all transform stages."""
    name: str = ""

    def apply(self, module: IRModule) -> None:
        raise NotImplementedError


_REGISTRY: Dict[str, Type[TransformStage]] = {}


def register_stage(name: str, cls: Type[TransformStage]) -> None:
    """Register a custom transform stage class under a given name."""
    _REGISTRY[name] = cls


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TransformPipeline:
    def __init__(self, stages: List[TransformStage]) -> None:
        self.stages = stages

    def run(self, module: IRModule) -> None:
        for stage in self.stages:
            stage.apply(module)


def build_pipeline_from_config(specs: List[TransformSpec]) -> TransformPipeline:
    stages = []
    for spec in specs:
        cls = _REGISTRY.get(spec.stage)
        if cls is None:
            raise ValueError(f"Unknown transform stage: '{spec.stage}'. "
                             f"Available: {sorted(_REGISTRY)}")
        stages.append(cls(**spec.kwargs))
    return TransformPipeline(stages)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _matches(name: str, pattern: str, is_regex: bool = False) -> bool:
    if is_regex:
        return bool(re.fullmatch(pattern, name))
    return pattern in ("*", name)


def _find_classes(module: IRModule, class_pattern: str, is_regex: bool = False) -> List[IRClass]:
    """Yield all classes (top-level and nested) matching the pattern."""
    result = []

    def _walk(cls: IRClass) -> None:
        if _matches(cls.name, class_pattern, is_regex):
            result.append(cls)
        for inner in cls.inner_classes:
            _walk(inner)

    for cls in module.classes:
        _walk(cls)
    return result


# ---------------------------------------------------------------------------
# Built-in stages
# ---------------------------------------------------------------------------

class RenameMethodStage(TransformStage):
    """Rename a method in a class for the binding output.

    YAML::
      stage: rename_method
      class: MyClass       # plain name or '*' for all classes
      from: getValueForKey
      to: get
      is_regex: false      # optional, default false
    """
    name = "rename_method"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.from_name: str = kwargs["from"]
        self.to_name: str = kwargs["to"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if _matches(method.name, self.from_name, self.is_regex):
                    method.rename = self.to_name


class RenameClassStage(TransformStage):
    """Rename a class for the binding output.

    YAML::
      stage: rename_class
      from: InternalHelper
      to: Helper
      is_regex: false
    """
    name = "rename_class"

    def __init__(self, **kwargs: Any) -> None:
        self.from_name: str = kwargs["from"]
        self.to_name: str = kwargs["to"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.from_name, self.is_regex):
            cls.rename = self.to_name


class SuppressMethodStage(TransformStage):
    """Set emit=False on matching methods.

    YAML::
      stage: suppress_method
      class: "*"
      pattern: "operator.*"
      is_regex: true
    """
    name = "suppress_method"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.pattern: str = kwargs["pattern"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if _matches(method.name, self.pattern, self.is_regex):
                    method.emit = False


class SuppressClassStage(TransformStage):
    """Set emit=False on matching classes.

    YAML::
      stage: suppress_class
      pattern: ".*Detail$"
      is_regex: true
    """
    name = "suppress_class"

    def __init__(self, **kwargs: Any) -> None:
        self.pattern: str = kwargs["pattern"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.pattern, self.is_regex):
            cls.emit = False


class InjectMethodStage(TransformStage):
    """Append a synthetic IRMethod to a class.

    YAML::
      stage: inject_method
      class: MyClass
      name: create
      return_type: "MyClass*"
      parameters:
        - name: value
          type: int
      is_static: true
    """
    name = "inject_method"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs["class"]
        self.method_name: str = kwargs["name"]
        self.return_type: str = kwargs.get("return_type", "void")
        self.parameters: List[Dict[str, str]] = kwargs.get("parameters", [])
        self.is_static: bool = kwargs.get("is_static", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern):
            params = [
                IRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
                for p in self.parameters
            ]
            method = IRMethod(
                name=self.method_name,
                spelling=self.method_name,
                qualified_name=f"{cls.qualified_name}::{self.method_name}",
                return_type=self.return_type,
                parameters=params,
                is_static=self.is_static,
            )
            cls.methods.append(method)


class AddTypeMappingStage(TransformStage):
    """Rewrite type spellings in method signatures and return types.

    YAML::
      stage: add_type_mapping
      from: "juce::String"
      to: "std::string"
    """
    name = "add_type_mapping"

    def __init__(self, **kwargs: Any) -> None:
        self.from_type: str = kwargs["from"]
        self.to_type: str = kwargs["to"]

    def apply(self, module: IRModule) -> None:
        def _remap(spelling: str) -> str:
            return self.to_type if spelling == self.from_type else spelling

        def _remap_class(cls: IRClass) -> None:
            for method in cls.methods:
                method.return_type = _remap(method.return_type)
                for param in method.parameters:
                    param.type_spelling = _remap(param.type_spelling)
            for field in cls.fields:
                field.type_spelling = _remap(field.type_spelling)
            for inner in cls.inner_classes:
                _remap_class(inner)

        for cls in module.classes:
            _remap_class(cls)
        for fn in module.functions:
            fn.return_type = _remap(fn.return_type)
            for param in fn.parameters:
                param.type_spelling = _remap(param.type_spelling)


# ---------------------------------------------------------------------------
# Register all built-in stages
# ---------------------------------------------------------------------------

for _stage_cls in [
    RenameMethodStage,
    RenameClassStage,
    SuppressMethodStage,
    SuppressClassStage,
    InjectMethodStage,
    AddTypeMappingStage,
]:
    register_stage(_stage_cls.name, _stage_cls)
