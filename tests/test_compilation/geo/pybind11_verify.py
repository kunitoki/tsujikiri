"""pybind11 runtime verification for the geo scenario.

Run with: python pybind11_verify.py
Requires PYTHONPATH to contain the directory with the built geo extension module.
"""

from __future__ import annotations

import sys

import geo  # type: ignore  # noqa: E402


def test_shape() -> None:
    s = geo.Shape()
    assert s.area() == 0.0, f"Shape.area() expected 0, got {s.area()}"
    assert s.perimeter() == 0.0, f"Shape.perimeter() expected 0, got {s.perimeter()}"
    assert s.type_name() == "Shape", f"Shape.typeName() expected 'Shape', got {s.type_name()}"


def test_circle() -> None:
    pi = 3.14159265358979
    c = geo.Circle(5.0)
    assert abs(c.area() - pi * 25.0) < 0.001, f"Circle.area() {c.area()}"
    assert abs(c.perimeter() - 2 * pi * 5.0) < 0.001, f"Circle.perimeter() {c.perimeter()}"
    assert c.type_name() == "Circle", f"Circle.typeName() {c.type_name()}"

    c.resize(2.0)
    assert abs(c.get_radius() - 10.0) < 0.001, f"Circle.resize(2) {c.get_radius()}"

    c.resize(1.0, 3.0)
    assert abs(c.get_radius() - 20.0) < 0.001, f"Circle.resize(1,3) {c.get_radius()}"


def test_rectangle() -> None:
    r = geo.Rectangle(3.0, 4.0)
    assert abs(r.area() - 12.0) < 0.001, f"Rectangle.area() {r.area()}"
    assert abs(r.perimeter() - 14.0) < 0.001, f"Rectangle.perimeter() {r.perimeter()}"
    assert not r.is_square(), "Rectangle(3,4) is not square"

    r.set_width(4.0)
    assert r.is_square(), "Rectangle(4,4) is square"


def test_static_factories() -> None:
    c = geo.Circle.unit()
    assert abs(c.get_radius() - 1.0) < 0.001, f"Circle.unit() {c.get_radius()}"

    sq = geo.Rectangle.square(7.0)
    assert sq.is_square(), "Rectangle.square(7) is square"
    assert abs(sq.area() - 49.0) < 0.001, f"Rectangle.square(7).area() {sq.area()}"


def test_inheritance() -> None:
    # Circle inherits Shape members
    c = geo.Circle(3.0)
    c.set_scale(2.5)
    assert abs(c.get_scale() - 2.5) < 0.001, f"Circle.getScale via Shape {c.get_scale()}"


def test_color_enum() -> None:
    assert geo.Color.Red == geo.Color.Red, "Color.Red identity"
    assert geo.Color.Green != geo.Color.Red, "Color.Green != Color.Red"
    assert geo.Color.Blue != geo.Color.Green, "Color.Blue != Color.Green"


def test_free_functions() -> None:
    pi = 3.14159265358979
    a1 = geo.compute_area(3.0)
    assert abs(a1 - pi * 9.0) < 0.001, f"computeArea(r) {a1}"
    a2 = geo.compute_area(4.0, 5.0)
    assert abs(a2 - 20.0) < 0.001, f"computeArea(w,h) {a2}"


def test_default_arguments() -> None:
    v = geo.Vec2(2.0, 3.0)
    a = v.offset(1.0)
    assert abs(a.x - 3.0) < 0.001 and abs(a.y - 3.0) < 0.001, f"offset(dx) {a.x},{a.y}"
    b = v.offset(1.0, 2.0)
    assert abs(b.x - 3.0) < 0.001 and abs(b.y - 5.0) < 0.001, f"offset(dx,dy) {b.x},{b.y}"
    c = v.offset(1.0, 2.0, 2.0)
    assert abs(c.x - 6.0) < 0.001 and abs(c.y - 10.0) < 0.001, f"offset(dx,dy,scale) {c.x},{c.y}"


def test_unary_and_binary_operators() -> None:
    v = geo.Vec2(2.0, 3.0)
    n = -v
    assert abs(n.x + 2.0) < 0.001 and abs(n.y + 3.0) < 0.001, f"__neg__ {n.x},{n.y}"
    s = v - 1.0
    assert abs(s.x - 1.0) < 0.001 and abs(s.y - 2.0) < 0.001, f"__sub__ {s.x},{s.y}"


def test_free_operator() -> None:
    total = geo.Vec2(1.0, 2.0) + geo.Vec2(3.0, 4.0)
    assert abs(total.x - 4.0) < 0.001 and abs(total.y - 6.0) < 0.001, f"__add__ {total.x},{total.y}"


def test_anonymous_union_fields() -> None:
    e = geo.Extent(3.0, 4.0)
    assert abs(e.width - 3.0) < 0.001, f"Extent.width {e.width}"
    assert abs(e.height - 4.0) < 0.001, f"Extent.height {e.height}"
    assert abs(e.area() - 12.0) < 0.001, f"Extent.area() {e.area()}"
    e.width = 5.0
    assert abs(e.area() - 20.0) < 0.001, "Extent.width is writable"
    assert not hasattr(e, "raw"), "array member is not bound"


if __name__ == "__main__":
    test_shape()
    test_circle()
    test_rectangle()
    test_static_factories()
    test_inheritance()
    test_color_enum()
    test_free_functions()
    test_default_arguments()
    test_unary_and_binary_operators()
    test_free_operator()
    test_anonymous_union_fields()
    print("geo pybind11 bindings: all checks passed")
    sys.exit(0)
