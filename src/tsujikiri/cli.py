"""Command-line interface for tsujikiri."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import re
import sys
from io import StringIO
from pathlib import Path
from typing import IO, Any, List, Optional

from tsujikiri.attribute_processor import AttributeProcessor
from tsujikiri.configurations import GenerationConfig, load_input_config, load_output_config
from tsujikiri.filters import FilterEngine
from tsujikiri.pretty_printers import pretty
from tsujikiri.formats import apply_format_inheritance, resolve_format_path, list_builtin_formats
from tsujikiri.generator import Generator
from tsujikiri.tir import TIRFunction, TIRModule, TIRParameter, merge_tir_modules, upgrade_module
from tsujikiri.manifest import compare_manifests, compute_manifest, load_manifest, save_manifest, suggest_version_bump
from tsujikiri.parser import parse_translation_unit
from tsujikiri.transforms import _REGISTRY, build_pipeline_from_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tsujikiri",
        description="辻斬り — Generic C++ Binding Generator",
    )
    p.add_argument(
        "--input", "-i",
        required=False,
        metavar="FILE",
        help="Input config YAML (e.g. myproject.input.yml)",
    )
    p.add_argument(
        "--target", "-t",
        nargs=2,
        metavar=("FORMAT", "FILE"),
        action="append",
        default=[],
        help=(
            "Output target: FORMAT is a built-in name (luabridge3) or path to .output.yml; "
            "FILE is the output path ('-' for stdout). Repeatable."
        ),
    )
    p.add_argument(
        "--classname", "-c",
        default=None,
        metavar="CLASS",
        help="Generate bindings for a single class only",
    )
    p.add_argument(
        "--formats-dir", "-f",
        action="append",
        default=[],
        metavar="DIR",
        help="Additional directory to search for .output.yml format files (repeatable)",
    )
    p.add_argument(
        "--list-formats",
        action="store_true",
        help="Print available built-in output formats and exit",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and filter but do not generate output; print a summary instead",
    )
    p.add_argument(
        "--manifest-file", "-m",
        default=None,
        metavar="FILE",
        help="Write API manifest JSON to FILE; if FILE already exists, compare with new manifest",
    )
    p.add_argument(
        "--check-compat",
        action="store_true",
        help="Exit 1 if --manifest-file exists and breaking API changes are detected",
    )
    p.add_argument(
        "--embed-version",
        action="store_true",
        help="Embed the API version hash in the generated code (template must support it)",
    )
    p.add_argument(
        "--trace-transforms",
        action="store_true",
        help="Print which transform stages ran and on what entities to stderr",
    )
    p.add_argument(
        "--dump-ir",
        nargs="?",
        const="-",
        default=None,
        metavar="FILE",
        help="Dump the post-transform IR as JSON to FILE (default: stdout when flag is given without FILE)",
    )
    p.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate the input config YAML (regex patterns, transform stage names) and exit",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output during parsing (currently only applies to Clang diagnostics)",
    )
    p.add_argument(
        "--api-version",
        metavar="VERSION",
        default=None,
        help="Target API version (semver). Entities with api_since > VERSION or api_until <= VERSION are excluded.",
    )
    return p


def _ir_to_dict(module: TIRModule) -> dict:
    """Serialize TIRModule to a JSON-compatible dict."""
    def _convert(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return {
                f.name: _convert(getattr(obj, f.name))
                for f in dataclasses.fields(obj)  # type: ignore[arg-type]
                if f.name != "origin"
            }
        if isinstance(obj, (list, tuple)):
            return [_convert(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _convert(v) for k, v in obj.items()}
        return obj

    d = _convert(module)
    d.pop("class_by_name", None)
    return d


def _validate_config_action(args: argparse.Namespace, extra_dirs: List[Path]) -> None:
    """Validate input config and print any issues. Exit 1 if invalid."""
    if not args.input:
        print("tsujikiri: error: --input is required for --validate-config", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"tsujikiri: error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    errors: List[str] = []

    try:
        input_config = load_input_config(input_path)
    except Exception as exc:
        print(f"tsujikiri: error: failed to load config: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate filter patterns
    for pattern in input_config.filters.namespaces:
        try:
            re.compile(pattern)
        except re.error as exc:
            errors.append(f"Filter namespace pattern '{pattern}' is not valid regex: {exc}")

    # Validate transform stage names across all sources
    all_transform_specs = list(input_config.transforms)
    for entry in input_config.get_source_entries():
        if entry.transforms:
            all_transform_specs.extend(entry.transforms)
    for override in input_config.format_overrides.values():
        if override.transforms:
            all_transform_specs.extend(override.transforms)

    for spec in all_transform_specs:
        if spec.stage not in _REGISTRY:
            errors.append(
                f"Unknown transform stage '{spec.stage}'. "
                f"Available: {sorted(_REGISTRY.keys())}"
            )

    # Validate target formats (if any specified)
    for fmt, _outfile in (args.target or []):
        try:
            resolve_format_path(fmt, extra_dirs=extra_dirs)
        except FileNotFoundError as exc:
            errors.append(str(exc))

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    print("Config is valid.", file=sys.stderr)


def _process_sources(
    input_config,
    source_entries,
    output_config,
    module_name: str,
    classname_filter: Optional[str],
    trace_stream: Optional[IO],
    verbose: bool = False,
) -> tuple[TIRModule, list[str]]:
    """Run parse → upgrade → filter → attribute → transform for all sources, return merged module and includes."""
    fmt_override = input_config.format_overrides.get(output_config.format_name)
    fmt_filters = fmt_override.filters if fmt_override else None
    fmt_transforms = fmt_override.transforms if fmt_override else None
    fmt_transforms_list: List = list(fmt_transforms) if fmt_transforms else []

    all_modules: List[TIRModule] = []
    all_includes: List[str] = list(input_config.generation.includes)

    for entry in source_entries:
        effective_filters = entry.filters if entry.filters is not None else input_config.filters
        if fmt_filters is not None:
            effective_filters = fmt_filters

        effective_transforms = entry.transforms if entry.transforms is not None else input_config.transforms
        if fmt_transforms_list:
            effective_transforms = list(effective_transforms) + fmt_transforms_list

        ir_module = parse_translation_unit(
            entry.source,
            effective_filters.namespaces,
            module_name,
            verbose=verbose,
        )
        module = upgrade_module(ir_module)

        if classname_filter:
            for tir_class in module.classes:
                if tir_class.name != classname_filter:
                    tir_class.emit = False  # type: ignore[union-attr]

        FilterEngine(effective_filters).apply(module)

        if verbose:
            suppressed_classes = [c.name for c in module.classes if not c.emit]
            suppressed_fns = [f.name for f in module.functions if not f.emit]
            suppressed_enums = [e.name for e in module.enums if not e.emit]
            emitted_classes = [c.name for c in module.classes if c.emit]
            emitted_fns = [f.name for f in module.functions if f.emit]
            emitted_enums = [e.name for e in module.enums if e.emit]
            print(f"[filter] emitted: classes={emitted_classes} functions={emitted_fns} enums={emitted_enums}", file=sys.stderr)
            if suppressed_classes or suppressed_fns or suppressed_enums:
                print(f"[filter] suppressed: classes={suppressed_classes} functions={suppressed_fns} enums={suppressed_enums}", file=sys.stderr)

        AttributeProcessor(input_config.attributes).apply(module)

        pipeline = build_pipeline_from_config(effective_transforms)
        if trace_stream:
            for stage in pipeline.stages:
                stage_info = {k: v for k, v in vars(stage).items() if not k.startswith("_")}
                trace_stream.write(f"[TRACE] {stage.__class__.__name__}: {stage_info}\n")
        pipeline.run(module)
        if trace_stream:
            for desc in pipeline.unmatched_stages():
                trace_stream.write(f"[WARN] unmatched transform: {desc}\n")

        all_modules.append(module)
        if entry.generation:
            all_includes.extend(entry.generation.includes)

    return merge_tir_modules(all_modules), all_includes


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    extra_dirs = [Path(d) for d in args.formats_dir]

    # --list-formats needs no other arguments
    if args.list_formats:
        for fmt in sorted(list_builtin_formats(extra_dirs=extra_dirs)):
            print(fmt)
        return

    # --validate-config
    if args.validate_config:
        _validate_config_action(args, extra_dirs)
        return

    # Normal operation requires --input and at least one --target
    if not args.input:
        parser.error("--input is required")
    if not args.target:
        parser.error("--target is required (e.g. --target luabridge3 bindings.cpp)")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"tsujikiri: error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    input_config = load_input_config(input_path)

    module_name = input_path.stem.replace(".input", "")

    source_entries = input_config.get_source_entries()
    if not source_entries:
        print("tsujikiri: error: no source defined (add 'source:' or 'sources:' to input YAML)", file=sys.stderr)
        sys.exit(1)

    trace_stream: Optional[IO] = sys.stderr if args.trace_transforms else None

    # Load the first target's output config for manifest computation and dry-run.
    first_fmt, _ = args.target[0]
    first_fmt_path = resolve_format_path(first_fmt, extra_dirs=extra_dirs)
    first_output_config = apply_format_inheritance(load_output_config(first_fmt_path), extra_dirs=extra_dirs)

    merged, all_includes = _process_sources(
        input_config, source_entries, first_output_config, module_name, args.classname, trace_stream,
        verbose=args.verbose,
    )

    # --- Inject declared functions from typesystem ---
    for fn_decl in input_config.typesystem.declared_functions:
        params = [
            TIRParameter(name=p["name"], type_spelling=p.get("type", ""))
            for p in fn_decl.parameters
        ]
        qualified = f"{fn_decl.namespace}::{fn_decl.name}" if fn_decl.namespace else fn_decl.name
        merged.functions.append(TIRFunction(  # type: ignore[arg-type]
            name=fn_decl.name,
            qualified_name=qualified,
            namespace=fn_decl.namespace,
            return_type=fn_decl.return_type,
            parameters=params,
            wrapper_code=fn_decl.wrapper_code,
            doc=fn_decl.doc,
        ))

    # --- Manifest: compute, compare, and optionally embed version ---
    manifest = compute_manifest(merged)
    has_breaking = False

    if args.manifest_file:
        manifest_path = Path(args.manifest_file)
        if manifest_path.exists():
            old_manifest = load_manifest(manifest_path)
            report = compare_manifests(old_manifest, manifest)
            if report.additive_changes:
                print("WARNING: Additive API changes:", file=sys.stderr)
                for ch in report.additive_changes:
                    print(f"  + {ch}", file=sys.stderr)
            if report.breaking_changes:
                print("ERROR: Breaking API changes detected:", file=sys.stderr)
                for ch in report.breaking_changes:
                    print(f"  ! {ch}", file=sys.stderr)
                if args.check_compat:
                    has_breaking = True
            new_version = suggest_version_bump(old_manifest, report)
            if new_version is not None:
                manifest["version"] = new_version
                old_version = old_manifest["version"]
                if new_version != old_version:
                    print(f"INFO: Suggested version bump: {old_version} -> {new_version}", file=sys.stderr)

    base_gen = input_config.generation

    # --- dry-run ---
    if args.dry_run:
        emitted_classes = [c.name for c in merged.classes if c.emit]
        emitted_functions = [f.name for f in merged.functions if f.emit]
        emitted_enums = [e.name for e in merged.enums if e.emit]
        print(f"Format  : {first_output_config.format_name} {first_output_config.format_version}")
        print(f"Sources : {len(source_entries)}")
        print(f"Classes : {len(emitted_classes)} — {', '.join(emitted_classes) or '(none)'}")
        print(f"Functions: {len(emitted_functions)} — {', '.join(emitted_functions) or '(none)'}")
        print(f"Enums   : {len(emitted_enums)} — {', '.join(emitted_enums) or '(none)'}")
        print(f"Version : {manifest['version']}")
        return

    # --- dump-ir ---
    if args.dump_ir is not None:
        ir_dict = _ir_to_dict(merged)
        ir_json = json.dumps(ir_dict, indent=2, default=str)
        if args.dump_ir == "-":
            sys.stdout.write(ir_json + "\n")
        else:
            Path(args.dump_ir).write_text(ir_json + "\n", encoding="utf-8")
            print(f"IR written to {args.dump_ir}", file=sys.stderr)

    # --- Generate for each target ---
    for target_idx, (fmt, outfile) in enumerate(args.target):
        # For the first target we already processed sources above.
        # For subsequent targets, re-process with format-specific overrides.
        if target_idx == 0:
            output_config = first_output_config
            target_merged = merged
            target_includes = all_includes
        else:
            fmt_path = resolve_format_path(fmt, extra_dirs=extra_dirs)
            output_config = apply_format_inheritance(load_output_config(fmt_path), extra_dirs=extra_dirs)
            target_merged, target_includes = _process_sources(
                input_config, source_entries, output_config, module_name, args.classname, trace_stream,
                verbose=args.verbose,
            )

        fmt_override = input_config.format_overrides.get(output_config.format_name)
        template_extends = fmt_override.template_extends if fmt_override else ""
        extra_unsupported = fmt_override.unsupported_types if fmt_override else []
        fmt_generation = fmt_override.generation if fmt_override else None

        if fmt_generation:
            effective_gen_includes = list(target_includes) + list(fmt_generation.includes)
            prefix = fmt_generation.prefix or base_gen.prefix
            postfix = fmt_generation.postfix or base_gen.postfix
            ev = fmt_generation.embed_version or base_gen.embed_version
        else:
            effective_gen_includes = list(target_includes)
            prefix = base_gen.prefix
            postfix = base_gen.postfix
            ev = base_gen.embed_version

        target_api_version = args.api_version or (manifest["version"] if (args.embed_version or ev) else "")

        effective_generation = GenerationConfig(
            includes=effective_gen_includes, prefix=prefix, postfix=postfix, embed_version=ev,
        )

        gen = Generator(
            output_config,
            generation=effective_generation,
            extra_unsupported_types=extra_unsupported,
            template_extends=template_extends,
            typesystem=input_config.typesystem,
            extra_dirs=extra_dirs,
            custom_data=input_config.custom_data,
        )

        buf = StringIO()
        gen.generate(target_merged, buf, api_version=target_api_version)
        content = buf.getvalue()

        if input_config.pretty:
            content = pretty(content, output_config.language, input_config.pretty_options)

        if outfile == "-":
            sys.stdout.write(content)
        else:
            out_path = Path(outfile)
            out_path.write_text(content, encoding="utf-8")
            print(f"Written to {out_path}", file=sys.stderr)

    # Write manifest only when there are no breaking changes (or compat check is off).
    if args.manifest_file and not has_breaking:
        manifest_path = Path(args.manifest_file)
        save_manifest(manifest, manifest_path)
        print(f"Written to {manifest_path}", file=sys.stderr)

    if has_breaking:
        sys.exit(1)
