/// new_features.hpp — test fixture for parser gap coverage:
///   scoped enums, anonymous enums, static members, conversion operators,
///   deprecated annotations, deleted copy/move constructors.

#pragma once
#include <ostream>

namespace mylib {

// ── Scoped enum ──────────────────────────────────────────────────────────────
enum class Status { Active = 0, Inactive = 1, Pending = 2 };

// ── Unscoped enum ────────────────────────────────────────────────────────────
enum Direction { North = 0, South = 1, East = 2, West = 3 };

// ── Anonymous enum ────────────────────────────────────────────────────────────
enum { MAX_SIZE = 100, MIN_SIZE = 1 };

// ── Deprecated free function ──────────────────────────────────────────────────
[[deprecated("use newCompute instead")]]
int computeOld(int x);

// ── Deprecated class ─────────────────────────────────────────────────────────
class [[deprecated("use NewWidget instead")]] OldWidget {
public:
    OldWidget() = default;
    void draw();
};

// ── Class with static member variables ───────────────────────────────────────
class Config {
public:
    static int maxRetries;
    static const int version;
    int timeout;
};

// ── Class with conversion operators ──────────────────────────────────────────
class Wrapper {
public:
    Wrapper(int v) : value_(v) {}
    explicit operator bool() const { return value_ != 0; }
    explicit operator int() const { return value_; }
private:
    int value_;
};

// ── Move-only class (deleted copy constructor) ────────────────────────────────
class UniqueResource {
public:
    UniqueResource() = default;
    UniqueResource(UniqueResource&&) = default;
    UniqueResource(const UniqueResource&) = delete;
    UniqueResource& operator=(const UniqueResource&) = delete;
    void use();
};

// ── Class with deprecated method ─────────────────────────────────────────────
class Server {
public:
    void start();
    [[deprecated("use startWithConfig instead")]]
    void startLegacy();
    void startWithConfig(int port);
};

// ── Free-function operator<< for __repr__ ─────────────────────────────────────
class Point {
public:
    Point(double x, double y) : x_(x), y_(y) {}
    double x_;
    double y_;
};

std::ostream& operator<<(std::ostream& os, const Point& p);

// ── Deprecated function with no message (covers parser line 220) ─────────
[[deprecated]]
void legacyOp();

// ── Varargs function (should be auto-suppressed) ───────────────────────────
int formatString(const char* fmt, ...);

// ── Class with varargs method ─────────────────────────────────────────────
class Logger {
public:
    Logger() = default;
    void log(const char* fmt, ...);
    void info(const char* msg);
};

// ── Class with explicit non-deleted copy constructor ─────────────────────
class Copyable {
public:
    Copyable() = default;
    Copyable(const Copyable& other) = default;  // explicit, public, non-deleted
};

// ── Class with deleted move constructor ──────────────────────────────────
class MoveDeleted {
public:
    MoveDeleted() = default;
    MoveDeleted(MoveDeleted&&) = delete;
    MoveDeleted(const MoveDeleted& other) = default;
};

// ── Base class with protected method ──────────────────────────────────────
class Animal {
public:
    Animal() = default;
    virtual void speak() = 0;
protected:
    void breathe();
};

// ── Derived class with using declaration ─────────────────────────────────
class Dog : public Animal {
public:
    Dog() = default;
    void speak() override;
    using Animal::breathe;
};

// ── Nested namespace for qualified using declaration ──────────────────────
namespace inner {
    class InnerBase {
    public:
        void process();
    };
}

// ── Qualified using declaration (namespace prefix exercises 488->487) ────
class InnerDerived : public inner::InnerBase {
public:
    using inner::InnerBase::process;
};

// ── Overloaded using declaration (exercises 487->491 when no TYPE_REF child) ─
struct PrintBase {
    void print();
    void print(int x);
};

struct PrintExtended : public PrintBase {
    using PrintBase::print;
};

} // namespace mylib
