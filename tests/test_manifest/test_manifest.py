"""Tests for the manifest module: compute, compare, save, load."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tsujikiri.ir import (
    IRClass,
    IRConstructor,
    IREnum,
    IREnumValue,
    IRField,
    IRFunction,
    IRMethod,
    IRModule,
    IRParameter,
)
from tsujikiri.manifest import (
    CompatibilityReport,
    compare_manifests,
    compute_manifest,
    load_manifest,
    save_manifest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_module(
    classes=None,
    functions=None,
    enums=None,
    name="testmod",
) -> IRModule:
    m = IRModule(name=name)
    for c in (classes or []):
        m.classes.append(c)
        m.class_by_name[c.qualified_name] = c
    m.functions.extend(functions or [])
    m.enums.extend(enums or [])
    return m


def _cls(
    name="Calculator",
    methods=None,
    constructors=None,
    fields=None,
    enums=None,
    emit=True,
) -> IRClass:
    return IRClass(
        name=name,
        qualified_name=f"testmod::{name}",
        namespace="testmod",
        methods=methods or [],
        constructors=constructors or [],
        fields=fields or [],
        enums=enums or [],
        emit=emit,
    )


def _method(name, params=None, return_type="void", is_static=False, emit=True) -> IRMethod:
    return IRMethod(
        name=name,
        spelling=name,
        qualified_name=f"testmod::{name}",
        return_type=return_type,
        parameters=[IRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        is_static=is_static,
        emit=emit,
    )


def _ctor(params=None, emit=True) -> IRConstructor:
    return IRConstructor(
        parameters=[IRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        emit=emit,
    )


def _field(name, type_spelling="int", is_const=False, emit=True) -> IRField:
    return IRField(name=name, type_spelling=type_spelling, is_const=is_const, emit=emit)


def _fn(name, params=None, return_type="void", emit=True) -> IRFunction:
    return IRFunction(
        name=name,
        qualified_name=f"testmod::{name}",
        namespace="testmod",
        return_type=return_type,
        parameters=[IRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        emit=emit,
    )


def _enum(name, values=None, emit=True) -> IREnum:
    return IREnum(
        name=name,
        qualified_name=f"testmod::{name}",
        values=[IREnumValue(name=v, value=i) for i, v in enumerate(values or [])],
        emit=emit,
    )


# ---------------------------------------------------------------------------
# compute_manifest: determinism
# ---------------------------------------------------------------------------

class TestComputeManifest:
    def test_same_module_same_version(self):
        mod = _make_module(classes=[_cls(methods=[_method("add", ["int", "int"], "int")])])
        m1 = compute_manifest(mod)
        m2 = compute_manifest(mod)
        assert m1["version"] == m2["version"]

    def test_version_is_sha256_hex(self):
        mod = _make_module()
        m = compute_manifest(mod)
        assert len(m["version"]) == 64
        assert all(c in "0123456789abcdef" for c in m["version"])

    def test_module_name_in_manifest(self):
        mod = _make_module(name="mylib")
        m = compute_manifest(mod)
        assert m["module"] == "mylib"

    def test_empty_module_has_version(self):
        mod = _make_module()
        m = compute_manifest(mod)
        assert "version" in m
        assert "api" in m

    def test_emit_false_class_excluded(self):
        mod_with = _make_module(classes=[_cls(emit=True)])
        mod_without = _make_module(classes=[_cls(emit=False)])
        assert compute_manifest(mod_with)["version"] != compute_manifest(mod_without)["version"]
        assert compute_manifest(mod_without)["api"]["classes"] == []

    def test_emit_false_method_excluded(self):
        mod = _make_module(classes=[_cls(methods=[
            _method("add", ["int"], emit=True),
            _method("hidden", emit=False),
        ])])
        m = compute_manifest(mod)
        methods = m["api"]["classes"][0]["methods"]
        assert all(m["name"] == "add" for m in methods)

    def test_emit_false_field_excluded(self):
        mod = _make_module(classes=[_cls(fields=[
            _field("visible", emit=True),
            _field("hidden", emit=False),
        ])])
        m = compute_manifest(mod)
        fields = m["api"]["classes"][0]["fields"]
        assert len(fields) == 1
        assert fields[0]["name"] == "visible"

    def test_emit_false_function_excluded(self):
        mod = _make_module(functions=[
            _fn("active", ["int"], "int", emit=True),
            _fn("hidden", emit=False),
        ])
        m = compute_manifest(mod)
        assert len(m["api"]["functions"]) == 1
        assert m["api"]["functions"][0]["name"] == "active"

    def test_rename_used_as_binding_name(self):
        m = IRMethod(
            name="getX", spelling="getX", qualified_name="C::getX",
            return_type="int", rename="x", emit=True,
        )
        mod = _make_module(classes=[_cls(methods=[m])])
        manifest = compute_manifest(mod)
        assert manifest["api"]["classes"][0]["methods"][0]["name"] == "x"

    def test_version_changes_when_method_param_added(self):
        mod_v1 = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        mod_v2 = _make_module(classes=[_cls(methods=[_method("add", ["int", "double"], "int")])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_method_removed(self):
        mod_v1 = _make_module(classes=[_cls(methods=[_method("add"), _method("sub")])])
        mod_v2 = _make_module(classes=[_cls(methods=[_method("add")])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_return_type_changes(self):
        mod_v1 = _make_module(classes=[_cls(methods=[_method("get", return_type="int")])])
        mod_v2 = _make_module(classes=[_cls(methods=[_method("get", return_type="double")])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_constructor_changes(self):
        mod_v1 = _make_module(classes=[_cls(constructors=[_ctor(["int"])])])
        mod_v2 = _make_module(classes=[_cls(constructors=[_ctor(["int", "double"])])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_field_type_changes(self):
        mod_v1 = _make_module(classes=[_cls(fields=[_field("x", "int")])])
        mod_v2 = _make_module(classes=[_cls(fields=[_field("x", "double")])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_enum_value_added(self):
        mod_v1 = _make_module(enums=[_enum("Color", ["Red", "Green"])])
        mod_v2 = _make_module(enums=[_enum("Color", ["Red", "Green", "Blue"])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_changes_when_enum_value_removed(self):
        mod_v1 = _make_module(enums=[_enum("Color", ["Red", "Green", "Blue"])])
        mod_v2 = _make_module(enums=[_enum("Color", ["Red", "Green"])])
        assert compute_manifest(mod_v1)["version"] != compute_manifest(mod_v2)["version"]

    def test_version_stable_across_insertion_order(self):
        """Manifest version must be deterministic regardless of insertion order."""
        cls_a = _cls("Alpha", methods=[_method("foo")])
        cls_b = _cls("Beta", methods=[_method("bar")])
        mod1 = _make_module(classes=[cls_a, cls_b])
        mod2 = _make_module(classes=[cls_b, cls_a])
        assert compute_manifest(mod1)["version"] == compute_manifest(mod2)["version"]


# ---------------------------------------------------------------------------
# save_manifest / load_manifest
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        mod = _make_module(classes=[_cls(methods=[_method("add", ["int", "int"], "int")])])
        m = compute_manifest(mod)
        path = tmp_path / "api.json"
        save_manifest(m, path)
        loaded = load_manifest(path)
        assert loaded["version"] == m["version"]
        assert loaded["api"] == m["api"]

    def test_saved_file_is_valid_json(self, tmp_path):
        mod = _make_module()
        path = tmp_path / "api.json"
        save_manifest(compute_manifest(mod), path)
        with open(path) as f:
            parsed = json.load(f)
        assert "version" in parsed


# ---------------------------------------------------------------------------
# compare_manifests: additive changes
# ---------------------------------------------------------------------------

class TestCompareManifoldsAdditive:
    def _compare(self, old_mod, new_mod) -> CompatibilityReport:
        return compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))

    def test_no_changes_is_compatible(self):
        mod = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        r = self._compare(mod, mod)
        assert r.is_compatible
        assert not r.has_changes

    def test_new_class_is_additive(self):
        old = _make_module()
        new = _make_module(classes=[_cls("Widget")])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("Widget" in c for c in r.additive_changes)

    def test_new_method_is_additive(self):
        old = _make_module(classes=[_cls(methods=[_method("add")])])
        new = _make_module(classes=[_cls(methods=[_method("add"), _method("sub")])])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("sub" in c for c in r.additive_changes)

    def test_new_constructor_overload_is_additive(self):
        old = _make_module(classes=[_cls(constructors=[_ctor(["int"])])])
        new = _make_module(classes=[_cls(constructors=[_ctor(["int"]), _ctor(["int", "double"])])])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("int, double" in c for c in r.additive_changes)

    def test_new_field_is_additive(self):
        old = _make_module(classes=[_cls()])
        new = _make_module(classes=[_cls(fields=[_field("x")])])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("x" in c for c in r.additive_changes)

    def test_new_enum_is_additive(self):
        old = _make_module()
        new = _make_module(enums=[_enum("Color", ["Red"])])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("Color" in c for c in r.additive_changes)

    def test_new_enum_value_is_additive(self):
        old = _make_module(enums=[_enum("Color", ["Red"])])
        new = _make_module(enums=[_enum("Color", ["Red", "Green"])])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("Green" in c for c in r.additive_changes)

    def test_new_function_is_additive(self):
        old = _make_module()
        new = _make_module(functions=[_fn("compute", ["double"], "double")])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("compute" in c for c in r.additive_changes)


# ---------------------------------------------------------------------------
# compare_manifests: breaking changes
# ---------------------------------------------------------------------------

class TestCompareManifoldBreaking:
    def _compare(self, old_mod, new_mod) -> CompatibilityReport:
        return compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))

    def test_removed_class_is_breaking(self):
        old = _make_module(classes=[_cls("Widget")])
        new = _make_module()
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Widget" in c for c in r.breaking_changes)

    def test_method_param_count_change_is_breaking(self):
        old = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        new = _make_module(classes=[_cls(methods=[_method("add", ["int", "double"], "int")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("add" in c for c in r.breaking_changes)

    def test_method_param_type_change_is_breaking(self):
        old = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        new = _make_module(classes=[_cls(methods=[_method("add", ["double"], "int")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("add" in c for c in r.breaking_changes)

    def test_method_return_type_change_is_breaking(self):
        old = _make_module(classes=[_cls(methods=[_method("get", [], "int")])])
        new = _make_module(classes=[_cls(methods=[_method("get", [], "double")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("get" in c for c in r.breaking_changes)

    def test_method_removed_is_breaking(self):
        old = _make_module(classes=[_cls(methods=[_method("add"), _method("sub")])])
        new = _make_module(classes=[_cls(methods=[_method("add")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("sub" in c for c in r.breaking_changes)

    def test_constructor_signature_change_is_breaking(self):
        old = _make_module(classes=[_cls(constructors=[_ctor(["int"])])])
        new = _make_module(classes=[_cls(constructors=[_ctor(["int", "double"])])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Calculator(int)" in c for c in r.breaking_changes)

    def test_field_removed_is_breaking(self):
        old = _make_module(classes=[_cls(fields=[_field("x")])])
        new = _make_module(classes=[_cls()])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("x" in c for c in r.breaking_changes)

    def test_field_type_changed_is_breaking(self):
        old = _make_module(classes=[_cls(fields=[_field("x", "int")])])
        new = _make_module(classes=[_cls(fields=[_field("x", "double")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("x" in c for c in r.breaking_changes)

    def test_field_const_changed_is_breaking(self):
        old = _make_module(classes=[_cls(fields=[_field("x", is_const=False)])])
        new = _make_module(classes=[_cls(fields=[_field("x", is_const=True)])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("x" in c for c in r.breaking_changes)

    def test_enum_removed_is_breaking(self):
        old = _make_module(enums=[_enum("Color", ["Red"])])
        new = _make_module()
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Color" in c for c in r.breaking_changes)

    def test_enum_value_removed_is_breaking(self):
        old = _make_module(enums=[_enum("Color", ["Red", "Green"])])
        new = _make_module(enums=[_enum("Color", ["Red"])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Green" in c for c in r.breaking_changes)

    def test_enum_value_integer_changed_is_breaking(self):
        old_enum = IREnum(
            name="Color", qualified_name="testmod::Color",
            values=[IREnumValue(name="Red", value=0), IREnumValue(name="Green", value=1)],
        )
        new_enum = IREnum(
            name="Color", qualified_name="testmod::Color",
            values=[IREnumValue(name="Red", value=0), IREnumValue(name="Green", value=99)],
        )
        old = _make_module(enums=[old_enum])
        new = _make_module(enums=[new_enum])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Green" in c for c in r.breaking_changes)

    def test_function_removed_is_breaking(self):
        old = _make_module(functions=[_fn("compute", ["double"], "double")])
        new = _make_module()
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("compute" in c for c in r.breaking_changes)

    def test_function_signature_changed_is_breaking(self):
        old = _make_module(functions=[_fn("compute", ["double"], "double")])
        new = _make_module(functions=[_fn("compute", ["double", "double"], "double")])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("compute" in c for c in r.breaking_changes)

    def test_static_method_removed_is_breaking(self):
        old = _make_module(classes=[_cls(methods=[_method("max", ["int", "int"], "int", is_static=True)])])
        new = _make_module(classes=[_cls()])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("max" in c for c in r.breaking_changes)

    def test_method_renamed_is_breaking(self):
        """Changing the binding name breaks Lua scripts that used the old name."""
        old = _make_module(classes=[_cls(methods=[_method("getValue")])])
        new = _make_module(classes=[_cls(methods=[_method("get_value")])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("getValue" in c for c in r.breaking_changes)
        assert any("get_value" in c for c in r.additive_changes)

    def test_nested_class_enum_change_is_breaking(self):
        nested_old = _enum("Status", ["OK", "Error"])
        nested_new = _enum("Status", ["OK"])
        old = _make_module(classes=[_cls(enums=[nested_old])])
        new = _make_module(classes=[_cls(enums=[nested_new])])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Error" in c for c in r.breaking_changes)
