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
from typing import Any, Dict, List, Optional, Set, Tuple

from tsujikiri.tir import TIRClass, TIRModule


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


def _canonical_injections(injections: List[Any]) -> List[Dict[str, str]]:
    return [{"position": c.position, "code": c.code} for c in injections]


def _metadata(pairs: List[Tuple[str, Any, Any]]) -> Dict[str, Any]:
    return {name: value for name, value, default in pairs if value != default}


def _canonical_class(ir_class: TIRClass) -> Dict[str, Any]:
    name = ir_class.binding_name

    constructors = sorted([tuple(_emitted_param_types(c.parameters)) for c in ir_class.constructors if c.emit])

    methods: List[Dict[str, Any]] = []
    for m in ir_class.methods:
        if not m.emit:
            continue
        methods.append(
            {
                "name": m.binding_name,
                "params": _emitted_param_types(m.parameters),
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

    return {
        "name": name,
        "constructors": [list(sig) for sig in constructors],
        "methods": methods,
        "fields": fields,
        "properties": properties,
        "enums": enums,
    }


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

    properties = sorted(
        [_canonical_property(p) for p in ir_class.properties if p.emit],
        key=lambda p: p["name"],
    )
    if properties:
        data["properties"] = properties

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
    with open(path, "w", encoding="utf-8") as f:
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
    _compare_classes(old.get("api", {}).get("classes", []), new.get("api", {}).get("classes", []), report)
    _compare_functions("", old.get("api", {}).get("functions", []), new.get("api", {}).get("functions", []), report)
    _compare_enums("", old.get("api", {}).get("enums", []), new.get("api", {}).get("enums", []), report)
    _compare_transformations(old.get("transformations", {}), new.get("transformations", {}), report)
    return report


# ---------------------------------------------------------------------------
# Internal comparators
# ---------------------------------------------------------------------------


def _compare_classes(
    old_list: List[Dict],
    new_list: List[Dict],
    report: CompatibilityReport,
) -> None:
    old_by_name = {c["name"]: c for c in old_list}
    new_by_name = {c["name"]: c for c in new_list}

    for name, old_cls in old_by_name.items():
        if name not in new_by_name:
            report.breaking_changes.append(f"Class '{name}' was removed")
            continue
        _compare_class_members(name, old_cls, new_by_name[name], report)

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Class '{name}' was added")


def _compare_class_members(
    class_name: str,
    old_cls: Dict,
    new_cls: Dict,
    report: CompatibilityReport,
) -> None:
    _compare_constructors(class_name, old_cls.get("constructors", []), new_cls.get("constructors", []), report)
    _compare_methods(class_name, old_cls.get("methods", []), new_cls.get("methods", []), report)
    _compare_fields(class_name, old_cls.get("fields", []), new_cls.get("fields", []), report)
    _compare_properties(class_name, old_cls.get("properties", []), new_cls.get("properties", []), report)
    _compare_enums(class_name, old_cls.get("enums", []), new_cls.get("enums", []), report)


def _compare_constructors(
    class_name: str,
    old_ctors: List[List[str]],
    new_ctors: List[List[str]],
    report: CompatibilityReport,
) -> None:
    old_sigs: Set[Tuple] = {tuple(p) for p in old_ctors}
    new_sigs: Set[Tuple] = {tuple(p) for p in new_ctors}

    for sig in old_sigs - new_sigs:
        params = ", ".join(sig)
        report.breaking_changes.append(f"Constructor '{class_name}({params})' was removed")
    for sig in new_sigs - old_sigs:
        params = ", ".join(sig)
        report.additive_changes.append(f"Constructor '{class_name}({params})' was added")


def _compare_methods(
    class_name: str,
    old_methods: List[Dict],
    new_methods: List[Dict],
    report: CompatibilityReport,
) -> None:
    # Group by (name, is_static) → set of (params_tuple, return_type)
    def _group(methods: List[Dict]) -> Dict[Tuple, Set[Tuple]]:
        groups: Dict[Tuple, Set[Tuple]] = {}
        for m in methods:
            key = (m["name"], m["is_static"])
            sig = (tuple(m["params"]), m["return_type"])
            groups.setdefault(key, set()).add(sig)
        return groups

    prefix = f"{class_name}." if class_name else ""
    old_groups = _group(old_methods)
    new_groups = _group(new_methods)

    for key, old_sigs in old_groups.items():
        name, is_static = key
        label = f"{'static ' if is_static else ''}{prefix}{name}"
        if key not in new_groups:
            report.breaking_changes.append(f"Method '{label}' was removed")
            continue
        new_sigs = new_groups[key]
        for sig in old_sigs - new_sigs:
            params_str = ", ".join(sig[0])
            report.breaking_changes.append(
                f"Method '{label}({params_str}) -> {sig[1]}' signature was removed or changed"
            )
        for sig in new_sigs - old_sigs:
            params_str = ", ".join(sig[0])
            report.additive_changes.append(f"Method '{label}({params_str}) -> {sig[1]}' overload was added")

    for key in new_groups:
        if key not in old_groups:
            name, is_static = key
            label = f"{'static ' if is_static else ''}{prefix}{name}"
            report.additive_changes.append(f"Method '{label}' was added")


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
            report.breaking_changes.append(f"Field '{label}' read-only changed: {old_read_only} -> {new_read_only}")

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
        if old_p["setter"] != new_p["setter"]:
            report.breaking_changes.append(f"Property '{label}' setter changed: {old_p['setter']} -> {new_p['setter']}")
        if old_p["read_only"] != new_p["read_only"]:
            report.breaking_changes.append(
                f"Property '{label}' read-only changed: {old_p['read_only']} -> {new_p['read_only']}"
            )

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Property '{prefix}{name}' was added")


def _compare_functions(
    prefix: str,
    old_fns: List[Dict],
    new_fns: List[Dict],
    report: CompatibilityReport,
) -> None:
    def _group(fns: List[Dict]) -> Dict[str, Set[Tuple]]:
        groups: Dict[str, Set[Tuple]] = {}
        for f in fns:
            sig = (tuple(f["params"]), f["return_type"])
            groups.setdefault(f["name"], set()).add(sig)
        return groups

    old_groups = _group(old_fns)
    new_groups = _group(new_fns)
    p = f"{prefix}." if prefix else ""

    for name, old_sigs in old_groups.items():
        label = f"{p}{name}"
        if name not in new_groups:
            report.breaking_changes.append(f"Function '{label}' was removed")
            continue
        new_sigs = new_groups[name]
        for sig in old_sigs - new_sigs:
            params_str = ", ".join(sig[0])
            report.breaking_changes.append(
                f"Function '{label}({params_str}) -> {sig[1]}' signature was removed or changed"
            )
        for sig in new_sigs - old_sigs:
            params_str = ", ".join(sig[0])
            report.additive_changes.append(f"Function '{label}({params_str}) -> {sig[1]}' overload was added")

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


def _compare_transformations(
    old_transformations: Dict[str, Any], new_transformations: Dict[str, Any], report: CompatibilityReport
) -> None:
    if old_transformations != new_transformations:
        report.breaking_changes.append("Transformed binding metadata changed")
