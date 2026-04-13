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
from tsujikiri.ir import (
    IRClass,
    IRCodeInjection,
    IRConstructor,
    IREnum,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
)


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


class ModifyMethodStage(TransformStage):
    """Comprehensively modify a method in a class.

    YAML::
      stage: modify_method
      class: MyClass          # plain name, '*', or regex
      method: getValue        # plain name, '*', or regex
      class_is_regex: false   # optional, default false
      method_is_regex: false  # optional, default false
      rename: get             # optional: new binding name
      remove: false           # optional: set emit=False
      return_type: "std::string"          # optional: override return type in output
      return_ownership: "cpp"             # optional: "none" | "cpp" | "script"
      allow_thread: true                  # optional: hint for GIL release
      wrapper_code: "return self->v();"   # optional: emit lambda instead of &Class::method
    """
    name = "modify_method"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_pattern: str = kwargs.get("method", "*")
        self.method_is_regex: bool = kwargs.get("method_is_regex", False)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)
        self.return_type: Optional[str] = kwargs.get("return_type")
        self.return_ownership: Optional[str] = kwargs.get("return_ownership")
        self.allow_thread: Optional[bool] = kwargs.get("allow_thread")
        self.wrapper_code: Optional[str] = kwargs.get("wrapper_code")

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if _matches(method.name, self.method_pattern, self.method_is_regex):
                    if self.rename is not None:
                        method.rename = self.rename
                    if self.remove:
                        method.emit = False
                    if self.return_type is not None:
                        method.return_type_override = self.return_type
                    if self.return_ownership is not None:
                        method.return_ownership = self.return_ownership
                    if self.allow_thread is not None:
                        method.allow_thread = self.allow_thread
                    if self.wrapper_code is not None:
                        method.wrapper_code = self.wrapper_code


class ModifyArgumentStage(TransformStage):
    """Modify a specific argument of a method.

    YAML::
      stage: modify_argument
      class: MyClass
      method: setData
      argument: data        # by name, or 0-based index as integer
      rename: value         # optional: new binding name
      remove: false         # optional: set emit=False (remove from signature)
      type: "std::string"   # optional: override type in output
      default: "std::string{}"  # optional: override default expression
      ownership: "cpp"      # optional: "none" | "cpp" | "script"
    """
    name = "modify_argument"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_pattern: str = kwargs.get("method", "*")
        self.method_is_regex: bool = kwargs.get("method_is_regex", False)
        raw_arg = kwargs["argument"]
        self.arg_index: Optional[int] = int(raw_arg) if str(raw_arg).isdigit() else None
        self.arg_name: Optional[str] = None if self.arg_index is not None else str(raw_arg)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)
        self.type_override: Optional[str] = kwargs.get("type")
        self.default_override: Optional[str] = kwargs.get("default")
        self.ownership: Optional[str] = kwargs.get("ownership")

    def _find_param(self, method: IRMethod) -> Optional[IRParameter]:
        if self.arg_index is not None:
            params = method.parameters
            if 0 <= self.arg_index < len(params):
                return params[self.arg_index]
            return None
        for p in method.parameters:
            if p.name == self.arg_name:
                return p
        return None

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if _matches(method.name, self.method_pattern, self.method_is_regex):
                    param = self._find_param(method)
                    if param is None:
                        continue
                    if self.rename is not None:
                        param.rename = self.rename
                    if self.remove:
                        param.emit = False
                    if self.type_override is not None:
                        param.type_override = self.type_override
                    if self.default_override is not None:
                        param.default_override = self.default_override
                    if self.ownership is not None:
                        param.ownership = self.ownership


class ModifyFieldStage(TransformStage):
    """Modify a field in a class.

    YAML::
      stage: modify_field
      class: MyClass
      field: data_        # plain name or '*'
      rename: data        # optional
      remove: false       # optional: set emit=False
      read_only: true     # optional: force read-only in binding
    """
    name = "modify_field"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.field_pattern: str = kwargs.get("field", "*")
        self.field_is_regex: bool = kwargs.get("field_is_regex", False)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)
        self.read_only: Optional[bool] = kwargs.get("read_only")

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for f in cls.fields:
                if _matches(f.name, self.field_pattern, self.field_is_regex):
                    if self.rename is not None:
                        f.rename = self.rename
                    if self.remove:
                        f.emit = False
                    if self.read_only is not None:
                        f.read_only = self.read_only


