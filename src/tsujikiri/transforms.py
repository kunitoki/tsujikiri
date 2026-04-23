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

import copy
import re
from typing import Any, Dict, List, Optional, Type

from tsujikiri.configurations import TransformSpec
from tsujikiri.ir import (
    IRCodeInjection,
    IRExceptionRegistration,
    IRProperty,
)
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)


# ---------------------------------------------------------------------------
# Stage protocol and registry
# ---------------------------------------------------------------------------

class TransformStage:
    """Base class for all transform stages."""
    name: str = ""
    _matched: bool = False

    def apply(self, module: TIRModule) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


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

    def run(self, module: TIRModule) -> None:
        for stage in self.stages:
            stage.apply(module)

    def unmatched_stages(self) -> List[str]:
        """Return repr of stages that ran but matched nothing."""
        return [repr(stage) for stage in self.stages if not stage._matched]


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

def _make_using_wrapper(cls_qualified_name: str, method: "TIRMethod") -> str:  # type: ignore[name-defined]
    """Build a C++ wrapper lambda for a method resolved via using-declaration.

    Using member-function pointers like &DerivedClass::baseMethod produces a
    pointer of type Base::* which LuaBridge3/pybind11 cannot reliably call on
    a Derived object with multiple inheritance (wrong this-pointer adjustment).
    A plain lambda avoids the issue entirely.
    """
    const_prefix = "const " if method.is_const else ""
    self_param = f"{const_prefix}{cls_qualified_name}& self"
    params_parts = [f"{p.type_spelling} {p.name}" for p in method.parameters]
    all_params = ", ".join([self_param] + params_parts)
    args = ", ".join(p.name for p in method.parameters)
    call = f"self.{method.spelling}({args})"
    body = call if method.return_type == "void" else f"return {call}"
    return f"+[]({all_params}) {{ {body}; }}"


def _matches(name: str, pattern: str, is_regex: bool = False) -> bool:
    if is_regex:
        return bool(re.fullmatch(pattern, name))
    return pattern in ("*", name)


def _find_classes(module: TIRModule, class_pattern: str, is_regex: bool = False) -> List[TIRClass]:
    """Yield all classes (top-level and nested) matching the pattern."""
    result: List[TIRClass] = []

    def _walk(cls: TIRClass) -> None:
        if _matches(cls.name, class_pattern, is_regex):
            result.append(cls)
        for inner in cls.inner_classes:
            _walk(inner)  # type: ignore[arg-type]

    for cls in module.classes:
        _walk(cls)  # type: ignore[arg-type]
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if _matches(method.name, self.pattern, self.is_regex):
                    method.emit = False
                    self._matched = True


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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.pattern, self.is_regex):
            cls.emit = False
            self._matched = True


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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern):
            params = [
                TIRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
                for p in self.parameters
            ]
            method = TIRMethod(
                name=self.method_name,
                spelling=self.method_name,
                qualified_name=f"{cls.qualified_name}::{self.method_name}",
                return_type=self.return_type,
                parameters=params,  # type: ignore[arg-type]
                is_static=self.is_static,
            )
            cls.methods.append(method)  # type: ignore[arg-type]


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

    def apply(self, module: TIRModule) -> None:
        def _remap(spelling: str) -> str:
            return self.to_type if spelling == self.from_type else spelling

        def _remap_class(cls: TIRClass) -> None:
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
        self.return_keep_alive: Optional[bool] = kwargs.get("return_keep_alive")
        self.allow_thread: Optional[bool] = kwargs.get("allow_thread")
        self.wrapper_code: Optional[str] = kwargs.get("wrapper_code")

    def apply(self, module: TIRModule) -> None:
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
                    if self.return_keep_alive is not None:
                        method.return_keep_alive = self.return_keep_alive
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

    def _find_param(self, method: TIRMethod) -> Optional[TIRParameter]:
        if self.arg_index is not None:
            params = method.parameters
            if 0 <= self.arg_index < len(params):
                return params[self.arg_index]
            return None
        for p in method.parameters:
            if p.name == self.arg_name:
                return p
        return None

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for f in cls.fields:
                if _matches(f.name, self.field_pattern, self.field_is_regex):
                    if self.rename is not None:
                        f.rename = self.rename
                    if self.remove:
                        f.emit = False
                    if self.read_only is not None:
                        f.read_only = self.read_only


