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
    defines: List[str] = field(default_factory=list)


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
class AttributeHandlerConfig:
    """Maps custom attribute names to actions: 'skip', 'keep', or 'rename'."""
    handlers: Dict[str, str] = field(default_factory=dict)


@dataclass
class GenerationConfig:
    """Per-project generation settings: headers to include, prefix/postfix code."""
    includes: List[str] = field(default_factory=list)
    prefix: str = ""
    postfix: str = ""
    embed_version: bool = False


@dataclass
class SourceEntry:
    """A single source in a multi-source configuration.

    ``filters`` and ``transforms`` override the top-level defaults for this
    source when set; ``None`` means "inherit from the top-level config".
    ``generation.includes`` is additive: per-source includes are collected on
    top of any top-level includes.
    """
    source: SourceConfig
    filters: Optional[FilterConfig] = None
    transforms: Optional[List[TransformSpec]] = None
    generation: Optional[GenerationConfig] = None


@dataclass
class FormatOverrideConfig:
    """Per-format configuration overrides.

    Specified under ``format_overrides.<format_name>`` in the input YAML.

    - ``template_extends``: inline Jinja2 child template using ``{% extends %}``
      to customise the format's single-template output via block overrides.
    - ``unsupported_types``: additional types to treat as unsupported.
    - ``filters``: if set, *replaces* the effective per-source/top-level filters
      when generating for this format (highest-priority filter override).
    - ``transforms``: if set, these stages are *appended* to the effective
      per-source/top-level transforms when generating for this format.
    - ``generation``: if set, ``includes`` are appended to the collected
      includes; ``prefix``/``postfix`` replace the top-level values when
      non-empty.
    """
    template_extends: str = ""  # inline child template for single-template system
    unsupported_types: List[str] = field(default_factory=list)
    filters: Optional[FilterConfig] = None
    transforms: Optional[List[TransformSpec]] = None
    generation: Optional[GenerationConfig] = None


@dataclass
class InputConfig:
    # Backward-compat single source (mutually exclusive with ``sources``).
    source: Optional[SourceConfig] = None
    # New multi-source list; takes precedence over ``source`` when non-empty.
    sources: List[SourceEntry] = field(default_factory=list)
    filters: FilterConfig = field(default_factory=FilterConfig)
    transforms: List[TransformSpec] = field(default_factory=list)
    tweaks: Dict[str, ClassTweak] = field(default_factory=dict)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    # Attribute-based annotation handlers (applied after filtering, before transforms).
    attributes: AttributeHandlerConfig = field(default_factory=AttributeHandlerConfig)
    # Per-format template/type overrides (keyed by format name, e.g. "luabridge3").
    format_overrides: Dict[str, FormatOverrideConfig] = field(default_factory=dict)
    # Post-generation pretty printing: run the language-appropriate pretty printer on output.
    pretty: bool = False
    pretty_options: List[str] = field(default_factory=list)

    def get_source_entries(self) -> List[SourceEntry]:
        """Return all source entries, normalising a bare ``source:`` key into the list."""
        if self.sources:
            return self.sources
        if self.source:
            return [SourceEntry(source=self.source)]
        return []


# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------

@dataclass
class OutputConfig:
    format_name: str = ""
    format_version: str = "1.0"
    description: str = ""
    language: str = ""  # target language, e.g. "cpp" or "lua"
    type_mappings: Dict[str, str] = field(default_factory=dict)
    unsupported_types: List[str] = field(default_factory=list)
    template: str = ""  # full Jinja2 template (single-template system)


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


