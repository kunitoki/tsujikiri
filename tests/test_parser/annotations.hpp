/// annotations.hpp — fixture for [[clang::annotate(...)]] parser tests.
///
/// custom namespace attributes such as [[mygame::no_export]] trigger
/// -Wunknown-attributes, which Clang and MSVC cannot silence per namespace.
/// [[clang::annotate("spec")]] is a warning-free alias for [[spec]].
#pragma once

namespace mylib {

class [[clang::annotate("tsujikiri::skip")]] Hidden {
public:
    [[clang::annotate("tsujikiri::skip")]]
    Hidden();

    [[clang::annotate("tsujikiri::rename(\"Alias\")")]]
    double area() const;

    [[clang::annotate("tsujikiri::readonly")]]
    double radius_ = 1.0;

    [[clang::annotate("mygame::no_export")]]
    void internalUpdate();

    [[clang::annotate("skip")]]
    void bareSkip();
};

enum class Color {
    Red [[clang::annotate("tsujikiri::skip")]] = 0,
    Green = 1,
};

[[clang::annotate("tsujikiri::doc(\"Free helper\")")]]
int freeHelper();

} // namespace mylib
