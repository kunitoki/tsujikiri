"""API manifest: compute, compare, save, and load binding surface snapshots.

A manifest captures the emitted binding surface of an IRModule as a
deterministic JSON document and derives a SHA-256 version hash from it.
Two manifests can be compared to classify API changes as additive (safe)
or breaking (scripts that rely on the old surface may break at runtime).
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
# Canonical builders (format-agnostic, raw C++ types, emit=True only)
# ---------------------------------------------------------------------------


def _canonical_class(ir_class: TIRClass) -> Dict[str, Any]:
    name = ir_class.binding_name

    constructors = sorted([tuple(p.type_spelling for p in c.parameters) for c in ir_class.constructors if c.emit])

    methods: List[Dict[str, Any]] = []
    for m in ir_class.methods:
        if not m.emit:
            continue
        methods.append(
            {
                "name": m.binding_name,
                "params": [p.type_spelling for p in m.parameters],
                "return_type": m.return_type,
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
                "type": f.type_spelling,
                "is_const": f.is_const,
            }
        )
    fields.sort(key=lambda f: f["name"])

    enums = sorted(
        [_canonical_enum_entry(e) for e in ir_class.enums if e.emit],
        key=lambda e: e["name"],
    )

    return {
        "name": name,
        "constructors": [list(sig) for sig in constructors],
        "methods": methods,
        "fields": fields,
        "enums": enums,
    }


def _canonical_enum_entry(enum) -> Dict[str, Any]:
    values = sorted(
        [{"name": v.name, "value": v.value} for v in enum.values if v.emit],
        key=lambda v: v["name"],
    )
    return {"name": enum.name, "values": values}


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
                "params": [p.type_spelling for p in fn.parameters],
                "return_type": fn.return_type,
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

    return {
        "module": module.name,
        "version": "0.0.0",
        "api": api,
    }


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

    for name in new_by_name:
        if name not in old_by_name:
            report.additive_changes.append(f"Field '{prefix}{name}' was added")


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
