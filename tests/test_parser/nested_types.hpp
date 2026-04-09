/// nested_types.hpp — fixture for parser nested class/enum tests.
#pragma once

// Top-level typedef triggers _collect_namespace_cursors continue (kind != NAMESPACE)
typedef int GlobalInt;

namespace mylib {

class Container {
public:
    Container();

    enum Status { Active = 0, Inactive = 1 };

    class Item {
    public:
        Item();
        int value_;
    };

    int data_;
};

} // namespace mylib
