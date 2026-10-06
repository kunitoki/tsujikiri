"""API manifest: compute, compare, save, and load binding surface snapshots.

A manifest captures the emitted binding surface of an IRModule as a
deterministic JSON document. Two manifests can be compared to classify API
changes as additive (safe) or breaking (scripts that rely on the old surface
may break at runtime).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tsujikiri.tir import minimum_arity, TIRClass, TIRModule


# ---------------------------------------------------------------------------
# Compatibility report
# ---------------------------------------------------------------------------


@dataclass
class CompatibilityReport:
    breaking_changes: List[str] = field(default_factory=list)
    additive_changes: List[str] = field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        return not self.breaking_changes

    @property
    def has_changes(self) -> bool:
        return bool(self.breaking_changes or self.additive_changes)


# ---------------------------------------------------------------------------
# Canonical builders (format-agnostic, transformed C++ types, emit=True only)
# ---------------------------------------------------------------------------


def _effective_param_type(param: Any) -> str:
    return param.type_override or param.type_spelling


def _effective_return_type(node: Any) -> str:
    return node.return_type_override or node.return_type


def _emitted_params(params: List[Any]) -> List[Any]:
    return [p for p in params if getattr(p, "emit", True)]


def _emitted_param_types(params: List[Any]) -> List[str]:
    return [_effective_param_type(p) for p in _emitted_params(params)]


def _min_arity(params: List[Any]) -> int:
    """Return the smallest number of arguments a caller may supply.

    Trailing defaulted parameters may be omitted in every target language, so
    dropping a default raises this number and breaks existing callers even
    though the parameter type list is unchanged.  Derived from the same rule the
    generator uses to decide which arities to emit.
    """
    emitted = _emitted_params(params)
    return minimum_arity([p.default_override or p.default_value for p in emitted])


def _canonical_injections(injections: List[Any]) -> List[Dict[str, str]]:
    return [{"position": c.position, "code": c.code} for c in injections]


def _metadata(pairs: List[Tuple[str, Any, Any]]) -> Dict[str, Any]:
    return {name: value for name, value, default in pairs if value != default}


def _canonical_class(ir_class: TIRClass) -> Dict[str, Any]:
    name = ir_class.binding_name

    constructors = sorted(
        [
            {"params": _emitted_param_types(c.parameters), "min_arity": _min_arity(c.parameters)}
            for c in ir_class.constructors
            if c.emit
        ],
        key=lambda c: tuple(c["params"]),
    )

    methods: List[Dict[str, Any]] = []
    for m in ir_class.methods:
        if not m.emit:
            continue
        methods.append(
            {
                "name": m.binding_name,
                "params": _emitted_param_types(m.parameters),
                "min_arity": _min_arity(m.parameters),
                "return_type": _effective_return_type(m),
                "is_static": m.is_static,
            }
        )
    methods.sort(key=lambda m: (m["name"], m["params"], m["is_static"]))

    fields: List[Dict[str, Any]] = []
    for f in ir_class.fields:
        if not f.emit:
            continue
        fields.append(
            {
                "name": f.binding_name,
                "type": f.type_override or f.type_spelling,
                "is_const": f.is_const,
                "read_only": f.read_only or f.is_const,
            }
        )
    fields.sort(key=lambda f: f["name"])

    properties = sorted(
        [_canonical_property(p) for p in ir_class.properties if p.emit],
        key=lambda p: p["name"],
    )

    enums = sorted(
        [_canonical_enum_entry(e) for e in ir_class.enums if e.emit],
        key=lambda e: e["name"],
    )

    bases = sorted(b.qualified_name for b in ir_class.bases if getattr(b, "emit", True))

    inner_classes = sorted(
        [_canonical_class(c) for c in ir_class.inner_classes if c.emit],
        key=lambda c: c["name"],
    )

    result: Dict[str, Any] = {
        "name": name,
        "constructors": constructors,
        "methods": methods,
        "fields": fields,
        "properties": properties,
        "enums": enums,
    }
    if bases:
        result["bases"] = bases
    if inner_classes:
        result["inner_classes"] = inner_classes
    return result


def _canonical_property(prop: Any) -> Dict[str, Any]:
    return {
        "name": prop.name,
        "getter": prop.getter,
        "setter": prop.setter,
        "type": prop.type_spelling,
        "read_only": prop.setter is None,
    }


def _canonical_enum_entry(enum) -> Dict[str, Any]:
    values = sorted(
        [{"name": v.binding_name, "value": v.value} for v in enum.values if v.emit],
        key=lambda v: v["name"],
    )
    return {"name": enum.binding_name, "values": values}


def _iter_classes(classes: List[Any]) -> List[Any]:
    result: List[Any] = []

    def _walk(cls: Any) -> None:
        result.append(cls)
        for inner in cls.inner_classes:
            _walk(inner)

    for cls in classes:
        _walk(cls)
    return result


def _canonical_param_transform(param: Any, index: int) -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("rename", param.rename, None),
            ("default", param.default_override, None),
            ("ownership", param.ownership, "none"),
        ]
    )
    if not data:
        return None
    return {
        "index": index,
        "name": param.name,
        **data,
    }


def _canonical_param_transforms(params: List[Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for index, param in enumerate(params):
        if not getattr(param, "emit", True):
            continue
        transformed = _canonical_param_transform(param, index)
        if transformed is not None:
            result.append(transformed)
    return result


def _canonical_constructor_transform(ctor: Any, class_name: str, index: int) -> Optional[Dict[str, Any]]:
    data: Dict[str, Any] = {}
    params = _canonical_param_transforms(ctor.parameters)
    if params:
        data["parameters"] = params
    injections = _canonical_injections(ctor.code_injections)
    if injections:
        data["code_injections"] = injections
    if not data:
        return None
    return {
        "class": class_name,
        "index": index,
        "params": _emitted_param_types(ctor.parameters),
        **data,
    }


def _canonical_method_transform(method: Any, class_name: str) -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("return_ownership", method.return_ownership, "none"),
            ("return_keep_alive", method.return_keep_alive, False),
            ("allow_thread", method.allow_thread, False),
            ("wrapper_code", method.wrapper_code, None),
            ("overload_priority", method.overload_priority, None),
            ("exception_policy", method.exception_policy, None),
            ("api_since", method.api_since, None),
            ("api_until", method.api_until, None),
        ]
    )
    params = _canonical_param_transforms(method.parameters)
    if params:
        data["parameters"] = params
    injections = _canonical_injections(method.code_injections)
    if injections:
        data["code_injections"] = injections
    if not data:
        return None
    return {
        "class": class_name,
        "name": method.binding_name,
        "params": _emitted_param_types(method.parameters),
        "return_type": _effective_return_type(method),
        "is_static": method.is_static,
        **data,
    }


def _canonical_function_transform(fn: Any) -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("return_ownership", fn.return_ownership, "none"),
            ("return_keep_alive", fn.return_keep_alive, False),
            ("allow_thread", fn.allow_thread, False),
            ("wrapper_code", fn.wrapper_code, None),
            ("overload_priority", fn.overload_priority, None),
            ("exception_policy", fn.exception_policy, None),
            ("api_since", fn.api_since, None),
            ("api_until", fn.api_until, None),
        ]
    )
    params = _canonical_param_transforms(fn.parameters)
    if params:
        data["parameters"] = params
    if not data:
        return None
    return {
        "name": fn.binding_name,
        "params": _emitted_param_types(fn.parameters),
        "return_type": _effective_return_type(fn),
        **data,
    }


def _canonical_field_transform(field: Any, class_name: str) -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("read_only", field.read_only, False),
        ]
    )
    if not data:
        return None
    return {
        "class": class_name,
        "name": field.binding_name,
        "type": field.type_override or field.type_spelling,
        **data,
    }


def _canonical_enum_transform(enum: Any, parent: str = "") -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("is_arithmetic", enum.is_arithmetic, False),
            ("api_since", enum.api_since, None),
            ("api_until", enum.api_until, None),
        ]
    )
    if not data:
        return None
    result: Dict[str, Any] = {
        "name": enum.binding_name,
        **data,
    }
    if parent:
        result["parent"] = parent
    return result


def _canonical_class_transform(ir_class: Any) -> Optional[Dict[str, Any]]:
    data = _metadata(
        [
            ("copyable", ir_class.copyable, None),
            ("movable", ir_class.movable, None),
            ("force_abstract", ir_class.force_abstract, False),
            ("holder_type", ir_class.holder_type, None),
            ("generate_hash", ir_class.generate_hash, False),
            ("smart_pointer_kind", ir_class.smart_pointer_kind, None),
            ("smart_pointer_managed_type", ir_class.smart_pointer_managed_type, None),
            ("api_since", ir_class.api_since, None),
            ("api_until", ir_class.api_until, None),
        ]
    )
    injections = _canonical_injections(ir_class.code_injections)
    if injections:
        data["code_injections"] = injections

    constructors: List[Dict[str, Any]] = []
    for index, ctor in enumerate(c for c in ir_class.constructors if c.emit):
        transformed = _canonical_constructor_transform(ctor, ir_class.binding_name, index)
        if transformed is not None:
            constructors.append(transformed)
    if constructors:
        data["constructors"] = constructors

    methods = [
        transformed
        for transformed in (_canonical_method_transform(m, ir_class.binding_name) for m in ir_class.methods if m.emit)
        if transformed is not None
    ]
    if methods:
        data["methods"] = sorted(
            methods,
            key=lambda m: (m["class"], m["name"], m["params"], m["is_static"]),
        )

    fields = [
        transformed
        for transformed in (_canonical_field_transform(f, ir_class.binding_name) for f in ir_class.fields if f.emit)
        if transformed is not None
    ]
    if fields:
        data["fields"] = sorted(fields, key=lambda f: (f["class"], f["name"]))

    enums = [
        transformed
        for transformed in (_canonical_enum_transform(e, ir_class.binding_name) for e in ir_class.enums if e.emit)
        if transformed is not None
    ]
    if enums:
        data["enums"] = sorted(enums, key=lambda e: (e.get("parent", ""), e["name"]))

    if not data:
        return None
    return {
        "name": ir_class.binding_name,
        "qualified_name": ir_class.qualified_name,
        **data,
    }


def _canonical_transformations(module: TIRModule) -> Dict[str, Any]:
    transformations: Dict[str, Any] = {}

    module_injections = _canonical_injections(module.code_injections)
    if module_injections:
        transformations["code_injections"] = module_injections

    exception_registrations = sorted(
        [
            {
                "cpp_exception_type": er.cpp_exception_type,
                "target_exception_name": er.target_exception_name,
                "base_target_exception": er.base_target_exception,
            }
            for er in module.exception_registrations
        ],
        key=lambda er: (er["cpp_exception_type"], er["target_exception_name"], er["base_target_exception"]),
    )
    if exception_registrations:
        transformations["exception_registrations"] = exception_registrations

    classes = [
        transformed
        for transformed in (_canonical_class_transform(c) for c in _iter_classes(module.classes) if c.emit)
        if transformed is not None
    ]
    if classes:
        transformations["classes"] = sorted(classes, key=lambda c: (c["qualified_name"], c["name"]))

    functions = [
        transformed
        for transformed in (_canonical_function_transform(fn) for fn in module.functions if fn.emit)
        if transformed is not None
    ]
    if functions:
        transformations["functions"] = sorted(functions, key=lambda f: (f["name"], f["params"]))

    enums = [
        transformed
        for transformed in (_canonical_enum_transform(e) for e in module.enums if e.emit)
        if transformed is not None
    ]
    if enums:
        transformations["enums"] = sorted(enums, key=lambda e: e["name"])

    return transformations


# ---------------------------------------------------------------------------
# Public: compute
# ---------------------------------------------------------------------------


def compute_manifest(module: TIRModule) -> Dict[str, Any]:
    """Build a canonical manifest dict from a fully-filtered/transformed IRModule."""
    classes = sorted(
        [_canonical_class(c) for c in module.classes if c.emit],
        key=lambda c: c["name"],
    )

    functions: List[Dict[str, Any]] = []
    for fn in module.functions:
        if not fn.emit:
            continue
        functions.append(
            {
                "name": fn.binding_name,
                "params": _emitted_param_types(fn.parameters),
                "min_arity": _min_arity(fn.parameters),
                "return_type": _effective_return_type(fn),
            }
        )
    functions.sort(key=lambda f: (f["name"], f["params"]))

    enums = sorted(
        [_canonical_enum_entry(e) for e in module.enums if e.emit],
        key=lambda e: e["name"],
    )

    api: Dict[str, Any] = {
        "classes": classes,
        "functions": functions,
        "enums": enums,
    }

    manifest: Dict[str, Any] = {
        "module": module.name,
        "version": "0.0.0",
        "api": api,
    }
    transformations = _canonical_transformations(module)
    if transformations:
        manifest["transformations"] = transformations
    return manifest


# ---------------------------------------------------------------------------
# Public: save / load
# ---------------------------------------------------------------------------


def save_manifest(manifest: Dict[str, Any], path: Path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def load_manifest(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Public: version bump suggestion
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def is_semver(s: str) -> bool:
    """Return True if *s* is a ``MAJOR.MINOR.PATCH`` semantic version string."""
    return bool(_SEMVER_RE.match(s))


def bump_semver(version: str, report: CompatibilityReport) -> str:
    """Return a bumped semver string derived from *report*.

    * Breaking changes (removed or modified API) → bump MAJOR, reset MINOR and PATCH to 0.
    * Additive-only changes (new classes, enums, functions, methods, constructors) →
      bump MINOR, reset PATCH to 0.
    * No changes → return *version* unchanged.

    Raises ``ValueError`` if *version* is not a valid ``MAJOR.MINOR.PATCH`` string.
    """
    m = _SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"Not a valid semver string: {version!r}")
    major, minor, _ = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if report.breaking_changes:
        return f"{major + 1}.0.0"
    if report.additive_changes:
        return f"{major}.{minor + 1}.0"
    return version


def suggest_version_bump(old_manifest: Dict[str, Any], report: CompatibilityReport) -> Optional[str]:
    """Return the suggested semver for the new manifest, or ``None``.

    A suggestion is returned only when *old_manifest* contains a ``"semver"``
    field that is a valid ``MAJOR.MINOR.PATCH`` string.  The returned value is
    the appropriately bumped version (or the same version when there are no
    changes).  ``None`` is returned when the old manifest has no semver field
    or its value is not a valid semver string.
    """
    old_version = old_manifest.get("version")
    if not isinstance(old_version, str) or not is_semver(old_version):
        return None
    return bump_semver(old_version, report)


# ---------------------------------------------------------------------------
# Public: compare
# ---------------------------------------------------------------------------


def compare_manifests(old: Dict[str, Any], new: Dict[str, Any]) -> CompatibilityReport:
    """Compare two manifests and classify each change as breaking or additive."""
    report = CompatibilityReport()
    covered: _Coverage = {}
    _compare_classes(old.get("api", {}).get("classes", []), new.get("api", {}).get("classes", []), report, covered)
    _compare_functions(
        "", old.get("api", {}).get("functions", []), new.get("api", {}).get("functions", []), report, covered
    )
    _compare_enums("", old.get("api", {}).get("enums", []), new.get("api", {}).get("enums", []), report)
    _compare_transformations(old.get("transformations", {}), new.get("transformations", {}), report, covered)
    return report


# ---------------------------------------------------------------------------
# Internal comparators
# ---------------------------------------------------------------------------

# An overload signature: emitted parameter types and return type (None for constructors).
_Signature = Tuple[Tuple[str, ...], Optional[str]]

# Old signatures that lost their exact match but stay callable through another
# overload, mapped to that overload.  Keys use the same shape as member
# transform keys, so the transformations diff can follow a signature to the
# overload that now serves it.
_Coverage = Dict[Tuple[Any, ...], Tuple[Any, ...]]


def _compare_classes(
    old_list: List[Dict],
    new_list: List[Dict],
    report: CompatibilityReport,
    covered: _Coverage,
) -> None:
    old_by_name = {c["name"]: c for c in old_list}
    new_by_name = {c["name"]: c for c in new_list}

    for name, old_cls in old_by_name.items():
        if name not in new_by_name:
            report.breaking_changes.append(f"Class '{name}' was removed")
            continue
        _compare_class_members(name, old_cls, new_by_name[name], report, covered)

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Class '{name}' was added")


def _compare_class_members(
    class_name: str,
    old_cls: Dict,
    new_cls: Dict,
    report: CompatibilityReport,
    covered: _Coverage,
) -> None:
    # Transform entries name their class by binding name, not by the dotted label.
    owner = old_cls["name"]
    _compare_bases(class_name, old_cls.get("bases", []), new_cls.get("bases", []), report)
    for params, via in _compare_constructors(
        class_name, old_cls.get("constructors", []), new_cls.get("constructors", []), report
    ).items():
        covered[("constructor", owner, params)] = ("constructor", owner, via)
    for (name, is_static, params), via in _compare_methods(
        class_name, old_cls.get("methods", []), new_cls.get("methods", []), report
    ).items():
        covered[("method", owner, name, params, is_static)] = ("method", owner, name, via, is_static)
    _compare_fields(class_name, old_cls.get("fields", []), new_cls.get("fields", []), report)
    _compare_properties(class_name, old_cls.get("properties", []), new_cls.get("properties", []), report)
    _compare_enums(class_name, old_cls.get("enums", []), new_cls.get("enums", []), report)
    _compare_inner_classes(
        class_name, old_cls.get("inner_classes", []), new_cls.get("inner_classes", []), report, covered
    )


def _compare_bases(
    class_name: str,
    old_bases: List[str],
    new_bases: List[str],
    report: CompatibilityReport,
) -> None:
    old_set: Set[str] = set(old_bases)
    new_set: Set[str] = set(new_bases)
    for base in old_set - new_set:
        report.breaking_changes.append(f"Class '{class_name}' removed base '{base}'")
    for base in new_set - old_set:
        report.additive_changes.append(f"Class '{class_name}' added base '{base}'")


def _compare_inner_classes(
    parent_class: str,
    old_list: List[Dict],
    new_list: List[Dict],
    report: CompatibilityReport,
    covered: _Coverage,
) -> None:
    old_by_name = {c["name"]: c for c in old_list}
    new_by_name = {c["name"]: c for c in new_list}
    for name, old_c in old_by_name.items():
        label = f"{parent_class}.{name}"
        if name not in new_by_name:
            report.breaking_changes.append(f"Inner class '{label}' was removed")
        else:
            _compare_class_members(label, old_c, new_by_name[name], report, covered)
    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Inner class '{parent_class}.{name}' was added")


def _signature_label(label: str, sig: _Signature) -> str:
    params_str = ", ".join(sig[0])
    return_str = f" -> {sig[1]}" if sig[1] is not None else ""
    return f"{label}({params_str}){return_str}"


def _arity_coverage(
    params: Tuple[str, ...],
    min_arity: Optional[int],
    candidates: List[Tuple[Tuple[str, ...], Optional[int]]],
) -> Dict[int, Optional[Tuple[str, ...]]]:
    """Map every arity an old signature accepts to the first candidate that still accepts it.

    A candidate serves ``k`` arguments when it starts with the same ``k``
    parameter types, has at least ``k`` parameters and needs at most ``k``
    arguments: the extra trailing parameters are defaulted, so every existing
    ``k``-argument call still resolves.  An old signature without ``min_arity``
    (legacy manifest) only claims its full arity; a candidate without it is
    assumed to need every parameter.
    """
    lowest = len(params) if min_arity is None else min_arity
    coverage: Dict[int, Optional[Tuple[str, ...]]] = {}
    for k in range(lowest, len(params) + 1):
        coverage[k] = next(
            (
                c
                for c, c_min in candidates
                if len(c) >= k and (len(c) if c_min is None else c_min) <= k and c[:k] == params[:k]
            ),
            None,
        )
    return coverage


def _compare_overloads(
    kind: str,
    label: str,
    old_sigs: Dict[_Signature, Optional[int]],
    new_sigs: Dict[_Signature, Optional[int]],
    removed: str,
    added: str,
    report: CompatibilityReport,
) -> Dict[Tuple[str, ...], Tuple[str, ...]]:
    """Diff one overload set, mapping each value to its ``min_arity``.

    An old signature only breaks callers when some arity it accepted is served
    by no new overload with the same leading parameter types and return type,
    so gaining trailing defaulted parameters, merging overloads into one
    defaulted signature, or splitting a default into overloads is not breaking.

    Returns the old parameter lists that lost their exact match but stay fully
    callable, mapped to the overload that serves their full arity.
    """
    covered: Dict[Tuple[str, ...], Tuple[str, ...]] = {}
    serving: Set[_Signature] = set()

    for sig in sorted(old_sigs):
        params, return_type = sig
        old_min = old_sigs[sig]
        # The exact match comes first so it is the preferred server of every arity.
        candidates = sorted(
            ((p, m) for (p, r), m in new_sigs.items() if r == return_type),
            key=lambda c: (c[0] != params, c[0]),
        )

        if sig in new_sigs:
            new_min = new_sigs[sig]
            # None means the manifest predates min_arity and simply does not say;
            # comparing against a guess would report a spurious change for every
            # defaulted parameter the first time an old manifest meets new code.
            if old_min is None or new_min is None:
                continue
            params_str = ", ".join(params)
            uncovered = [k for k, c in _arity_coverage(params, old_min, candidates).items() if c is None]
            if uncovered:
                report.breaking_changes.append(
                    f"{kind} '{label}({params_str})' no longer accepts {uncovered[0]} argument(s): "
                    f"a parameter default was removed (minimum arity {old_min} -> {new_min})"
                )
            elif new_min < old_min:
                report.additive_changes.append(
                    f"{kind} '{label}({params_str})' now accepts {new_min} argument(s): "
                    f"a parameter default was added (minimum arity {old_min} -> {new_min})"
                )
            continue

        coverage = _arity_coverage(params, old_min, candidates)
        servers = [c for c in coverage.values() if c is not None]
        if len(servers) < len(coverage):
            report.breaking_changes.append(f"{kind} '{_signature_label(label, sig)}' {removed}")
            continue
        # Arity order, so the last server is the one taking the full argument list.
        covered[params] = servers[-1]
        via = list(dict.fromkeys(servers))
        serving.update((p, return_type) for p in via)
        via_str = ", ".join(f"'{_signature_label(label, (p, return_type))}'" for p in via)
        report.additive_changes.append(
            f"{kind} '{_signature_label(label, sig)}' is still callable via {via_str} (defaulted parameter(s) added)"
        )

    for sig in sorted(new_sigs.keys() - old_sigs.keys()):
        if sig not in serving:
            report.additive_changes.append(f"{kind} '{_signature_label(label, sig)}' {added}")

    return covered


def _compare_constructors(
    class_name: str,
    old_ctors: List[Any],
    new_ctors: List[Any],
    report: CompatibilityReport,
) -> Dict[Tuple[str, ...], Tuple[str, ...]]:
    # Manifests written before min_arity existed store each constructor as a bare
    # list of parameter types; normalise both shapes to (params, min_arity|None).
    def _normalise(ctors: List[Any]) -> Dict[_Signature, Optional[int]]:
        result: Dict[_Signature, Optional[int]] = {}
        for c in ctors:
            if isinstance(c, dict):
                result[(tuple(c["params"]), None)] = c.get("min_arity")
            else:
                result[(tuple(c), None)] = None
        return result

    return _compare_overloads(
        "Constructor", class_name, _normalise(old_ctors), _normalise(new_ctors), "was removed", "was added", report
    )


def _compare_methods(
    class_name: str,
    old_methods: List[Dict],
    new_methods: List[Dict],
    report: CompatibilityReport,
) -> Dict[Tuple[str, bool, Tuple[str, ...]], Tuple[str, ...]]:
    # Group by (name, is_static) → {(params_tuple, return_type): min_arity}
    def _group(methods: List[Dict]) -> Dict[Tuple[str, bool], Dict[_Signature, Optional[int]]]:
        groups: Dict[Tuple[str, bool], Dict[_Signature, Optional[int]]] = {}
        for m in methods:
            key = (m["name"], m["is_static"])
            sig = (tuple(m["params"]), m["return_type"])
            groups.setdefault(key, {})[sig] = m.get("min_arity")
        return groups

    prefix = f"{class_name}." if class_name else ""
    old_groups = _group(old_methods)
    new_groups = _group(new_methods)
    covered: Dict[Tuple[str, bool, Tuple[str, ...]], Tuple[str, ...]] = {}

    for key, old_sigs in old_groups.items():
        name, is_static = key
        label = f"{'static ' if is_static else ''}{prefix}{name}"
        if key not in new_groups:
            report.breaking_changes.append(f"Method '{label}' was removed")
            continue
        group_covered = _compare_overloads(
            "Method", label, old_sigs, new_groups[key], "signature was removed or changed", "overload was added", report
        )
        for params, via in group_covered.items():
            covered[(name, is_static, params)] = via

    for key in new_groups:
        if key not in old_groups:
            name, is_static = key
            label = f"{'static ' if is_static else ''}{prefix}{name}"
            report.additive_changes.append(f"Method '{label}' was added")

    return covered


def _compare_fields(
    class_name: str,
    old_fields: List[Dict],
    new_fields: List[Dict],
    report: CompatibilityReport,
) -> None:
    old_by_name = {f["name"]: f for f in old_fields}
    new_by_name = {f["name"]: f for f in new_fields}
    prefix = f"{class_name}." if class_name else ""

    for name, old_f in old_by_name.items():
        label = f"{prefix}{name}"
        if name not in new_by_name:
            report.breaking_changes.append(f"Field '{label}' was removed")
            continue
        new_f = new_by_name[name]
        if old_f["type"] != new_f["type"]:
            report.breaking_changes.append(f"Field '{label}' type changed: {old_f['type']} -> {new_f['type']}")
        if old_f["is_const"] != new_f["is_const"]:
            report.breaking_changes.append(
                f"Field '{label}' const qualifier changed: {old_f['is_const']} -> {new_f['is_const']}"
            )
        old_read_only = old_f.get("read_only", old_f["is_const"])
        new_read_only = new_f.get("read_only", new_f["is_const"])
        if old_read_only != new_read_only:
            message = f"Field '{label}' read-only changed: {old_read_only} -> {new_read_only}"
            # Becoming writable keeps every read working; with a type change the
            # field is already reported as breaking above.
            if old_read_only and old_f["type"] == new_f["type"]:
                report.additive_changes.append(message)
            else:
                report.breaking_changes.append(message)

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Field '{prefix}{name}' was added")


def _compare_properties(
    class_name: str,
    old_properties: List[Dict],
    new_properties: List[Dict],
    report: CompatibilityReport,
) -> None:
    old_by_name = {p["name"]: p for p in old_properties}
    new_by_name = {p["name"]: p for p in new_properties}
    prefix = f"{class_name}." if class_name else ""

    for name, old_p in old_by_name.items():
        label = f"{prefix}{name}"
        if name not in new_by_name:
            report.breaking_changes.append(f"Property '{label}' was removed")
            continue
        new_p = new_by_name[name]
        if old_p["type"] != new_p["type"]:
            report.breaking_changes.append(f"Property '{label}' type changed: {old_p['type']} -> {new_p['type']}")
        if old_p["getter"] != new_p["getter"]:
            report.breaking_changes.append(f"Property '{label}' getter changed: {old_p['getter']} -> {new_p['getter']}")
        # A setter appearing is what makes a read-only property writable; that is
        # reported once, as the read-only change below.
        if old_p["setter"] != new_p["setter"] and old_p["setter"] is not None:
            report.breaking_changes.append(f"Property '{label}' setter changed: {old_p['setter']} -> {new_p['setter']}")
        if old_p["read_only"] != new_p["read_only"]:
            message = f"Property '{label}' read-only changed: {old_p['read_only']} -> {new_p['read_only']}"
            if old_p["read_only"]:
                report.additive_changes.append(message)
            else:
                report.breaking_changes.append(message)

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Property '{prefix}{name}' was added")


def _compare_functions(
    prefix: str,
    old_fns: List[Dict],
    new_fns: List[Dict],
    report: CompatibilityReport,
    covered: _Coverage,
) -> None:
    def _group(fns: List[Dict]) -> Dict[str, Dict[_Signature, Optional[int]]]:
        groups: Dict[str, Dict[_Signature, Optional[int]]] = {}
        for f in fns:
            sig = (tuple(f["params"]), f["return_type"])
            groups.setdefault(f["name"], {})[sig] = f.get("min_arity")
        return groups

    old_groups = _group(old_fns)
    new_groups = _group(new_fns)
    p = f"{prefix}." if prefix else ""

    for name, old_sigs in old_groups.items():
        label = f"{p}{name}"
        if name not in new_groups:
            report.breaking_changes.append(f"Function '{label}' was removed")
            continue
        group_covered = _compare_overloads(
            "Function",
            label,
            old_sigs,
            new_groups[name],
            "signature was removed or changed",
            "overload was added",
            report,
        )
        for params, via in group_covered.items():
            covered[("function", name, params)] = ("function", name, via)

    for name in new_groups:
        if name not in old_groups:
            report.additive_changes.append(f"Function '{p}{name}' was added")


def _compare_enums(
    parent: str,
    old_enums: List[Dict],
    new_enums: List[Dict],
    report: CompatibilityReport,
) -> None:
    old_by_name = {e["name"]: e for e in old_enums}
    new_by_name = {e["name"]: e for e in new_enums}
    prefix = f"{parent}." if parent else ""

    for name, old_e in old_by_name.items():
        label = f"{prefix}{name}"
        if name not in new_by_name:
            report.breaking_changes.append(f"Enum '{label}' was removed")
            continue
        new_e = new_by_name[name]
        old_values = {v["name"]: v["value"] for v in old_e["values"]}
        new_values = {v["name"]: v["value"] for v in new_e["values"]}
        for vname, vval in old_values.items():
            if vname not in new_values:
                report.breaking_changes.append(f"Enum value '{label}.{vname}' was removed")
            elif vval != new_values[vname]:
                report.breaking_changes.append(
                    f"Enum value '{label}.{vname}' integer changed: {vval} -> {new_values[vname]}"
                )
        for vname in new_values:
            if vname not in old_values:
                report.additive_changes.append(f"Enum value '{label}.{vname}' was added")

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Enum '{prefix}{name}' was added")


def _compare_transformation_list(
    old_list: List[Dict[str, Any]],
    new_list: List[Dict[str, Any]],
    key_fn: Callable[[Dict[str, Any]], Any],
    label_fn: Callable[[Dict[str, Any]], str],
    report: CompatibilityReport,
) -> None:
    old_by_key = {key_fn(item): item for item in old_list}
    new_by_key = {key_fn(item): item for item in new_list}
    for key, old_item in old_by_key.items():
        if key not in new_by_key:
            report.breaking_changes.append(f"Binding {label_fn(old_item)} was removed")
        elif old_item != new_by_key[key]:
            report.breaking_changes.append(f"Binding {label_fn(old_item)} was changed")
    for key, new_item in new_by_key.items():
        if key not in old_by_key:
            report.additive_changes.append(f"Binding {label_fn(new_item)} was added")


def _member_transform_body(entry: Dict[str, Any], arity: Optional[int] = None) -> Dict[str, Any]:
    """Return what a member transform does, without where it sits.

    ``params`` identifies the signature and a constructor's ``index`` is only its
    position among constructors, so neither is compared.  With *arity*, parameter
    transforms at or past it are dropped as well: they belong to parameters the
    old signature did not have.  Parameter ``index`` also counts suppressed
    parameters, so that cut is approximate around them; both sides get the same.
    """
    body = {k: v for k, v in entry.items() if k not in ("params", "index")}
    if arity is not None:
        parameters = [p for p in body.pop("parameters", []) if p["index"] < arity]
        if parameters:
            body["parameters"] = parameters
    return body


def _compare_member_transforms(
    old_list: List[Dict[str, Any]],
    new_list: List[Dict[str, Any]],
    key_fn: Callable[[Dict[str, Any]], Tuple[Any, ...]],
    label_fn: Callable[[Dict[str, Any]], str],
    covered: _Coverage,
    report: CompatibilityReport,
) -> None:
    """Diff per-member transforms: new ones are additive, changed or removed ones breaking.

    An entry whose signature is still callable through another overload (see
    ``_compare_overloads``) is compared with that overload's entry instead.
    """
    old_by_key = {key_fn(item): item for item in old_list}
    new_by_key = {key_fn(item): item for item in new_list}
    serving: Set[Tuple[Any, ...]] = set()

    for key, old_item in old_by_key.items():
        if key in new_by_key:
            if _member_transform_body(old_item) != _member_transform_body(new_by_key[key]):
                report.breaking_changes.append(f"Binding {label_fn(old_item)} was changed")
            continue
        via = covered.get(key)
        if via is None or via not in new_by_key:
            report.breaking_changes.append(f"Binding {label_fn(old_item)} was removed")
            continue
        serving.add(via)
        arity = len(old_item["params"])
        if _member_transform_body(old_item, arity) != _member_transform_body(new_by_key[via], arity):
            report.breaking_changes.append(f"Binding {label_fn(old_item)} was changed")

    for key, new_item in new_by_key.items():
        if key not in old_by_key and key not in serving:
            report.additive_changes.append(f"Binding {label_fn(new_item)} was added")


_CLASS_MEMBER_TRANSFORMS = ("constructors", "methods", "fields", "enums")


def _compare_class_transforms(
    old_list: List[Dict[str, Any]],
    new_list: List[Dict[str, Any]],
    covered: _Coverage,
    report: CompatibilityReport,
) -> None:
    old_by_name = {c["qualified_name"]: c for c in old_list}
    new_by_name = {c["qualified_name"]: c for c in new_list}

    for qualified_name, old_cls in old_by_name.items():
        new_cls: Dict[str, Any] = new_by_name.get(qualified_name, {})
        old_meta = {k: v for k, v in old_cls.items() if k not in _CLASS_MEMBER_TRANSFORMS}
        new_meta = {k: v for k, v in new_cls.items() if k not in _CLASS_MEMBER_TRANSFORMS}
        if qualified_name not in new_by_name:
            # The entry also vanishes when its last member transform goes away;
            # only class-level metadata makes that a removal of its own.
            if old_meta.keys() - {"name", "qualified_name"}:
                report.breaking_changes.append(f"Binding class transform '{qualified_name}' was removed")
        elif old_meta != new_meta:
            report.breaking_changes.append(f"Binding class transform '{qualified_name}' was changed")

        # Field transforms only carry read_only and type, which the API field
        # diff already classifies (relaxing read-only is additive there).
        _compare_member_transforms(
            old_cls.get("constructors", []),
            new_cls.get("constructors", []),
            key_fn=lambda c: ("constructor", c["class"], tuple(c["params"])),
            label_fn=lambda c: f"constructor transform '{c['class']}({', '.join(c['params'])})'",
            covered=covered,
            report=report,
        )
        _compare_member_transforms(
            old_cls.get("methods", []),
            new_cls.get("methods", []),
            key_fn=lambda m: ("method", m["class"], m["name"], tuple(m["params"]), m["is_static"]),
            label_fn=lambda m: (
                f"method transform '{'static ' if m['is_static'] else ''}"
                f"{m['class']}.{m['name']}({', '.join(m['params'])})'"
            ),
            covered=covered,
            report=report,
        )
        _compare_member_transforms(
            old_cls.get("enums", []),
            new_cls.get("enums", []),
            key_fn=lambda e: ("enum", e["parent"], e["name"]),
            label_fn=lambda e: f"enum transform '{e['parent']}.{e['name']}'",
            covered=covered,
            report=report,
        )

    for qualified_name in new_by_name:
        if qualified_name not in old_by_name:
            report.additive_changes.append(f"Binding class transform '{qualified_name}' was added")


def _compare_transformations(
    old_transformations: Dict[str, Any],
    new_transformations: Dict[str, Any],
    report: CompatibilityReport,
    covered: _Coverage,
) -> None:
    if old_transformations.get("code_injections") != new_transformations.get("code_injections"):
        report.breaking_changes.append("Module code injections changed")

    _compare_transformation_list(
        old_transformations.get("exception_registrations", []),
        new_transformations.get("exception_registrations", []),
        key_fn=lambda er: (er["cpp_exception_type"], er["target_exception_name"]),
        label_fn=lambda er: f"exception registration '{er['cpp_exception_type']}'",
        report=report,
    )
    _compare_class_transforms(
        old_transformations.get("classes", []),
        new_transformations.get("classes", []),
        covered,
        report,
    )
    _compare_member_transforms(
        old_transformations.get("functions", []),
        new_transformations.get("functions", []),
        key_fn=lambda f: ("function", f["name"], tuple(f["params"])),
        label_fn=lambda f: f"function transform '{f['name']}'",
        covered=covered,
        report=report,
    )
    _compare_transformation_list(
        old_transformations.get("enums", []),
        new_transformations.get("enums", []),
        key_fn=lambda e: e["name"],
        label_fn=lambda e: f"enum transform '{e['name']}'",
        report=report,
    )
