/// shapes.hpp — geo scenario: derived shapes (Circle, Rectangle).
#pragma once
#include "base.hpp"

namespace geo {

class Circle : public Shape {
public:
    Circle() = default;
    explicit Circle(double radius) : radius_(radius) {}
    Circle(double radius, const char* name) : Shape(name), radius_(radius) {}

    double area() const override { return 3.14159265358979 * radius_ * radius_; }
    double perimeter() const override { return 2.0 * 3.14159265358979 * radius_; }
    const char* typeName() const override { return "Circle"; }

    double getRadius() const { return radius_; }
    void   setRadius(double r) { radius_ = r; }

    void resize(double factor) { radius_ *= factor; }
    void resize(double fx, double fy) { radius_ *= (fx + fy) * 0.5; }

    static Circle unit() { return Circle(1.0); }

public:
    double radius_ = 1.0;
};

class Rectangle : public Shape {
public:
    Rectangle() = default;
    Rectangle(double w, double h) : width_(w), height_(h) {}
    Rectangle(double w, double h, const char* name) : Shape(name), width_(w), height_(h) {}

    double area() const override { return width_ * height_; }
    double perimeter() const override { return 2.0 * (width_ + height_); }
    const char* typeName() const override { return "Rectangle"; }

    double getWidth() const  { return width_; }
    double getHeight() const { return height_; }
    void   setWidth(double w)  { width_ = w; }
    void   setHeight(double h) { height_ = h; }

    bool isSquare() const { return width_ == height_; }

    static Rectangle square(double side) { return Rectangle(side, side); }

public:
    double width_  = 1.0;
    double height_ = 1.0;
};

inline double computeArea(double radius) { return 3.14159265358979 * radius * radius; }
inline double computeArea(double width, double height) { return width * height; }

/// Carries a unary and a binary operator- (they must bind to distinct
/// metamethods) plus a method with two defaulted arguments.
class Vec2 {
public:
    Vec2() = default;
    Vec2(double x, double y) : x(x), y(y) {}

    Vec2 operator-() const { return Vec2(-x, -y); }
    Vec2 operator-(double s) const { return Vec2(x - s, y - s); }

    Vec2 offset(double dx, double dy = 0.0, double scale = 1.0) const
    {
        return Vec2((x + dx) * scale, (y + dy) * scale);
    }

public:
    double x = 0.0;
    double y = 0.0;
};

/// Free binary operator+ — binds as a metamethod on its first operand's class.
inline Vec2 operator+(const Vec2& a, const Vec2& b) { return Vec2(a.x + b.x, a.y + b.y); }

/// Anonymous union holding an array and a nested anonymous struct: `width` and
/// `height` are injected into Extent's scope and bind as ordinary fields, while
/// the array member `raw` is skipped.
class Extent {
public:
    Extent() : width(0.0), height(0.0) {}
    Extent(double w, double h) : width(w), height(h) {}

    double area() const { return width * height; }

public:
    union {
        double raw[2];
        struct {
            double width;
            double height;
        };
    };
};

} // namespace geo
