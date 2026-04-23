import argparse
from tsujikiri.attribute_processor import AttributeProcessor as AttributeProcessor
from tsujikiri.configurations import (
    FormatOverrideConfig as FormatOverrideConfig,
    GenerationConfig as GenerationConfig,
    InputConfig as InputConfig,
    load_input_config as load_input_config,
    load_output_config as load_output_config,
)
from tsujikiri.filters import FilterEngine as FilterEngine
from tsujikiri.formats import (
    apply_format_inheritance as apply_format_inheritance,
    list_builtin_formats as list_builtin_formats,
    resolve_format_path as resolve_format_path,
)
from tsujikiri.generator import Generator as Generator
from tsujikiri.manifest import (
    compare_manifests as compare_manifests,
    compute_manifest as compute_manifest,
    load_manifest as load_manifest,
    save_manifest as save_manifest,
    suggest_version_bump as suggest_version_bump,
)
from tsujikiri.parser import parse_translation_unit as parse_translation_unit
from tsujikiri.pretty_printers import pretty as pretty
from tsujikiri.tir import (
    TIRFunction as TIRFunction,
    TIRModule as TIRModule,
    TIRParameter as TIRParameter,
    merge_tir_modules as merge_tir_modules,
    upgrade_module as upgrade_module,
)
from tsujikiri.transforms import build_pipeline_from_config as build_pipeline_from_config

def build_parser() -> argparse.ArgumentParser: ...
def main() -> None: ...
