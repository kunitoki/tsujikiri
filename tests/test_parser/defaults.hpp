/// defaults.hpp — fixture for default-parameter-value parser tests.
#pragma once

namespace mylib {

class Defaults {
public:
    Defaults() = default;

    int    compute(int x = 0, int y = 1) const;
    double scale(double factor = 1.0, bool normalize = true) const;
    void   greet(const char* msg = "hello") const;
    int    noDefault(int x, int y) const;
};

int freeWithDefault(int x = 42, bool flag = false);

} // namespace mylib
