/// Minimal pybind11 stub for tsujikiri compilation tests.
/// Satisfies zig c++ -fsyntax-only without the real pybind11 library.
#pragma once

namespace pybind11 {

struct module_ {
    template<typename... A>
    module_& def(const char*, A&&...) { return *this; }
};
using module = module_;

template<typename T, typename... Bases>
struct class_ {
    class_(module_&, const char*) {}

    template<typename... A>
    class_& def(const char*, A&&...) { return *this; }

    template<typename... A>
    class_& def_static(const char*, A&&...) { return *this; }

    template<typename M>
    class_& def_readwrite(const char*, M) { return *this; }

    template<typename M>
    class_& def_readonly(const char*, M) { return *this; }
};

template<typename... Args>
struct init {};

template<typename T>
struct enum_ {
    enum_(module_&, const char*) {}
    enum_& value(const char*, T) { return *this; }
    void   export_values() {}
};

} // namespace pybind11

#define PYBIND11_MODULE(name, var) \
    static void _tsujikiri_pybind11_##name(pybind11::module_& var); \
    void        _tsujikiri_pybind11_##name(pybind11::module_& var)
