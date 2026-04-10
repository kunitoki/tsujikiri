"""Generate binding code from an IRModule using an OutputConfig.

Template strings use Jinja2. An empty template string produces no output for
that construct. Unsupported return types (as listed in
OutputConfig.unsupported_types) cause the method/function to be commented out
using the line_comment prefix.

Template overrides (from the input YAML ``format_overrides`` section) can
replace any template by name. An override may contain ``{{ super }}`` which
expands to the base format's rendered template for that key.

Parameters are passed to templates as structured lists (``method_params``,
``function_params``, ``constructor_params``), each element being a dict with
keys ``name``, ``type`` (mapped), and ``raw_type`` (original C++ spelling).
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

import jinja2

from tsujikiri.configurations import GenerationConfig, OutputConfig
from tsujikiri.ir import (
    IRClass,
    IREnum,
    IRFunction,
    IRMethod,
    IRModule,
)


def param_pairs(params: List[Dict[str, Any]], name_key: str, sep: str, type_key: str, joiner: str) -> str:
    """Jinja2 filter helper to format parameter lists."""
    return joiner.join(f"{p[name_key]}{sep}{p[type_key]}" for p in params)

def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case for variable naming."""
    import re
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class Generator:
    def __init__(
        self,
        output_config: OutputConfig,
        generation: Optional[GenerationConfig] = None,
        template_overrides: Optional[Dict[str, str]] = None,
        extra_unsupported_types: Optional[List[str]] = None,
    ) -> None:
        self.cfg = output_config
        self.tmpl = output_config.templates
        self.generation = generation
        self.overrides: Dict[str, str] = template_overrides or {}
        self.extra_unsupported: List[str] = extra_unsupported_types or []

        env = jinja2.Environment(
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )
        env.filters["map_type"] = self._map_type
        env.filters["param_pairs"] = param_pairs
        env.filters["camel_to_snake"] = camel_to_snake
        self.jinja_env = env

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, module: IRModule, out: io.TextIOBase) -> None:
        ctx: Dict[str, Any] = {"module_name": module.name}

        if self.generation:
            if self.generation.prefix:
                out.write(self.generation.prefix)
            for inc in self.generation.includes:
                # include_directive defaults to C-style when not set by the format
                inc_ctx = {**ctx, "include": inc}
                base = getattr(self.tmpl, "include_directive", "") or "#include {{ include }}\n"
                override = self.overrides.get("include_directive")
                if override is not None:
                    if "{{ super }}" in override:
                        super_rendered = self._render(base, inc_ctx)
                        out.write(self._render(override, {**inc_ctx, "super": super_rendered}))
                    elif override:
                        out.write(self._render(override, inc_ctx))
                else:
                    out.write(self._render(base, inc_ctx))

        self._write("prologue", ctx, out)

        # Top-level enums
        for enum in module.enums:
            if enum.emit:
                self._emit_enum(enum, ctx, out)

        # Free functions
        self._emit_functions(module.functions, ctx, out)

        # Classes in topological order (bases before derived)
        for ir_class in self._topo_sort(module.classes, module.class_by_name):
            if ir_class.emit:
                self._emit_class(ir_class, ctx, out)

        self._write("epilogue", ctx, out)

        if self.generation and self.generation.postfix:
            out.write(self.generation.postfix)

    # ------------------------------------------------------------------
    # Class emission
    # ------------------------------------------------------------------

    def _emit_class(self, ir_class: IRClass, parent_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        class_name = ir_class.rename or ir_class.name
        class_base_name = ir_class.bases[0] if ir_class.bases else ""
        parent_variable_name = parent_ctx.get("class_variable_name") or parent_ctx.get("module_name", "")

        class_base_short_name = class_base_name.split("::")[-1] if class_base_name else ""

        ctx = dict(parent_ctx)
        ctx.update({
            "class_name": class_name,
            "class_base_name": class_base_name,
            "class_base_short_name": class_base_short_name,
            "class_variable_name": ir_class.variable_name,
            "parent_variable_name": parent_variable_name,
            "qualified_class_name": ir_class.qualified_name,
        })

        ctx["class_fields_block"] = self._render_field_annotations(ir_class, ctx)

        if class_base_name:
            self._write("class_derived_begin", ctx, out)
        else:
            self._write("class_begin", ctx, out)

        self._emit_constructors(ir_class, ctx, out)
        self._emit_methods(ir_class, ctx, out)
        self._emit_fields(ir_class, ctx, out)

        for enum in ir_class.enums:
            if enum.emit:
                self._emit_enum(enum, ctx, out)

        self._write("class_end", ctx, out)

        # Inner classes (use class_variable_name as their parent_variable_name)
        for inner in ir_class.inner_classes:
            if inner.emit:
                self._emit_class(inner, ctx, out)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _emit_methods(self, ir_class: IRClass, class_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        methods = [m for m in ir_class.methods if m.emit]
        if not methods:
            return

        self._write("class_methods_begin", class_ctx, out)

        # Group same-name methods (preserving original order) so we can emit group wrappers
        groups: Dict[tuple, List[IRMethod]] = {}
        order: List[tuple] = []
        for method in methods:
            key = (method.rename or method.name, method.is_static)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(method)

        for key in order:
            group = groups[key]
            is_static = key[1]
            group_begin_name = (
                "class_overloaded_static_method_group_begin" if is_static
                else "class_overloaded_method_group_begin"
            )
            if len(group) > 1 and self._has_template(group_begin_name):
                self._emit_overload_method_group(group, class_ctx, out)
            else:
                for i, method in enumerate(group):
                    self._emit_method(method, class_ctx, out, overload_index=i)

        self._write("class_methods_end", class_ctx, out)

    def _emit_overload_method_group(self, methods: List[IRMethod], class_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        is_static = methods[0].is_static
        method_name = methods[0].rename or methods[0].name

        group_begin_name = (
            "class_overloaded_static_method_group_begin" if is_static
            else "class_overloaded_method_group_begin"
        )
        group_end_name = (
            "class_overloaded_static_method_group_end" if is_static
            else "class_overloaded_method_group_end"
        )

        any_unsupported = any(self._is_unsupported(m.return_type) for m in methods)
        if any_unsupported:
            return

        group_ctx = dict(class_ctx)
        group_ctx.update({
            "method_name": method_name,
            "overloads": [
                {
                    "method_params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in m.parameters
                    ],
                    "method_return": self._map_type(m.return_type),
                }
                for m in methods
            ],
        })

        self._write(group_begin_name, group_ctx, out)

        for i, method in enumerate(methods):
            is_last = i == len(methods) - 1

            if self._is_unsupported(method.return_type):
                continue

            ctx = dict(class_ctx)
            ctx.update({
                "method_name": method_name,
                "method_spelling": method.spelling,
                "method_params": [
                    {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                    for p in method.parameters
                ],
                "method_return": self._map_type(method.return_type),
                "method_is_const": self._get_template("class_overload_const_definition") if method.is_const else "",
                "method_overload_cast": self._get_method_overload_cast(methods, method),
                "method_overload_separator": "" if is_last else ",",
            })

            if is_static:
                begin_name = "class_overloaded_static_method_begin"
                end_name = "class_overloaded_static_method_end"
            else:
                begin_name = "class_overloaded_method_begin"
                end_name = "class_overloaded_method_end"

            self._write(begin_name, ctx, out)
            self._write(end_name, ctx, out)

        self._write(group_end_name, group_ctx, out)

    def _get_method_overload_cast(self, group: List[IRMethod], method: IRMethod) -> str:
        """Return the overload cast string for this method within its group."""
        method_args = ", ".join(p.type_spelling for p in method.parameters)
        for other in group:
            if other is method:
                continue
            other_args = ", ".join(p.type_spelling for p in other.parameters)
            if other_args == method_args and other.is_const != method.is_const:
                cast_name = "class_const_overload_cast" if method.is_const else "class_nonconst_overload_cast"
                return self._get_template(cast_name)
        return self._get_template("class_overload_cast")

    def _emit_method(self, method: IRMethod, class_ctx: Dict[str, Any], out: io.TextIOBase, overload_index: int = 0) -> None:
        if self._is_unsupported(method.return_type):
            return

        method_name = method.rename or method.name

        ctx = dict(class_ctx)
        ctx.update({
            "method_name": method_name,
            "method_spelling": method.spelling,
            "method_params": [
                {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                for p in method.parameters
            ],
            "method_return": self._map_type(method.return_type),
            "method_is_const": self._get_template("class_overload_const_definition") if method.is_const else "",
            "method_overload_cast": self._get_template("class_overload_cast"),
            "method_overload_separator": "",
            "overload_index": str(overload_index),
        })

        if method.is_static:
            begin_name = "class_overloaded_static_method_begin" if method.is_overload else "class_static_method_begin"
            end_name = "class_overloaded_static_method_end" if method.is_overload else "class_static_method_end"
        else:
            begin_name = "class_overloaded_method_begin" if method.is_overload else "class_method_begin"
            end_name = "class_overloaded_method_end" if method.is_overload else "class_method_end"

        self._write(begin_name, ctx, out)
        self._write(end_name, ctx, out)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    def _emit_constructors(self, ir_class: IRClass, class_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        ctors = [c for c in ir_class.constructors if c.emit]
        if not ctors:
            return

        if len(ctors) > 1 and self._has_template("class_constructor_group_begin"):
            group_ctx = dict(class_ctx)
            group_ctx["overloads"] = [
                {
                    "constructor_params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in ctor.parameters
                    ]
                }
                for ctor in ctors
            ]
            self._write("class_constructor_group_begin", group_ctx, out)
            self._write("class_constructor_group_end", group_ctx, out)
            return

        for i, ctor in enumerate(ctors):
            ctx = dict(class_ctx)
            ctx["constructor_params"] = [
                {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                for p in ctor.parameters
            ]
            ctx["overload_index"] = str(i)

            begin_name = "class_overloaded_constructor_begin" if ctor.is_overload else "class_constructor_begin"
            end_name = "class_overloaded_constructor_end" if ctor.is_overload else "class_constructor_end"

            self._write(begin_name, ctx, out)
            self._write(end_name, ctx, out)

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def _render_field_annotations(self, ir_class: IRClass, class_ctx: Dict[str, Any]) -> str:
        """Pre-render field header annotations for inclusion in class_begin templates."""
        annotation_template = self._get_template("class_field_annotation")
        if not annotation_template:
            return ""

        parts = []
        for field in ir_class.fields:
            if not field.emit or self._is_unsupported(field.type_spelling):
                continue
            field_name = field.rename or field.name
            ctx = dict(class_ctx)
            ctx.update({
                "field_name": field_name,
                "field_type": self._map_type(field.type_spelling),
                "field_is_const": "true" if field.is_const else "false",
            })
            parts.append(self._render(annotation_template, ctx))
        return "".join(parts)

    def _emit_fields(self, ir_class: IRClass, class_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        for field in ir_class.fields:
            if not field.emit or self._is_unsupported(field.type_spelling):
                continue

            field_name = field.rename or field.name
            ctx = dict(class_ctx)
            ctx.update({
                "field_name": field_name,
                "field_type": self._map_type(field.type_spelling),
                "field_is_const": "true" if field.is_const else "false",
            })

            if field.is_const:
                self._write("class_readonly_field_begin", ctx, out)
                self._write("class_readonly_field_end", ctx, out)
            else:
                self._write("class_field_begin", ctx, out)
                self._write("class_field_end", ctx, out)

    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------

    def _emit_enum(self, enum: IREnum, parent_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        ctx = dict(parent_ctx)
        ctx.update({
            "enum_name": enum.name,
            "qualified_enum_name": enum.qualified_name,
        })

        self._write("enum_begin", ctx, out)

        for val in enum.values:
            if val.emit:
                vctx = dict(ctx)
                vctx.update({
                    "value_name": val.name,
                    "value_number": str(val.value),
                })
                self._write("enum_value", vctx, out)

        self._write("enum_end", ctx, out)

    # ------------------------------------------------------------------
    # Free functions
    # ------------------------------------------------------------------

    def _emit_functions(self, functions: List[IRFunction], parent_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        active = [fn for fn in functions if fn.emit]
        if not active:
            return

        # Group same-name free functions (preserving order) for group-wrapper support
        groups: Dict[str, List[IRFunction]] = {}
        order: List[str] = []
        for fn in active:
            key = fn.rename or fn.name
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(fn)

        for key in order:
            group = groups[key]
            if len(group) > 1 and self._has_template("function_overloaded_group_begin"):
                self._emit_overload_function_group(group, parent_ctx, out)
            else:
                for i, fn in enumerate(group):
                    self._emit_function(fn, parent_ctx, out, overload_index=i)

    def _emit_overload_function_group(self, functions: List[IRFunction], parent_ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        fn_name = functions[0].rename or functions[0].name

        any_unsupported = any(self._is_unsupported(fn.return_type) for fn in functions)
        if any_unsupported:
            return

        group_ctx = dict(parent_ctx)
        group_ctx.update({
            "function_name": fn_name,
            "overloads": [
                {
                    "function_params": [
                        {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                        for p in fn.parameters
                    ],
                    "function_return": self._map_type(fn.return_type),
                }
                for fn in functions
            ],
        })

        self._write("function_overloaded_group_begin", group_ctx, out)

        for i, fn in enumerate(functions):
            is_last = i == len(functions) - 1

            ctx = dict(parent_ctx)
            ctx.update({
                "function_name": fn_name,
                "function_spelling": fn.qualified_name,
                "function_params": [
                    {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                    for p in fn.parameters
                ],
                "function_return": self._map_type(fn.return_type),
                "function_overload_cast": self._get_template("function_overload_cast"),
                "function_overload_separator": "" if is_last else ",",
            })

            self._write("function_overloaded_begin", ctx, out)
            self._write("function_overloaded_end", ctx, out)

        self._write("function_overloaded_group_end", group_ctx, out)

    def _emit_function(self, fn: IRFunction, parent_ctx: Dict[str, Any], out: io.TextIOBase, overload_index: int = 0) -> None:
        if self._is_unsupported(fn.return_type):
            return

        fn_name = fn.rename or fn.name
        ctx = dict(parent_ctx)
        ctx.update({
            "function_name": fn_name,
            "function_spelling": fn.qualified_name,
            "function_params": [
                {"name": p.name, "type": self._map_type(p.type_spelling), "raw_type": p.type_spelling}
                for p in fn.parameters
            ],
            "function_return": self._map_type(fn.return_type),
            "function_overload_cast": self._get_template("function_overload_cast"),
            "function_overload_separator": "",
            "overload_index": str(overload_index),
        })

        begin_name = "function_overloaded_begin" if fn.is_overload else "function_begin"
        end_name = "function_overloaded_end" if fn.is_overload else "function_end"

        self._write(begin_name, ctx, out)
        self._write(end_name, ctx, out)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _map_type(self, type_spelling: str) -> str:
        """Apply output-format type mappings (e.g. C++ → Lua types)."""
        return self.cfg.type_mappings.get(type_spelling, type_spelling)

    def _is_unsupported(self, type_spelling: str) -> bool:
        """Return True if the type spelling matches any unsupported type (base or extra)."""
        all_unsupported = self.cfg.unsupported_types + self.extra_unsupported
        return any(t in type_spelling for t in all_unsupported)

    def _get_template(self, name: str) -> str:
        """Return the effective template string (override if present, else base)."""
        override = self.overrides.get(name)
        if override is not None:
            return override
        return getattr(self.tmpl, name, "")

    def _has_template(self, name: str) -> bool:
        """Return True if the effective template for *name* is non-empty."""
        return bool(self._get_template(name))

    def _render(self, template_str: str, ctx: Dict[str, Any]) -> str:
        """Render a Jinja2 template string with the given context."""
        try:
            return self.jinja_env.from_string(template_str).render(ctx)
        except jinja2.UndefinedError as e:
            raise KeyError(str(e)) from e

    def _write(self, name: str, ctx: Dict[str, Any], out: io.TextIOBase) -> None:
        """Render the template identified by *name* and write to *out*.

        If an override is present and contains ``{{ super }}``, the base template
        is rendered first (with *ctx*) and the result is made available as the
        ``super`` variable when rendering the override.
        """
        base = getattr(self.tmpl, name, "")
        override = self.overrides.get(name)

        if override is not None:
            if not override:
                return
            if "{{ super }}" in override:
                super_rendered = self._render(base, ctx) if base else ""
                out.write(self._render(override, {**ctx, "super": super_rendered}))
            else:
                out.write(self._render(override, ctx))
        elif base:
            out.write(self._render(base, ctx))

    def _topo_sort(self, classes: List[IRClass], class_by_name: Dict[str, IRClass]) -> List[IRClass]:  # noqa: ARG002
        """Kahn's algorithm: emit bases before derived classes."""
        # Only consider top-level emit=True classes
        nodes = [c for c in classes if c.emit]
        qualified_set = {c.qualified_name for c in nodes}

        # Build in-degree and adjacency using qualified names (bases are fully qualified)
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

        # Append any remaining (cycle or unknown bases) to avoid dropping them
        emitted = {c.qualified_name for c in result}
        for c in nodes:
            if c.qualified_name not in emitted:
                result.append(c)

        return result
