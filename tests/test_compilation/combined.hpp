/// combined.hpp — fixture for compilation tests.
/// Uses only primitive-type returns so the C API header is valid C.
#pragma once

namespace mylib {

enum class Color { Red = 0, Green = 1, Blue = 2 };

class Shape {
public:
    Shape();
    explicit Shape(const char* name);

    virtual double area() const;
    virtual double perimeter() const;

    const char* getName() const;
    void        setName(const char* name);
    double      getScale() const;
    void        setScale(double scale);

public:
    double scale_;
};

class Circle : public Shape {
public:
    Circle();
    explicit Circle(double radius);

    double area() const;
    double perimeter() const;

    double getRadius() const;
    void   setRadius(double r);

    void resize(double factor);
    void resize(double factorX, double factorY);

public:
    double radius_;
};

class Calculator {
public:
    Calculator();

    int    add(int a, int b);
    double add(double a, double b);

    static int    max(int a, int b);
    static double max(double a, double b);

    int  getValue() const;
    void setValue(int v);

public:
    int value_;
};

double computeArea(double radius);
double computeArea(double width, double height);

} // namespace mylib
