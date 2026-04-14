from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class PrimitiveTypeEntry:
    cpp_name: str
    python_name: str

@dataclass
class TypedefTypeEntry:
    cpp_name: str
    source: str

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
class LoadTypesystemEntry:
    path: str

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
    load_typesystems: list[LoadTypesystemEntry] = field(default_factory=list)
    declared_functions: list[DeclaredFunctionEntry] = field(default_factory=list)
    conversion_rules: list[ConversionRuleEntry] = field(default_factory=list)

@dataclass
class FilterPattern:
    pattern: str
    is_regex: bool = ...

@dataclass
class SourceConfig:
    path: str
    parse_args: list[str] = field(default_factory=list)
    include_paths: list[str] = field(default_factory=list)
    system_include_paths: list[str] = field(default_factory=list)
    defines: list[str] = field(default_factory=list)

@dataclass
class SourceFilter:
    exclude_patterns: list[str] = field(default_factory=list)

@dataclass
class ClassFilter:
    whitelist: list[FilterPattern] = field(default_factory=list)
    blacklist: list[FilterPattern] = field(default_factory=list)
    internal: list[FilterPattern] = field(default_factory=list)

@dataclass
class MethodFilter:
    global_blacklist: list[FilterPattern] = field(default_factory=list)
    per_class: dict[str, list[FilterPattern]] = field(default_factory=dict)

@dataclass
class FieldFilter:
    global_blacklist: list[FilterPattern] = field(default_factory=list)
    per_class: dict[str, list[FilterPattern]] = field(default_factory=dict)

@dataclass
class ConstructorFilter:
    include: bool = ...
    signatures: list[FilterPattern] = field(default_factory=list)

@dataclass
class FunctionFilter:
    whitelist: list[FilterPattern] = field(default_factory=list)
    blacklist: list[FilterPattern] = field(default_factory=list)

@dataclass
class EnumFilter:
    whitelist: list[FilterPattern] = field(default_factory=list)
    blacklist: list[FilterPattern] = field(default_factory=list)

@dataclass
class FilterConfig:
    namespaces: list[str] = field(default_factory=list)
    sources: SourceFilter = field(default_factory=SourceFilter)
    classes: ClassFilter = field(default_factory=ClassFilter)
    methods: MethodFilter = field(default_factory=MethodFilter)
    fields: FieldFilter = field(default_factory=FieldFilter)
    functions: FunctionFilter = field(default_factory=FunctionFilter)
    enums: EnumFilter = field(default_factory=EnumFilter)
    constructors: ConstructorFilter = field(default_factory=ConstructorFilter)

@dataclass
class TransformSpec:
    stage: str
    kwargs: dict[str, Any] = field(default_factory=dict)

@dataclass
class ClassTweak:
    rename: str | None = ...
    skip_methods: list[str] = field(default_factory=list)

@dataclass
class AttributeHandlerConfig:
    handlers: dict[str, str] = field(default_factory=dict)

@dataclass
class GenerationConfig:
    includes: list[str] = field(default_factory=list)
    prefix: str = ...
    postfix: str = ...
    embed_version: bool = ...
    trampoline_prefix: str = ...

@dataclass
class SourceEntry:
    source: SourceConfig
    filters: FilterConfig | None = ...
    transforms: list[TransformSpec] | None = ...
    generation: GenerationConfig | None = ...

@dataclass
class FormatOverrideConfig:
    template_extends: str = ...
    unsupported_types: list[str] = field(default_factory=list)
    filters: FilterConfig | None = ...
    transforms: list[TransformSpec] | None = ...
    generation: GenerationConfig | None = ...

@dataclass
class InputConfig:
    source: SourceConfig | None = ...
    sources: list[SourceEntry] = field(default_factory=list)
    filters: FilterConfig = field(default_factory=FilterConfig)
    transforms: list[TransformSpec] = field(default_factory=list)
    tweaks: dict[str, ClassTweak] = field(default_factory=dict)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    attributes: AttributeHandlerConfig = field(default_factory=AttributeHandlerConfig)
    format_overrides: dict[str, FormatOverrideConfig] = field(default_factory=dict)
    pretty: bool = ...
    pretty_options: list[str] = field(default_factory=list)
    typesystem: TypesystemConfig = field(default_factory=TypesystemConfig)
    def get_source_entries(self) -> list[SourceEntry]: ...

@dataclass
class OutputConfig:
    format_name: str = ...
    format_version: str = ...
    description: str = ...
    language: str = ...
    type_mappings: dict[str, str] = field(default_factory=dict)
    operator_mappings: dict[str, str] = field(default_factory=dict)
    unsupported_types: list[str] = field(default_factory=list)
    template: str = ...

def load_input_config(config_file: Path) -> InputConfig: ...
def load_output_config(config_file: Path) -> OutputConfig: ...
