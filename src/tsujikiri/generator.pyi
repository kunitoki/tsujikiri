import io
import jinja2
from _typeshed import Incomplete
from pathlib import Path
from tsujikiri.configurations import GenerationConfig as GenerationConfig, OutputConfig as OutputConfig, TypesystemConfig as TypesystemConfig, load_output_config as load_output_config
from tsujikiri.generator_filters import camel_to_snake as camel_to_snake, code_at as code_at, param_pairs as param_pairs, snake_to_camel as snake_to_camel
from tsujikiri.ir import IRClass as IRClass, IREnum as IREnum, IRFunction as IRFunction, IRMethod as IRMethod, IRModule as IRModule
from typing import Any

class ItemFirstEnvironment(jinja2.Environment):
    def getattr(self, obj: object, attribute: str) -> Any: ...

class Generator:
    cfg: Incomplete
    generation: Incomplete
    extra_unsupported: list[str]
    template_extends: str
    extra_dirs: list[Path]
    def __init__(self, output_config: OutputConfig, generation: GenerationConfig | None = None, extra_unsupported_types: list[str] | None = None, template_extends: str | None = None, typesystem: TypesystemConfig | None = None, extra_dirs: list[Path] | None = None) -> None: ...
    def generate(self, module: IRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
    def generate_from_template(self, module: IRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
