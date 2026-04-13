"""FilterEngine — applies InputConfig.filters to a fully built IRModule.

Filtering works by setting emit=False on suppressed IR nodes.
No nodes are removed from the lists; the generator skips emit=False nodes.
This means transforms can still re-enable nodes after filtering if needed.
"""

from __future__ import annotations

import fnmatch
import re
from typing import List

from tsujikiri.configurations import FilterConfig, FilterPattern
from tsujikiri.ir import IRClass, IRModule


def _matches(name: str, patterns: List[FilterPattern]) -> bool:
    """Return True if `name` matches any pattern in the list."""
    for p in patterns:
        if p.is_regex:
            if re.fullmatch(p.pattern, name):
                return True
        else:
            if p.pattern == name:
                return True
    return False


def _matches_glob(path: str, globs: List[str]) -> bool:
    """Return True if `path` matches any glob pattern."""
    for g in globs:
        if fnmatch.fnmatch(path, g):
            return True
    return False


class FilterEngine:
    def __init__(self, filter_config: FilterConfig) -> None:
        self.cfg = filter_config

    def apply(self, module: IRModule) -> None:
        """Mutate module in place, setting emit=False on filtered nodes."""
        self._filter_classes(module)
        self._filter_functions(module)
        self._filter_enums(module.enums, self.cfg.enums.whitelist, self.cfg.enums.blacklist)

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _filter_classes(self, module: IRModule) -> None:
        for ir_class in module.classes:
            if not ir_class.emit:
                continue
            self._filter_class(ir_class)

    def _filter_class(self, ir_class: IRClass) -> None:
        name = ir_class.name
        cfg = self.cfg

        # Source file exclusion
        if ir_class.source_file and _matches_glob(ir_class.source_file, cfg.sources.exclude_patterns):
            ir_class.emit = False
            return

        # Class internal (silent suppression — treated same as blacklist here)
        if _matches(name, cfg.classes.internal):
            ir_class.emit = False
            return

        # Class blacklist
        if _matches(name, cfg.classes.blacklist):
            ir_class.emit = False
            return

        # Class whitelist (non-empty = only these classes are emitted)
        if cfg.classes.whitelist and not _matches(name, cfg.classes.whitelist):
            ir_class.emit = False
            return

        # Methods
        self._filter_methods(ir_class)

        # Constructors
        self._filter_constructors(ir_class)

        # Fields
        self._filter_fields(ir_class)

        # Nested enums
        self._filter_enums(ir_class.enums, [], [])  # no enum-level config yet per-class

        # Inner classes (recursive)
        for inner in ir_class.inner_classes:
            self._filter_class(inner)

    def _filter_methods(self, ir_class: IRClass) -> None:
        per_class = self.cfg.methods.per_class.get(ir_class.name, [])
        for method in ir_class.methods:
            if not method.emit:
                continue
            # Auto-suppress variadic (varargs) methods — no Python dunder equivalent
            if method.is_varargs:
                method.emit = False
                continue
            # Operator suppression is done via config (global_blacklist or per-class pattern)
            # Global blacklist
            if _matches(method.name, self.cfg.methods.global_blacklist):
                method.emit = False
                continue
            # Per-class blacklist
            if _matches(method.name, per_class):
                method.emit = False

    def _filter_constructors(self, ir_class: IRClass) -> None:
        cfg = self.cfg.constructors
        if not cfg.include:
            for ctor in ir_class.constructors:
                ctor.emit = False
            return

        if cfg.signatures:
            for ctor in ir_class.constructors:
                # Match by comma-joined parameter types
                sig = ", ".join(p.type_spelling for p in ctor.parameters)
                if not _matches(sig, cfg.signatures):
                    ctor.emit = False

    def _filter_fields(self, ir_class: IRClass) -> None:
        per_class = self.cfg.fields.per_class.get(ir_class.name, [])
        for f in ir_class.fields:
            if not f.emit:
                continue
            if _matches(f.name, self.cfg.fields.global_blacklist):
                f.emit = False
                continue
            if _matches(f.name, per_class):
                f.emit = False

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _filter_functions(self, module: IRModule) -> None:
        cfg = self.cfg.functions
        whitelist = cfg.whitelist
        blacklist = cfg.blacklist
        for fn in module.functions:
            if not fn.emit:
                continue
            # Auto-suppress variadic (varargs) functions
            if fn.is_varargs:
                fn.emit = False
                continue
            if _matches(fn.name, blacklist):
                fn.emit = False
                continue
            if whitelist and not _matches(fn.name, whitelist):
                fn.emit = False

    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------

    def _filter_enums(self, enums, whitelist, blacklist) -> None:
        for enum in enums:
            if not enum.emit:
                continue
            if _matches(enum.name, blacklist):
                enum.emit = False
                continue
            if whitelist and not _matches(enum.name, whitelist):
                enum.emit = False
