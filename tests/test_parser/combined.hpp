/// combined.hpp — fixture for parser tests.
/// Same content as tests/test_compilation/combined.hpp (duplicated by design:
/// each test folder is self-contained).
#pragma once

namespace mylib {

enum class Color { Red = 0, Green = 1, Blue = 2 };

struct Protected {};
struct Private {};

class Shape {
public:
    Shape() noexcept;
    explicit Shape(const char* name);

    virtual double area() const noexcept = 0;
    virtual double perimeter() const = 0;

    const char* getName() const [[tsujikiri::skip]];
    void        setName(const char* name) [[tsujikiri::rename("name")]];
    double      getScale() const [[mygame::no_export]];
    [[mygame::no_export]]
    void        setScale(double scale);

protected:
    void protectedMethod() const;

private:
    void privateMethod() const noexcept;

public:
    double scale_;
};

class Circle : public Shape, protected Protected, private Private {
public:
    Circle() noexcept;
    explicit Circle(double radius);

    double area() const noexcept;
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

double computeArea(double radius) noexcept;
double computeArea(double width, double height);

} // namespace mylib
