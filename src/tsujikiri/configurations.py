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

from tsujikiri.typesystem import TypesystemConfig, _parse_typesystem_config

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
    system_include_paths: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)


@dataclass
class SourceFilter:
    """Glob patterns for source file paths to exclude from the IR."""

    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class ClassFilter:
    whitelist: List[FilterPattern] = field(default_factory=list)  # empty = include all
    blacklist: List[FilterPattern] = field(default_factory=list)
    internal: List[FilterPattern] = field(default_factory=list)  # skip silently


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
    trampoline_prefix: str = "Py"  # prefix for generated trampoline class names


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
    - ``template_extends_file``: path to an external Jinja2 child template file;
      takes precedence over ``template_extends`` when non-empty.  Relative paths
      are resolved relative to the input YAML file's directory.
    - ``unsupported_types``: additional types to treat as unsupported.
    - ``filters``: if set, *replaces* the effective per-source/top-level filters
      when generating for this format (highest-priority filter override).
    - ``transforms``: if set, these stages are *appended* to the effective
      per-source/top-level transforms when generating for this format.
    - ``generation``: if set, ``includes`` are appended to the collected
      includes; ``prefix``/``postfix`` replace the top-level values when
      non-empty.
    - ``typesystem``: inline typesystem declarations that override / extend the
      top-level typesystem when generating for this format.  Entries here take
      priority over the top-level entries (first-match wins in the generator).
    - ``typesystem_file``: path to a YAML file whose ``typesystem:`` block is
      loaded as the format typesystem; takes precedence over inline
      ``typesystem`` when non-empty.  Relative paths are resolved relative to
      the input YAML file's directory.
    - ``pretty``: ``None`` = inherit the top-level ``pretty`` setting;
      ``True`` = force-enable for this format; ``False`` = force-disable
      for this format even when the global default is ``True``.
    - ``pretty_options``: ``None`` = inherit the top-level ``pretty_options``
      list; a list = use these args instead of the global ones.
    """

    template_extends: str = ""  # inline child template for single-template system
    template_extends_file: str = ""  # external file path; takes precedence over template_extends
    unsupported_types: List[str] = field(default_factory=list)
    filters: Optional[FilterConfig] = None
    transforms: Optional[List[TransformSpec]] = None
    generation: Optional[GenerationConfig] = None
    typesystem: Optional[TypesystemConfig] = None
    typesystem_file: str = ""  # external file path; takes precedence over inline typesystem
    pretty: Optional[bool] = None
    pretty_options: Optional[List[str]] = None


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
    # First-class typesystem declarations (primitive, typedef, custom, container, smart-pointer types).
    typesystem: TypesystemConfig = field(default_factory=TypesystemConfig)
    # Arbitrary user-defined data passed verbatim into the template context as ``custom_data``.
    custom_data: Dict[str, Any] = field(default_factory=dict)

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
    extends: str = ""  # name of base format to inherit from (e.g. "luabridge3")
    type_mappings: Dict[str, str] = field(default_factory=dict)
    operator_mappings: Dict[str, str] = field(default_factory=dict)  # C++ operator → binding name
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
        trampoline_prefix=gen_raw.get("trampoline_prefix", "Py"),
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
        system_include_paths=entry_raw.get("system_include_paths", []),
        defines=entry_raw.get("defines", []),
    )

    filters, transforms, generation = _parse_optional_overrides(entry_raw)
    return SourceEntry(source=source, filters=filters, transforms=transforms, generation=generation)


def _merge_yaml_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two raw YAML dicts. override extends/wins over base.

    - Scalar conflicts: override wins
    - List conflicts: base list followed by override list
    - Dict conflicts: recursive merge
    """
    result = dict(base)
    for key, override_val in override.items():
        if key not in result:
            result[key] = override_val
        elif isinstance(result[key], list) and isinstance(override_val, list):
            result[key] = result[key] + override_val
        elif isinstance(result[key], dict) and isinstance(override_val, dict):
            result[key] = _merge_yaml_dicts(result[key], override_val)
        else:
            result[key] = override_val
    return result


