"""Manifest tests for defaulted-argument arity tracking.

Dropping a C++ default leaves the parameter type list untouched but raises the
number of arguments a caller must supply, breaking existing callers in every
target language. ``min_arity`` is what lets ``--check-compat`` see that.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import pytest

from tsujikiri.manifest import CompatibilityReport, compare_manifests, compute_manifest, suggest_version_bump
from tsujikiri.tir import (
    TIRClass,
    TIRConstructor,
    TIRFunction,
    TIRMethod,
    TIRModule,
    TIRParameter,
    minimum_arity,
    trailing_defaulted_count,
)


def _params(spec: List[Any]) -> List[TIRParameter]:
    """spec entries are either "type" or ("type", "default")."""
    out = []
    for i, entry in enumerate(spec):
        type_spelling, default = entry if isinstance(entry, tuple) else (entry, None)
        out.append(TIRParameter(name=f"p{i}", type_spelling=type_spelling, default_value=default))
    return out


def _method(spec: List[Any], name: str = "f", return_type: str = "int", is_static: bool = False) -> TIRMethod:
    return TIRMethod(
        name=name,
        spelling=name,
        qualified_name=f"C::{name}",
        return_type=return_type,
        parameters=_params(spec),
        is_static=is_static,
    )


def _function(spec: List[Any], return_type: str = "int") -> TIRFunction:
    return TIRFunction(name="g", qualified_name="g", namespace="", return_type=return_type, parameters=_params(spec))


def _module(
    methods: Optional[List[TIRMethod]] = None,
    ctors: Optional[List[TIRConstructor]] = None,
    functions: Optional[List[TIRFunction]] = None,
) -> Dict[str, Any]:
    cls = TIRClass(
        name="C",
        qualified_name="C",
        namespace="",
        variable_name="classC",
        methods=methods or [],
        constructors=ctors or [],
    )
    return compute_manifest(TIRModule(name="m", classes=[cls], functions=functions or []))


def _entry(manifest: Dict[str, Any], kind: str = "methods") -> Dict[str, Any]:
    return manifest["api"]["classes"][0][kind][0]


# ---------------------------------------------------------------------------
# The shared rule
# ---------------------------------------------------------------------------


class TestTrailingDefaultedCount:
    @pytest.mark.parametrize(
        "defaults,expected",
        [
            ([], 0),
            ([None], 0),
            ([None, "1"], 1),
            ([None, "1", "2"], 2),
            (["1", "2"], 2),
            # A non-default after a default stops the run.
            (["1", None], 0),
            # An empty string is not a default expression.
            ([None, ""], 0),
        ],
    )
    def test_counts_trailing_run(self, defaults, expected) -> None:
        assert trailing_defaulted_count(defaults) == expected

    def test_minimum_arity_is_complement(self) -> None:
        assert minimum_arity([None, "1", "2"]) == 1
        assert minimum_arity([None, None]) == 2
        assert minimum_arity([]) == 0


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class TestMinArityRecording:
    def test_method_records_min_arity(self) -> None:
        m = _module(methods=[_method(["int", ("float", "1.0f")])])
        assert _entry(m)["min_arity"] == 1
        assert _entry(m)["params"] == ["int", "float"]

    def test_method_without_defaults_has_full_min_arity(self) -> None:
        assert _entry(_module(methods=[_method(["int", "float"])]))["min_arity"] == 2

    def test_constructor_records_min_arity(self) -> None:
        ctor = TIRConstructor(parameters=_params(["int", ("float", "1.0f")]))
        assert _entry(_module(ctors=[ctor]), "constructors") == {"params": ["int", "float"], "min_arity": 1}

    def test_function_records_min_arity(self) -> None:
        fn = TIRFunction(
            name="g",
            qualified_name="g",
            namespace="",
            return_type="int",
            parameters=_params(["int", ("float", "1.0f")]),
        )
        assert _module(functions=[fn])["api"]["functions"][0]["min_arity"] == 1

    def test_min_arity_follows_emitted_params_only(self) -> None:
        """A parameter dropped by a transform must not be counted."""
        m = _method(["int", ("float", "1.0f")])
        m.parameters[1].emit = False
        entry = _entry(_module(methods=[m]))
        assert entry["params"] == ["int"]
        assert entry["min_arity"] == 1

    def test_two_constructors_sort_without_error(self) -> None:
        """Constructor entries are dicts now, so the sort key must be explicit."""
        ctors = [TIRConstructor(parameters=_params(["int"])), TIRConstructor(parameters=_params(["double"]))]
        assert [c["params"] for c in _module(ctors=ctors)["api"]["classes"][0]["constructors"]] == [
            ["double"],
            ["int"],
        ]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _strip_min_arity(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy shaped like a manifest written before min_arity existed."""
    legacy = copy.deepcopy(manifest)
    for cls in legacy["api"]["classes"]:
        for m in cls["methods"]:
            m.pop("min_arity", None)
        cls["constructors"] = [c["params"] for c in cls["constructors"]]
    for fn in legacy["api"]["functions"]:
        fn.pop("min_arity", None)
    return legacy


