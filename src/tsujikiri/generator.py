"""Generate binding code from an IRModule using a single Jinja2 template.

Each output format defines a ``template:`` key in its ``.output.yml`` file
containing a full Jinja2 template with named ``{% block %}`` tags.  Users
can extend a built-in format template using standard Jinja2 template
inheritance (``{% extends "luabridge3.tpl" %}``) and override specific
blocks.

The complete IR is serialised into a plain-data context dict before
rendering, so templates iterate over the data themselves rather than
relying on Python-side orchestration.  All Jinja2 filters (``map_type``,
``param_pairs``, ``camel_to_snake``) remain available inside templates.

Unsupported return/field types (as listed in OutputConfig.unsupported_types
plus any extra list) are excluded from the context entirely — the template
never sees them.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import jinja2
import jinja2.sandbox

from tsujikiri.configurations import GenerationConfig, OutputConfig
from tsujikiri.generator_filters import camel_to_snake, param_pairs
from tsujikiri.ir import (
    IRClass,
    IREnum,
    IRFunction,
    IRMethod,
    IRModule,
)


class _ItemFirstEnvironment(jinja2.Environment):
    """Jinja2 Environment that resolves ``obj.attr`` via item access before
    attribute access.  This ensures that plain-dict context values (e.g.
    ``enum['values']``) take priority over Python built-in dict methods like
    ``dict.values()``, which would otherwise shadow same-named keys."""

    def getattr(self, obj, attribute):  # type: ignore[override]
        try:
            return obj[attribute]
        except (TypeError, LookupError, AttributeError):
            pass
        try:
            return getattr(obj, attribute)
        except AttributeError:
            return self.undefined(obj=obj, name=attribute)


class Generator:
    def __init__(
        self,
        output_config: OutputConfig,
        generation: Optional[GenerationConfig] = None,
        extra_unsupported_types: Optional[List[str]] = None,
        template_extends: Optional[str] = None,
    ) -> None:
        self.cfg = output_config
        self.generation = generation
        self.extra_unsupported: List[str] = extra_unsupported_types or []
        self.template_extends: str = template_extends or ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, module: IRModule, out: io.TextIOBase) -> None:
        self.generate_from_template(module, out)

    # ------------------------------------------------------------------
    # Single-template rendering
    # ------------------------------------------------------------------

    def generate_from_template(self, module: IRModule, out: io.TextIOBase) -> None:
        """Render the format's single Jinja2 template with full IR context."""
        from tsujikiri.configurations import load_output_config
        from tsujikiri.formats import _FORMATS_DIR

        ctx = self._build_ir_context(module)

        # Build a DictLoader with all available format templates so that
        # {% extends "luabridge3.tpl" %} (etc.) resolves correctly.
        dict_templates: Dict[str, str] = {}
        for fmt_file in _FORMATS_DIR.glob("*.output.yml"):
            try:
                cfg = load_output_config(fmt_file)
                if cfg.template:
                    dict_templates[f"{cfg.format_name}.tpl"] = cfg.template
            except Exception:
                pass

        # Register current format as "main.tpl" alias.
        if self.cfg.template:
            dict_templates["main.tpl"] = self.cfg.template
            dict_templates[f"{self.cfg.format_name}.tpl"] = self.cfg.template

        # Register override child template if provided.
        if self.template_extends:
            dict_templates["__override__.tpl"] = self.template_extends

        env = _ItemFirstEnvironment(
            loader=jinja2.DictLoader(dict_templates),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )

        env.filters.update({
            "map_type": self._map_type,
            "param_pairs": param_pairs,
            "camel_to_snake": camel_to_snake,
        })

        if self.generation and self.generation.prefix:
            out.write(self.generation.prefix)

        template_name = "__override__.tpl" if self.template_extends else "main.tpl"
        tmpl = env.get_template(template_name)
        out.write(tmpl.render(ctx))

        if self.generation and self.generation.postfix:
            out.write(self.generation.postfix)

    # ------------------------------------------------------------------
    # IR context building
    # ------------------------------------------------------------------

    def _build_ir_context(self, module: IRModule) -> Dict[str, Any]:
        """Build a plain-data context dict from the IR for template rendering."""
        topo = self._topo_sort(module.classes, module.class_by_name)
        flat_classes: List[Dict[str, Any]] = []
        for cls in topo:
            if cls.emit:
                flat_classes.extend(self._flatten_class_ctx(cls))

        return {
            "module_name": module.name,
            "includes": list(self.generation.includes) if self.generation else [],
            "enums": [self._build_enum_ctx(e) for e in module.enums if e.emit],
            "function_groups": self._build_function_group_ctxs(module.functions),
            "classes": flat_classes,
        }

    def _flatten_class_ctx(self, ir_class: IRClass) -> List[Dict[str, Any]]:
        """Return class ctx followed by inner-class ctxs (recursive, flattened)."""
        result = [self._build_class_ctx(ir_class)]
        for inner in ir_class.inner_classes:
            if inner.emit:
                result.extend(self._flatten_class_ctx(inner))
        return result

    def _build_enum_ctx(self, enum: IREnum) -> Dict[str, Any]:
        return {
            "name": enum.name,
            "qualified_name": enum.qualified_name,
            "values": [
                {"name": v.name, "number": str(v.value)}
                for v in enum.values
                if v.emit
            ],
        }

    def _build_function_group_ctxs(self, functions: List[IRFunction]) -> List[Dict[str, Any]]:
        active = [fn for fn in functions if fn.emit and not self._is_unsupported(fn.return_type)]
        groups: Dict[str, List[IRFunction]] = {}
        order: List[str] = []
        for fn in active:
            key = fn.rename or fn.name
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(fn)

        result = []
        for key in order:
            group = groups[key]
            is_overloaded = len(group) > 1
            fns = []
            for i, fn in enumerate(group):
                is_last = i == len(group) - 1
                fns.append({
                    "name": fn.rename or fn.name,
                    "spelling": fn.qualified_name,
                    "params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in fn.parameters
                    ],
                    "return_type": self._map_type(fn.return_type),
                    "raw_return_type": fn.return_type,
                    "overload_kind": "overload",
                    "overload_separator": "" if is_last else ",",
                    "overload_index": i,
                })
            result.append({
                "name": key,
                "is_overloaded": is_overloaded,
                "functions": fns,
            })
        return result

    def _build_class_ctx(self, ir_class: IRClass) -> Dict[str, Any]:
        name = ir_class.rename or ir_class.name
        base_name = ir_class.bases[0] if ir_class.bases else ""

        # Constructor group
        ctors = [c for c in ir_class.constructors if c.emit]
        ctor_group = {
            "is_overloaded": len(ctors) > 1,
            "constructors": [
                {
                    "params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in ctor.parameters
                    ],
                    "overload_index": i,
                }
                for i, ctor in enumerate(ctors)
            ],
        }

        # Method groups (preserving original order)
        methods = [m for m in ir_class.methods if m.emit and not self._is_unsupported(m.return_type)]
        mgroups: Dict[tuple, List[IRMethod]] = {}
        morder: List[tuple] = []
        for m in methods:
            key = (m.rename or m.name, m.is_static)
            if key not in mgroups:
                mgroups[key] = []
                morder.append(key)
            mgroups[key].append(m)

        method_groups = []
        for key in morder:
            group = mgroups[key]
            group_name, is_static = key
            is_overloaded = len(group) > 1
            method_ctxs = []
            for i, m in enumerate(group):
                is_last = i == len(group) - 1
                method_ctxs.append({
                    "name": group_name,
                    "spelling": m.spelling,
                    "params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in m.parameters
                    ],
                    "return_type": self._map_type(m.return_type),
                    "overload_kind": self._compute_overload_kind(group, m),
                    "overload_separator": "" if is_last else ",",
                    "is_const": m.is_const,
                    "overload_index": i,
                })
            method_groups.append({
                "name": group_name,
                "is_overloaded": is_overloaded,
                "is_static": is_static,
                "methods": method_ctxs,
            })

        # Fields (excluding unsupported types and emit=False)
        fields = [
            {
                "name": f.rename or f.name,
                "type": self._map_type(f.type_spelling),
                "raw_type": f.type_spelling,
                "is_const": f.is_const,
            }
            for f in ir_class.fields
            if f.emit and not self._is_unsupported(f.type_spelling)
        ]

        return {
            "name": name,
            "qualified_name": ir_class.qualified_name,
            "base_name": base_name,
            "base_short_name": base_name.split("::")[-1] if base_name else "",
            "variable_name": ir_class.variable_name,
            "constructor_group": ctor_group,
            "method_groups": method_groups,
            "fields": fields,
            "enums": [self._build_enum_ctx(e) for e in ir_class.enums if e.emit],
        }

    def _compute_overload_kind(self, group: List[IRMethod], method: IRMethod) -> str:
        """Return 'const', 'nonconst', or 'overload' for the cast type of this method."""
        method_args = ", ".join(p.type_spelling for p in method.parameters)
        for other in group:
            if other is method:
                continue
            other_args = ", ".join(p.type_spelling for p in other.parameters)
            if other_args == method_args and other.is_const != method.is_const:
                return "const" if method.is_const else "nonconst"
        return "overload"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _map_type(self, type_spelling: str) -> str:
        """Apply output-format type mappings (e.g. C++ → Lua types)."""
        return self.cfg.type_mappings.get(type_spelling, type_spelling)

    def _is_unsupported(self, type_spelling: str) -> bool:
        """Return True if the type spelling matches any unsupported type."""
        all_unsupported = self.cfg.unsupported_types + self.extra_unsupported
        return any(t in type_spelling for t in all_unsupported)

    def _topo_sort(self, classes: List[IRClass], class_by_name: Dict[str, IRClass]) -> List[IRClass]:  # noqa: ARG002
        """Kahn's algorithm: emit bases before derived classes."""
        nodes = [c for c in classes if c.emit]
        qualified_set = {c.qualified_name for c in nodes}

        in_degree: Dict[str, int] = {c.qualified_name: 0 for c in nodes}
        dependents: Dict[str, List[str]] = {c.qualified_name: [] for c in nodes}

        for c in nodes:
            for base in c.bases:
                if base in qualified_set:
                    in_degree[c.qualified_name] += 1
                    dependents[base].append(c.qualified_name)

        queue = [c for c in nodes if in_degree[c.qualified_name] == 0]
        result = []
        qname_to_cls = {c.qualified_name: c for c in nodes}

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep_qname in dependents.get(node.qualified_name, []):
                in_degree[dep_qname] -= 1
                if in_degree[dep_qname] == 0:
                    queue.append(qname_to_cls[dep_qname])

        emitted = {c.qualified_name for c in result}
        for c in nodes:
            if c.qualified_name not in emitted:
                result.append(c)

        return result
