import io
import jinja2
from _typeshed import Incomplete
from jinja2.bccache import Bucket
from pathlib import Path
from tsujikiri.configurations import GenerationConfig as GenerationConfig, OutputConfig as OutputConfig, load_output_config as load_output_config
from tsujikiri.generator_filters import camel_to_snake as camel_to_snake, code_at as code_at, param_name as param_name, param_pairs as param_pairs, snake_to_camel as snake_to_camel
from tsujikiri.tir import TIRClass as TIRClass, TIREnum as TIREnum, TIRFunction as TIRFunction, TIRMethod as TIRMethod, TIRModule as TIRModule, trailing_defaulted_count as trailing_defaulted_count
from tsujikiri.typesystem import TypesystemConfig as TypesystemConfig
from typing import Any

class ItemFirstEnvironment(jinja2.Environment):
    def getattr(self, obj: object, attribute: str) -> Any: ...

class _SourceKeyedBytecodeCache(jinja2.BytecodeCache):
    def __init__(self) -> None: ...
    def get_bucket(self, environment: jinja2.Environment, name: str, filename: str | None, source: str) -> Bucket: ...
    def load_bytecode(self, bucket: Bucket) -> None: ...
    def dump_bytecode(self, bucket: Bucket) -> None: ...

class TemplateCache:
    bytecode_cache: jinja2.BytecodeCache
    def __init__(self) -> None: ...
    def format_templates(self, extra_dirs: list[Path]) -> dict[str, str]: ...

class Generator:
    cfg: Incomplete
    generation: Incomplete
    extra_unsupported: list[str]
    template_extends: str
    extra_dirs: list[Path]
    custom_data: dict[str, Any]
    template_cache: TemplateCache
    def __init__(self, output_config: OutputConfig, generation: GenerationConfig | None = None, extra_unsupported_types: list[str] | None = None, template_extends: str | None = None, typesystem: TypesystemConfig | None = None, extra_dirs: list[Path] | None = None, custom_data: dict[str, Any] | None = None, template_cache: TemplateCache | None = None) -> None: ...
    def generate(self, module: TIRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
    def generate_from_template(self, module: TIRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
