/// filter.hpp — fixture for filter tests.
#pragma once

namespace testns {

class Allowed {};
class Blacklisted {};
class InternalClass {};
class DetailImpl {};  // matches ".*Impl$" regex

class HasMethods {
public:
    void keep();
    void skipGlobal();
    void skipPerClass();
    void operator+(const HasMethods&);
};

class HasFields {
public:
    int  keep_;
    int  pimpl_;
};

enum class KeepEnum   { A = 0, B = 1 };
enum class SkipEnum   { X = 0, Y = 1 };

void freeKeep();
void freeSkip();

} // namespace testns
