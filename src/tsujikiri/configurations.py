"""Configuration dataclasses for tsujikiri.

Two distinct config objects:
  - InputConfig  loaded from ``myproject.input.yml``  — what to parse and filter
  - OutputConfig loaded from ``luabridge3.output.yml`` — how to emit the bindings

Both are loaded via ``yaml.safe_load`` (no YAML tags required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Input configuration helpers
# ---------------------------------------------------------------------------

@dataclass
class FilterPattern:
    """A single filter entry: plain string or regex."""
    pattern: str
    is_regex: bool = False


@dataclass
class SourceConfig:
    path: str
    parse_args: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)


@dataclass
class SourceFilter:
    """Glob patterns for source file paths to exclude from the IR."""
    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class ClassFilter:
    whitelist: List[FilterPattern] = field(default_factory=list)  # empty = include all
    blacklist: List[FilterPattern] = field(default_factory=list)
    internal: List[FilterPattern] = field(default_factory=list)   # skip silently


@dataclass
class MethodFilter:
    global_blacklist: List[FilterPattern] = field(default_factory=list)
    per_class: Dict[str, List[FilterPattern]] = field(default_factory=dict)


@dataclass
class FieldFilter:
    global_blacklist: List[FilterPattern] = field(default_factory=list)
    per_class: Dict[str, List[FilterPattern]] = field(default_factory=dict)


@dataclass
class ConstructorFilter:
    include: bool = True
    signatures: List[FilterPattern] = field(default_factory=list)  # empty = all ctors


@dataclass
class FunctionFilter:
    whitelist: List[FilterPattern] = field(default_factory=list)
    blacklist: List[FilterPattern] = field(default_factory=list)


@dataclass
class EnumFilter:
    whitelist: List[FilterPattern] = field(default_factory=list)
    blacklist: List[FilterPattern] = field(default_factory=list)


@dataclass
class FilterConfig:
    namespaces: List[str] = field(default_factory=list)  # empty = all namespaces
    sources: SourceFilter = field(default_factory=SourceFilter)
    classes: ClassFilter = field(default_factory=ClassFilter)
    methods: MethodFilter = field(default_factory=MethodFilter)
    fields: FieldFilter = field(default_factory=FieldFilter)
    functions: FunctionFilter = field(default_factory=FunctionFilter)
    enums: EnumFilter = field(default_factory=EnumFilter)
    constructors: ConstructorFilter = field(default_factory=ConstructorFilter)


@dataclass
class TransformSpec:
    """Specification for a single transform stage from the input YAML."""
    stage: str
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClassTweak:
    rename: Optional[str] = None
    skip_methods: List[str] = field(default_factory=list)


@dataclass
class InputConfig:
    source: SourceConfig
    filters: FilterConfig = field(default_factory=FilterConfig)
    transforms: List[TransformSpec] = field(default_factory=list)
    tweaks: Dict[str, ClassTweak] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------

@dataclass
class TemplateSet:
    line_comment: str = ""
    prologue: str = ""
    epilogue: str = ""
    module_name: str = ""
    # class
    class_begin: str = ""
    class_derived_begin: str = ""
    class_end: str = ""
    class_methods_begin: str = ""
    class_methods_end: str = ""
    # methods
    class_method_begin: str = ""
    class_method_end: str = ""
    class_overloaded_method_begin: str = ""
    class_overloaded_method_end: str = ""
    class_static_method_begin: str = ""
    class_static_method_end: str = ""
    class_overloaded_static_method_begin: str = ""
    class_overloaded_static_method_end: str = ""
    class_overload_const_definition: str = ""
    # constructors
    class_constructor_begin: str = ""
    class_constructor_end: str = ""
    class_overloaded_constructor_begin: str = ""
    class_overloaded_constructor_end: str = ""
    # fields / properties
    class_field_begin: str = ""
    class_field_end: str = ""
    class_readonly_field_begin: str = ""
    class_readonly_field_end: str = ""
    # free functions
    function_begin: str = ""
    function_end: str = ""
    function_overloaded_begin: str = ""
    function_overloaded_end: str = ""
    # enums
    enum_begin: str = ""
    enum_end: str = ""
    enum_value: str = ""


@dataclass
class OutputConfig:
    format_name: str = ""
    format_version: str = "1.0"
    description: str = ""
    templates: TemplateSet = field(default_factory=TemplateSet)
    type_mappings: Dict[str, str] = field(default_factory=dict)
    unsupported_types: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _parse_filter_pattern(raw: Any) -> FilterPattern:
    if isinstance(raw, str):
        return FilterPattern(pattern=raw)
    return FilterPattern(
        pattern=raw.get("pattern", ""),
        is_regex=raw.get("is_regex", False),
    )


def _parse_filter_patterns(raw: Any) -> List[FilterPattern]:
    if not raw:
        return []
    return [_parse_filter_pattern(r) for r in raw]


def _parse_per_class_filter(raw: Any) -> Dict[str, List[FilterPattern]]:
    if not raw:
        return {}
    return {cls: _parse_filter_patterns(patterns) for cls, patterns in raw.items()}


def _parse_transform_spec(raw: Dict[str, Any]) -> TransformSpec:
    stage = raw.pop("stage")
    return TransformSpec(stage=stage, kwargs=raw)


def load_input_config(config_file: Path) -> InputConfig:
    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    src = data.get("source", {})
    source = SourceConfig(
        path=src.get("path", ""),
        parse_args=src.get("parse_args", []),
        include_paths=src.get("include_paths", []),
    )

    filt_raw = data.get("filters", {})
    src_filt_raw = filt_raw.get("sources", {})
    cls_raw = filt_raw.get("classes", {})
    meth_raw = filt_raw.get("methods", {})
    field_raw = filt_raw.get("fields", {})
    fn_raw = filt_raw.get("functions", {})
    enum_raw = filt_raw.get("enums", {})
    ctor_raw = filt_raw.get("constructors", {})

    filters = FilterConfig(
        namespaces=filt_raw.get("namespaces", []),
        sources=SourceFilter(
            exclude_patterns=src_filt_raw.get("exclude_patterns", []),
        ),
        classes=ClassFilter(
            whitelist=_parse_filter_patterns(cls_raw.get("whitelist", [])),
            blacklist=_parse_filter_patterns(cls_raw.get("blacklist", [])),
            internal=_parse_filter_patterns(cls_raw.get("internal", [])),
        ),
        methods=MethodFilter(
            global_blacklist=_parse_filter_patterns(meth_raw.get("global_blacklist", [])),
            per_class=_parse_per_class_filter(meth_raw.get("per_class", {})),
        ),
        fields=FieldFilter(
            global_blacklist=_parse_filter_patterns(field_raw.get("global_blacklist", [])),
            per_class=_parse_per_class_filter(field_raw.get("per_class", {})),
        ),
        functions=FunctionFilter(
            whitelist=_parse_filter_patterns(fn_raw.get("whitelist", [])),
            blacklist=_parse_filter_patterns(fn_raw.get("blacklist", [])),
        ),
        enums=EnumFilter(
            whitelist=_parse_filter_patterns(enum_raw.get("whitelist", [])),
            blacklist=_parse_filter_patterns(enum_raw.get("blacklist", [])),
        ),
        constructors=ConstructorFilter(
            include=ctor_raw.get("include", True),
            signatures=_parse_filter_patterns(ctor_raw.get("signatures", [])),
        ),
    )

    transforms_raw = data.get("transforms", [])
    transforms = [_parse_transform_spec(dict(t)) for t in transforms_raw]

    tweaks_raw = data.get("tweaks", {})
    tweaks = {
        cls: ClassTweak(
            rename=tw.get("rename"),
            skip_methods=tw.get("skip_methods", []),
        )
        for cls, tw in tweaks_raw.items()
    }

    return InputConfig(source=source, filters=filters, transforms=transforms, tweaks=tweaks)


def _parse_template_set(raw: Dict[str, Any]) -> TemplateSet:
    tmpl = TemplateSet()
    for fname in TemplateSet.__dataclass_fields__:
        if fname in raw:
            setattr(tmpl, fname, raw[fname] or "")
    return tmpl


def load_output_config(config_file: Path) -> OutputConfig:
    with open(config_file, "r") as f:
        data = yaml.safe_load(f) or {}

    templates = _parse_template_set(data.get("templates", {}))

    return OutputConfig(
        format_name=data.get("format_name", ""),
        format_version=str(data.get("format_version", "1.0")),
        description=data.get("description", ""),
        templates=templates,
        type_mappings=data.get("type_mappings", {}),
        unsupported_types=data.get("unsupported_types", []),
    )
