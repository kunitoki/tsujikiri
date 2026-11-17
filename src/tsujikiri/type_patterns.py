"""Generic (placeholder-based) type mappings for output formats.

A ``type_mappings`` key containing ``{Name}`` or ``{Name...}`` placeholders is a
generic pattern rather than an exact type spelling::

    type_mappings:
      "std::optional<{T}>": "{T}?"
      "std::map<{K}, {V}>": "table<{K}, {V}>"
      "std::variant<{T...}>": "{T... | }"

``{Name}`` captures exactly one bracket-balanced template argument; ``{Name...}``
captures one or more comma-separated arguments.  In the value, ``{Name}``
substitutes the mapped capture and ``{Name...SEP}`` joins variadic captures with
``SEP`` (``", "`` when omitted).  Captured arguments are mapped recursively by
the caller, so nested generics compose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

_KEY_PLACEHOLDER_RE = re.compile(r"\{(\w+)(\.\.\.)?\}")
_VALUE_PLACEHOLDER_RE = re.compile(r"\{(\w+)(?:\.\.\.([^{}]*))?\}")
_OPENERS = "<([{"
_CLOSERS = ">)]}"
_PUNCTUATION = "<>,()[]&*"
_DEFAULT_SEPARATOR = ", "

Capture = Union[str, List[str]]


def is_generic_key(key: str) -> bool:
    """Return ``True`` if a ``type_mappings`` key contains a placeholder."""
    return _KEY_PLACEHOLDER_RE.search(key) is not None


def _literal_regex(literal: str) -> "re.Pattern[str]":
    """Compile a literal key segment, tolerating whitespace differences around punctuation."""
    parts: List[str] = []
    for ch in literal:
        if ch.isspace():
            parts.append(r"\s*")
        elif ch in _PUNCTUATION:
            parts.append(r"\s*" + re.escape(ch) + r"\s*")
        else:
            parts.append(re.escape(ch))
    return re.compile(re.sub(r"(?:\\s\*)+", r"\\s*", "".join(parts)))


def _is_balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def split_top_level(text: str) -> List[str]:
    """Split *text* on commas that are not nested inside brackets."""
    pieces: List[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS:
            depth -= 1
        elif ch == "," and depth == 0:
            pieces.append(text[start:i])
            start = i + 1
    pieces.append(text[start:])
    return [p.strip() for p in pieces]


@dataclass
class _Literal:
    regex: "re.Pattern[str]"


@dataclass
class _Placeholder:
    name: str
    variadic: bool


PatternToken = Union[_Literal, _Placeholder]


@dataclass
class TypePattern:
    """A compiled generic ``type_mappings`` entry."""

    key: str
    value: str
    tokens: List[PatternToken]
    literal_length: int

    def match(self, spelling: str) -> Optional[Dict[str, Capture]]:
        """Return placeholder captures if *spelling* matches the whole pattern."""
        return self._match(spelling.strip(), 0, 0, {})

    def _match(self, text: str, ti: int, pos: int, captures: Dict[str, Capture]) -> Optional[Dict[str, Capture]]:
        if ti == len(self.tokens):
            return captures if pos == len(text) else None
        token = self.tokens[ti]
        if isinstance(token, _Literal):
            m = token.regex.match(text, pos)
            if m is None:
                return None
            return self._match(text, ti + 1, m.end(), captures)
        if ti + 1 == len(self.tokens):
            return self._bind(token, text[pos:], captures)
        follow = self.tokens[ti + 1]
        assert isinstance(follow, _Literal)
        start = pos
        while True:
            m = follow.regex.search(text, start)
            if m is None:
                return None
            bound = self._bind(token, text[pos : m.start()], captures)
            if bound is not None:
                result = self._match(text, ti + 2, m.end(), bound)
                if result is not None:
                    return result
            start = m.start() + 1

    @staticmethod
    def _bind(token: _Placeholder, raw: str, captures: Dict[str, Capture]) -> Optional[Dict[str, Capture]]:
        if not _is_balanced(raw):
            return None
        pieces = split_top_level(raw)
        if any(not p for p in pieces):
            return None
        if token.variadic:
            return {**captures, token.name: pieces}
        if len(pieces) != 1:
            return None
        return {**captures, token.name: pieces[0]}

    def render(self, captures: Dict[str, Capture], map_type: Callable[[str], str]) -> str:
        """Substitute mapped captures into the mapping value."""

        def _sub(m: "re.Match[str]") -> str:
            captured = captures[m.group(1)]
            if isinstance(captured, list):
                separator = m.group(2) if m.group(2) else _DEFAULT_SEPARATOR
                return separator.join(map_type(c) for c in captured)
            return map_type(captured)

        return _VALUE_PLACEHOLDER_RE.sub(_sub, self.value)


def compile_type_pattern(key: str, value: str) -> TypePattern:
    """Compile one generic mapping, raising ``ValueError`` when it is malformed."""
    tokens: List[PatternToken] = []
    names: Dict[str, bool] = {}
    literal_length = 0
    pos = 0
    for m in _KEY_PLACEHOLDER_RE.finditer(key):
        literal = key[pos : m.start()]
        if literal:
            tokens.append(_Literal(_literal_regex(literal)))
            literal_length += len(literal.strip())
        elif tokens:
            raise ValueError(f"type mapping '{key}': placeholders must be separated by literal text")
        name, variadic = m.group(1), bool(m.group(2))
        if name in names:
            raise ValueError(f"type mapping '{key}': placeholder '{{{name}}}' is used more than once")
        if variadic and any(names.values()):
            raise ValueError(f"type mapping '{key}': only one variadic placeholder is allowed")
        names[name] = variadic
        tokens.append(_Placeholder(name=name, variadic=variadic))
        pos = m.end()
    tail = key[pos:]
    if tail:
        tokens.append(_Literal(_literal_regex(tail)))
        literal_length += len(tail.strip())
    if literal_length == 0:
        raise ValueError(f"type mapping '{key}': a generic key needs literal text besides placeholders")
    for vm in _VALUE_PLACEHOLDER_RE.finditer(value):
        name = vm.group(1)
        if name not in names:
            raise ValueError(f"type mapping '{key}': value placeholder '{{{name}}}' does not appear in the key")
        if vm.group(2) is not None and not names[name]:
            raise ValueError(
                f"type mapping '{key}': '{{{name}...}}' used in the value but '{{{name}}}' is not variadic"
            )
    return TypePattern(key=key, value=value, tokens=tokens, literal_length=literal_length)


def compile_type_patterns(mappings: Dict[str, str]) -> List[TypePattern]:
    """Compile every generic entry of *mappings*, most specific (longest literal text) first."""
    indexed: List[Tuple[int, TypePattern]] = [
        (i, compile_type_pattern(k, v)) for i, (k, v) in enumerate(mappings.items()) if is_generic_key(k)
    ]
    indexed.sort(key=lambda item: (-item[1].literal_length, item[0]))
    return [p for _, p in indexed]
