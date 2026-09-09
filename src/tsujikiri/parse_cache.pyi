from dataclasses import dataclass, field
from tsujikiri.configurations import SourceConfig as SourceConfig
from tsujikiri.ir import IRModule as IRModule
from tsujikiri.parser import parse_translation_unit_ir as parse_translation_unit_ir
from typing import Sequence

@dataclass(frozen=True)
class ParseKey:
    path: str
    parse_args: tuple[str, ...]
    include_paths: tuple[str, ...]
    system_include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    namespaces: tuple[str, ...]
    module_name: str
    @classmethod
    def from_source(cls, source: SourceConfig, namespaces: Sequence[str], module_name: str) -> ParseKey: ...
    def to_source(self) -> SourceConfig: ...

@dataclass
class ParseResult:
    module: IRModule
    clang_errors: list[str] = field(default_factory=list)
    stderr_text: str = ...

def parse_worker(key: ParseKey, verbose: bool) -> ParseResult: ...

class ParseCache:
    hits: int
    misses: int
    def __init__(self, verbose: bool = False, jobs: int = 1) -> None: ...
    def get(self, key: ParseKey, clang_errors: list[str] | None = None) -> IRModule: ...
    def prefetch(self, keys: Sequence[ParseKey], clang_errors: list[str] | None = None) -> None: ...
