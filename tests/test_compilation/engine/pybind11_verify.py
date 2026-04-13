"""pybind11 runtime verification for the engine scenario (multi-namespace: math + engine).

Run with: python pybind11_verify.py
Requires PYTHONPATH to contain the directory with the built engine extension module.

Note: constructors and methods taking const char* are avoided here because
pybind11 converts Python str to a temporary const char* whose lifetime is
limited to the call — storing that pointer (as entity/audio classes do) is
unsafe. We test only numeric/boolean API surface.
"""
from __future__ import annotations

import math
import sys

import engine  # type: ignore  # noqa: E402


def test_vec3() -> None:
    v = engine.Vec3(3.0, 4.0, 0.0)
    assert abs(v.length() - 5.0) < 0.001, f"Vec3.length() {v.length()}"
    assert abs(v.x - 3.0) < 0.001, f"Vec3.x {v.x}"
    assert abs(v.y - 4.0) < 0.001, f"Vec3.y {v.y}"
    assert abs(v.z - 0.0) < 0.001, f"Vec3.z {v.z}"


def test_vec3_static_factories() -> None:
    z = engine.Vec3.zero()
    assert z.length() == 0.0, f"Vec3.zero length {z.length()}"
    u = engine.Vec3.up()
    assert abs(u.y - 1.0) < 0.001, f"Vec3.up y {u.y}"
    f = engine.Vec3.forward()
    assert abs(f.z - (-1.0)) < 0.001, f"Vec3.forward z {f.z}"


def test_vec3_methods() -> None:
    a = engine.Vec3(1.0, 0.0, 0.0)
    b = engine.Vec3(0.0, 1.0, 0.0)
    c = a.add(b)
    assert abs(c.x - 1.0) < 0.001, f"Vec3.add x {c.x}"
    assert abs(c.y - 1.0) < 0.001, f"Vec3.add y {c.y}"
    d = a.scale(3.0)
    assert abs(d.x - 3.0) < 0.001, f"Vec3.scale x {d.x}"


def test_entity_boolean_methods() -> None:
    e = engine.Entity()
    assert e.is_active(), "Entity is_active default"
    e.set_active(False)
    assert not e.is_active(), "Entity set_active False"
    e.set_active(True)
    assert e.is_active(), "Entity set_active True"


def test_entity_position_with_vec3() -> None:
    v = engine.Vec3(1.0, 2.0, 3.0)
    e = engine.Entity()
    e.set_position(v)
    pos = e.get_position()
    assert abs(pos.x - 1.0) < 0.001, f"Entity pos.x {pos.x}"
    assert abs(pos.y - 2.0) < 0.001, f"Entity pos.y {pos.y}"
    assert abs(pos.z - 3.0) < 0.001, f"Entity pos.z {pos.z}"


def test_player_health() -> None:
    p = engine.Player()
    assert abs(p.get_health() - 100.0) < 0.001, f"Player health {p.get_health()}"
    p.take_damage(30.0)
    assert abs(p.get_health() - 70.0) < 0.001, f"Player after damage {p.get_health()}"
    assert p.is_alive(), "Player is alive after 30 damage"
    p.take_damage(200.0)
    assert not p.is_alive(), "Player dead after lethal damage"


def test_player_inherits_entity() -> None:
    p = engine.Player()
    # is_active / set_active are inherited from Entity
    assert p.is_active(), "Player is_active via Entity default"
    p.set_active(False)
    assert not p.is_active(), "Player set_active via Entity"


def test_player_move_uses_vec3() -> None:
    p = engine.Player()
    direction = engine.Vec3(1.0, 0.0, 0.0)
    p.move(direction)
    pos = p.get_position()
    assert abs(pos.x - 1.0) < 0.001, f"Player moved x {pos.x}"


def test_free_functions() -> None:
    a = engine.Vec3(1.0, 0.0, 0.0)
    b = engine.Vec3(0.0, 1.0, 0.0)
    d = engine.dot(a, b)
    assert abs(d - 0.0) < 0.001, f"dot(x,y) {d}"
    d2 = engine.dot(a, a)
    assert abs(d2 - 1.0) < 0.001, f"dot(x,x) {d2}"
    c = engine.cross(a, b)
    assert abs(c.z - 1.0) < 0.001, f"cross(x,y).z {c.z}"


if __name__ == "__main__":
    test_vec3()
    test_vec3_static_factories()
    test_vec3_methods()
    test_entity_boolean_methods()
    test_entity_position_with_vec3()
    test_player_health()
    test_player_inherits_entity()
    test_player_move_uses_vec3()
    test_free_functions()
    print("engine pybind11 bindings: all checks passed")
    sys.exit(0)
