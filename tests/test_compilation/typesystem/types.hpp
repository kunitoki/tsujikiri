/// types.hpp — typesystem scenario.
///
/// Demonstrates:
///   - primitive_types mapping (int64_t methods remappable via TypesystemConfig)
///   - custom_types unlocking (OSType methods filtered by default, unlocked via custom_types)
///   - free function overloads using int64_t (type appears in luabridge3 overload<> template)
#pragma once

#include <cstdint>

namespace types {

// OSType is listed in the default unsupported_types for luabridge3/pybind11/luals/pyi.
// Using a struct so libclang preserves the type name (not resolved to a builtin),
// making it detectable via the unsupported_types substring check.
struct OSType {
    unsigned int value = 0;
};

class TypedClass {
public:
    TypedClass() = default;
    explicit TypedClass(int64_t id, int value) : id_(id), value_(value), tag_{} {}

    // Uses int64_t — remappable via primitive_types in TypesystemConfig
    int64_t getId() const { return id_; }
    void setId(int64_t id) { id_ = id; }

    // Uses OSType — filtered by default (OSType is in unsupported_types),
    // unlockable via custom_types in TypesystemConfig
    OSType getTag() const { return tag_; }
    void setTag(OSType tag) { tag_ = tag; }

    // Regular int method — always included regardless of typesystem config
    int getValue() const { return value_; }
    void setValue(int v) { value_ = v; }

private:
    int64_t id_ = 0;
    OSType tag_ = {};
    int value_ = 0;
};

// Free function overloads using int64_t — type appears explicitly in
// luabridge3 overload<> template output, so mapping is observable.
inline int64_t computeId(int64_t base) { return base * 2; }
inline int64_t computeId(int64_t base, int64_t offset) { return base + offset; }

} // namespace types