def _ctor_signature(ctor: TIRConstructor) -> str:
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if method.name == self.method_name:
                    sig = ", ".join(p.type_spelling for p in method.parameters)
                    if sig == self.signature:
                        method.emit = False


class OverloadPriorityStage(TransformStage):
    """Assign an explicit priority index to a specific method overload.

    Lower priority values sort first. Use this to control which overload
    pybind11/LuaBridge resolves first during argument matching.

    YAML::
      stage: overload_priority
      class: MyClass
      method: process
      signature: "int process()"   # "return_type method_name(param_types...)"
      priority: 0
    """
    name = "overload_priority"

    def __init__(self, **kwargs: Any) -> None:
        self.class_name: str = kwargs.get("class", "*")
        self.method_name: str = kwargs["method"]
        self.signature: str = kwargs["signature"]
        self.priority: int = int(kwargs["priority"])

    def apply(self, module: TIRModule) -> None:
        for cls in module.classes:
            if self.class_name not in ("*", cls.name, cls.qualified_name):
                continue
            for m in cls.methods:
                if m.name != self.method_name:
                    continue
                sig_types = ", ".join(p.type_spelling for p in m.parameters)
                candidate_sig = f"{m.return_type} {m.name}({sig_types})"
                if candidate_sig == self.signature:
                    m.overload_priority = self.priority


class ExceptionPolicyStage(TransformStage):
    """Set the exception propagation policy for methods and/or free functions.

    YAML::
      stage: exception_policy
      class: MyClass        # optional, default "*" (all classes)
      method: doWork        # optional, default "*" (all methods)
      function: myFunc      # optional, targets free functions
      policy: pass_through  # "none" | "pass_through" | "abort"
    """
    name = "exception_policy"
    _VALID_POLICIES = frozenset({"none", "pass_through", "abort"})

    def __init__(self, **kwargs: Any) -> None:
        policy = kwargs["policy"]
        if policy not in self._VALID_POLICIES:
            raise ValueError(f"exception_policy must be one of {self._VALID_POLICIES}, got {policy!r}")
        self._policy = policy
        self._class_name: str = kwargs.get("class", "*")
        self._method: str = kwargs.get("method", "*")
        self._function: str = kwargs.get("function", "*")

    def apply(self, module: TIRModule) -> None:
        for cls in module.classes:
            if self._class_name not in ("*", cls.name, cls.qualified_name):
                continue
            for m in cls.methods:
                if self._method in ("*", m.name):
                    m.exception_policy = self._policy
        for fn in module.functions:
            if self._function in ("*", fn.name):
                fn.exception_policy = self._policy


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

    def apply(self, module: TIRModule) -> None:
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
      copyable: false              # optional: override copy-constructibility
      movable: true                # optional: override move-constructibility
      force_abstract: true         # optional: suppress constructor binding
      holder_type: std::shared_ptr # optional: smart pointer holder for binding declaration
      generate_hash: true          # optional: emit __hash__ using std::hash<T>
      smart_pointer_kind: shared   # optional: "shared", "unique", or "weak"
      smart_pointer_managed_type: MyClass  # optional: inner type for smart pointer
    """
    name = "set_type_hint"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.copyable: Optional[bool] = kwargs.get("copyable")
        self.movable: Optional[bool] = kwargs.get("movable")
        self.force_abstract: Optional[bool] = kwargs.get("force_abstract")
        self.holder_type: Optional[str] = kwargs.get("holder_type")
        self.generate_hash: Optional[bool] = kwargs.get("generate_hash")
        self.smart_pointer_kind: Optional[str] = kwargs.get("smart_pointer_kind")
        self.smart_pointer_managed_type: Optional[str] = kwargs.get("smart_pointer_managed_type")

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            if self.copyable is not None:
                cls.copyable = self.copyable
            if self.movable is not None:
                cls.movable = self.movable
            if self.force_abstract is not None:
                cls.force_abstract = self.force_abstract
            if self.holder_type is not None:
                cls.holder_type = self.holder_type
            if self.generate_hash is not None:
                cls.generate_hash = self.generate_hash
            if self.smart_pointer_kind is not None:
                cls.smart_pointer_kind = self.smart_pointer_kind
            if self.smart_pointer_managed_type is not None:
                cls.smart_pointer_managed_type = self.smart_pointer_managed_type


# ---------------------------------------------------------------------------
# Enum helper
# ---------------------------------------------------------------------------

def _find_enums(module: TIRModule, enum_pattern: str, is_regex: bool = False) -> List[TIREnum]:
    """Yield all enums (top-level and nested inside classes) matching the pattern."""
    result: List[TIREnum] = []

    def _walk_class(cls: TIRClass) -> None:
        for enum in cls.enums:
            if _matches(enum.name, enum_pattern, is_regex):
                result.append(enum)  # type: ignore[arg-type]
        for inner in cls.inner_classes:
            _walk_class(inner)  # type: ignore[arg-type]

    for enum in module.enums:
        if _matches(enum.name, enum_pattern, is_regex):
            result.append(enum)  # type: ignore[arg-type]
    for cls in module.classes:
        _walk_class(cls)  # type: ignore[arg-type]
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
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
      arithmetic: true     # optional: enable bitwise ops (py::arithmetic())
    """
    name = "modify_enum"

    def __init__(self, **kwargs: Any) -> None:
        self.enum_pattern: str = kwargs.get("enum", "*")
        self.enum_is_regex: bool = kwargs.get("enum_is_regex", False)
        self.rename: Optional[str] = kwargs.get("rename")
        self.remove: bool = kwargs.get("remove", False)
        self.arithmetic: Optional[bool] = kwargs.get("arithmetic")

    def apply(self, module: TIRModule) -> None:
        for enum in _find_enums(module, self.enum_pattern, self.enum_is_regex):
            if self.rename is not None:
                enum.rename = self.rename
            if self.remove:
                enum.emit = False
            if self.arithmetic is not None:
                enum.is_arithmetic = self.arithmetic


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

    def apply(self, module: TIRModule) -> None:
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

    def apply(self, module: TIRModule) -> None:
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
        self.return_keep_alive: Optional[bool] = kwargs.get("return_keep_alive")
        self.allow_thread: Optional[bool] = kwargs.get("allow_thread")
        self.wrapper_code: Optional[str] = kwargs.get("wrapper_code")

    def apply(self, module: TIRModule) -> None:
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
                if self.return_keep_alive is not None:
                    fn.return_keep_alive = self.return_keep_alive
                if self.allow_thread is not None:
                    fn.allow_thread = self.allow_thread
                if self.wrapper_code is not None:
                    fn.wrapper_code = self.wrapper_code


