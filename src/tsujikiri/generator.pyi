import io
import jinja2
from _typeshed import Incomplete
from tsujikiri.configurations import GenerationConfig as GenerationConfig, OutputConfig as OutputConfig
from tsujikiri.generator_filters import camel_to_snake as camel_to_snake, code_at as code_at, param_pairs as param_pairs
from tsujikiri.ir import IRClass as IRClass, IREnum as IREnum, IRFunction as IRFunction, IRMethod as IRMethod, IRModule as IRModule
from typing import Any

class ItemFirstEnvironment(jinja2.Environment):
    def getattr(self, obj: object, attribute: str) -> Any: ...

class Generator:
    cfg: Incomplete
    generation: Incomplete
    extra_unsupported: list[str]
    template_extends: str
    def __init__(self, output_config: OutputConfig, generation: GenerationConfig | None = None, extra_unsupported_types: list[str] | None = None, template_extends: str | None = None) -> None: ...
    def generate(self, module: IRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
    def generate_from_template(self, module: IRModule, out: io.TextIOBase, api_version: str = '') -> None: ...