def _ctor_signature(ctor: IRConstructor) -> str:
    """Return a comma+space joined string of parameter type spellings."""
    return ", ".join(p.type_spelling for p in ctor.parameters)


class ModifyConstructorStage(TransformStage):
    """Modify a specific constructor of a class.

    YAML::
      stage: modify_constructor
      class: MyClass
      signature: "int, float"   # comma+space joined param types; "" = default ctor
      remove: false             # optional: set emit=False
    """
    name = "modify_constructor"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.signature: str = kwargs.get("signature", "")
        self.remove: bool = kwargs.get("remove", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for ctor in cls.constructors:
                if _ctor_signature(ctor) == self.signature:
                    if self.remove:
                        ctor.emit = False


class RemoveOverloadStage(TransformStage):
    """Remove a specific overload of a method by its parameter type signature.

    YAML::
      stage: remove_overload
      class: MyClass
      method: process
      signature: "int, float"   # comma+space joined param types
    """
    name = "remove_overload"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_name: str = kwargs["method"]
        self.signature: str = kwargs["signature"]

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if method.name == self.method_name:
                    sig = ", ".join(p.type_spelling for p in method.parameters)
                    if sig == self.signature:
                        method.emit = False


class InjectCodeStage(TransformStage):
    """Inject arbitrary code at a specific position in the output.

    YAML::
      stage: inject_code
      target: method         # "module" | "class" | "method" | "constructor"
      class: MyClass         # required when target != "module"
      method: getValue       # required when target == "method"
      signature: "int"       # optional, for target == "constructor"
      position: end          # "beginning" | "end"
      code: |
        // injected code here
    """
    name = "inject_code"

    def __init__(self, **kwargs: Any) -> None:
        self.target: str = kwargs["target"]
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_pattern: str = kwargs.get("method", "*")
        self.method_is_regex: bool = kwargs.get("method_is_regex", False)
        self.signature: Optional[str] = kwargs.get("signature")
        self.position: str = kwargs.get("position", "end")
        self.code: str = kwargs["code"]

    def apply(self, module: IRModule) -> None:
        injection = IRCodeInjection(position=self.position, code=self.code)
        if self.target == "module":
            module.code_injections.append(injection)
        elif self.target == "class":
            for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
                cls.code_injections.append(IRCodeInjection(position=self.position, code=self.code))
        elif self.target == "method":
            for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
                for method in cls.methods:
                    if _matches(method.name, self.method_pattern, self.method_is_regex):
                        method.code_injections.append(IRCodeInjection(position=self.position, code=self.code))
        elif self.target == "constructor":
            for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
                for ctor in cls.constructors:
                    if self.signature is None or _ctor_signature(ctor) == self.signature:
                        ctor.code_injections.append(IRCodeInjection(position=self.position, code=self.code))


class SetTypeHintStage(TransformStage):
    """Set type-level metadata hints on a class.

    YAML::
      stage: set_type_hint
      class: MyClass
      copyable: false           # optional: override copy-constructibility
      movable: true             # optional: override move-constructibility
      force_abstract: true      # optional: suppress constructor binding
      holder_type: std::shared_ptr  # optional: smart pointer holder for binding declaration
    """
    name = "set_type_hint"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.copyable: Optional[bool] = kwargs.get("copyable")
        self.movable: Optional[bool] = kwargs.get("movable")
        self.force_abstract: Optional[bool] = kwargs.get("force_abstract")
        self.holder_type: Optional[str] = kwargs.get("holder_type")

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            if self.copyable is not None:
                cls.copyable = self.copyable
            if self.movable is not None:
                cls.movable = self.movable
            if self.force_abstract is not None:
                cls.force_abstract = self.force_abstract
            if self.holder_type is not None:
                cls.holder_type = self.holder_type


# ---------------------------------------------------------------------------
# Enum helper
# ---------------------------------------------------------------------------

def _find_enums(module: IRModule, enum_pattern: str, is_regex: bool = False) -> List[IREnum]:
    """Yield all enums (top-level and nested inside classes) matching the pattern."""
    result: List[IREnum] = []

    def _walk_class(cls: IRClass) -> None:
        for enum in cls.enums:
            if _matches(enum.name, enum_pattern, is_regex):
                result.append(enum)
        for inner in cls.inner_classes:
            _walk_class(inner)

    for enum in module.enums:
        if _matches(enum.name, enum_pattern, is_regex):
            result.append(enum)
    for cls in module.classes:
        _walk_class(cls)
    return result


# ---------------------------------------------------------------------------
# Enum stages
# ---------------------------------------------------------------------------

class RenameEnumStage(TransformStage):
    """Rename an enum for the binding output.

    YAML::
      stage: rename_enum
      from: Color
      to: Colour
      is_regex: false
    """
    name = "rename_enum"

    def __init__(self, **kwargs: Any) -> None:
        self.from_name: str = kwargs["from"]
        self.to_name: str = kwargs["to"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for enum in _find_enums(module, self.from_name, self.is_regex):
            enum.rename = self.to_name


class RenameEnumValueStage(TransformStage):
    """Rename a specific enum value for the binding output.

    YAML::
      stage: rename_enum_value
      enum: Color          # plain name, '*', or regex; '*' = all enums
      from: Red
      to: red
      is_regex: false
    """
    name = "rename_enum_value"

    def __init__(self, **kwargs: Any) -> None:
        self.enum_pattern: str = kwargs.get("enum", "*")
        self.enum_is_regex: bool = kwargs.get("enum_is_regex", False)
        self.from_name: str = kwargs["from"]
        self.to_name: str = kwargs["to"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for enum in _find_enums(module, self.enum_pattern, self.enum_is_regex):
            for val in enum.values:
                if _matches(val.name, self.from_name, self.is_regex):
                    val.rename = self.to_name


class SuppressEnumStage(TransformStage):
    """Set emit=False on matching enums.

    YAML::
      stage: suppress_enum
      pattern: ".*Detail$"
      is_regex: true
    """
    name = "suppress_enum"

    def __init__(self, **kwargs: Any) -> None:
        self.pattern: str = kwargs["pattern"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for enum in _find_enums(module, self.pattern, self.is_regex):
            enum.emit = False


class SuppressEnumValueStage(TransformStage):
    """Set emit=False on matching enum values.

    YAML::
      stage: suppress_enum_value
      enum: Color          # plain name, '*', or regex
      pattern: "Reserved.*"
      is_regex: true
    """
    name = "suppress_enum_value"

    def __init__(self, **kwargs: Any) -> None:
        self.enum_pattern: str = kwargs.get("enum", "*")
        self.enum_is_regex: bool = kwargs.get("enum_is_regex", False)
        self.pattern: str = kwargs["pattern"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for enum in _find_enums(module, self.enum_pattern, self.enum_is_regex):
            for val in enum.values:
                if _matches(val.name, self.pattern, self.is_regex):
                    val.emit = False


class ModifyEnumStage(TransformStage):
    """Modify an enum's properties.

    YAML::
      stage: modify_enum
      enum: Color
      rename: Colour       # optional: new binding name
      remove: false        # optional: set emit=False
    """
    name = "modify_enum"

    def __init__(self, **kwargs: Any) -> None:
        self.enum_pattern: str = kwargs.get("enum", "*")
        self.enum_is_regex: bool = kwargs.get("enum_is_regex", False)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)

    def apply(self, module: IRModule) -> None:
        for enum in _find_enums(module, self.enum_pattern, self.enum_is_regex):
            if self.rename is not None:
                enum.rename = self.rename
            if self.remove:
                enum.emit = False


# ---------------------------------------------------------------------------
# Free-function stages
# ---------------------------------------------------------------------------

class RenameFunctionStage(TransformStage):
    """Rename a free function for the binding output.

    YAML::
      stage: rename_function
      from: computeArea
      to: compute_area
      is_regex: false
    """
    name = "rename_function"

    def __init__(self, **kwargs: Any) -> None:
        self.from_name: str = kwargs["from"]
        self.to_name: str = kwargs["to"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for fn in module.functions:
            if _matches(fn.name, self.from_name, self.is_regex):
                fn.rename = self.to_name


class SuppressFunctionStage(TransformStage):
    """Set emit=False on matching free functions.

    YAML::
      stage: suppress_function
      pattern: "internal_.*"
      is_regex: true
    """
    name = "suppress_function"

    def __init__(self, **kwargs: Any) -> None:
        self.pattern: str = kwargs["pattern"]
        self.is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for fn in module.functions:
            if _matches(fn.name, self.pattern, self.is_regex):
                fn.emit = False


class ModifyFunctionStage(TransformStage):
    """Comprehensively modify a free function.

    YAML::
      stage: modify_function
      function: computeArea      # plain name, '*', or regex
      function_is_regex: false   # optional, default false
      rename: compute_area       # optional: new binding name
      remove: false              # optional: set emit=False
      return_type: "float"       # optional: override return type in output
      return_ownership: "cpp"    # optional: "none" | "cpp" | "script"
      allow_thread: true         # optional: GIL-release hint
      wrapper_code: "return 0;"  # optional: emit lambda instead of &qualified_name
    """
    name = "modify_function"

    def __init__(self, **kwargs: Any) -> None:
        self.function_pattern: str = kwargs.get("function", "*")
        self.function_is_regex: bool = kwargs.get("function_is_regex", False)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)
        self.return_type: Optional[str] = kwargs.get("return_type")
        self.return_ownership: Optional[str] = kwargs.get("return_ownership")
        self.allow_thread: Optional[bool] = kwargs.get("allow_thread")
        self.wrapper_code: Optional[str] = kwargs.get("wrapper_code")

    def apply(self, module: IRModule) -> None:
        for fn in module.functions:
            if _matches(fn.name, self.function_pattern, self.function_is_regex):
                if self.rename is not None:
                    fn.rename = self.rename
                if self.remove:
                    fn.emit = False
                if self.return_type is not None:
                    fn.return_type_override = self.return_type
                if self.return_ownership is not None:
                    fn.return_ownership = self.return_ownership
                if self.allow_thread is not None:
                    fn.allow_thread = self.allow_thread
                if self.wrapper_code is not None:
                    fn.wrapper_code = self.wrapper_code


# ---------------------------------------------------------------------------
# Injection stages
# ---------------------------------------------------------------------------

class InjectConstructorStage(TransformStage):
    """Append a synthetic IRConstructor to a class.

    YAML::
      stage: inject_constructor
      class: MyClass
      parameters:
        - name: value
          type: int
    """
    name = "inject_constructor"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs["class"]
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.parameters: List[Dict[str, str]] = kwargs.get("parameters", [])

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            params = [
                IRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
                for p in self.parameters
            ]
            is_overload = len(cls.constructors) > 0
            # Mark existing constructors as overloads too
            if is_overload:
                for existing in cls.constructors:
                    existing.is_overload = True
            ctor = IRConstructor(parameters=params, is_overload=is_overload)
            cls.constructors.append(ctor)


class InjectFunctionStage(TransformStage):
    """Append a synthetic IRFunction to the module.

    YAML::
      stage: inject_function
      name: create
      namespace: mylib
      return_type: "MyClass*"
      parameters:
        - name: value
          type: int
    """
    name = "inject_function"

    def __init__(self, **kwargs: Any) -> None:
        self.fn_name: str = kwargs["name"]
        self.namespace: str = kwargs.get("namespace", "")
        self.return_type: str = kwargs.get("return_type", "void")
        self.parameters: List[Dict[str, str]] = kwargs.get("parameters", [])

    def apply(self, module: IRModule) -> None:
        params = [
            IRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
            for p in self.parameters
        ]
        qualified = f"{self.namespace}::{self.fn_name}" if self.namespace else self.fn_name
        fn = IRFunction(
            name=self.fn_name,
            qualified_name=qualified,
            namespace=self.namespace,
            return_type=self.return_type,
            parameters=params,
        )
        module.functions.append(fn)


# ---------------------------------------------------------------------------
# Base-class suppression
# ---------------------------------------------------------------------------

class SuppressBaseStage(TransformStage):
    """Suppress a base class from appearing in the binding output.

    YAML::
      stage: suppress_base
      class: Circle        # plain name, '*', or regex
      base: ".*Protected"  # matches against the base's qualified_name
      is_regex: true
    """
    name = "suppress_base"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.base_pattern: str = kwargs["base"]
        self.base_is_regex: bool = kwargs.get("is_regex", False)

    def apply(self, module: IRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for base in cls.bases:
                if _matches(base.qualified_name, self.base_pattern, self.base_is_regex):
                    base.emit = False


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
    ModifyMethodStage,
    ModifyArgumentStage,
    ModifyFieldStage,
    ModifyConstructorStage,
    RemoveOverloadStage,
    InjectCodeStage,
    SetTypeHintStage,
    # Enum stages
    RenameEnumStage,
    RenameEnumValueStage,
    SuppressEnumStage,
    SuppressEnumValueStage,
    ModifyEnumStage,
    # Free-function stages
    RenameFunctionStage,
    SuppressFunctionStage,
    ModifyFunctionStage,
    # Injection stages
    InjectConstructorStage,
    InjectFunctionStage,
    # Base-class suppression
    SuppressBaseStage,
]:
    register_stage(_stage_cls.name, _stage_cls)
