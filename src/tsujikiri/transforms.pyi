from _typeshed import Incomplete
from tsujikiri.configurations import TransformSpec as TransformSpec
from tsujikiri.ir import IRClass as IRClass, IRCodeInjection as IRCodeInjection, IRConstructor as IRConstructor, IREnum as IREnum, IRExceptionRegistration as IRExceptionRegistration, IRField as IRField, IRFunction as IRFunction, IRMethod as IRMethod, IRModule as IRModule, IRParameter as IRParameter, IRProperty as IRProperty
from typing import Any

class TransformStage:
    name: str
    def apply(self, module: IRModule) -> None: ...

def register_stage(name: str, cls: type[TransformStage]) -> None: ...

class TransformPipeline:
    stages: Incomplete
    def __init__(self, stages: list[TransformStage]) -> None: ...
    def run(self, module: IRModule) -> None: ...
    def unmatched_stages(self) -> list[str]: ...

def build_pipeline_from_config(specs: list[TransformSpec]) -> TransformPipeline: ...

class RenameMethodStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    from_name: str
    to_name: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RenameClassStage(TransformStage):
    name: str
    from_name: str
    to_name: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressMethodStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    pattern: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressClassStage(TransformStage):
    name: str
    pattern: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class InjectMethodStage(TransformStage):
    name: str
    class_pattern: str
    method_name: str
    return_type: str
    parameters: list[dict[str, str]]
    is_static: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class AddTypeMappingStage(TransformStage):
    name: str
    from_type: str
    to_type: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyMethodStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    method_pattern: str
    method_is_regex: bool
    rename: str | None
    remove: bool
    return_type: str | None
    return_ownership: str | None
    return_keep_alive: bool | None
    allow_thread: bool | None
    wrapper_code: str | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyArgumentStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    method_pattern: str
    method_is_regex: bool
    arg_index: int | None
    arg_name: str | None
    rename: str | None
    remove: bool
    type_override: str | None
    default_override: str | None
    ownership: str | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyFieldStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    field_pattern: str
    field_is_regex: bool
    rename: str | None
    remove: bool
    read_only: bool | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyConstructorStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    signature: str
    remove: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RemoveOverloadStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    method_name: str
    signature: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class OverloadPriorityStage(TransformStage):
    name: str
    class_name: str
    method_name: str
    signature: str
    priority: int
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ExceptionPolicyStage(TransformStage):
    name: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class InjectCodeStage(TransformStage):
    name: str
    target: str
    class_pattern: str
    class_is_regex: bool
    method_pattern: str
    method_is_regex: bool
    signature: str | None
    position: str
    code: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SetTypeHintStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    copyable: bool | None
    movable: bool | None
    force_abstract: bool | None
    holder_type: str | None
    generate_hash: bool | None
    smart_pointer_kind: str | None
    smart_pointer_managed_type: str | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RenameEnumStage(TransformStage):
    name: str
    from_name: str
    to_name: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RenameEnumValueStage(TransformStage):
    name: str
    enum_pattern: str
    enum_is_regex: bool
    from_name: str
    to_name: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressEnumStage(TransformStage):
    name: str
    pattern: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressEnumValueStage(TransformStage):
    name: str
    enum_pattern: str
    enum_is_regex: bool
    pattern: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyEnumStage(TransformStage):
    name: str
    enum_pattern: str
    enum_is_regex: bool
    rename: str | None
    remove: bool
    arithmetic: bool | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RenameFunctionStage(TransformStage):
    name: str
    from_name: str
    to_name: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressFunctionStage(TransformStage):
    name: str
    pattern: str
    is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ModifyFunctionStage(TransformStage):
    name: str
    function_pattern: str
    function_is_regex: bool
    rename: str | None
    remove: bool
    return_type: str | None
    return_ownership: str | None
    return_keep_alive: bool | None
    allow_thread: bool | None
    wrapper_code: str | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class InjectConstructorStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    parameters: list[dict[str, str]]
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class InjectFunctionStage(TransformStage):
    name: str
    fn_name: str
    namespace: str
    return_type: str
    parameters: list[dict[str, str]]
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class SuppressBaseStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    base_pattern: str
    base_is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class InjectPropertyStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    prop_name: str
    getter: str
    setter: str | None
    type_spelling: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class MarkDeprecatedStage(TransformStage):
    name: str
    target: str
    class_pattern: str
    class_is_regex: bool
    method_pattern: str
    method_is_regex: bool
    function_pattern: str
    function_is_regex: bool
    enum_pattern: str
    enum_is_regex: bool
    message: str | None
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ExpandSpaceshipStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ExposeProtectedStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    method_pattern: str
    method_is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class ResolveUsingDeclarationsStage(TransformStage):
    name: str
    class_pattern: str
    class_is_regex: bool
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...

class RegisterExceptionStage(TransformStage):
    name: str
    cpp_exception_type: str
    python_exception_name: str
    base_python_exception: str
    def __init__(self, **kwargs: Any) -> None: ...
    def apply(self, module: IRModule) -> None: ...
