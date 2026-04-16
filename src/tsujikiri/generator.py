"""Generate binding code from an IRModule using a single Jinja2 template.

Each output format defines a ``template:`` key in its ``.output.yml`` file
or a ``template_file:`` key referencing an external file containing a full
Jinja2 template with named ``{% block %}`` tags.  Users can extend a built-in
format template using standard Jinja2 template inheritance 
(``{% extends "luabridge3.tpl" %}``) and override specific blocks.

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
from pathlib import Path
from typing import Any, Dict, List, Optional

import jinja2

from tsujikiri.configurations import GenerationConfig, OutputConfig, TypesystemConfig, load_output_config
from tsujikiri.formats import _FORMATS_DIR
from tsujikiri.generator_filters import camel_to_snake, snake_to_camel, code_at, param_pairs
from tsujikiri.ir import (
    IRClass,
    IREnum,
    IRFunction,
    IRMethod,
    IRModule,
)


class ItemFirstEnvironment(jinja2.Environment):
    """Jinja2 Environment that resolves ``obj.attr`` via item access before
    attribute access.  This ensures that plain-dict context values (e.g.
    ``enum['values']``) take priority over Python built-in dict methods like
    ``dict.values()``, which would otherwise shadow same-named keys."""

    def getattr(self, obj: object, attribute: str) -> Any:
        try:
            return obj[attribute]
        except (TypeError, LookupError, AttributeError):
            pass
        try:
            return getattr(obj, attribute)
        except AttributeError:
            return self.undefined(obj=obj, name=attribute)


def _type_lookup_candidates(type_spelling: str) -> List[str]:
    """Return type-spelling candidates ordered from most to least specific.

    Reference qualifiers (``&``, ``&&``) and ``const`` are stripped to produce
    fallback candidates so that a mapping for ``T`` also matches ``const T &``
    unless a more-specific entry is present.

    Pointer types (``*``) are never stripped: ``char``, ``char *`` and
    ``const char *`` are semantically distinct and must be mapped individually.
    """
    s = type_spelling.strip()

    # Pointers are distinct — no fallback
    if "*" in s:
        return [s]

    has_const = s.startswith("const ")
    if s.endswith(" &&"):
        ref_len = 3
    elif s.endswith(" &"):
        ref_len = 2
    else:
        ref_len = 0

    has_ref = ref_len > 0
    if not has_const and not has_ref:
        return [s]

    candidates: List[str] = [s]
    const_length = len("const ")

    # Level 1: strip exactly one qualifier
    if has_ref:
        candidates.append(s[:-ref_len].strip())

    if has_const:
        candidates.append(s[const_length:].strip())

    # Level 2: strip both qualifiers
    if has_const and has_ref:
        candidates.append(s[const_length:-ref_len].strip())

    return candidates


class Generator:
    def __init__(
        self,
        output_config: OutputConfig,
        generation: Optional[GenerationConfig] = None,
        extra_unsupported_types: Optional[List[str]] = None,
        template_extends: Optional[str] = None,
        typesystem: Optional[TypesystemConfig] = None,
        extra_dirs: Optional[List[Path]] = None,
    ) -> None:
        self.cfg = output_config
        self.generation = generation
        self.extra_unsupported: List[str] = extra_unsupported_types or []
        self.template_extends: str = template_extends or ""
        self._typesystem: Optional[TypesystemConfig] = typesystem
        self.extra_dirs: List[Path] = extra_dirs or []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def generate(self, module: IRModule, out: io.TextIOBase, api_version: str = "") -> None:
        self.generate_from_template(module, out, api_version)

    # ------------------------------------------------------------------
    # Single-template rendering
    # ------------------------------------------------------------------

    def generate_from_template(self, module: IRModule, out: io.TextIOBase, api_version: str = "") -> None:
        """Render the format's single Jinja2 template with full IR context."""
        ctx = self._build_ir_context(module, api_version)

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

        # Also load templates from extra_dirs so that custom formats can extend
        # each other via {% extends "customfmt.tpl" %}.
        # If a format has no template but declares ``extends``, synthesise an
        # implicit pass-through so it still participates in the DictLoader chain.
        for d in self.extra_dirs:
            for fmt_file in d.glob("*.output.yml"):
                try:
                    cfg = load_output_config(fmt_file)
                    tpl_key = f"{cfg.format_name}.tpl"
                    tpl_body = cfg.template
                    if not tpl_body and cfg.extends:
                        tpl_body = f'{{% extends "{cfg.extends}.tpl" %}}'
                    if tpl_body and tpl_key not in dict_templates:
                        dict_templates[tpl_key] = tpl_body
                except Exception:
                    pass

        # Register current format as "main.tpl" alias.
        if self.cfg.template:
            dict_templates["main.tpl"] = self.cfg.template
            dict_templates[f"{self.cfg.format_name}.tpl"] = self.cfg.template

        # Register override child template if provided.
        if self.template_extends:
            dict_templates["__override__.tpl"] = self.template_extends

        env = ItemFirstEnvironment(
            loader=jinja2.DictLoader(dict_templates),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
        )

        env.filters.update({
            "map_type": self._map_type,
            "param_pairs": param_pairs,
            "camel_to_snake": camel_to_snake,
            "snake_to_camel": snake_to_camel,
            "code_at": code_at,
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

    def _build_ir_context(self, module: IRModule, api_version: str = "") -> Dict[str, Any]:
        """Build a plain-data context dict from the IR for template rendering."""
        vir = self._version_in_range  # shorthand
        topo = self._topo_sort(module.classes, module.class_by_name)
        flat_classes: List[Dict[str, Any]] = []
        for cls in topo:
            if cls.emit and vir(api_version, cls.api_since, cls.api_until):
                flat_classes.extend(self._flatten_class_ctx(cls, module.functions, api_version))

        active_enums = [
            e for e in module.enums
            if e.emit and vir(api_version, e.api_since, e.api_until)
        ]
        active_fns = [
            fn for fn in module.functions
            if fn.emit and vir(api_version, fn.api_since, fn.api_until)
        ]

        return {
            "module_name": module.name,
            "includes": list(self.generation.includes) if self.generation else [],
            "enums": [self._build_enum_ctx(e) for e in active_enums],
            "function_groups": self._build_function_group_ctxs(active_fns),
            "classes": flat_classes,
            "api_version": api_version,
            "operator_mappings": dict(self.cfg.operator_mappings),
            "code_injections": [{"position": c.position, "code": c.code} for c in module.code_injections],
            "exception_registrations": [
                {
                    "cpp_type": er.cpp_exception_type,
                    "python_name": er.python_exception_name,
                    "base": er.base_python_exception,
                }
                for er in module.exception_registrations
            ],
            "conversion_rules": (
                [
                    {
                        "cpp_type": r.cpp_type,
                        "native_to_target": r.native_to_target,
                        "target_to_native": r.target_to_native,
                    }
                    for r in self._typesystem.conversion_rules
                ]
                if self._typesystem else []
            ),
        }

    def _flatten_class_ctx(
        self,
        ir_class: IRClass,
        module_functions: Optional[List[IRFunction]] = None,
        api_version: str = "",
    ) -> List[Dict[str, Any]]:
        """Return class ctx followed by inner-class ctxs (recursive, flattened)."""
        result = [self._build_class_ctx(ir_class, module_functions, api_version)]
        vir = self._version_in_range
        for inner in ir_class.inner_classes:
            if inner.emit and vir(api_version, inner.api_since, inner.api_until):
                result.extend(self._flatten_class_ctx(inner, module_functions, api_version))
        return result

    def _build_enum_ctx(self, enum: IREnum) -> Dict[str, Any]:
        return {
            "name": enum.rename or enum.name,
            "qualified_name": enum.qualified_name,
            "is_scoped": enum.is_scoped,
            "is_anonymous": enum.is_anonymous,
            "is_arithmetic": enum.is_arithmetic,
            "is_deprecated": enum.is_deprecated,
            "deprecation_message": enum.deprecation_message or "",
            "doc": enum.doc,
            "attributes": list(enum.attributes),
            "values": [
                {
                    "name": v.rename or v.name,
                    "original_name": v.name,
                    "number": str(v.value),
                    "doc": v.doc,
                    "attributes": list(v.attributes),
                }
                for v in enum.values
                if v.emit
            ],
        }

    def _build_function_group_ctxs(self, functions: List[IRFunction]) -> List[Dict[str, Any]]:
        effective_return_fn = lambda fn: fn.return_type_override or fn.return_type  # noqa: E731
        active = [fn for fn in functions if fn.emit and not self._is_unsupported(effective_return_fn(fn))]
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
                eff_return = effective_return_fn(fn)
                fns.append({
                    "name": fn.rename or fn.name,
                    "spelling": fn.qualified_name,
                    "params": [
                        {
                            "name": p.rename or p.name,
                            "original_name": p.name,
                            "type": self._map_type(p.type_override or p.type_spelling),
                            "raw_type": p.type_override or p.type_spelling,
                            "ownership": p.ownership,
                            "default": p.default_override or p.default_value,
                        }
                        for p in fn.parameters
                        if p.emit
                    ],
                    "return_type": self._map_type(eff_return),
                    "raw_return_type": eff_return,
                    "return_ownership": fn.return_ownership,
                    "return_keep_alive": fn.return_keep_alive,
                    "allow_thread": fn.allow_thread,
                    "wrapper_code": fn.wrapper_code,
                    "overload_kind": "overload",
                    "overload_separator": "" if is_last else ",",
                    "overload_index": i,
                    "is_noexcept": fn.is_noexcept,
                    "is_deprecated": fn.is_deprecated,
                    "deprecation_message": fn.deprecation_message or "",
                    "doc": fn.doc,
                    "attributes": list(fn.attributes),
                })
            result.append({
                "name": key,
                "is_overloaded": is_overloaded,
                "functions": fns,
            })
        return result

    def _build_class_ctx(self, ir_class: IRClass, module_functions: Optional[List[IRFunction]] = None, api_version: str = "") -> Dict[str, Any]:
        name = ir_class.rename or ir_class.name

        # Only emit=True public bases for deriveClass<> template usage
        public_bases = [
            b for b in ir_class.bases
            if b.emit and b.access == "public"
        ]
        base_name = public_bases[0].qualified_name if public_bases else ""

        # Virtual methods list for trampoline generation (ungrouped, each override individually)
        virtual_methods_ctx = []
        exposed_protected_ctx = []
        for m in ir_class.methods:
            if m.is_virtual or m.is_pure_virtual:
                if m.emit:
                    eff_rt = m.return_type_override or m.return_type
                    virtual_methods_ctx.append({
                        "name": m.spelling,
                        "return_type": self._map_type(eff_rt),
                        "raw_return_type": eff_rt,
                        "is_const": m.is_const,
                        "is_pure_virtual": m.is_pure_virtual,
                        "params": [
                            {
                                "name": p.rename or p.name,
                                "type": self._map_type(p.type_override or p.type_spelling),
                                "raw_type": p.type_override or p.type_spelling,
                            }
                            for p in m.parameters
                            if p.emit
                        ],
                    })
            if m.access == "public_via_trampoline":
                exposed_protected_ctx.append({"spelling": m.spelling})

        # Constructor group
        ctors = [c for c in ir_class.constructors if c.emit]
        ctor_group = {
            "is_overloaded": len(ctors) > 1,
            "constructors": [
                {
                    "params": [
                        {
                            "name": p.rename or p.name,
                            "original_name": p.name,
                            "type": self._map_type(p.type_override or p.type_spelling),
                            "raw_type": p.type_override or p.type_spelling,
                            "ownership": p.ownership,
                            "default": p.default_override or p.default_value,
                        }
                        for p in ctor.parameters
                        if p.emit
                    ],
                    "overload_index": i,
                    "is_noexcept": ctor.is_noexcept,
                    "is_explicit": ctor.is_explicit,
                    "doc": ctor.doc,
                    "code_injections": [{"position": c.position, "code": c.code} for c in ctor.code_injections],
                }
                for i, ctor in enumerate(ctors)
            ],
        }

        # Method groups (preserving original order)
        effective_return = lambda m: m.return_type_override or m.return_type  # noqa: E731
        methods = [
            m for m in ir_class.methods
            if m.emit
            and not self._is_unsupported(effective_return(m))
            and self._version_in_range(api_version, m.api_since, m.api_until)
        ]
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
                        {
                            "name": p.rename or p.name,
                            "original_name": p.name,
                            "type": self._map_type(p.type_override or p.type_spelling),
                            "raw_type": p.type_override or p.type_spelling,
                            "ownership": p.ownership,
                            "default": p.default_override or p.default_value,
                        }
                        for p in m.parameters
                        if p.emit
                    ],
                    "return_type": self._map_type(effective_return(m)),
                    "raw_return_type": effective_return(m),
                    "return_ownership": m.return_ownership,
                    "return_keep_alive": m.return_keep_alive,
                    "allow_thread": m.allow_thread,
                    "wrapper_code": m.wrapper_code,
                    "overload_kind": self._compute_overload_kind(group, m),
                    "overload_separator": "" if is_last else ",",
                    "is_const": m.is_const,
                    "is_virtual": m.is_virtual,
                    "is_pure_virtual": m.is_pure_virtual,
                    "is_noexcept": m.is_noexcept,
                    "is_operator": m.is_operator,
                    "operator_type": m.operator_type or "",
                    "operator_name": self.cfg.operator_mappings.get(m.operator_type or "", "") if m.is_operator else "",
                    "is_conversion_operator": m.is_conversion_operator,
                    "conversion_target_type": m.conversion_target_type or "",
                    "overload_index": i,
                    "is_deprecated": m.is_deprecated,
                    "deprecation_message": m.deprecation_message or "",
                    "doc": m.doc,
                    "attributes": list(m.attributes),
                    "code_injections": [{"position": c.position, "code": c.code} for c in m.code_injections],
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
                "type": self._map_type(f.type_override or f.type_spelling),
                "raw_type": f.type_override or f.type_spelling,
                "is_const": f.is_const,
                "is_static": f.is_static,
                "read_only": f.read_only or f.is_const,
                "doc": f.doc,
            }
            for f in ir_class.fields
            if f.emit and not self._is_unsupported(f.type_override or f.type_spelling)
        ]

        # Synthetic getter/setter properties
        properties = [
            {
                "name": p.name,
                "getter": p.getter,
                "setter": p.setter,
                "type": self._map_type(p.type_spelling),
                "raw_type": p.type_spelling,
                "doc": p.doc,
            }
            for p in ir_class.properties
            if p.emit
        ]

        # Detect free-function operator<< for this class (for __repr__ generation)
        has_free_ostream_op = False
        if module_functions:
            for fn in module_functions:
                if fn.emit and fn.is_operator and fn.operator_type == "operator<<":
                    params = [p for p in fn.parameters if p.emit]
                    if len(params) == 2:
                        second = params[1].type_spelling
                        if ir_class.name in second or ir_class.qualified_name in second:
                            has_free_ostream_op = True
                            break

        return {
            "name": name,
            "cpp_name": ir_class.name,
            "qualified_name": ir_class.qualified_name,
            "doc": ir_class.doc,
            "attributes": list(ir_class.attributes),
            "is_deprecated": ir_class.is_deprecated,
            "deprecation_message": ir_class.deprecation_message or "",
            "has_deleted_copy_constructor": ir_class.has_deleted_copy_constructor,
            "has_deleted_move_constructor": ir_class.has_deleted_move_constructor,
            "generate_hash": ir_class.generate_hash,
            "has_free_ostream_op": has_free_ostream_op,
            "bases": [
                {"qualified_name": b.qualified_name, "access": b.access, "emit": b.emit}
                for b in ir_class.bases
            ],
            "public_bases": [
                {
                    "qualified_name": b.qualified_name,
                    "short_name": b.qualified_name.split("::")[-1],
                }
                for b in public_bases
            ],
            "base_name": base_name,
            "base_short_name": base_name.split("::")[-1] if base_name else "",
            "variable_name": ir_class.variable_name,
            "has_virtual_methods": ir_class.has_virtual_methods,
            "is_abstract": ir_class.is_abstract,
            "copyable": ir_class.copyable,
            "movable": ir_class.movable,
            "force_abstract": ir_class.force_abstract,
            "holder_type": ir_class.holder_type or "",
            "trampoline_name": f"{self.generation.trampoline_prefix if self.generation else 'Py'}{ir_class.name}",
            "virtual_methods": virtual_methods_ctx,
            "exposed_protected_methods": exposed_protected_ctx,
            "has_exposed_protected": len(exposed_protected_ctx) > 0,
            "constructor_group": ctor_group,
            "method_groups": method_groups,
            "fields": fields,
            "properties": properties,
            "enums": [self._build_enum_ctx(e) for e in ir_class.enums if e.emit],
            "code_injections": [{"position": c.position, "code": c.code} for c in ir_class.code_injections],
            "declaration_injections": [{"position": c.position, "code": c.code} for c in ir_class.code_injections if c.position == "declaration"],
        }

    def _compute_overload_kind(self, group: List[IRMethod], method: IRMethod) -> str:
        """Return 'const', 'nonconst', or 'overload' for the cast type of this method."""
        def _eff_args(m: IRMethod) -> str:
            return ", ".join((p.type_override or p.type_spelling) for p in m.parameters if p.emit)

        method_args = _eff_args(method)
        for other in group:
            if other is method:
                continue
            other_args = _eff_args(other)
            if other_args == method_args and other.is_const != method.is_const:
                return "const" if method.is_const else "nonconst"
        return "overload"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # API version gating
    # ------------------------------------------------------------------

    @staticmethod
    def _version_in_range(api_version: str, api_since: Optional[str], api_until: Optional[str]) -> bool:
        """Return True if api_version falls within [api_since, api_until).

        Returns True when api_version is empty (no gating requested) or when
        the entity has no since/until constraints.
        """
        if not api_version:
            return True
        try:
            from packaging.version import Version
            v = Version(api_version)
            if api_since and v < Version(api_since):
                return False
            if api_until and v >= Version(api_until):
                return False
        except Exception:
            return True  # unparseable: include by default
        return True

    # ------------------------------------------------------------------
    # Type helpers
    # ------------------------------------------------------------------

    def _map_type(self, type_spelling: str) -> str:
        """Apply output-format type mappings, falling back to typesystem declarations.

        Type mappings are resolved from most specific to least specific.  For
        reference-qualified types (``&``, ``&&``) the lookup also tries
        progressively stripped variants so that a mapping for ``std::string``
        automatically covers ``const std::string &`` unless a more specific
        entry exists.  Pointer types (``*``) are never stripped — ``char``,
        ``char *`` and ``const char *`` remain distinct.
        """
        for candidate in _type_lookup_candidates(type_spelling):
            if candidate in self.cfg.type_mappings:
                return self.cfg.type_mappings[candidate]
        if self._typesystem:
            for pt in self._typesystem.primitive_types:
                if pt.cpp_name == type_spelling:
                    return pt.python_name
            for tt in self._typesystem.typedef_types:
                if tt.cpp_name == type_spelling:
                    return tt.source
        return type_spelling

    def _is_unsupported(self, type_spelling: str) -> bool:
        """Return True if the type spelling matches any unsupported type.

        custom_types from the typesystem are explicitly known externals and
        are never treated as unsupported even if listed in unsupported_types.
        """
        if self._typesystem:
            for ct in self._typesystem.custom_types:
                if ct.cpp_name in type_spelling:
                    return False
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
                if base.qualified_name in qualified_set:
                    in_degree[c.qualified_name] += 1
                    dependents[base.qualified_name].append(c.qualified_name)

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
