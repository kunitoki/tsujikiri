from dataclasses import dataclass, field

@dataclass
class PrimitiveTypeEntry:
    cpp_name: str
    target_name: str

@dataclass
class TypedefTypeEntry:
    cpp_name: str
    target_name: str

@dataclass
class CustomTypeEntry:
    cpp_name: str

@dataclass
class ContainerTypeEntry:
    cpp_name: str
    kind: str

@dataclass
class SmartPointerTypeEntry:
    cpp_name: str
    kind: str
    getter: str = ...

@dataclass
class ConversionRuleEntry:
    cpp_type: str
    native_to_target: str
    target_to_native: str

@dataclass
class DeclaredFunctionEntry:
    name: str
    namespace: str = ...
    return_type: str = ...
    parameters: list[dict[str, str]] = field(default_factory=list)
    wrapper_code: str | None = ...
    doc: str | None = ...

@dataclass
class TypesystemConfig:
    primitive_types: list[PrimitiveTypeEntry] = field(default_factory=list)
    typedef_types: list[TypedefTypeEntry] = field(default_factory=list)
    custom_types: list[CustomTypeEntry] = field(default_factory=list)
    container_types: list[ContainerTypeEntry] = field(default_factory=list)
    smart_pointer_types: list[SmartPointerTypeEntry] = field(default_factory=list)
    declared_functions: list[DeclaredFunctionEntry] = field(default_factory=list)
    conversion_rules: list[ConversionRuleEntry] = field(default_factory=list)

def merge_typesystems(priority: TypesystemConfig, base: TypesystemConfig) -> TypesystemConfig: ...
