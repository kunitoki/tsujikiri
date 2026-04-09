"""Command-line interface for tsujikiri."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tsujikiri.configurations import GenerationConfig, load_input_config, load_output_config
from tsujikiri.filters import FilterEngine
from tsujikiri.formats import resolve_format_path
from tsujikiri.generator import Generator
from tsujikiri.ir import merge_modules
from tsujikiri.parser import parse_translation_unit
from tsujikiri.transforms import build_pipeline_from_config


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
        "--output", "-o",
        required=False,
        metavar="FORMAT_OR_FILE",
        help="Output format: built-in name (luabridge3) or path to .output.yml",
    )
    p.add_argument(
        "--output-file", "-O",
        default=None,
        metavar="FILE",
        help="Write generated code to FILE instead of stdout",
    )
    p.add_argument(
        "--classname", "-c",
        default=None,
        metavar="CLASS",
        help="Generate bindings for a single class only",
    )
    p.add_argument(
        "--formats-dir", "-F",
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
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    extra_dirs = [Path(d) for d in args.formats_dir]

    # --list-formats needs no other arguments
    if args.list_formats:
        from tsujikiri.formats import list_builtin_formats
        for fmt in sorted(list_builtin_formats(extra_dirs=extra_dirs)):
            print(fmt)
        return

    # Normal operation requires --input and --output
    if not args.input:
        parser.error("--input is required")
    if not args.output:
        parser.error("--output is required")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"tsujikiri: error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    input_config = load_input_config(input_path)

    output_format_path = resolve_format_path(args.output, extra_dirs=extra_dirs)
    output_config = load_output_config(output_format_path)

    module_name = input_path.stem.replace(".input", "")

    # --- Collect format overrides for the chosen format ---
    fmt_override = input_config.format_overrides.get(output_config.format_name)
    template_overrides = fmt_override.templates if fmt_override else {}
    extra_unsupported = fmt_override.unsupported_types if fmt_override else []
    fmt_filters = fmt_override.filters if fmt_override else None
    fmt_transforms = fmt_override.transforms if fmt_override else None
    fmt_generation = fmt_override.generation if fmt_override else None
    # Pre-compute once; appended to per-source transforms in the loop below.
    fmt_transforms_list: list = list(fmt_transforms) if fmt_transforms else []

    # --- Process each source entry ---
    source_entries = input_config.get_source_entries()
    if not source_entries:
        print("tsujikiri: error: no source defined (add 'source:' or 'sources:' to input YAML)", file=sys.stderr)
        sys.exit(1)

    all_modules = []
    all_includes: list[str] = list(input_config.generation.includes)

    for entry in source_entries:
        # Per-source overrides take precedence over top-level; per-format overrides
        # take precedence over both (highest priority filter).
        effective_filters = entry.filters if entry.filters is not None else input_config.filters
        if fmt_filters is not None:
            effective_filters = fmt_filters

        effective_transforms = entry.transforms if entry.transforms is not None else input_config.transforms
        if fmt_transforms_list:
            effective_transforms = list(effective_transforms) + fmt_transforms_list

        module = parse_translation_unit(
            entry.source,
            effective_filters.namespaces,
            module_name,
        )

        # CLI --classname filter (additive to config filters)
        if args.classname:
            for ir_class in module.classes:
                if ir_class.name != args.classname:
                    ir_class.emit = False

        FilterEngine(effective_filters).apply(module)
        build_pipeline_from_config(effective_transforms).run(module)

        all_modules.append(module)

        if entry.generation:
            all_includes.extend(entry.generation.includes)

    merged = merge_modules(all_modules)

    # Format-specific generation: includes are additive; prefix/postfix replace
    # the top-level values when non-empty.
    base_gen = input_config.generation
    if fmt_generation:
        all_includes.extend(fmt_generation.includes)
        prefix = fmt_generation.prefix or base_gen.prefix
        postfix = fmt_generation.postfix or base_gen.postfix
    else:
        prefix = base_gen.prefix
        postfix = base_gen.postfix
    effective_generation = GenerationConfig(includes=all_includes, prefix=prefix, postfix=postfix)

    if args.dry_run:
        emitted_classes = [c.name for c in merged.classes if c.emit]
        emitted_functions = [f.name for f in merged.functions if f.emit]
        emitted_enums = [e.name for e in merged.enums if e.emit]
        print(f"Format  : {output_config.format_name} {output_config.format_version}")
        print(f"Sources : {len(source_entries)}")
        print(f"Classes : {len(emitted_classes)} — {', '.join(emitted_classes) or '(none)'}")
        print(f"Functions: {len(emitted_functions)} — {', '.join(emitted_functions) or '(none)'}")
        print(f"Enums   : {len(emitted_enums)} — {', '.join(emitted_enums) or '(none)'}")
        return

    gen = Generator(
        output_config,
        generation=effective_generation,
        template_overrides=template_overrides,
        extra_unsupported_types=extra_unsupported,
    )

    if args.output_file:
        out_path = Path(args.output_file)
        with open(out_path, "w", encoding="utf-8") as out:
            gen.generate(merged, out)
        print(f"Written to {out_path}", file=sys.stderr)
    else:
        gen.generate(merged, sys.stdout)
