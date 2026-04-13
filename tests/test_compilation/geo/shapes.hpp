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

} // namespace geo
