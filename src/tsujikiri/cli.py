"""Command-line interface for tsujikiri."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tsujikiri.configurations import load_input_config, load_output_config
from tsujikiri.filters import FilterEngine
from tsujikiri.formats import resolve_format_path
from tsujikiri.generator import Generator
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
        help="Output format: built-in name (luabridge3, pybind11, c_api) or path to .output.yml",
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

    # --list-formats needs no other arguments
    if args.list_formats:
        from tsujikiri.formats import list_builtin_formats
        for fmt in sorted(list_builtin_formats()):
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

    output_format_path = resolve_format_path(args.output)
    output_config = load_output_config(output_format_path)

    module_name = input_path.stem.replace(".input", "")
    module = parse_translation_unit(input_config, module_name=module_name)

    # CLI --classname filter (additive to config filters)
    if args.classname:
        for ir_class in module.classes:
            if ir_class.name != args.classname:
                ir_class.emit = False

    FilterEngine(input_config.filters).apply(module)
    build_pipeline_from_config(input_config.transforms).run(module)

    if args.dry_run:
        emitted_classes = [c.name for c in module.classes if c.emit]
        emitted_functions = [f.name for f in module.functions if f.emit]
        emitted_enums = [e.name for e in module.enums if e.emit]
        print(f"Format  : {output_config.format_name} {output_config.format_version}")
        print(f"Source  : {input_config.source.path}")
        print(f"Classes : {len(emitted_classes)} — {', '.join(emitted_classes) or '(none)'}")
        print(f"Functions: {len(emitted_functions)} — {', '.join(emitted_functions) or '(none)'}")
        print(f"Enums   : {len(emitted_enums)} — {', '.join(emitted_enums) or '(none)'}")
        return

    if args.output_file:
        out_path = Path(args.output_file)
        with open(out_path, "w", encoding="utf-8") as out:
            Generator(output_config).generate(module, out)
        print(f"Written to {out_path}", file=sys.stderr)
    else:
        Generator(output_config).generate(module, sys.stdout)