class TestMinArityComparison:
    WITH = [_method(["int", ("float", "1.0f")])]
    WITHOUT = [_method(["int", "float"])]

    def test_removing_a_default_is_breaking(self) -> None:
        r = compare_manifests(_module(methods=self.WITH), _module(methods=self.WITHOUT))
        assert not r.is_compatible
        assert "no longer accepts 1 argument(s)" in r.breaking_changes[0]
        assert "C.f(int, float)" in r.breaking_changes[0]

    def test_adding_a_default_is_additive(self) -> None:
        r = compare_manifests(_module(methods=self.WITHOUT), _module(methods=self.WITH))
        assert r.is_compatible
        assert "now accepts 1 argument(s)" in r.additive_changes[0]

    def test_changing_a_default_value_reports_nothing(self) -> None:
        """The callable surface is unchanged; only behaviour differs."""
        other = [_method(["int", ("float", "2.0f")])]
        r = compare_manifests(_module(methods=self.WITH), _module(methods=other))
        assert r.breaking_changes == []
        assert r.additive_changes == []

    def test_identical_manifests_report_nothing(self) -> None:
        r = compare_manifests(_module(methods=self.WITH), _module(methods=self.WITH))
        assert r.breaking_changes == []
        assert r.additive_changes == []

    def test_legacy_manifest_without_min_arity_reports_nothing(self) -> None:
        """Comparing against a guess would flag every defaulted parameter once."""
        new = _module(methods=self.WITHOUT)
        r = compare_manifests(_strip_min_arity(_module(methods=self.WITH)), new)
        assert r.breaking_changes == []
        assert r.additive_changes == []

    def test_new_manifest_against_legacy_reports_nothing(self) -> None:
        old = _module(methods=self.WITH)
        r = compare_manifests(old, _strip_min_arity(_module(methods=self.WITHOUT)))
        assert r.breaking_changes == []
        assert r.additive_changes == []

    def test_removing_a_constructor_default_is_breaking(self) -> None:
        with_default = [TIRConstructor(parameters=_params(["int", ("float", "1.0f")]))]
        without = [TIRConstructor(parameters=_params(["int", "float"]))]
        r = compare_manifests(_module(ctors=with_default), _module(ctors=without))
        assert not r.is_compatible
        assert "Constructor 'C(int, float)'" in r.breaking_changes[0]

    def test_adding_a_constructor_default_is_additive(self) -> None:
        with_default = [TIRConstructor(parameters=_params(["int", ("float", "1.0f")]))]
        without = [TIRConstructor(parameters=_params(["int", "float"]))]
        r = compare_manifests(_module(ctors=without), _module(ctors=with_default))
        assert r.is_compatible
        assert "Constructor 'C(int, float)'" in r.additive_changes[0]

    def test_legacy_constructor_list_shape_is_accepted(self) -> None:
        """Manifests on disk store constructors as bare lists of parameter types."""
        new = _module(ctors=[TIRConstructor(parameters=_params(["int", ("float", "1.0f")]))])
        r = compare_manifests(_strip_min_arity(new), new)
        assert r.breaking_changes == []
        assert r.additive_changes == []

    def test_legacy_constructor_signature_change_still_detected(self) -> None:
        """Dropping min_arity must not blind the existing signature diff."""
        old = _strip_min_arity(_module(ctors=[TIRConstructor(parameters=_params(["int"]))]))
        new = _module(ctors=[TIRConstructor(parameters=_params(["double"]))])
        r = compare_manifests(old, new)
        assert "Constructor 'C(int)' was removed" in r.breaking_changes

    def test_removing_a_function_default_is_breaking(self) -> None:
        def fn(spec):
            return TIRFunction(name="g", qualified_name="g", namespace="", return_type="int", parameters=_params(spec))

        r = compare_manifests(
            _module(functions=[fn(["int", ("float", "1.0f")])]),
            _module(functions=[fn(["int", "float"])]),
        )
        assert not r.is_compatible
        assert "Function 'g(int, float)'" in r.breaking_changes[0]

    def test_adding_a_function_default_is_additive(self) -> None:
        def fn(spec):
            return TIRFunction(name="g", qualified_name="g", namespace="", return_type="int", parameters=_params(spec))

        r = compare_manifests(
            _module(functions=[fn(["int", "float"])]),
            _module(functions=[fn(["int", ("float", "1.0f")])]),
        )
        assert r.is_compatible
        assert "Function 'g(int, float)'" in r.additive_changes[0]

    def test_static_method_arity_change_is_labelled_static(self) -> None:
        a = _method(["int", ("float", "1.0f")])
        a.is_static = True
        b = _method(["int", "float"])
        b.is_static = True
        r = compare_manifests(_module(methods=[a]), _module(methods=[b]))
        assert "static C.f" in r.breaking_changes[0]


