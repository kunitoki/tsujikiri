import re
from _typeshed import Incomplete
from dataclasses import dataclass
from typing import Callable

Capture = str | list[str]

def is_generic_key(key: str) -> bool: ...
def split_top_level(text: str) -> list[str]: ...

@dataclass
class _Literal:
    regex: re.Pattern[str]

@dataclass
class _Placeholder:
    name: str
    variadic: bool

PatternToken: Incomplete

@dataclass
class TypePattern:
    key: str
    value: str
    tokens: list[PatternToken]
    literal_length: int
    def match(self, spelling: str) -> dict[str, Capture] | None: ...
    def render(self, captures: dict[str, Capture], map_type: Callable[[str], str]) -> str: ...

def compile_type_pattern(key: str, value: str) -> TypePattern: ...
def compile_type_patterns(mappings: dict[str, str]) -> list[TypePattern]: ...
