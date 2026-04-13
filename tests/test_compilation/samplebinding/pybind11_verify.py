"""pybind11 runtime verification for the samplebinding scenario.

Demonstrates:
  - Python subclassing a C++ class with virtual methods (trampoline)
  - Overriding virtual methods from Python
  - Ownership transfer: Truck.add_flavor() takes ownership of Icecream
  - shared_ptr holder type
"""
from __future__ import annotations

import sys

import samplebinding  # type: ignore  # noqa: E402


def test_basic_icecream() -> None:
    ice = samplebinding.Icecream("vanilla")
    assert ice.get_flavor() == "vanilla", f"Expected 'vanilla', got '{ice.get_flavor()}'"
    clone = ice.clone()
    assert clone.get_flavor() == "vanilla", f"Clone flavor mismatch: {clone.get_flavor()}"


def test_python_subclass_overrides_virtual() -> None:
    class ChocolateIcecream(samplebinding.Icecream):
        def __init__(self) -> None:
            super().__init__("chocolate")

        def get_flavor(self) -> str:
            return "double-chocolate"

        def clone(self) -> samplebinding.Icecream:
            c = ChocolateIcecream()
            return c

    ice = ChocolateIcecream()
    assert ice.get_flavor() == "double-chocolate", (
        f"Expected 'double-chocolate', got '{ice.get_flavor()}'"
    )
    clone = ice.clone()
    assert clone.get_flavor() == "double-chocolate", (
        f"Clone flavor mismatch: {clone.get_flavor()}"
    )


def test_truck_holds_flavors() -> None:
    strawberry = samplebinding.Icecream("strawberry")
    mint = samplebinding.Icecream("mint")
    truck = samplebinding.Truck()
    truck.add_flavor(strawberry)
    truck.add_flavor(mint)
    assert truck.flavor_count() == 2, f"Expected 2 flavors, got {truck.flavor_count()}"
    assert truck.flavor_at(0) == "strawberry", f"flavor_at(0): {truck.flavor_at(0)}"
    assert truck.flavor_at(1) == "mint", f"flavor_at(1): {truck.flavor_at(1)}"


def test_truck_with_python_subclass_flavor() -> None:
    class VanillaIcecream(samplebinding.Icecream):
        def __init__(self) -> None:
            super().__init__("plain")

        def get_flavor(self) -> str:
            return "vanilla-bean"

    # Hold an explicit reference — pybind11 trampolines require the Python object
    # to stay alive for virtual dispatch to call back into Python.
    ice = VanillaIcecream()
    truck = samplebinding.Truck()
    truck.add_flavor(ice)
    assert truck.flavor_count() == 1
    # The truck calls getFlavor() via virtual dispatch — should hit Python override
    assert truck.flavor_at(0) == "vanilla-bean", (
        f"Virtual dispatch through Truck: {truck.flavor_at(0)}"
    )


def test_truck_is_leaving_flag() -> None:
    t1 = samplebinding.Truck(False)
    t2 = samplebinding.Truck(True)
    assert not t1.is_leaving()
    assert t2.is_leaving()


if __name__ == "__main__":
    test_basic_icecream()
    test_python_subclass_overrides_virtual()
    test_truck_holds_flavors()
    test_truck_with_python_subclass_flavor()
    test_truck_is_leaving_flag()
    print("samplebinding pybind11 bindings: all checks passed")
    sys.exit(0)