# ---------------------------------------------------------------------------
# Arity coverage across overloads
# ---------------------------------------------------------------------------


def _compare_methods(old: List[TIRMethod], new: List[TIRMethod]) -> CompatibilityReport:
    return compare_manifests(_module(methods=old), _module(methods=new))


class TestArityCoverageAdditive:
    """Existing calls still resolve, so the change must not be breaking."""

    def test_trailing_defaulted_param_appended_to_method(self) -> None:
        r = _compare_methods([_method([])], [_method([("bool", "false")])])
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'C.f() -> int' is still callable via 'C.f(bool) -> int' (defaulted parameter(s) added)"
        ]

    def test_several_trailing_defaulted_params_appended(self) -> None:
        r = _compare_methods([_method(["int"])], [_method(["int", ("bool", "false"), ("char", "'a'")])])
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'C.f(int) -> int' is still callable via 'C.f(int, bool, char) -> int' "
            "(defaulted parameter(s) added)"
        ]

    def test_signature_with_defaults_extended_by_another_default(self) -> None:
        """One new overload serves every arity the old one accepted."""
        r = _compare_methods(
            [_method(["int", ("bool", "false")])],
            [_method(["int", ("bool", "false"), ("char", "'a'")])],
        )
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'C.f(int, bool) -> int' is still callable via 'C.f(int, bool, char) -> int' "
            "(defaulted parameter(s) added)"
        ]

    def test_static_method_extended(self) -> None:
        r = _compare_methods([_method([], is_static=True)], [_method([("bool", "false")], is_static=True)])
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'static C.f() -> int' is still callable via 'static C.f(bool) -> int' "
            "(defaulted parameter(s) added)"
        ]

    def test_constructor_extended(self) -> None:
        r = compare_manifests(
            _module(ctors=[TIRConstructor(parameters=_params(["int"]))]),
            _module(ctors=[TIRConstructor(parameters=_params(["int", ("bool", "false")]))]),
        )
        assert r.is_compatible
        assert r.additive_changes == [
            "Constructor 'C(int)' is still callable via 'C(int, bool)' (defaulted parameter(s) added)"
        ]

    def test_function_extended(self) -> None:
        r = compare_manifests(
            _module(functions=[_function([])]),
            _module(functions=[_function([("bool", "false"), ("int", "0")])]),
        )
        assert r.is_compatible
        assert r.additive_changes == [
            "Function 'g() -> int' is still callable via 'g(bool, int) -> int' (defaulted parameter(s) added)"
        ]

    def test_overloads_merged_into_defaulted_signature(self) -> None:
        r = _compare_methods([_method([]), _method(["int"])], [_method([("int", "0")])])
        assert r.is_compatible
        assert sorted(r.additive_changes) == [
            "Method 'C.f() -> int' is still callable via 'C.f(int) -> int' (defaulted parameter(s) added)",
            "Method 'C.f(int)' now accepts 0 argument(s): a parameter default was added (minimum arity 1 -> 0)",
        ]

    def test_default_split_into_explicit_overloads(self) -> None:
        """The dropped one-argument call is still served, by the new f(int)."""
        r = _compare_methods([_method(["int", ("bool", "false")])], [_method(["int"]), _method(["int", "bool"])])
        assert r.breaking_changes == []
        assert r.additive_changes == ["Method 'C.f(int) -> int' overload was added"]

    def test_arities_served_by_several_overloads(self) -> None:
        r = _compare_methods(
            [_method(["int", ("bool", "false")])],
            [_method(["int"]), _method(["int", "bool", ("char", "'a'")])],
        )
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'C.f(int, bool) -> int' is still callable via 'C.f(int) -> int', "
            "'C.f(int, bool, char) -> int' (defaulted parameter(s) added)"
        ]

    def test_legacy_old_manifest_extended_is_covered(self) -> None:
        """Without min_arity only the full old arity is claimed, and it is still served."""
        old = _strip_min_arity(_module(methods=[_method(["int"])]))
        r = compare_manifests(old, _module(methods=[_method(["int", ("bool", "false")])]))
        assert r.is_compatible
        assert r.additive_changes == [
            "Method 'C.f(int) -> int' is still callable via 'C.f(int, bool) -> int' (defaulted parameter(s) added)"
        ]

    def test_legacy_old_constructor_extended_is_covered(self) -> None:
        old = _strip_min_arity(_module(ctors=[TIRConstructor(parameters=_params([]))]))
        new = _module(ctors=[TIRConstructor(parameters=_params([("int", "0")]))])
        r = compare_manifests(old, new)
        assert r.is_compatible
        assert r.additive_changes == ["Constructor 'C()' is still callable via 'C(int)' (defaulted parameter(s) added)"]

    def test_extended_method_suggests_minor_bump(self) -> None:
        old = _module(methods=[_method([])])
        old["version"] = "1.2.3"
        r = compare_manifests(old, _module(methods=[_method([("bool", "false")])]))
        assert suggest_version_bump(old, r) == "1.3.0"


