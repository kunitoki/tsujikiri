"""Configuration dataclasses for tsujikiri.

Two distinct config objects:
  - InputConfig  loaded from ``myproject.input.yml``  — what to parse and filter
  - OutputConfig loaded from ``luabridge3.output.yml`` — how to emit the bindings

Both are loaded via ``yaml.safe_load`` (no YAML tags required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
class MethodClassFilter:
    whitelist: List[FilterPattern] = field(default_factory=list)
    blacklist: List[FilterPattern] = field(default_factory=list)


@dataclass
class MethodFilter:
    global_blacklist: List[FilterPattern] = field(default_factory=list)
    per_class: Dict[str, MethodClassFilter] = field(default_factory=dict)


@dataclass
class FieldFilter:
    global_blacklist: List[FilterPattern] = field(default_factory=list)
    per_class: Dict[str, List[FilterPattern]] = field(default_factory=dict)


@dataclass
class ConstructorClassFilter:
    include: Optional[bool] = None  # None = inherit global
    signatures: List[FilterPattern] = field(default_factory=list)


@dataclass
class ConstructorFilter:
    include: bool = True
    signatures: List[FilterPattern] = field(default_factory=list)  # empty = all ctors
    per_class: Dict[str, ConstructorClassFilter] = field(default_factory=dict)


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
class OutputGroupEntry:
    """A named group of source files that produce one output file."""

    name: str
    sources: List[str]  # raw path strings from YAML; resolved via InputConfig.resolve_group_sources()


def _path_parts_for_lookup(path: str) -> tuple[str, ...]:
    path_obj = Path(path)
    if path_obj.is_absolute():
        return path_obj.resolve().parts
    return path_obj.parts


def _source_path_matches(source_path: str, requested_path: str) -> bool:
    requested_parts = _path_parts_for_lookup(requested_path)
    if not requested_parts:
        return False

    source_parts = _path_parts_for_lookup(source_path)
    if Path(requested_path).is_absolute():
        return source_parts == requested_parts

    return len(requested_parts) <= len(source_parts) and source_parts[-len(requested_parts) :] == requested_parts


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
    # Named output groups; sources in each group are raw YAML path strings resolved
    # against self.sources at processing time via resolve_group_sources().
    output_groups: List[OutputGroupEntry] = field(default_factory=list)
    filters: FilterConfig = field(default_factory=FilterConfig)
    transforms: List[TransformSpec] = field(default_factory=list)
    tweaks: Dict[str, ClassTweak] = field(default_factory=dict)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    # Attribute-based annotation handlers (applied after filtering, before transforms).
    attributes: AttributeHandlerConfig = field(default_factory=AttributeHandlerConfig)
    # Per-format template/type overrides (keyed by format name, e.g. "luabridge3").
    format_overrides: Dict[str, FormatOverrideConfig] = field(default_factory=dict)
    # Per-output-group format overrides: output group name -> format name -> override.
    output_format_overrides: Dict[str, Dict[str, FormatOverrideConfig]] = field(default_factory=dict)
    # Post-generation pretty printing: run the language-appropriate pretty printer on output.
    pretty: bool = False
    pretty_options: List[str] = field(default_factory=list)
    # First-class typesystem declarations (primitive, typedef, custom, container, smart-pointer types).
    typesystem: TypesystemConfig = field(default_factory=TypesystemConfig)
    # Arbitrary user-defined data passed verbatim into the template context as ``custom_data``.
    custom_data: Dict[str, Any] = field(default_factory=dict)
    parse_args: List[str] = field(default_factory=list)
    include_paths: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)

    def resolve_group_sources(self, group: "OutputGroupEntry") -> List[SourceEntry]:
        """Resolve a group's path strings to SourceEntry objects using self.sources as lookup.

        Absolute paths match exactly. Relative paths match any unique source
        path suffix, so ``source.h``, ``to/source.h``, and
        ``path/to/source.h`` can all refer to ``../../path/to/source.h``.
        Unmatched paths produce a bare SourceEntry (path only, no extra clang
        flags). Ambiguous matches are rejected.
        """
        return [self._resolve_group_source(group, source_path) for source_path in group.sources]

    def _resolve_group_source(self, group: "OutputGroupEntry", source_path: str) -> SourceEntry:
        matches = [entry for entry in self.sources if _source_path_matches(entry.source.path, source_path)]
        if not matches:
            return SourceEntry(source=SourceConfig(path=source_path))
        if len(matches) == 1:
            return matches[0]

        candidates = ", ".join(entry.source.path for entry in matches)
        raise ValueError(
            f"Ambiguous source reference '{source_path}' in output group '{group.name}'; matches: {candidates}"
        )

    def get_source_entries(self) -> List[SourceEntry]:
        """Return all source entries, normalising a bare ``source:`` key into the list."""
        if self.output_groups:
            seen: Set[str] = set()
            result: List[SourceEntry] = []
            for group in self.output_groups:
                for entry in self.resolve_group_sources(group):
                    if entry.source.path not in seen:
                        seen.add(entry.source.path)
                        result.append(entry)
            return result
        if self.sources:
            return self.sources
        if self.source:
            return [SourceEntry(source=self.source)]
        return []

    def format_override_for(
        self,
        format_name: str,
        output_name: Optional[str] = None,
    ) -> Optional[FormatOverrideConfig]:
        """Return the override for a format, preferring a merged output-scoped override."""
        if output_name is not None:
            output_override = self.output_format_overrides.get(output_name, {}).get(format_name)
            if output_override is not None:
                return output_override
        return self.format_overrides.get(format_name)

    def all_format_overrides(self) -> List[FormatOverrideConfig]:
        """Return global and output-scoped format overrides for validation."""
        overrides = list(self.format_overrides.values())
        for scoped_overrides in self.output_format_overrides.values():
            overrides.extend(scoped_overrides.values())
        return overrides

    def effective_source(self, entry: "SourceEntry") -> "SourceConfig":
        return SourceConfig(
            path=entry.source.path,
            parse_args=self.parse_args + entry.source.parse_args,
            include_paths=self.include_paths + entry.source.include_paths,
            system_include_paths=entry.source.system_include_paths,
            defines=self.defines + entry.source.defines,
        )


# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------


@dataclass
class OutputConfig:
    format_name: str = ""
    format_version: str = "1.0"
    description: str = ""
    language: str = ""  # target language, e.g. "cpp" or "lua"
    extension: str = ""  # output file extension, e.g. ".cpp" or ".lua"
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


def _parse_method_class_filter(raw: Any) -> MethodClassFilter:
    if not raw:
        return MethodClassFilter()
    return MethodClassFilter(
        whitelist=_parse_filter_patterns(raw.get("whitelist", [])),
        blacklist=_parse_filter_patterns(raw.get("blacklist", [])),
    )


def _parse_constructor_class_filter(raw: Any) -> ConstructorClassFilter:
    if not raw:
        return ConstructorClassFilter()
    return ConstructorClassFilter(
        include=raw.get("include"),
        signatures=_parse_filter_patterns(raw.get("signatures", [])),
    )


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
            per_class={cls: _parse_method_class_filter(v) for cls, v in (meth_raw.get("per_class", {}) or {}).items()},
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
            per_class={
                cls: _parse_constructor_class_filter(v) for cls, v in (ctor_raw.get("per_class", {}) or {}).items()
            },
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


def _parse_format_override_config(override_raw: Dict[str, Any], config_dir: Path) -> FormatOverrideConfig:
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
    return FormatOverrideConfig(
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


def _resolve_source_path(src_path: str, config_dir: Path, basepath: str) -> str:
    """Resolve a source path to absolute, honouring an optional basepath prefix."""
    if not src_path or Path(src_path).is_absolute():
        return src_path
    if basepath:
        base = Path(basepath)
        if not base.is_absolute():
            base = (config_dir / base).resolve()
        return str((base / src_path).resolve())
    return str((config_dir / src_path).resolve())


def _parse_source_entry(entry_raw: Dict[str, Any], config_dir: Path, basepath: str = "") -> SourceEntry:
    src_path = _resolve_source_path(entry_raw.get("path", ""), config_dir, basepath)

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


def _normalize_format_overrides_to_list(data: Dict[str, Any]) -> None:
    """Convert dict-form format_overrides to list-form for uniform loads: merging."""
    fov = data.get("format_overrides")
    if isinstance(fov, dict):
        data["format_overrides"] = [{k: v} for k, v in fov.items()]


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
        _normalize_format_overrides_to_list(load_data)
        merged_base = _merge_yaml_dicts(merged_base, load_data)

    if merged_base:
        _normalize_format_overrides_to_list(data)
    result = _merge_yaml_dicts(merged_base, data)
    result.pop("loads", None)
    return result


def load_input_config(config_file: Path) -> InputConfig:
    data = _load_raw_with_loads(config_file)

    config_dir = config_file.parent
    basepath: str = data.get("basepath", "") or ""

    # --- Single source (backward compat) ---
    source: Optional[SourceConfig] = None
    if "source" in data:
        src = data["source"]
        source = SourceConfig(
            path=_resolve_source_path(src.get("path", ""), config_dir, basepath),
            parse_args=src.get("parse_args", []),
            include_paths=src.get("include_paths", []),
            system_include_paths=src.get("system_include_paths", []),
            defines=src.get("defines", []),
        )

    # --- Multiple sources ---
    sources: List[SourceEntry] = [
        _parse_source_entry(entry_raw, config_dir, basepath) for entry_raw in data.get("sources", [])
    ]

    output_groups: List[OutputGroupEntry] = [
        OutputGroupEntry(name=group_raw.get("name", ""), sources=group_raw.get("sources", []))
        for group_raw in data.get("outputs", [])
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
    global_format_overrides_raw: Dict[str, Dict[str, Any]] = {}
    scoped_format_overrides_raw: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _format_override_raw(fmt_name: str, override_raw: Any) -> Dict[str, Any]:
        if override_raw is None:
            return {}
        if not isinstance(override_raw, dict):
            raise ValueError(f"format_overrides.{fmt_name} must be a mapping")
        return override_raw

    if isinstance(fmt_overrides_raw, dict):
        for fmt_name, override_raw in fmt_overrides_raw.items():
            global_format_overrides_raw[fmt_name] = _format_override_raw(fmt_name, override_raw)
    elif isinstance(fmt_overrides_raw, list):
        for entry_raw in fmt_overrides_raw:
            if not isinstance(entry_raw, dict):
                raise ValueError("format_overrides list entries must be mappings")
            output_name = entry_raw.get("output")
            if output_name is not None and not isinstance(output_name, str):
                raise ValueError("format_overrides output values must be strings")

            for fmt_name, override_raw in entry_raw.items():
                if fmt_name == "output":
                    continue
                fmt_override_raw = _format_override_raw(fmt_name, override_raw)
                if output_name is None:
                    base = global_format_overrides_raw.get(fmt_name, {})
                    global_format_overrides_raw[fmt_name] = _merge_yaml_dicts(base, fmt_override_raw)
                else:
                    scoped_by_format = scoped_format_overrides_raw.setdefault(output_name, {})
                    base = scoped_by_format.get(fmt_name, {})
                    scoped_by_format[fmt_name] = _merge_yaml_dicts(base, fmt_override_raw)
    elif fmt_overrides_raw:
        raise ValueError("format_overrides must be a mapping or a list of mappings")

    if scoped_format_overrides_raw:
        known_outputs = {group.name for group in output_groups}
        unknown_outputs = sorted(set(scoped_format_overrides_raw) - known_outputs)
        if unknown_outputs:
            unknown = ", ".join(unknown_outputs)
            raise ValueError(f"format_overrides references unknown output group(s): {unknown}")

    format_overrides: Dict[str, FormatOverrideConfig] = {
        fmt_name: _parse_format_override_config(override_raw, config_dir)
        for fmt_name, override_raw in global_format_overrides_raw.items()
    }
    output_format_overrides: Dict[str, Dict[str, FormatOverrideConfig]] = {}
    for output_name, scoped_by_format in scoped_format_overrides_raw.items():
        output_format_overrides[output_name] = {}
        for fmt_name, scoped_override_raw in scoped_by_format.items():
            merged_override_raw = _merge_yaml_dicts(global_format_overrides_raw.get(fmt_name, {}), scoped_override_raw)
            output_format_overrides[output_name][fmt_name] = _parse_format_override_config(
                merged_override_raw,
                config_dir,
            )

    # --- Typesystem ---
    ts_raw = data.get("typesystem", {})
    typesystem = _parse_typesystem_config(ts_raw) if ts_raw else TypesystemConfig()

    # --- Custom data ---
    custom_data: Dict[str, Any] = data.get("custom_data") or {}

    # --- Global clang flags ---
    parse_args: List[str] = data.get("parse_args", []) or []
    include_paths: List[str] = data.get("include_paths", []) or []
    defines: List[str] = data.get("defines", []) or []

    return InputConfig(
        source=source,
        sources=sources,
        output_groups=output_groups,
        filters=filters,
        transforms=transforms,
        tweaks=tweaks,
        generation=generation,
        attributes=attributes,
        format_overrides=format_overrides,
        output_format_overrides=output_format_overrides,
        pretty=data.get("pretty", False),
        pretty_options=data.get("pretty_options", []),
        typesystem=typesystem,
        custom_data=custom_data,
        parse_args=parse_args,
        include_paths=include_paths,
        defines=defines,
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
        extension=data.get("extension", "") or "",
        extends=data.get("extends", "") or "",
        type_mappings=data.get("type_mappings", {}),
        operator_mappings=data.get("operator_mappings", {}),
        unsupported_types=data.get("unsupported_types", []),
        template=template,
    )
