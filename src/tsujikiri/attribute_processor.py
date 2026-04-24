"""Apply C++ attribute annotations to IR nodes.

Runs after FilterEngine (so attributes can override config-based filter
decisions) and before the transform pipeline (so transforms can still
override attribute decisions).

Built-in attribute handlers (always active):
  ``[[tsujikiri::skip]]``                          — set emit=False
  ``[[tsujikiri::keep]]``                          — set emit=True (re-enable suppressed node)
  ``[[tsujikiri::rename("newName")]]``             — set rename field to first string argument
  ``[[tsujikiri::readonly]]``                      — set read_only=True on IRField
  ``[[tsujikiri::thread_safe]]``                   — set allow_thread=True on IRMethod/IRFunction
  ``[[tsujikiri::doc("text")]]``                   — set doc field on any node
  ``[[tsujikiri::rename_argument("old", "new")]]`` — rename a parameter by name
  ``[[tsujikiri::type_map("CppType", "Target")]]`` — override type of matching params/return/field

Custom handlers are configured in ``input.yml`` under ``attributes.handlers``
and map attribute names to the same three simple actions:

  attributes:
    handlers:
      "mygame::no_export": skip
      "mygame::force_export": keep
      "mygame::bind_as": rename
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from tsujikiri.configurations import AttributeHandlerConfig
from tsujikiri.tir import TIRClass, TIRModule


_BUILTIN_HANDLERS: Dict[str, str] = {
    "tsujikiri::skip": "skip",
    "tsujikiri::keep": "keep",
    "tsujikiri::rename": "rename",
}

# Built-in attribute names that require special (non-action-string) handling.
_COMPLEX_BUILTINS = frozenset(
    {
        "tsujikiri::readonly",
        "tsujikiri::thread_safe",
        "tsujikiri::doc",
        "tsujikiri::rename_argument",
        "tsujikiri::type_map",
        "tsujikiri::arithmetic",
        "tsujikiri::hashable",
    }
)


def _parse_attribute(attr: str) -> Tuple[str, List[str]]:
    """Parse ``'ns::name("arg1", "arg2")'`` into ``('ns::name', ['arg1', 'arg2'])``.

    The attribute name is everything before the first ``(``.  Arguments are
    the double-quoted strings found inside the parentheses.
    """
    m = re.match(r"^([^(]+)(?:\((.*)\))?$", attr.strip())
    if not m:
        return attr.strip(), []
    name = m.group(1).strip()
    args_str = m.group(2)
    args = re.findall(r'"([^"]*)"', args_str) if args_str else []
    return name, args


def _apply_complex_builtin(attr_name: str, args: List[str], node: Any) -> None:
    """Apply one of the complex built-in attribute handlers to *node*."""
    if attr_name == "tsujikiri::readonly":
        if hasattr(node, "read_only"):
            node.read_only = True
    elif attr_name == "tsujikiri::thread_safe":
        if hasattr(node, "allow_thread"):
            node.allow_thread = True
    elif attr_name == "tsujikiri::doc" and args:
        if hasattr(node, "doc"):
            node.doc = args[0]
    elif attr_name == "tsujikiri::rename_argument" and len(args) == 2:
        old_name, new_name = args
        for p in getattr(node, "parameters", []):
            if p.name == old_name:
                p.rename = new_name
    elif attr_name == "tsujikiri::type_map" and len(args) == 2:
        src_type, tgt_type = args
        for p in getattr(node, "parameters", []):
            if p.type_spelling == src_type:
                p.type_override = tgt_type
        if getattr(node, "return_type", None) == src_type and hasattr(node, "return_type_override"):
            node.return_type_override = tgt_type
        if getattr(node, "type_spelling", None) == src_type and hasattr(node, "type_override"):
            node.type_override = tgt_type
    elif attr_name == "tsujikiri::arithmetic":
        if hasattr(node, "is_arithmetic"):
            node.is_arithmetic = True
    elif attr_name == "tsujikiri::hashable":
        if hasattr(node, "generate_hash"):
            node.generate_hash = True


def _apply_attrs(node: Any, handlers: Dict[str, str]) -> None:
    """Apply handler actions to a single IR node based on its attributes list."""
    for raw_attr in getattr(node, "attributes", []):
        attr_name, args = _parse_attribute(raw_attr)
        if attr_name in _COMPLEX_BUILTINS:
            _apply_complex_builtin(attr_name, args, node)
        else:
            action = handlers.get(attr_name)
            if action == "skip":
                node.emit = False
            elif action == "keep":
                node.emit = True
            elif action == "rename" and args:
                node.rename = args[0]


class AttributeProcessor:
    """Walk the IR and apply attribute-based annotations to every node."""

    def __init__(self, config: AttributeHandlerConfig) -> None:
        # Custom handlers extend (and can override) the built-ins.
        self.handlers: Dict[str, str] = {**_BUILTIN_HANDLERS, **config.handlers}

    def apply(self, module: TIRModule) -> None:
        for cls in module.classes:
            self._process_class(cls)
        for fn in module.functions:
            _apply_attrs(fn, self.handlers)
        for enum in module.enums:
            _apply_attrs(enum, self.handlers)
            for val in enum.values:
                _apply_attrs(val, self.handlers)

    def _process_class(self, cls: TIRClass) -> None:
        _apply_attrs(cls, self.handlers)
        for method in cls.methods:
            _apply_attrs(method, self.handlers)
        for ctor in cls.constructors:
            _apply_attrs(ctor, self.handlers)
        for field in cls.fields:
            _apply_attrs(field, self.handlers)
        for enum in cls.enums:
            _apply_attrs(enum, self.handlers)
            for val in enum.values:
                _apply_attrs(val, self.handlers)
        for inner in cls.inner_classes:
            self._process_class(inner)