class TestArityCoverageBreaking:
    """Some call that used to resolve no longer does."""

    def test_extended_with_changed_return_type(self) -> None:
        r = _compare_methods([_method([])], [_method([("bool", "false")], return_type="bool")])
        assert r.breaking_changes == ["Method 'C.f() -> int' signature was removed or changed"]
        assert r.additive_changes == ["Method 'C.f(bool) -> bool' overload was added"]

    def test_parameter_prepended_instead_of_appended(self) -> None:
        r = _compare_methods([_method(["int"])], [_method(["bool", ("int", "0")])])
        assert r.breaking_changes == ["Method 'C.f(int) -> int' signature was removed or changed"]
        assert r.additive_changes == ["Method 'C.f(bool, int) -> int' overload was added"]

    def test_appended_parameter_without_default(self) -> None:
        r = _compare_methods([_method([])], [_method(["bool"])])
        assert r.breaking_changes == ["Method 'C.f() -> int' signature was removed or changed"]

    def test_legacy_old_manifest_extended_without_default(self) -> None:
        old = _strip_min_arity(_module(methods=[_method(["int"])]))
        r = compare_manifests(old, _module(methods=[_method(["int", "bool"])]))
        assert r.breaking_changes == ["Method 'C.f(int) -> int' signature was removed or changed"]

    def test_instance_method_cannot_cover_static(self) -> None:
        r = _compare_methods([_method([], is_static=True)], [_method([("bool", "false")])])
        assert r.breaking_changes == ["Method 'static C.f' was removed"]

    def test_static_method_cannot_cover_instance(self) -> None:
        r = _compare_methods([_method([])], [_method([("bool", "false")], is_static=True)])
        assert r.breaking_changes == ["Method 'C.f' was removed"]

    def test_min_arity_lowered_only_partway(self) -> None:
        """f(int, bool = x) accepted one argument; f(int, bool, char = y) needs two."""
        r = _compare_methods([_method(["int", ("bool", "false")])], [_method(["int", "bool", ("char", "'a'")])])
        assert r.breaking_changes == ["Method 'C.f(int, bool) -> int' signature was removed or changed"]

    def test_new_manifest_without_min_arity_is_not_covering(self) -> None:
        """An unknown new min_arity is assumed to require every parameter."""
        new = _strip_min_arity(_module(methods=[_method([("bool", "false")])]))
        r = compare_manifests(_module(methods=[_method([])]), new)
        assert r.breaking_changes == ["Method 'C.f() -> int' signature was removed or changed"]

    def test_default_removed_and_middle_arity_not_served(self) -> None:
        """f(int) still serves one argument, but nothing serves two any more."""
        r = _compare_methods(
            [_method(["int", ("bool", "false"), ("char", "'a'")])],
            [_method(["int", "bool", "char"]), _method(["int"])],
        )
        assert r.breaking_changes == [
            "Method 'C.f(int, bool, char)' no longer accepts 2 argument(s): "
            "a parameter default was removed (minimum arity 1 -> 3)"
        ]

    def test_function_extended_without_default(self) -> None:
        r = compare_manifests(_module(functions=[_function([])]), _module(functions=[_function(["bool"])]))
        assert r.breaking_changes == ["Function 'g() -> int' signature was removed or changed"]

    def test_constructor_extended_without_default(self) -> None:
        r = compare_manifests(
            _module(ctors=[TIRConstructor(parameters=_params(["int"]))]),
            _module(ctors=[TIRConstructor(parameters=_params(["int", "bool"]))]),
        )
        assert r.breaking_changes == ["Constructor 'C(int)' was removed"]
        assert r.additive_changes == ["Constructor 'C(int, bool)' was added"]
