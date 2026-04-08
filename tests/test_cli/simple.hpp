/// simple.hpp — fixture for CLI tests.
#pragma once

namespace simple {

class Widget {
public:
    Widget();
    explicit Widget(int id);

    int  getId() const;
    void setId(int id);

public:
    int id_;
};

int add(int a, int b);

} // namespace simple