def _parse_filter_config(filt_raw: Dict[str, Any]) -> FilterConfig:
    src_filt_raw = filt_raw.get("sources", {})
    cls_raw = filt_raw.get("classes", {})
    meth_raw = filt_raw.get("methods", {})
    field_raw = filt_raw.get("fields", {})
    fn_raw = filt_raw.get("functions", {})
    enum_raw = filt_raw.get("enums", {})
    ctor_raw = filt_raw.get("constructors", {})

    return FilterConfig(
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


def _parse_generation_config(gen_raw: Dict[str, Any]) -> GenerationConfig:
    return GenerationConfig(
        includes=gen_raw.get("includes", []),
        prefix=gen_raw.get("prefix", "") or "",
        postfix=gen_raw.get("postfix", "") or "",
        embed_version=gen_raw.get("embed_version", False),
    )


def _parse_transforms_list(transforms_raw: List[Any]) -> List[TransformSpec]:
    return [_parse_transform_spec(dict(t)) for t in transforms_raw]


def _parse_optional_overrides(
    raw: Dict[str, Any],
) -> tuple[Optional[FilterConfig], Optional[List[TransformSpec]], Optional[GenerationConfig]]:
    """Parse the optional filters/transforms/generation keys shared by SourceEntry and FormatOverrideConfig."""
    filters = _parse_filter_config(raw["filters"]) if "filters" in raw else None
    transforms = _parse_transforms_list(raw["transforms"]) if "transforms" in raw else None
    generation = _parse_generation_config(raw["generation"]) if "generation" in raw else None
    return filters, transforms, generation


def _parse_source_entry(entry_raw: Dict[str, Any], config_dir: Path) -> SourceEntry:
    src_path = entry_raw.get("path", "")
    if src_path and not Path(src_path).is_absolute():
        src_path = str((config_dir / src_path).resolve())

    source = SourceConfig(
        path=src_path,
        parse_args=entry_raw.get("parse_args", []),
        include_paths=entry_raw.get("include_paths", []),
        defines=entry_raw.get("defines", []),
    )

    filters, transforms, generation = _parse_optional_overrides(entry_raw)
    return SourceEntry(source=source, filters=filters, transforms=transforms, generation=generation)


def load_input_config(config_file: Path) -> InputConfig:
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    config_dir = config_file.parent

    # --- Single source (backward compat) ---
    source: Optional[SourceConfig] = None
    if "source" in data:
        src = data["source"]
        src_path = src.get("path", "")
        if src_path and not Path(src_path).is_absolute():
            src_path = str((config_dir / src_path).resolve())
        source = SourceConfig(
            path=src_path,
            parse_args=src.get("parse_args", []),
            include_paths=src.get("include_paths", []),
            defines=src.get("defines", []),
        )

    # --- Multiple sources ---
    sources: List[SourceEntry] = [
        _parse_source_entry(entry_raw, config_dir)
        for entry_raw in data.get("sources", [])
    ]

    # --- Filters / transforms / generation (top-level defaults) ---
    filters = _parse_filter_config(data.get("filters", {}))
    transforms = _parse_transforms_list(data.get("transforms", []))
    generation = _parse_generation_config(data.get("generation", {}))

    # --- Attribute handlers ---
    attr_raw = data.get("attributes", {})
    attributes = AttributeHandlerConfig(
        handlers=attr_raw.get("handlers", {}),
    )

    # --- Tweaks ---
    tweaks_raw = data.get("tweaks", {})
    tweaks = {
        cls: ClassTweak(
            rename=tw.get("rename"),
            skip_methods=tw.get("skip_methods", []),
        )
        for cls, tw in tweaks_raw.items()
    }

    # --- Format overrides ---
    fmt_overrides_raw = data.get("format_overrides", {})
    format_overrides: Dict[str, FormatOverrideConfig] = {
        fmt_name: FormatOverrideConfig(
            template_extends=override_raw.get("template_extends", "") or "",
            unsupported_types=override_raw.get("unsupported_types", []),
            filters=filters,
            transforms=transforms,
            generation=generation,
        )
        for fmt_name, override_raw in fmt_overrides_raw.items()
        for filters, transforms, generation in [_parse_optional_overrides(override_raw)]
    }

    return InputConfig(
        source=source,
        sources=sources,
        filters=filters,
        transforms=transforms,
        tweaks=tweaks,
        generation=generation,
        attributes=attributes,
        format_overrides=format_overrides,
        pretty=data.get("pretty", False),
        pretty_options=data.get("pretty_options", []),
    )


def load_output_config(config_file: Path) -> OutputConfig:
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return OutputConfig(
        format_name=data.get("format_name", ""),
        format_version=str(data.get("format_version", "1.0")),
        description=data.get("description", ""),
        language=data.get("language", ""),
        type_mappings=data.get("type_mappings", {}),
        unsupported_types=data.get("unsupported_types", []),
        template=data.get("template", "") or "",
    )