# ---------------------------------------------------------------------------
# Injection stages
# ---------------------------------------------------------------------------

class InjectConstructorStage(TransformStage):
    """Append a synthetic TIRConstructor to a class.

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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            params = [
                TIRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
                for p in self.parameters
            ]
            is_overload = len(cls.constructors) > 0
            if is_overload:
                for existing in cls.constructors:
                    existing.is_overload = True
            ctor = TIRConstructor(parameters=params, is_overload=is_overload)  # type: ignore[arg-type]
            cls.constructors.append(ctor)  # type: ignore[arg-type]


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

    def apply(self, module: TIRModule) -> None:
        params = [
            TIRParameter(name=p.get("name", ""), type_spelling=p.get("type", ""))
            for p in self.parameters
        ]
        qualified = f"{self.namespace}::{self.fn_name}" if self.namespace else self.fn_name
        fn = TIRFunction(
            name=self.fn_name,
            qualified_name=qualified,
            namespace=self.namespace,
            return_type=self.return_type,
            parameters=params,  # type: ignore[arg-type]
        )
        module.functions.append(fn)  # type: ignore[arg-type]


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

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for base in cls.bases:
                if _matches(base.qualified_name, self.base_pattern, self.base_is_regex):
                    base.emit = False


class InjectPropertyStage(TransformStage):
    """Inject a synthetic getter/setter property binding on a class.

    YAML::
      stage: inject_property
      class: MyClass
      name: arrivalMessage
      getter: getArrivalMessage
      setter: setArrivalMessage  # optional; omit for read-only
      type: "std::string"        # optional
    """
    name = "inject_property"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs["class"]
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.prop_name: str = kwargs["name"]
        self.getter: str = kwargs["getter"]
        self.setter: Optional[str] = kwargs.get("setter")
        self.type_spelling: str = kwargs.get("type", "")

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            cls.properties.append(IRProperty(
                name=self.prop_name,
                getter=self.getter,
                setter=self.setter,
                type_spelling=self.type_spelling,
            ))


# ---------------------------------------------------------------------------
# Deprecation stage
# ---------------------------------------------------------------------------

class MarkDeprecatedStage(TransformStage):
    """Mark a class, method, function, or enum as deprecated.

    YAML::
      stage: mark_deprecated
      target: method            # "class" | "method" | "function" | "enum"
      class: MyClass            # required for target "class" or "method"
      method: oldMethod         # required for target "method"
      function: oldFn           # required for target "function"
      enum: OldEnum             # required for target "enum"
      message: "Use newMethod"  # optional deprecation message
    """
    name = "mark_deprecated"

    def __init__(self, **kwargs: Any) -> None:
        self.target: str = kwargs.get("target", "method")
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_pattern: str = kwargs.get("method", "*")
        self.method_is_regex: bool = kwargs.get("method_is_regex", False)
        self.function_pattern: str = kwargs.get("function", "*")
        self.function_is_regex: bool = kwargs.get("function_is_regex", False)
        self.enum_pattern: str = kwargs.get("enum", "*")
        self.enum_is_regex: bool = kwargs.get("enum_is_regex", False)
        self.message: Optional[str] = kwargs.get("message")

    def apply(self, module: TIRModule) -> None:
        if self.target == "class":
            for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
                cls.is_deprecated = True
                if self.message is not None:
                    cls.deprecation_message = self.message
        elif self.target == "method":
            for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
                for method in cls.methods:
                    if _matches(method.name, self.method_pattern, self.method_is_regex):
                        method.is_deprecated = True
                        if self.message is not None:
                            method.deprecation_message = self.message
        elif self.target == "function":
            for fn in module.functions:
                if _matches(fn.name, self.function_pattern, self.function_is_regex):
                    fn.is_deprecated = True
                    if self.message is not None:
                        fn.deprecation_message = self.message
        elif self.target == "enum":
            for enum in _find_enums(module, self.enum_pattern, self.enum_is_regex):
                enum.is_deprecated = True
                if self.message is not None:
                    enum.deprecation_message = self.message


# ---------------------------------------------------------------------------
# Spaceship operator expansion stage
# ---------------------------------------------------------------------------

class ExpandSpaceshipStage(TransformStage):
    """Expand operator<=> into six comparison operator methods.

    For each class method with operator_type == "operator<=>", synthesizes
    six IRMethod entries (operator<, operator<=, operator>, operator>=,
    operator==, operator!=) using std::is_lt etc., then suppresses the
    original operator<=>.

    YAML::
      stage: expand_spaceship
      class: MyClass    # plain name, '*', or regex
    """
    name = "expand_spaceship"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)

    def apply(self, module: TIRModule) -> None:
        _OPS: List[tuple] = [
            ("operator<",  "__lt__",  "std::is_lt"),
            ("operator<=", "__le__",  "std::is_lteq"),
            ("operator>",  "__gt__",  "std::is_gt"),
            ("operator>=", "__ge__",  "std::is_gteq"),
            ("operator==", "__eq__",  "std::is_eq"),
            ("operator!=", "__ne__",  "std::is_neq"),
        ]
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            new_methods: List[TIRMethod] = []
            for method in cls.methods:
                if method.operator_type == "operator<=>":
                    method.emit = False
                    qname = cls.qualified_name
                    for op_spelling, _dunder, std_fn in _OPS:
                        wrapper = (
                            f"[](const {qname}& a, const {qname}& b)"
                            f" {{ return {std_fn}(a <=> b); }}"
                        )
                        new_methods.append(TIRMethod(
                            name=op_spelling,
                            spelling=op_spelling,
                            qualified_name=f"{qname}::{op_spelling}",
                            return_type="bool",
                            parameters=list(method.parameters),
                            is_static=False,
                            is_const=method.is_const,
                            is_operator=True,
                            operator_type=op_spelling,
                            wrapper_code=wrapper,
                        ))
            cls.methods.extend(new_methods)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Protected member exposure stage (Gap 4)
# ---------------------------------------------------------------------------

class ExposeProtectedStage(TransformStage):
    """Expose protected methods for trampoline override in pybind11.

    Sets access="public_via_trampoline" and emit=True on matching protected
    methods, causing pybind11 templates to emit ``using Base::method;`` inside
    the trampoline class body.

    YAML::
      stage: expose_protected
      class: MyClass        # plain name, '*', or regex
      method: "*"           # optional: method pattern (default = all protected)
      class_is_regex: false
      method_is_regex: false
    """
    name = "expose_protected"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)
        self.method_pattern: str = kwargs.get("method", "*")
        self.method_is_regex: bool = kwargs.get("method_is_regex", False)

    def apply(self, module: TIRModule) -> None:
        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for method in cls.methods:
                if method.access == "protected" and _matches(method.name, self.method_pattern, self.method_is_regex):
                    method.access = "public_via_trampoline"
                    method.emit = True


# ---------------------------------------------------------------------------
# Using declaration resolution stage (Gap 14)
# ---------------------------------------------------------------------------

class ResolveUsingDeclarationsStage(TransformStage):
    """Copy methods from base classes into derived classes for using declarations.

    For each ``using Base::method;`` declaration on a class, finds the matching
    method in a base class in the module and copies it to the derived class so
    it appears in the binding output.

    YAML::
      stage: resolve_using_declarations
      class: "*"   # optional: restrict to specific derived classes
    """
    name = "resolve_using_declarations"

    def __init__(self, **kwargs: Any) -> None:
        self.class_pattern: str = kwargs.get("class", "*")
        self.class_is_regex: bool = kwargs.get("class_is_regex", False)

    def apply(self, module: TIRModule) -> None:
        by_qname: Dict[str, TIRClass] = {c.qualified_name: c for c in module.classes}  # type: ignore[misc]

        for cls in _find_classes(module, self.class_pattern, self.class_is_regex):
            for ud in cls.using_declarations:
                if not ud.emit:
                    continue
                base_cls: Optional[TIRClass] = None
                if ud.base_qualified_name:
                    base_cls = by_qname.get(ud.base_qualified_name)
                if base_cls is None:
                    for base in cls.bases:
                        candidate = by_qname.get(base.qualified_name)
                        if candidate is not None:
                            has_match = any(m.name == ud.member_name for m in candidate.methods)
                            if has_match:
                                base_cls = candidate
                                break
                if base_cls is None:
                    continue
                existing_names = {m.name for m in cls.methods}
                for method in base_cls.methods:
                    if method.name == ud.member_name and method.name not in existing_names:
                        new_method = copy.copy(method)
                        new_method.access = "public"
                        new_method.emit = True
                        new_method.wrapper_code = _make_using_wrapper(cls.qualified_name, method)
                        cls.methods.append(new_method)


# ---------------------------------------------------------------------------
# Exception registration stage (Gap 12)
# ---------------------------------------------------------------------------

class RegisterExceptionStage(TransformStage):
    """Register a C++ exception type as a Python exception class.

    Adds an IRExceptionRegistration to the module, which causes pybind11
    output to emit ``py::register_exception<CppType>(m, "Name")`` and pyi
    output to emit ``class Name(BaseException): ...``.

    YAML::
      stage: register_exception
      cpp_type: "ns::MyException"    # C++ qualified type
      target_name: "MyException"     # Python class name (defaults to cpp_type)
      base: "Exception"              # Python base class (defaults to "Exception")
    """
    name = "register_exception"

    def __init__(self, **kwargs: Any) -> None:
        self.cpp_exception_type: str = kwargs["cpp_type"]
        self.target_exception_name: str = kwargs.get("target_name", kwargs["cpp_type"].split("::")[-1])
        self.base_target_exception: str = kwargs.get("base", "Exception")

    def apply(self, module: TIRModule) -> None:
        module.exception_registrations.append(IRExceptionRegistration(
            cpp_exception_type=self.cpp_exception_type,
            target_exception_name=self.target_exception_name,
            base_target_exception=self.base_target_exception,
        ))


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
    InjectPropertyStage,
    # Base-class suppression
    SuppressBaseStage,
    # Deprecation
    MarkDeprecatedStage,
    # Spaceship expansion
    ExpandSpaceshipStage,
    # Protected member exposure
    ExposeProtectedStage,
    # Using declaration resolution
    ResolveUsingDeclarationsStage,
    # Exception registration
    RegisterExceptionStage,
    # Overload priority
    OverloadPriorityStage,
    # Exception policy
    ExceptionPolicyStage,
]:
    register_stage(_stage_cls.name, _stage_cls)
