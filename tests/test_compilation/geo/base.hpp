/// base.hpp — geo scenario: base types (Color enum, Shape base class).
#pragma once

namespace geo {

enum class Color { Red = 0, Green = 1, Blue = 2 };

class Shape {
public:
    Shape() = default;
    explicit Shape(const char* name) : name_(name) {}

    virtual double area() const { return 0.0; }
    virtual double perimeter() const { return 0.0; }
    virtual const char* typeName() const { return "Shape"; }

    const char* getName() const { return name_; }
    void        setName(const char* name) { name_ = name; }

    Color getColor() const { return color_; }
    void  setColor(Color c) { color_ = c; }

    double getScale() const { return scale_; }
    void   setScale(double s) { scale_ = s; }

    static int instanceCount() { return 0; }

public:
    double scale_ = 1.0;

private:
    const char* name_  = "unnamed";
    Color       color_ = Color::Red;
};

} // namespace geo
