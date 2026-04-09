/// combined.hpp — fixture for compilation tests.
/// Uses only primitive-type returns so the C API header is valid C.
#pragma once

namespace mylib {

enum class Color { Red = 0, Green = 1, Blue = 2 };

class Shape {
public:
    Shape() = default;
    explicit Shape(const char* name) {}

    virtual double area() const { return 0.0; }
    virtual double perimeter() const { return 0.0; }

    const char* getName() const { return ""; }
    void        setName(const char* name) {}
    double      getScale() const { return 0.0; }
    void        setScale(double scale) {}

public:
    double scale_ = 1.0;
};

class Circle : public Shape {
public:
    Circle() = default;
    explicit Circle(double radius) : radius_(radius) {}

    double area() const { return 3.14159 * radius_ * radius_; }
    double perimeter() const { return 2 * 3.14159 * radius_; }

    double getRadius() const { return radius_; }
    void   setRadius(double r) { radius_ = r; }

    void resize(double factor) { radius_ *= factor; }
    void resize(double factorX, double factorY) { radius_ *= (factorX + factorY) / 2; }

public:
    double radius_ = 1.0;
};

class Calculator {
public:
    Calculator() = default;

    int    add(int a, int b) { return a + b; }
    double add(double a, double b) { return a + b; }

    static int    max(int a, int b) { return (a > b) ? a : b; }
    static double max(double a, double b) { return (a > b) ? a : b; }

    int  getValue() const { return value_; }
    void setValue(int v) { value_ = v; }

protected:
    int protectedValue_ = 0;

private:
    int value_ = 0;
};

inline double computeArea(double radius) { return 3.14159 * radius * radius; }
inline double computeArea(double width, double height) { return width * height; }

} // namespace mylib
