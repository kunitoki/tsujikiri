/// Minimal LuaBridge3 stub for tsujikiri compilation tests.
/// Satisfies zig c++ -fsyntax-only without the real LuaBridge3 library.
///
/// Chain: getGlobalNamespace → Namespace
///        Namespace.beginClass<T>  → ClassProxy<T>
///        ClassProxy.addFunction/addProperty/... → ClassProxy<T>& (chainable)
///        ClassProxy.endClass()    → Namespace
///        Namespace.deriveClass<T,B> → ClassProxy<T>
///        Namespace.beginNamespace → Namespace
///        Namespace.endNamespace   → Namespace
///        ;                        terminates expression
#pragma once

struct lua_State {};

namespace luabridge {

struct Namespace;

template<typename T>
struct ClassProxy {
    template<typename... A>
    ClassProxy& addFunction(const char*, A&&...) { return *this; }

    template<typename... A>
    ClassProxy& addStaticFunction(const char*, A&&...) { return *this; }

    template<typename... A>
    ClassProxy& addConstructor() { return *this; }

    template<typename... A>
    ClassProxy& addProperty(const char*, A&&...) { return *this; }

    Namespace endClass();
};

struct Namespace {
    template<typename T>
    ClassProxy<T> beginClass(const char*) { return {}; }

    template<typename T, typename Base>
    ClassProxy<T> deriveClass(const char*) { return {}; }

    Namespace beginNamespace(const char*) { return {}; }
    Namespace endNamespace() { return {}; }

    template<typename... A>
    Namespace& addFunction(const char*, A&&...) { return *this; }

    template<typename... A>
    Namespace& addProperty(const char*, A&&...) { return *this; }

    template<typename... A>
    Namespace& addVariable(const char*, A&&...) { return *this; }
};

template<typename T>
inline Namespace ClassProxy<T>::endClass() { return {}; }

inline Namespace getGlobalNamespace(lua_State*) { return {}; }

} // namespace luabridge
