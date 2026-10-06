"""Tests for the manifest module: compute, compare, save, load."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, TypeVar
from unittest.mock import patch

import pytest

from tsujikiri.ir import IRCodeInjection, IRExceptionRegistration, IRProperty
from tsujikiri.tir import (
    TIRBase,
    TIRClass,
    TIRConstructor,
    TIREnum,
    TIREnumValue,
    TIRField,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
)
from tsujikiri.manifest import (
    CompatibilityReport,
    bump_semver,
    compare_manifests,
    compute_manifest,
    is_semver,
    load_manifest,
    save_manifest,
    suggest_version_bump,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(
    classes=None,
    functions=None,
    enums=None,
    name="testmod",
) -> TIRModule:
    m = TIRModule(name=name)
    for c in classes or []:
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
) -> TIRClass:
    return TIRClass(
        name=name,
        qualified_name=f"testmod::{name}",
        namespace="testmod",
        methods=methods or [],
        constructors=constructors or [],
        fields=fields or [],
        enums=enums or [],
        emit=emit,
    )


def _method(name, params=None, return_type="void", is_static=False, emit=True) -> TIRMethod:
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"testmod::{name}",
        return_type=return_type,
        parameters=[TIRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        is_static=is_static,
        emit=emit,
    )


def _ctor(params=None, emit=True) -> TIRConstructor:
    return TIRConstructor(
        parameters=[TIRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        emit=emit,
    )


def _field(name, type_spelling="int", is_const=False, emit=True) -> TIRField:
    return TIRField(name=name, type_spelling=type_spelling, is_const=is_const, emit=emit)


def _fn(name, params=None, return_type="void", emit=True) -> TIRFunction:
    return TIRFunction(
        name=name,
        qualified_name=f"testmod::{name}",
        namespace="testmod",
        return_type=return_type,
        parameters=[TIRParameter(name=f"p{i}", type_spelling=t) for i, t in enumerate(params or [])],
        emit=emit,
    )


def _enum(name, values=None, emit=True) -> TIREnum:
    return TIREnum(
        name=name,
        qualified_name=f"testmod::{name}",
        values=[TIREnumValue(name=v, value=i) for i, v in enumerate(values or [])],
        emit=emit,
    )


# ---------------------------------------------------------------------------
# compute_manifest: determinism
# ---------------------------------------------------------------------------


class TestComputeManifest:
    def test_module_name_in_manifest(self):
        mod = _make_module(name="mylib")
        m = compute_manifest(mod)
        assert m["module"] == "mylib"

    def test_empty_module_has_version(self):
        mod = _make_module()
        m = compute_manifest(mod)
        assert "version" in m
        assert "api" in m
        assert "transformations" not in m

    def test_emit_false_class_excluded(self):
        mod_with = _make_module(classes=[_cls(emit=True)])
        mod_without = _make_module(classes=[_cls(emit=False)])
        assert compute_manifest(mod_with)["api"]["classes"] != []
        assert compute_manifest(mod_without)["api"]["classes"] == []

    def test_emit_false_method_excluded(self):
        mod = _make_module(
            classes=[
                _cls(
                    methods=[
                        _method("add", ["int"], emit=True),
                        _method("hidden", emit=False),
                    ]
                )
            ]
        )
        m = compute_manifest(mod)
        methods = m["api"]["classes"][0]["methods"]
        assert all(m["name"] == "add" for m in methods)

    def test_emit_false_field_excluded(self):
        mod = _make_module(
            classes=[
                _cls(
                    fields=[
                        _field("visible", emit=True),
                        _field("hidden", emit=False),
                    ]
                )
            ]
        )
        m = compute_manifest(mod)
        fields = m["api"]["classes"][0]["fields"]
        assert len(fields) == 1
        assert fields[0]["name"] == "visible"

    def test_emit_false_function_excluded(self):
        mod = _make_module(
            functions=[
                _fn("active", ["int"], "int", emit=True),
                _fn("hidden", emit=False),
            ]
        )
        m = compute_manifest(mod)
        assert len(m["api"]["functions"]) == 1
        assert m["api"]["functions"][0]["name"] == "active"

    def test_rename_used_as_binding_name(self):
        m = TIRMethod(
            name="getX",
            spelling="getX",
            qualified_name="C::getX",
            return_type="int",
            rename="x",
            emit=True,
        )
        mod = _make_module(classes=[_cls(methods=[m])])
        manifest = compute_manifest(mod)
        assert manifest["api"]["classes"][0]["methods"][0]["name"] == "x"

    def test_transformed_method_signature_is_manifested(self):
        p0 = TIRParameter(name="value", type_spelling="int", type_override="float")
        p1 = TIRParameter(name="hidden", type_spelling="bool", emit=False)
        method = TIRMethod(
            name="convert",
            spelling="convert",
            qualified_name="C::convert",
            return_type="int",
            return_type_override="double",
            parameters=[p0, p1],
        )
        mod = _make_module(classes=[_cls(methods=[method])])

        manifest_method = compute_manifest(mod)["api"]["classes"][0]["methods"][0]

        assert manifest_method["params"] == ["float"]
        assert manifest_method["return_type"] == "double"

    def test_transformed_enum_names_are_manifested(self):
        enum = TIREnum(
            name="Color",
            qualified_name="testmod::Color",
            rename="Colour",
            values=[TIREnumValue(name="VeryRed", value=1, rename="red")],
        )
        mod = _make_module(enums=[enum])
        manifest_enum = compute_manifest(mod)["api"]["enums"][0]

        assert manifest_enum["name"] == "Colour"
        assert manifest_enum["values"][0]["name"] == "red"

    def test_code_injections_are_manifested(self):
        method = _method("add")
        method.code_injections.append(IRCodeInjection(position="end", code="// method end"))
        cls = _cls(methods=[method])
        cls.code_injections.append(IRCodeInjection(position="beginning", code="// class start"))
        mod = _make_module(classes=[cls])
        mod.code_injections.append(IRCodeInjection(position="beginning", code="// module start"))

        transformations = compute_manifest(mod)["transformations"]

        assert transformations["code_injections"] == [{"position": "beginning", "code": "// module start"}]
        assert transformations["classes"][0]["code_injections"] == [{"position": "beginning", "code": "// class start"}]
        assert transformations["classes"][0]["methods"][0]["code_injections"] == [
            {"position": "end", "code": "// method end"}
        ]

    def test_injected_properties_are_manifested(self):
        cls = _cls()
        cls.properties.append(IRProperty(name="value", getter="getValue", setter="setValue", type_spelling="int"))
        mod = _make_module(classes=[cls])

        manifest_class = compute_manifest(mod)["api"]["classes"][0]

        assert manifest_class["properties"] == [
            {
                "name": "value",
                "getter": "getValue",
                "setter": "setValue",
                "type": "int",
                "read_only": False,
            }
        ]

    def test_transform_metadata_branches_are_manifested(self):
        ctor_param = TIRParameter(name="x", type_spelling="int", rename="value", default_override="0", ownership="cpp")
        ctor = TIRConstructor(parameters=[ctor_param])
        ctor.code_injections.append(IRCodeInjection(position="end", code="// ctor"))

        method_param = TIRParameter(name="arg", type_spelling="float", rename="amount", ownership="script")
        method = TIRMethod(
            name="scale",
            spelling="scale",
            qualified_name="testmod::Widget::scale",
            return_type="void",
            parameters=[method_param],
        )
        field = TIRField(name="state_", type_spelling="int", read_only=True)
        nested_enum = TIREnum(
            name="Mode",
            qualified_name="testmod::Widget::Mode",
            is_arithmetic=True,
            values=[TIREnumValue(name="Fast", value=1)],
        )
        inner = TIRClass(
            name="Inner", qualified_name="testmod::Widget::Inner", namespace="testmod", force_abstract=True
        )
        cls = TIRClass(
            name="Widget",
            qualified_name="testmod::Widget",
            namespace="testmod",
            constructors=[ctor],
            methods=[method],
            fields=[field],
            enums=[nested_enum],
            inner_classes=[inner],
        )

        fn_param = TIRParameter(name="input", type_spelling="int", default_override="1")
        fn = TIRFunction(
            name="make",
            qualified_name="testmod::make",
            namespace="testmod",
            return_type="Widget",
            parameters=[fn_param],
            allow_thread=True,
        )
        enum = TIREnum(
            name="Flags",
            qualified_name="testmod::Flags",
            is_arithmetic=True,
            values=[TIREnumValue(name="Enabled", value=1)],
        )
        mod = _make_module(classes=[cls], functions=[fn], enums=[enum])
        mod.exception_registrations.append(
            IRExceptionRegistration(
                cpp_exception_type="WidgetError",
                target_exception_name="WidgetError",
                base_target_exception="RuntimeError",
            )
        )

        transformations = compute_manifest(mod)["transformations"]

        assert transformations["exception_registrations"] == [
            {
                "cpp_exception_type": "WidgetError",
                "target_exception_name": "WidgetError",
                "base_target_exception": "RuntimeError",
            }
        ]
        widget = next(c for c in transformations["classes"] if c["name"] == "Widget")
        assert widget["constructors"][0]["parameters"][0]["rename"] == "value"
        assert widget["constructors"][0]["code_injections"] == [{"position": "end", "code": "// ctor"}]
        assert widget["methods"][0]["parameters"][0]["ownership"] == "script"
        assert widget["fields"][0]["read_only"] is True
        assert widget["enums"][0] == {"name": "Mode", "is_arithmetic": True, "parent": "Widget"}
        inner_manifest = next(c for c in transformations["classes"] if c["name"] == "Inner")
        assert inner_manifest["force_abstract"] is True
        assert transformations["functions"][0]["allow_thread"] is True
        assert transformations["functions"][0]["parameters"][0]["default"] == "1"
        assert transformations["enums"][0] == {"name": "Flags", "is_arithmetic": True}


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

    def test_saved_file_uses_lf_newlines(self, tmp_path: Path) -> None:
        mod = _make_module(classes=[_cls(methods=[_method("add", ["int", "int"], "int")])])
        path = tmp_path / "api.json"
        save_manifest(compute_manifest(mod), path)
        data = path.read_bytes()
        assert b"\r" not in data
        assert b"\n" in data
        assert data.endswith(b"}\n")

    def test_save_opens_file_with_lf_newline(self, tmp_path: Path) -> None:
        path = tmp_path / "api.json"
        with patch("builtins.open", side_effect=open) as mock_open:
            save_manifest(compute_manifest(_make_module()), path)
        mock_open.assert_called_once_with(path, "w", encoding="utf-8", newline="\n")


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

    def test_new_property_is_additive(self):
        old = _make_module(classes=[_cls()])
        new_cls = _cls()
        new_cls.properties.append(IRProperty(name="value", getter="getValue", setter=None, type_spelling="int"))
        new = _make_module(classes=[new_cls])

        r = self._compare(old, new)

        assert r.is_compatible
        assert "Property 'Calculator.value' was added" in r.additive_changes

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

    def test_adding_function_with_transform_metadata_is_additive(self):
        old = _make_module()
        fn = _fn("compute", ["double"], "double")
        fn.allow_thread = True  # non-default → lands in transformations
        new = _make_module(functions=[fn])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("compute" in c for c in r.additive_changes)

    def test_adding_class_with_transform_metadata_is_additive(self):
        old = _make_module()
        cls = _cls("Widget")
        cls.holder_type = "shared_ptr"  # non-default → lands in transformations
        new = _make_module(classes=[cls])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("Widget" in c for c in r.additive_changes)

    def test_adding_exception_registration_is_additive(self):
        old = _make_module()
        new = _make_module()
        new.exception_registrations.append(
            IRExceptionRegistration(
                cpp_exception_type="FooError",
                target_exception_name="FooError",
                base_target_exception="Exception",
            )
        )
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("FooError" in c for c in r.additive_changes)

    def test_base_class_added_is_additive(self):
        old = _make_module(classes=[_cls()])
        new_cls = _cls()
        new_cls.bases.append(TIRBase(qualified_name="testmod::Base"))
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("testmod::Base" in c for c in r.additive_changes)

    def test_inner_class_added_is_additive(self):
        old = _make_module(classes=[_cls()])
        inner = TIRClass(name="Inner", qualified_name="testmod::Calculator::Inner", namespace="testmod")
        new_cls = _cls()
        new_cls.inner_classes.append(inner)
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert r.is_compatible
        assert any("Inner" in c for c in r.additive_changes)


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
        old_enum = TIREnum(
            name="Color",
            qualified_name="testmod::Color",
            values=[TIREnumValue(name="Red", value=0), TIREnumValue(name="Green", value=1)],
        )
        new_enum = TIREnum(
            name="Color",
            qualified_name="testmod::Color",
            values=[TIREnumValue(name="Red", value=0), TIREnumValue(name="Green", value=99)],
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

    def test_property_removed_is_breaking(self):
        old_cls = _cls()
        old_cls.properties.append(IRProperty(name="value", getter="getValue", setter=None, type_spelling="int"))
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[_cls()])

        r = self._compare(old, new)

        assert "Property 'Calculator.value' was removed" in r.breaking_changes

    def test_unchanged_property_is_compatible(self):
        old_cls = _cls()
        old_cls.properties.append(IRProperty(name="value", getter="getValue", setter="setValue", type_spelling="int"))
        new_cls = _cls()
        new_cls.properties.append(IRProperty(name="value", getter="getValue", setter="setValue", type_spelling="int"))
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[new_cls])

        r = self._compare(old, new)

        assert r.is_compatible
        assert not r.has_changes

    def test_property_changes_are_breaking(self):
        old_cls = _cls()
        old_cls.properties.append(IRProperty(name="value", getter="getValue", setter="setValue", type_spelling="int"))
        new_cls = _cls()
        new_cls.properties.append(IRProperty(name="value", getter="readValue", setter=None, type_spelling="double"))
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[new_cls])

        r = self._compare(old, new)

        assert "Property 'Calculator.value' type changed: int -> double" in r.breaking_changes
        assert "Property 'Calculator.value' getter changed: getValue -> readValue" in r.breaking_changes
        assert "Property 'Calculator.value' setter changed: setValue -> None" in r.breaking_changes
        assert "Property 'Calculator.value' read-only changed: False -> True" in r.breaking_changes

    def test_transform_signature_override_change_is_breaking(self):
        old_method = _method("value", return_type="int")
        old_method.return_type_override = "float"
        new_method = _method("value", return_type="int")
        new_method.return_type_override = "double"
        old = _make_module(classes=[_cls(methods=[old_method])])
        new = _make_module(classes=[_cls(methods=[new_method])])

        r = self._compare(old, new)

        assert not r.is_compatible
        assert any("value" in c for c in r.breaking_changes)

    def test_code_injection_change_is_breaking(self):
        old = _make_module()
        old.code_injections.append(IRCodeInjection(position="beginning", code="// old"))
        new = _make_module()
        new.code_injections.append(IRCodeInjection(position="beginning", code="// new"))

        r = self._compare(old, new)

        assert not r.is_compatible
        assert any("code injections" in c for c in r.breaking_changes)

    def test_wrapper_code_change_is_breaking(self):
        old_method = _method("value")
        old_method.wrapper_code = "+[](C& self) { return 1; }"
        new_method = _method("value")
        new_method.wrapper_code = "+[](C& self) { return 2; }"
        old = _make_module(classes=[_cls(methods=[old_method])])
        new = _make_module(classes=[_cls(methods=[new_method])])

        r = self._compare(old, new)

        assert not r.is_compatible
        assert any("Calculator" in c for c in r.breaking_changes)

    def test_unchanged_class_transform_is_compatible(self):
        old_cls = _cls("Widget")
        old_cls.holder_type = "shared_ptr"
        old = _make_module(classes=[old_cls])
        new_cls = _cls("Widget")
        new_cls.holder_type = "shared_ptr"  # same
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert r.is_compatible
        assert not r.has_changes

    def test_removing_class_transform_is_breaking(self):
        old_cls = _cls("Widget")
        old_cls.holder_type = "shared_ptr"
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[_cls("Widget")])  # holder_type dropped
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Widget" in c for c in r.breaking_changes)

    def test_changing_class_transform_is_breaking(self):
        old_cls = _cls("Widget")
        old_cls.holder_type = "shared_ptr"
        old = _make_module(classes=[old_cls])
        new_cls = _cls("Widget")
        new_cls.holder_type = "unique_ptr"
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Widget" in c for c in r.breaking_changes)

    def test_removing_exception_registration_is_breaking(self):
        old = _make_module()
        old.exception_registrations.append(
            IRExceptionRegistration(
                cpp_exception_type="BarError",
                target_exception_name="BarError",
                base_target_exception="Exception",
            )
        )
        new = _make_module()
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("BarError" in c for c in r.breaking_changes)

    def test_base_class_removed_is_breaking(self):
        old_cls = _cls()
        old_cls.bases.append(TIRBase(qualified_name="testmod::Base"))
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[_cls()])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("testmod::Base" in c for c in r.breaking_changes)

    def test_base_class_changed_is_breaking(self):
        old_cls = _cls()
        old_cls.bases.append(TIRBase(qualified_name="testmod::OldBase"))
        old = _make_module(classes=[old_cls])
        new_cls = _cls()
        new_cls.bases.append(TIRBase(qualified_name="testmod::NewBase"))
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("testmod::OldBase" in c for c in r.breaking_changes)
        assert any("testmod::NewBase" in c for c in r.additive_changes)

    def test_non_emitted_base_class_ignored(self):
        old = _make_module(classes=[_cls()])
        new_cls = _cls()
        new_cls.bases.append(TIRBase(qualified_name="testmod::Hidden", emit=False))
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert r.is_compatible
        assert not r.has_changes

    def test_inner_class_removed_is_breaking(self):
        inner = TIRClass(name="Inner", qualified_name="testmod::Calculator::Inner", namespace="testmod")
        old_cls = _cls()
        old_cls.inner_classes.append(inner)
        old = _make_module(classes=[old_cls])
        new = _make_module(classes=[_cls()])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("Inner" in c for c in r.breaking_changes)

    def test_inner_class_method_removed_is_breaking(self):
        inner_old = TIRClass(
            name="Inner",
            qualified_name="testmod::Calculator::Inner",
            namespace="testmod",
            methods=[_method("foo")],
        )
        inner_new = TIRClass(name="Inner", qualified_name="testmod::Calculator::Inner", namespace="testmod")
        old_cls = _cls()
        old_cls.inner_classes.append(inner_old)
        old = _make_module(classes=[old_cls])
        new_cls = _cls()
        new_cls.inner_classes.append(inner_new)
        new = _make_module(classes=[new_cls])
        r = self._compare(old, new)
        assert not r.is_compatible
        assert any("foo" in c for c in r.breaking_changes)


# ---------------------------------------------------------------------------
# is_semver
# ---------------------------------------------------------------------------


class TestIsSemver:
    def test_valid_semver(self):
        assert is_semver("1.0.0")
        assert is_semver("0.1.0")
        assert is_semver("2.3.4")
        assert is_semver("10.20.30")

    def test_invalid_semver_sha256(self):
        assert not is_semver("a" * 64)

    def test_invalid_semver_partial(self):
        assert not is_semver("1.0")
        assert not is_semver("1")
        assert not is_semver("1.0.0.0")

    def test_invalid_semver_empty(self):
        assert not is_semver("")

    def test_invalid_semver_with_prefix(self):
        assert not is_semver("v1.0.0")


# ---------------------------------------------------------------------------
# bump_semver
# ---------------------------------------------------------------------------


class TestBumpSemver:
    def _report(self, breaking=None, additive=None) -> CompatibilityReport:
        return CompatibilityReport(
            breaking_changes=breaking or [],
            additive_changes=additive or [],
        )

    def test_breaking_bumps_major(self):
        r = self._report(breaking=["Class 'Foo' was removed"])
        assert bump_semver("1.2.3", r) == "2.0.0"

    def test_breaking_resets_minor_and_patch(self):
        r = self._report(breaking=["Method 'bar' was removed"])
        assert bump_semver("3.5.7", r) == "4.0.0"

    def test_additive_only_bumps_minor(self):
        r = self._report(additive=["Class 'Widget' was added"])
        assert bump_semver("1.2.3", r) == "1.3.0"

    def test_additive_resets_patch(self):
        r = self._report(additive=["Method 'compute' was added"])
        assert bump_semver("2.4.9", r) == "2.5.0"

    def test_no_changes_returns_same(self):
        r = self._report()
        assert bump_semver("1.2.3", r) == "1.2.3"

    def test_breaking_takes_priority_over_additive(self):
        r = self._report(breaking=["Class 'X' was removed"], additive=["Class 'Y' was added"])
        assert bump_semver("1.0.0", r) == "2.0.0"

    def test_invalid_semver_raises(self):
        r = self._report()
        with pytest.raises(ValueError):
            bump_semver("not-a-version", r)


# ---------------------------------------------------------------------------
# suggest_version_bump
# ---------------------------------------------------------------------------


class TestSuggestVersionBump:
    def _make_manifest(self, version=None) -> dict:
        mod = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        m = compute_manifest(mod)
        if version is not None:
            m["version"] = version
        return m

    def _report(self, breaking=None, additive=None) -> CompatibilityReport:
        return CompatibilityReport(
            breaking_changes=breaking or [],
            additive_changes=additive or [],
        )

    def test_bumps_from_default_version(self):
        old = self._make_manifest(version=None)  # "version" defaults to "0.0.0"
        r = self._report(additive=["Class 'X' was added"])
        assert suggest_version_bump(old, r) == "0.1.0"

    def test_returns_none_when_version_field_absent(self):
        old = self._make_manifest(version=None)
        del old["version"]
        r = self._report(additive=["Class 'X' was added"])
        assert suggest_version_bump(old, r) is None

    def test_returns_none_when_semver_is_sha256(self):
        old = self._make_manifest()
        old["version"] = "abcdefghijklmn"
        r = self._report(additive=["Class 'X' was added"])
        assert suggest_version_bump(old, r) is None

    def test_returns_none_when_semver_invalid(self):
        old = self._make_manifest(version="v1.0.0")
        r = self._report(breaking=["Class 'Y' was removed"])
        assert suggest_version_bump(old, r) is None

    def test_breaking_suggests_major_bump(self):
        old = self._make_manifest(version="1.4.2")
        r = self._report(breaking=["Method 'foo' was removed"])
        assert suggest_version_bump(old, r) == "2.0.0"

    def test_additive_suggests_minor_bump(self):
        old = self._make_manifest(version="1.4.2")
        r = self._report(additive=["Class 'Widget' was added"])
        assert suggest_version_bump(old, r) == "1.5.0"

    def test_no_changes_returns_same_version(self):
        old = self._make_manifest(version="2.3.1")
        r = self._report()
        assert suggest_version_bump(old, r) == "2.3.1"

    def test_new_enum_at_module_level_suggests_minor(self):
        old_mod = _make_module()
        new_mod = _make_module(enums=[_enum("Color", ["Red", "Green"])])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "0.2.0"
        assert suggest_version_bump(old, report) == "0.3.0"

    def test_new_class_suggests_minor(self):
        old_mod = _make_module()
        new_mod = _make_module(classes=[_cls("Widget")])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.0.0"
        assert suggest_version_bump(old, report) == "1.1.0"

    def test_new_function_suggests_minor(self):
        old_mod = _make_module()
        new_mod = _make_module(functions=[_fn("compute", ["double"], "double")])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "3.1.4"
        assert suggest_version_bump(old, report) == "3.2.0"

    def test_new_method_on_existing_class_suggests_minor(self):
        old_mod = _make_module(classes=[_cls(methods=[_method("add")])])
        new_mod = _make_module(classes=[_cls(methods=[_method("add"), _method("sub")])])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.0.0"
        assert suggest_version_bump(old, report) == "1.1.0"

    def test_new_constructor_on_existing_class_suggests_minor(self):
        old_mod = _make_module(classes=[_cls(constructors=[_ctor(["int"])])])
        new_mod = _make_module(classes=[_cls(constructors=[_ctor(["int"]), _ctor(["int", "double"])])])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.0.0"
        assert suggest_version_bump(old, report) == "1.1.0"

    def test_removed_class_suggests_major(self):
        old_mod = _make_module(classes=[_cls("Widget")])
        new_mod = _make_module()
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.5.0"
        assert suggest_version_bump(old, report) == "2.0.0"

    def test_changed_method_signature_suggests_major(self):
        old_mod = _make_module(classes=[_cls(methods=[_method("add", ["int"], "int")])])
        new_mod = _make_module(classes=[_cls(methods=[_method("add", ["double"], "int")])])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "2.0.0"
        assert suggest_version_bump(old, report) == "3.0.0"

    def test_changed_transform_signature_suggests_major(self):
        old_method = _method("value", return_type="int")
        old_method.return_type_override = "float"
        new_method = _method("value", return_type="int")
        new_method.return_type_override = "double"
        old_mod = _make_module(classes=[_cls(methods=[old_method])])
        new_mod = _make_module(classes=[_cls(methods=[new_method])])
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "2.0.0"
        assert suggest_version_bump(old, report) == "3.0.0"

    def test_changed_code_injection_suggests_major(self):
        old_mod = _make_module()
        old_mod.code_injections.append(IRCodeInjection(position="beginning", code="// old"))
        new_mod = _make_module()
        new_mod.code_injections.append(IRCodeInjection(position="beginning", code="// new"))
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.4.0"
        assert suggest_version_bump(old, report) == "2.0.0"

    def test_removed_function_suggests_major(self):
        old_mod = _make_module(functions=[_fn("compute", ["double"], "double")])
        new_mod = _make_module()
        report = compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))
        old = compute_manifest(old_mod)
        old["version"] = "1.2.3"
        assert suggest_version_bump(old, report) == "2.0.0"


# ---------------------------------------------------------------------------
# compare_manifests: transform metadata follows the signature serving a call
# ---------------------------------------------------------------------------


_Callable = TypeVar("_Callable", TIRMethod, TIRFunction, TIRConstructor)
_Gateable = TypeVar("_Gateable", TIRMethod, TIRFunction)


def _append_defaulted(node: _Callable, type_spelling: str = "bool", default: str = "false") -> _Callable:
    """Append a trailing defaulted parameter, as a header gaining ``bool force = false`` would."""
    node.parameters.append(
        TIRParameter(name=f"p{len(node.parameters)}", type_spelling=type_spelling, default_value=default)
    )
    return node


def _compare_modules(old_mod: TIRModule, new_mod: TIRModule) -> CompatibilityReport:
    return compare_manifests(compute_manifest(old_mod), compute_manifest(new_mod))


def _gated(node: _Gateable, since: str = "1.0") -> _Gateable:
    node.api_since = since
    return node


class TestCompareTransformsFollowSignature:
    def test_extended_method_with_same_transform_is_compatible(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"))])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_append_defaulted(_method("refresh")))])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == []
        assert r.additive_changes == [
            "Method 'Widget.refresh() -> void' is still callable via 'Widget.refresh(bool) -> void' "
            "(defaulted parameter(s) added)"
        ]

    def test_transform_on_appended_parameter_is_ignored(self) -> None:
        """Parameter transforms at or past the old arity belong to the new parameters."""
        old_method = _method("scale", ["float"])
        old_method.parameters[0].rename = "amount"
        new_method = _append_defaulted(_method("scale", ["float"]))
        new_method.parameters[0].rename = "amount"
        new_method.parameters[1].rename = "clamp"
        old = _make_module(classes=[_cls("Widget", methods=[old_method])])
        new = _make_module(classes=[_cls("Widget", methods=[new_method])])
        r = _compare_modules(old, new)
        assert r.is_compatible
        assert not any("Binding" in c for c in r.additive_changes)

    def test_extended_method_with_changed_transform_is_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"), "1.0")])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_append_defaulted(_method("refresh")), "2.0")])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.refresh()' was changed"]

    def test_extended_method_parameter_transform_changed_is_breaking(self) -> None:
        old_method = _method("scale", ["float"])
        old_method.parameters[0].rename = "amount"
        new_method = _append_defaulted(_method("scale", ["float"]))
        new_method.parameters[0].rename = "factor"
        old = _make_module(classes=[_cls("Widget", methods=[old_method])])
        new = _make_module(classes=[_cls("Widget", methods=[new_method])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.scale(float)' was changed"]

    def test_extended_method_losing_its_transform_is_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"))])])
        new = _make_module(classes=[_cls("Widget", methods=[_append_defaulted(_method("refresh"))])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.refresh()' was removed"]

    def test_extended_static_method_with_same_transform_is_compatible(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("create", is_static=True))])])
        new_method = _gated(_append_defaulted(_method("create", is_static=True)))
        new = _make_module(classes=[_cls("Widget", methods=[new_method])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == []

    def test_uncovered_method_transform_label_is_static(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("create", is_static=True))])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_method("create", ["int"], is_static=True))])])
        r = _compare_modules(old, new)
        assert "Binding method transform 'static Widget.create()' was removed" in r.breaking_changes
        assert "Binding method transform 'static Widget.create(int)' was added" in r.additive_changes

    def test_merged_overloads_keep_their_transforms(self) -> None:
        old_methods = [_gated(_method("resize")), _gated(_method("resize", ["int"]))]
        new_method = _gated(_method("resize", ["int"]))
        new_method.parameters[0].default_value = "0"
        old = _make_module(classes=[_cls("Widget", methods=old_methods)])
        new = _make_module(classes=[_cls("Widget", methods=[new_method])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == []

    def test_extended_constructor_with_same_transform_is_compatible(self) -> None:
        old_ctor = _ctor(["int"])
        old_ctor.parameters[0].rename = "size"
        new_ctor = _append_defaulted(_ctor(["int"]))
        new_ctor.parameters[0].rename = "size"
        old = _make_module(classes=[_cls("Widget", constructors=[old_ctor])])
        new = _make_module(classes=[_cls("Widget", constructors=[new_ctor])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == []
        assert r.additive_changes == [
            "Constructor 'Widget(int)' is still callable via 'Widget(int, bool)' (defaulted parameter(s) added)"
        ]

    def test_constructor_inserted_before_transformed_one_is_additive(self) -> None:
        """A constructor transform's index is only its position, not its identity."""
        transformed = _ctor(["int"])
        transformed.parameters[0].rename = "size"
        moved = _ctor(["int"])
        moved.parameters[0].rename = "size"
        old = _make_module(classes=[_cls("Widget", constructors=[transformed])])
        new = _make_module(classes=[_cls("Widget", constructors=[_ctor(), moved])])
        r = _compare_modules(old, new)
        assert r.is_compatible
        assert r.additive_changes == ["Constructor 'Widget()' was added"]

    def test_constructor_transform_changed_is_breaking(self) -> None:
        old_ctor = _ctor(["int"])
        old_ctor.parameters[0].rename = "size"
        new_ctor = _ctor(["int"])
        new_ctor.parameters[0].rename = "count"
        old = _make_module(classes=[_cls("Widget", constructors=[old_ctor])])
        new = _make_module(classes=[_cls("Widget", constructors=[new_ctor])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding constructor transform 'Widget(int)' was changed"]

    def test_new_transformed_constructor_on_transformed_class_is_additive(self) -> None:
        added = _ctor(["int"])
        added.parameters[0].rename = "size"
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"))])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"))], constructors=[added])])
        r = _compare_modules(old, new)
        assert r.is_compatible
        assert sorted(r.additive_changes) == [
            "Binding constructor transform 'Widget(int)' was added",
            "Constructor 'Widget(int)' was added",
        ]

    def test_extended_inner_class_method_with_same_transform_is_compatible(self) -> None:
        """Transform entries name the inner class by binding name, not by its dotted label."""

        def module(method: TIRMethod) -> TIRModule:
            inner = TIRClass(
                name="Panel", qualified_name="testmod::Widget::Panel", namespace="testmod", methods=[method]
            )
            outer = _cls("Widget")
            outer.inner_classes.append(inner)
            return _make_module(classes=[outer])

        r = _compare_modules(module(_gated(_method("refresh"))), module(_gated(_append_defaulted(_method("refresh")))))
        assert r.breaking_changes == []
        assert r.additive_changes == [
            "Method 'Widget.Panel.refresh() -> void' is still callable via 'Widget.Panel.refresh(bool) -> void' "
            "(defaulted parameter(s) added)"
        ]

    def test_new_transformed_method_on_transformed_class_is_additive(self) -> None:
        old_cls = _cls("Widget", methods=[_gated(_method("refresh"))])
        old_cls.holder_type = "std::shared_ptr"
        new_cls = _cls("Widget", methods=[_gated(_method("refresh")), _gated(_method("reset"))])
        new_cls.holder_type = "std::shared_ptr"
        r = _compare_modules(_make_module(classes=[old_cls]), _make_module(classes=[new_cls]))
        assert r.is_compatible
        assert sorted(r.additive_changes) == [
            "Binding method transform 'Widget.reset()' was added",
            "Method 'Widget.reset' was added",
        ]

    def test_new_field_and_enum_on_transformed_class_are_additive(self) -> None:
        old_cls = _cls("Widget", methods=[_gated(_method("refresh"))])
        mode = TIREnum(
            name="Mode",
            qualified_name="testmod::Widget::Mode",
            is_arithmetic=True,
            values=[TIREnumValue(name="Fast", value=0)],
        )
        new_cls = _cls(
            "Widget",
            methods=[_gated(_method("refresh"))],
            fields=[TIRField(name="state_", type_spelling="int", read_only=True)],
            enums=[mode],
        )
        r = _compare_modules(_make_module(classes=[old_cls]), _make_module(classes=[new_cls]))
        assert r.is_compatible
        assert "Binding enum transform 'Widget.Mode' was added" in r.additive_changes
        assert "Field 'Widget.state_' was added" in r.additive_changes

    def test_changed_member_transform_is_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"), "1.0")])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"), "2.0")])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.refresh()' was changed"]

    def test_removed_member_transform_is_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh")), _gated(_method("reset"))])])
        new = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh")), _method("reset")])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.reset()' was removed"]

    def test_last_member_transform_removed_is_reported_once(self) -> None:
        """The class entry vanishes with it, but carries no class-level metadata of its own."""
        old = _make_module(classes=[_cls("Widget", methods=[_gated(_method("refresh"))])])
        new = _make_module(classes=[_cls("Widget", methods=[_method("refresh")])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding method transform 'Widget.refresh()' was removed"]

    def test_class_metadata_change_is_breaking_alongside_members(self) -> None:
        old_cls = _cls("Widget", methods=[_gated(_method("refresh"))])
        old_cls.holder_type = "std::shared_ptr"
        new_cls = _cls("Widget", methods=[_gated(_method("refresh"))])
        new_cls.holder_type = "std::unique_ptr"
        r = _compare_modules(_make_module(classes=[old_cls]), _make_module(classes=[new_cls]))
        assert r.breaking_changes == ["Binding class transform 'testmod::Widget' was changed"]

    def test_changed_nested_enum_transform_is_breaking(self) -> None:
        def module(is_arithmetic: bool) -> TIRModule:
            mode = TIREnum(
                name="Mode",
                qualified_name="testmod::Widget::Mode",
                is_arithmetic=is_arithmetic,
                api_since="1.0",
                values=[TIREnumValue(name="Fast", value=0)],
            )
            return _make_module(classes=[_cls("Widget", enums=[mode])])

        r = _compare_modules(module(True), module(False))
        assert r.breaking_changes == ["Binding enum transform 'Widget.Mode' was changed"]

    def test_read_only_transform_removed_is_additive(self) -> None:
        old = _make_module(classes=[_cls("Widget", fields=[TIRField(name="x", type_spelling="int", read_only=True)])])
        new = _make_module(classes=[_cls("Widget", fields=[TIRField(name="x", type_spelling="int")])])
        r = _compare_modules(old, new)
        assert r.is_compatible
        assert r.additive_changes == ["Field 'Widget.x' read-only changed: True -> False"]

    def test_extended_function_with_same_transform_is_compatible(self) -> None:
        old = _make_module(functions=[_gated(_fn("render"))])
        new = _make_module(functions=[_gated(_append_defaulted(_fn("render")))])
        r = _compare_modules(old, new)
        assert r.breaking_changes == []
        assert r.additive_changes == [
            "Function 'render() -> void' is still callable via 'render(bool) -> void' (defaulted parameter(s) added)"
        ]

    def test_extended_function_with_changed_transform_is_breaking(self) -> None:
        old = _make_module(functions=[_gated(_fn("render"), "1.0")])
        new = _make_module(functions=[_gated(_append_defaulted(_fn("render")), "2.0")])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding function transform 'render' was changed"]

    def test_removed_function_transform_is_breaking(self) -> None:
        old = _make_module(functions=[_gated(_fn("render"))])
        new = _make_module(functions=[_fn("render")])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Binding function transform 'render' was removed"]


class TestCompareReadOnlyRelaxed:
    def _property_module(self, setter: Optional[str]) -> TIRModule:
        cls = _cls("Widget")
        cls.properties.append(IRProperty(name="value", getter="getValue", setter=setter, type_spelling="int"))
        return _make_module(classes=[cls])

    def test_setter_added_is_additive(self) -> None:
        r = _compare_modules(self._property_module(None), self._property_module("setValue"))
        assert r.is_compatible
        assert r.additive_changes == ["Property 'Widget.value' read-only changed: True -> False"]

    def test_setter_removed_is_breaking(self) -> None:
        r = _compare_modules(self._property_module("setValue"), self._property_module(None))
        assert r.breaking_changes == [
            "Property 'Widget.value' setter changed: setValue -> None",
            "Property 'Widget.value' read-only changed: False -> True",
        ]

    def test_setter_replaced_is_breaking(self) -> None:
        r = _compare_modules(self._property_module("setValue"), self._property_module("assignValue"))
        assert r.breaking_changes == ["Property 'Widget.value' setter changed: setValue -> assignValue"]
        assert r.additive_changes == []

    def test_field_made_read_only_is_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", fields=[TIRField(name="x", type_spelling="int")])])
        new = _make_module(classes=[_cls("Widget", fields=[TIRField(name="x", type_spelling="int", read_only=True)])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == ["Field 'Widget.x' read-only changed: False -> True"]

    def test_const_dropped_with_type_change_stays_breaking(self) -> None:
        old = _make_module(classes=[_cls("Widget", fields=[_field("x", "const int", is_const=True)])])
        new = _make_module(classes=[_cls("Widget", fields=[_field("x", "int")])])
        r = _compare_modules(old, new)
        assert r.breaking_changes == [
            "Field 'Widget.x' type changed: const int -> int",
            "Field 'Widget.x' const qualifier changed: True -> False",
            "Field 'Widget.x' read-only changed: True -> False",
        ]
        assert r.additive_changes == []


class TestCompareModuleEnumTransforms:
    def _module(self, is_arithmetic: bool) -> TIRModule:
        flags = _enum("Flags", ["Enabled"])
        flags.is_arithmetic = is_arithmetic
        flags.api_since = "1.0"
        return _make_module(enums=[flags])

    def test_unchanged_enum_transform_reports_nothing(self) -> None:
        r = _compare_modules(self._module(True), self._module(True))
        assert not r.has_changes

    def test_changed_enum_transform_is_breaking(self) -> None:
        r = _compare_modules(self._module(True), self._module(False))
        assert r.breaking_changes == ["Binding enum transform 'Flags' was changed"]