def _load_raw_with_loads(config_file: Path, _seen: frozenset[str] = frozenset()) -> Dict[str, Any]:
    """Load a YAML config file and recursively expand any top-level ``loads:`` entries.

    Paths in ``loads`` are resolved relative to the file that declares them.
    Cycle detection is performed via the resolved absolute path set ``_seen``.
    Loaded data provides defaults; the loading file's own values take precedence.
    """
    resolved = str(config_file.resolve())
    if resolved in _seen:
        return {}

    with open(config_file, encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f) or {}

    config_dir = config_file.parent
    seen = _seen | {resolved}

    load_paths: List[str] = data.get("loads", [])
    merged_base: Dict[str, Any] = {}
    for load_path_str in load_paths:
        load_path = Path(load_path_str)
        if not load_path.is_absolute():
            load_path = config_dir / load_path
        load_data = _load_raw_with_loads(load_path.resolve(), seen)
        merged_base = _merge_yaml_dicts(merged_base, load_data)

    result = _merge_yaml_dicts(merged_base, data)
    result.pop("loads", None)
    return result


def load_input_config(config_file: Path) -> InputConfig:
    data = _load_raw_with_loads(config_file)

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
            system_include_paths=src.get("system_include_paths", []),
            defines=src.get("defines", []),
        )

    # --- Multiple sources ---
    sources: List[SourceEntry] = [_parse_source_entry(entry_raw, config_dir) for entry_raw in data.get("sources", [])]

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
    format_overrides: Dict[str, FormatOverrideConfig] = {}
    for fmt_name, override_raw in fmt_overrides_raw.items():
        ov_filters, ov_transforms, ov_generation = _parse_optional_overrides(override_raw)
        tef_path_str = override_raw.get("template_extends_file", "") or ""
        ov_template_extends = override_raw.get("template_extends", "") or ""
        if tef_path_str:
            tef_path = Path(tef_path_str)
            if not tef_path.is_absolute():
                tef_path = config_dir / tef_path
            with open(tef_path, "r", encoding="utf-8") as _tf:
                ov_template_extends = _tf.read()
        # Parse format-specific typesystem (inline or from file).
        ov_ts_file_str = override_raw.get("typesystem_file", "") or ""
        ov_typesystem: Optional[TypesystemConfig] = None
        if ov_ts_file_str:
            ov_ts_path = Path(ov_ts_file_str)
            if not ov_ts_path.is_absolute():
                ov_ts_path = config_dir / ov_ts_path
            with open(ov_ts_path, encoding="utf-8") as _f:
                _ts_doc = yaml.safe_load(_f) or {}
            ov_ts_raw = _ts_doc.get("typesystem", _ts_doc)
            ov_typesystem = _parse_typesystem_config(ov_ts_raw)
        elif "typesystem" in override_raw:
            ov_typesystem = _parse_typesystem_config(override_raw["typesystem"] or {})
        # Use "key in" guard so `pretty: false` is not confused with absent key.
        ov_pretty: Optional[bool] = override_raw["pretty"] if "pretty" in override_raw else None
        ov_pretty_options: Optional[List[str]] = override_raw.get("pretty_options")
        format_overrides[fmt_name] = FormatOverrideConfig(
            template_extends=ov_template_extends,
            template_extends_file=tef_path_str,
            unsupported_types=override_raw.get("unsupported_types", []),
            filters=ov_filters,
            transforms=ov_transforms,
            generation=ov_generation,
            typesystem=ov_typesystem,
            typesystem_file=ov_ts_file_str,
            pretty=ov_pretty,
            pretty_options=ov_pretty_options,
        )

    # --- Typesystem ---
    ts_raw = data.get("typesystem", {})
    typesystem = _parse_typesystem_config(ts_raw) if ts_raw else TypesystemConfig()

    # --- Custom data ---
    custom_data: Dict[str, Any] = data.get("custom_data") or {}

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
        typesystem=typesystem,
        custom_data=custom_data,
    )


def load_output_config(config_file: Path) -> OutputConfig:
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    template = data.get("template", "") or ""
    template_file = data.get("template_file", "") or ""
    if template_file:
        template_path = Path(template_file)
        if not template_path.is_absolute():
            template_path = config_file.parent / template_path
        with open(template_path, "r", encoding="utf-8") as tf:
            template = tf.read()

    return OutputConfig(
        format_name=data.get("format_name", ""),
        format_version=str(data.get("format_version", "1.0")),
        description=data.get("description", ""),
        language=data.get("language", ""),
        extends=data.get("extends", "") or "",
        type_mappings=data.get("type_mappings", {}),
        operator_mappings=data.get("operator_mappings", {}),
        unsupported_types=data.get("unsupported_types", []),
        template=template,
    )
