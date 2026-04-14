"""pybind11 runtime verification for the typesystem scenario.

Exercises:
  - TypedClass construction (default and two-arg int64_t, int)
  - int64_t getId/setId round-trip
  - OSType getTag/setTag round-trip (unlocked via custom_types in types.input.yml)
  - setValue/getValue for regular int
  - computeId free function overloads
"""
from __future__ import annotations

import sys

import typesystem  # type: ignore  # noqa: E402


def test_default_construction() -> None:
    obj = typesystem.TypedClass()
    assert obj.get_value() == 0, f"default get_value: {obj.get_value()}"
    assert obj.get_id() == 0, f"default get_id: {obj.get_id()}"


def test_two_arg_constructor() -> None:
    obj = typesystem.TypedClass(500, 200)
    assert obj.get_id() == 500, f"constructor id: {obj.get_id()}"
    assert obj.get_value() == 200, f"constructor value: {obj.get_value()}"


def test_int_set_get() -> None:
    obj = typesystem.TypedClass()
    obj.set_value(42)
    assert obj.get_value() == 42, f"set/get value: {obj.get_value()}"
    obj.set_value(0)
    assert obj.get_value() == 0, f"reset value: {obj.get_value()}"


def test_int64_set_get() -> None:
    obj = typesystem.TypedClass()
    large = 1_000_000_000
    obj.set_id(large)
    assert obj.get_id() == large, f"int64 round-trip: {obj.get_id()}"
    # Value beyond int32_t range, within int64_t
    big = 10_000_000_000
    obj.set_id(big)
    assert obj.get_id() == big, f"int64 big round-trip: {obj.get_id()}"


def test_ostype_default_value() -> None:
    obj = typesystem.TypedClass()
    tag = obj.get_tag()
    assert tag.value == 0, f"default OSType.value: {tag.value}"


def test_ostype_roundtrip() -> None:
    obj = typesystem.TypedClass()
    tag = obj.get_tag()
    tag.value = 99
    obj.set_tag(tag)
    updated = obj.get_tag()
    assert updated.value == 99, f"OSType roundtrip: {updated.value}"


def test_ostype_multiple_values() -> None:
    obj = typesystem.TypedClass()
    for v in (0, 1, 127, 255, 65535, 0xFFFF_FFFF):
        tag = obj.get_tag()
        tag.value = v
        obj.set_tag(tag)
        check = obj.get_tag()
        assert check.value == v, f"OSType.value {v}: got {check.value}"


def test_independent_instances() -> None:
    a = typesystem.TypedClass(1, 10)
    b = typesystem.TypedClass(2, 20)
    assert a.get_id() == 1
    assert b.get_id() == 2
    assert a.get_value() == 10
    assert b.get_value() == 20
    a.set_value(99)
    assert a.get_value() == 99
    assert b.get_value() == 20, "b.value unchanged after mutating a"


def test_compute_id_single_arg() -> None:
    assert typesystem.compute_id(10) == 20, f"compute_id(10): {typesystem.compute_id(10)}"
    assert typesystem.compute_id(0) == 0
    assert typesystem.compute_id(500) == 1000


def test_compute_id_two_args() -> None:
    assert typesystem.compute_id(10, 5) == 15, f"compute_id(10,5): {typesystem.compute_id(10, 5)}"
    assert typesystem.compute_id(100, 100) == 200
    assert typesystem.compute_id(0, 0) == 0


def test_compute_id_large_values() -> None:
    large = 5_000_000_000
    assert typesystem.compute_id(large) == large * 2
    assert typesystem.compute_id(large, large) == large * 2


if __name__ == "__main__":
    test_default_construction()
    test_two_arg_constructor()
    test_int_set_get()
    test_int64_set_get()
    test_ostype_default_value()
    test_ostype_roundtrip()
    test_ostype_multiple_values()
    test_independent_instances()
    test_compute_id_single_arg()
    test_compute_id_two_args()
    test_compute_id_large_values()
    print("typesystem pybind11 bindings: all checks passed")
    sys.exit(0)
