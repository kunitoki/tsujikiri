"""Apply C++ attribute annotations to IR nodes.

Runs after FilterEngine (so attributes can override config-based filter
decisions) and before the transform pipeline (so transforms can still
override attribute decisions).

Built-in attribute handlers (always active):
  ``[[tsujikiri::skip]]``              — set emit=False
  ``[[tsujikiri::keep]]``              — set emit=True (re-enable suppressed node)
  ``[[tsujikiri::rename("newName")]]`` — set rename field to first string argument

Custom handlers are configured in ``input.yml`` under ``attributes.handlers``
and map attribute names to the same three actions:

  attributes:
    handlers:
      "mygame::no_export": skip
      "mygame::force_export": keep
      "mygame::bind_as": rename
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from tsujikiri.configurations import AttributeHandlerConfig
from tsujikiri.ir import IRClass, IRModule


_BUILTIN_HANDLERS: Dict[str, str] = {
    "tsujikiri::skip": "skip",
    "tsujikiri::keep": "keep",
    "tsujikiri::rename": "rename",
}


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


def _apply_attrs(node: Any, handlers: Dict[str, str]) -> None:
    """Apply handler actions to a single IR node based on its attributes list."""
    for raw_attr in getattr(node, "attributes", []):
        attr_name, args = _parse_attribute(raw_attr)
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

    def apply(self, module: IRModule) -> None:
        for cls in module.classes:
            self._process_class(cls)
        for fn in module.functions:
            _apply_attrs(fn, self.handlers)
        for enum in module.enums:
            _apply_attrs(enum, self.handlers)
            for val in enum.values:
                _apply_attrs(val, self.handlers)

    def _process_class(self, cls: IRClass) -> None:
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
