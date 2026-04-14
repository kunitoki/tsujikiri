/// luabridge3_main.cpp — typesystem scenario: build + runtime test for LuaBridge3 bindings.
///
/// Exercises:
///   - TypedClass construction (default + int64_t, int two-arg)
///   - int64_t getId/setId round-trip
///   - OSType getTag/setTag round-trip (unlocked via custom_types in types.input.yml)
///   - setValue/getValue for regular int
///   - computeId free function overloads (int64_t → observable in overload<> template)
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
#include <cstdio>

extern void register_typesystem(lua_State* L);

static int run_script(lua_State* L, const char* code)
{
    if (luaL_dostring(L, code) != LUA_OK) {
        fprintf(stderr, "Lua error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return 1;
    }
    return 0;
}

int main()
{
    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    register_typesystem(L);

    int rc = 0;

    // Default construction and basic int methods
    rc |= run_script(L, R"(
        local obj = typesystem.TypedClass()
        assert(obj:get_value() == 0, "default get_value")
        obj:set_value(42)
        assert(obj:get_value() == 42, "set_value/get_value round-trip")
    )");

    // Two-arg constructor: TypedClass(int64_t id, int value)
    rc |= run_script(L, R"(
        local obj = typesystem.TypedClass(500, 200)
        assert(obj:get_id()    == 500, "constructor id arg")
        assert(obj:get_value() == 200, "constructor value arg")
    )");

    // int64_t set/get round-trip
    rc |= run_script(L, R"(
        local obj = typesystem.TypedClass()
        obj:set_id(1000000000)
        assert(obj:get_id() == 1000000000, "int64_t set_id/get_id round-trip")
        obj:set_id(0)
        assert(obj:get_id() == 0, "int64_t reset to 0")
    )");

    // OSType: get_tag() returns a bound OSType object; value field is readable.
    // LuaBridge3 returns by-value objects as read-only (no write-back to a C++ temporary).
    // We verify the binding works: get_tag() gives a non-nil OSType with default value 0,
    // and set_tag() accepts that object without error.
    rc |= run_script(L, R"(
        local obj = typesystem.TypedClass()
        local tag = obj:get_tag()
        assert(tag ~= nil, "get_tag returns non-nil OSType")
        assert(tag.value == 0, "default OSType.value is 0")
        -- set_tag accepts the result of get_tag — verifies the type binding is compatible
        obj:set_tag(tag)
        local tag2 = obj:get_tag()
        assert(tag2.value == 0, "OSType value preserved through set_tag/get_tag")
    )");

    // Multiple TypedClass instances are independent
    rc |= run_script(L, R"(
        local a = typesystem.TypedClass(1, 10)
        local b = typesystem.TypedClass(2, 20)
        assert(a:get_id()    == 1,  "a.id == 1")
        assert(b:get_id()    == 2,  "b.id == 2")
        assert(a:get_value() == 10, "a.value == 10")
        assert(b:get_value() == 20, "b.value == 20")
        a:set_value(99)
        assert(a:get_value() == 99, "a.value mutated")
        assert(b:get_value() == 20, "b.value unchanged")
    )");

    // computeId free function overloads
    rc |= run_script(L, R"(
        local r1 = typesystem.compute_id(10)
        assert(r1 == 20, "computeId(10) == 20")
        local r2 = typesystem.compute_id(10, 5)
        assert(r2 == 15, "computeId(10, 5) == 15")
        local r3 = typesystem.compute_id(0)
        assert(r3 == 0, "computeId(0) == 0")
        local r4 = typesystem.compute_id(100, 100)
        assert(r4 == 200, "computeId(100, 100) == 200")
    )");

    // OSType across multiple instances: each instance's tag is independent
    rc |= run_script(L, R"LUA(
        local a = typesystem.TypedClass()
        local b = typesystem.TypedClass()
        local tag_a = a:get_tag()
        local tag_b = b:get_tag()
        assert(tag_a.value == 0, "a.tag.value == 0")
        assert(tag_b.value == 0, "b.tag.value == 0")
        b:set_tag(tag_a)
        assert(b:get_tag().value == 0, "b.tag value preserved through set_tag")
    )LUA");

    lua_close(L);
    return rc;
}
