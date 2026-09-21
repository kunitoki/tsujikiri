/// annotate.hpp — fixture for CLI tests exercising [[clang::annotate(...)]].
#pragma once

namespace annotated {

class Widget {
public:
    Widget();

    // Hidden from the bindings via a namespaced built-in payload.
    [[clang::annotate("tsujikiri::skip")]]
    void internal();

    // Bare payload resolves to the tsujikiri:: built-ins.
    [[clang::annotate("skip")]]
    void bareInternal();

    // Renamed through a payload carrying an argument.
    [[clang::annotate("tsujikiri::rename(\"identifier\")")]]
    int getId() const;

    // Re-enabled via a custom handler registered in the input.yml.
    [[clang::annotate("mygame::export")]]
    void exported();
};

} // namespace annotated
