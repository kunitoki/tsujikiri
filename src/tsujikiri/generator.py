"""Generate binding code from an IRModule using an OutputConfig.

Template strings use Python's str.format(**ctx). An empty template string
produces no output for that construct. Unsupported return types (as listed in
OutputConfig.unsupported_types) cause the method/function to be commented out
using the line_comment prefix.
"""

from __future__ import annotations

import io
from typing import Dict, List

from tsujikiri.configurations import OutputConfig
from tsujikiri.ir import (
    IRClass,
    IREnum,
    IRFunction,
    IRMethod,
    IRModule,
)


class Generator:
    def __init__(self, output_config: OutputConfig) -> None:
        self.cfg = output_config
        self.tmpl = output_config.templates

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, module: IRModule, out: io.TextIOBase) -> None:
        ctx: Dict[str, str] = {"module_name": module.name}

        self._write(self.tmpl.prologue, ctx, out)

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

        self._write(self.tmpl.epilogue, ctx, out)

    # ------------------------------------------------------------------
    # Class emission
    # ------------------------------------------------------------------

    def _emit_class(self, ir_class: IRClass, parent_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        class_name = ir_class.rename or ir_class.name
        class_base_name = ir_class.bases[0] if ir_class.bases else ""
        parent_variable_name = parent_ctx.get("class_variable_name") or parent_ctx.get("module_name", "")

        ctx = dict(parent_ctx)
        ctx.update({
            "class_name": class_name,
            "class_base_name": class_base_name,
            "class_variable_name": ir_class.variable_name,
            "parent_variable_name": parent_variable_name,
            "qualified_class_name": ir_class.qualified_name,
        })

        if class_base_name:
            self._write(tmpl.class_derived_begin, ctx, out)
        else:
            self._write(tmpl.class_begin, ctx, out)

        self._emit_constructors(ir_class, ctx, out)
        self._emit_methods(ir_class, ctx, out)
        self._emit_fields(ir_class, ctx, out)

        for enum in ir_class.enums:
            if enum.emit:
                self._emit_enum(enum, ctx, out)

        self._write(tmpl.class_end, ctx, out)

        # Inner classes (use class_variable_name as their parent_variable_name)
        for inner in ir_class.inner_classes:
            if inner.emit:
                self._emit_class(inner, ctx, out)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _emit_methods(self, ir_class: IRClass, class_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        methods = [m for m in ir_class.methods if m.emit]
        if not methods:
            return

        self._write(tmpl.class_methods_begin, class_ctx, out)

        for method in methods:
            self._emit_method(method, class_ctx, out)

        self._write(tmpl.class_methods_end, class_ctx, out)

    def _emit_method(self, method: IRMethod, class_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        comment = ""
        if self._is_unsupported(method.return_type):
            comment = f"{tmpl.line_comment} "

        method_args = ", ".join(p.type_spelling for p in method.parameters)
        method_name = method.rename or method.name

        ctx = dict(class_ctx)
        ctx.update({
            "method_comment": comment,
            "method_name": method_name,
            "method_spelling": method.spelling,
            "method_args": method_args,
            "method_args_sep": f", {method_args}" if method_args else "",
            "method_return": method.return_type,
            "method_is_const": tmpl.class_overload_const_definition if method.is_const else "",
        })

        if method.is_static:
            begin = tmpl.class_overloaded_static_method_begin if method.is_overload else tmpl.class_static_method_begin
            end = tmpl.class_overloaded_static_method_end if method.is_overload else tmpl.class_static_method_end
        else:
            begin = tmpl.class_overloaded_method_begin if method.is_overload else tmpl.class_method_begin
            end = tmpl.class_overloaded_method_end if method.is_overload else tmpl.class_method_end

        self._write(begin, ctx, out)
        self._write(end, ctx, out)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    def _emit_constructors(self, ir_class: IRClass, class_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        ctors = [c for c in ir_class.constructors if c.emit]
        for ctor in ctors:
            ctor_args = ", ".join(p.type_spelling for p in ctor.parameters)
            ctx = dict(class_ctx)
            ctx["constructor_args"] = ctor_args
            ctx["method_comment"] = ""

            begin = tmpl.class_overloaded_constructor_begin if ctor.is_overload else tmpl.class_constructor_begin
            end = tmpl.class_overloaded_constructor_end if ctor.is_overload else tmpl.class_constructor_end

            self._write(begin, ctx, out)
            self._write(end, ctx, out)

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def _emit_fields(self, ir_class: IRClass, class_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        for field in ir_class.fields:
            if not field.emit:
                continue
            comment = ""
            if self._is_unsupported(field.type_spelling):
                comment = f"{tmpl.line_comment} "

            field_name = field.rename or field.name
            ctx = dict(class_ctx)
            ctx.update({
                "field_comment": comment,
                "field_name": field_name,
                "field_type": field.type_spelling,
                "field_is_const": "true" if field.is_const else "false",
            })

            if field.is_const:
                self._write(tmpl.class_readonly_field_begin, ctx, out)
                self._write(tmpl.class_readonly_field_end, ctx, out)
            else:
                self._write(tmpl.class_field_begin, ctx, out)
                self._write(tmpl.class_field_end, ctx, out)

    # ------------------------------------------------------------------
    # Enums
    # ------------------------------------------------------------------

    def _emit_enum(self, enum: IREnum, parent_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        ctx = dict(parent_ctx)
        ctx.update({
            "enum_name": enum.name,
            "qualified_enum_name": enum.qualified_name,
        })
        self._write(tmpl.enum_begin, ctx, out)
        for val in enum.values:
            if val.emit:
                vctx = dict(ctx)
                vctx.update({
                    "value_name": val.name,
                    "value_number": str(val.value),
                })
                self._write(tmpl.enum_value, vctx, out)
        self._write(tmpl.enum_end, ctx, out)

    # ------------------------------------------------------------------
    # Free functions
    # ------------------------------------------------------------------

    def _emit_functions(self, functions: List[IRFunction], parent_ctx: Dict[str, str], out: io.TextIOBase) -> None:
        tmpl = self.tmpl
        for fn in functions:
            if not fn.emit:
                continue
            comment = ""
            if self._is_unsupported(fn.return_type):
                comment = f"{tmpl.line_comment} "

            fn_args = ", ".join(p.type_spelling for p in fn.parameters)
            fn_name = fn.rename or fn.name
            ctx = dict(parent_ctx)
            ctx.update({
                "function_comment": comment,
                "function_name": fn_name,
                "function_spelling": fn.qualified_name,
                "function_args": fn_args,
                "function_return": fn.return_type,
            })

            begin = tmpl.function_overloaded_begin if fn.is_overload else tmpl.function_begin
            end = tmpl.function_overloaded_end if fn.is_overload else tmpl.function_end

            self._write(begin, ctx, out)
            self._write(end, ctx, out)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_unsupported(self, type_spelling: str) -> bool:
        return any(t in type_spelling for t in self.cfg.unsupported_types)

    def _write(self, template: str, ctx: Dict[str, str], out: io.TextIOBase) -> None:
        if not template:
            return
        try:
            out.write(template.format(**ctx))
        except KeyError as e:
            raise KeyError(f"Missing template variable {e} in context with keys: {sorted(ctx)}")

    def _topo_sort(self, classes: List[IRClass], class_by_name: Dict[str, IRClass]) -> List[IRClass]:  # noqa: ARG002
        """Kahn's algorithm: emit bases before derived classes."""
        # Only consider top-level emit=True classes
        nodes = [c for c in classes if c.emit]
        name_set = {c.name for c in nodes}

        # Build in-degree and adjacency (base -> derived)
        in_degree: Dict[str, int] = {c.name: 0 for c in nodes}
        dependents: Dict[str, List[str]] = {c.name: [] for c in nodes}

        for c in nodes:
            for base in c.bases:
                if base in name_set:
                    in_degree[c.name] += 1
                    dependents[base].append(c.name)

        queue = [c for c in nodes if in_degree[c.name] == 0]
        result = []
        name_to_cls = {c.name: c for c in nodes}

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dep_name in dependents.get(node.name, []):
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    queue.append(name_to_cls[dep_name])

        # Append any remaining (cycle or unknown bases) to avoid dropping them
        emitted_names = {c.name for c in result}
        for c in nodes:
            if c.name not in emitted_names:
                result.append(c)

        return result
