/// luabridge3_main.cpp — transforms scenario: build + runtime test for LuaBridge3 bindings.
/// Exercises all transform stages by verifying the generated binding behaves correctly.
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
#include <cstdio>

extern void register_transforms(lua_State* L);

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
    register_transforms(L);

    int rc = 0;

    // rename_class: WidgetManager -> Manager
    rc |= run_script(L, R"(
        assert(transforms.Manager ~= nil, "Manager class present after rename_class")
        assert(transforms.WidgetManager == nil, "WidgetManager absent after rename_class")
        local m = transforms.Manager()
        assert(m:get_count() == 0, "Manager get_count initial value")
    )");

    // suppress_class: WidgetInternal absent
    rc |= run_script(L, R"(
        assert(transforms.WidgetInternal == nil, "WidgetInternal absent after suppress_class")
    )");

    // rename_method: getIdInternal -> get_id
    rc |= run_script(L, R"(
        local w = transforms.Widget(5)
        assert(w:get_id() == 5, "rename_method: get_id works")
    )");

    // suppress_method: legacyReset absent; describe re-injected via inject_method
    rc |= run_script(L, R"(
        local w = transforms.Widget(1)
        assert(w.legacyReset == nil, "suppress_method: legacyReset absent")
        local desc = w:describe()
        assert(type(desc) == "string", "inject_method: describe returns string")
        assert(#desc > 0, "inject_method: describe returns non-empty string")
    )");

    // modify_method: processData -> process_data
    rc |= run_script(L, R"(
        local w = transforms.Widget(10)
        w:process_data(3)
        assert(w:get_id() == 13, "modify_method: process_data adds to id")
    )");

    // modify_argument: configure(rawOption, rawName) -> configure(option, name)
    // (Lua uses positional args; just verify the method works)
    rc |= run_script(L, R"(
        local w = transforms.Widget()
        w:configure(42, "hello")
        assert(w:get_id() == 42, "modify_argument: configure sets id via option arg")
    )");

    // remove_overload: update(float) removed; update(int) and update(double) still work
    rc |= run_script(L, R"(
        local w = transforms.Widget()
        w:update(7)
        assert(w:get_id() == 7, "remove_overload: update(int) works")
        w:update(3.14)
        assert(w:get_id() == 3, "remove_overload: update(double) works")
    )");

    // overload_priority: both compute overloads present
    rc |= run_script(L, R"(
        local w = transforms.Widget()
        local r1 = w:compute(3)
        assert(math.abs(r1 - 9.0) < 0.001, "overload_priority: compute(int) = 9")
        local r2 = w:compute(2.5)
        assert(math.abs(r2 - 6.25) < 0.001, "overload_priority: compute(double) = 6.25")
    )");

    // inject_property: raw_value readable and writable
    rc |= run_script(L, R"(
        local w = transforms.Widget(0)
        w.raw_value = 7
        assert(w.raw_value == 7, "inject_property: raw_value write/read")
        assert(w:get_id() == 7, "inject_property: raw_value aliases id_")
    )");

    // modify_constructor: Widget(int, int) re-injected via inject_constructor
    rc |= run_script(L, R"(
        local w = transforms.Widget(1, 2)
        assert(w:get_id() == 3, "inject_constructor: Widget(1,2).id == 1+2 == 3")
    )");

    // modify_field: id_ renamed to "id"; cache_name_ removed
    rc |= run_script(L, R"(
        local w = transforms.Widget(99)
        assert(w.id == 99, "modify_field rename: id field accessible")
        assert(w.cache_name_ == nil, "modify_field remove: cache_name_ absent")
    )");

    // inject_code: static_assert in generated file compiles fine (no runtime check needed)

    // rename_enum: OldColor -> Color
    rc |= run_script(L, R"(
        assert(transforms.Color ~= nil, "rename_enum: Color namespace present")
        assert(transforms.OldColor == nil, "rename_enum: OldColor absent")
    )");

    // rename_enum_value: Red -> Crimson; suppress_enum_value: Alpha absent
    rc |= run_script(L, R"(
        assert(transforms.Color.Crimson == 0, "rename_enum_value: Crimson == 0")
        assert(transforms.Color.Red == nil, "rename_enum_value: Red absent")
        assert(transforms.Color.Alpha == nil, "suppress_enum_value: Alpha absent")
        assert(transforms.Color.Green == 1, "enum value Green still present")
        assert(transforms.Color.Blue == 2, "enum value Blue still present")
    )");

    // suppress_enum: WidgetState absent
    rc |= run_script(L, R"(
        assert(transforms.WidgetState == nil, "suppress_enum: WidgetState absent")
    )");

    // rename_function: computeWidgetScore -> compute_score
    rc |= run_script(L, R"(
        assert(transforms.compute_score ~= nil, "rename_function: compute_score present")
        assert(transforms.compute_score(3) == 9, "rename_function: compute_score(3) == 9")
        assert(transforms.computeWidgetScore == nil, "rename_function: computeWidgetScore absent")
    )");

    // suppress_function: internalUtility absent
    rc |= run_script(L, R"(
        assert(transforms.internal_utility == nil, "suppress_function: internalUtility absent")
    )");

    // inject_function: makeWidget re-injected (suppressed original, then injected back)
    rc |= run_script(L, R"(
        assert(transforms.make_widget ~= nil, "inject_function: make_widget present")
        local w = transforms.make_widget(5)
        assert(w:get_id() == 5, "inject_function: make_widget creates Widget with id 5")
    )");

    // modify_function: processWidget -> process_widget
    rc |= run_script(L, R"(
        assert(transforms.process_widget ~= nil, "modify_function: process_widget present")
        assert(math.abs(transforms.process_widget(2.0) - 4.0) < 0.001, "modify_function: process_widget(2.0) == 4.0")
    )");

    // suppress_base: DerivedWidget derives from Widget (not BaseHelper in binding)
    rc |= run_script(L, R"(
        local dw = transforms.DerivedWidget(3)
        assert(dw:get_id() == 3, "suppress_base: DerivedWidget inherits Widget methods")
        assert(dw.helperMethod == nil, "suppress_base: BaseHelper methods not exposed")
    )");

    // resolve_using_declarations: ExtendedWidget has extendedMethod and extendedValue
    rc |= run_script(L, R"(
        local ew = transforms.ExtendedWidget()
        assert(ew.extended_method ~= nil, "resolve_using_declarations: extended_method present")
        assert(ew.extended_value ~= nil, "resolve_using_declarations: extended_value present")
        assert(ew:extended_value() == 0, "resolve_using_declarations: initial extended_value == 0")
        ew:extended_method(7)
        assert(ew:extended_value() == 7, "resolve_using_declarations: extended_value after method call")
    )");

    // expand_spaceship: Score has comparison metamethods
    rc |= run_script(L, R"(
        local s1 = transforms.Score(1)
        local s2 = transforms.Score(2)
        assert(s1 < s2, "expand_spaceship: Score s1 < s2")
        assert(s1 <= s2, "expand_spaceship: Score s1 <= s2")
        assert(s2 > s1, "expand_spaceship: Score s2 > s1")
        assert(s2 >= s1, "expand_spaceship: Score s2 >= s1")
        assert(s1 == s1, "expand_spaceship: Score s1 == s1")
        assert(s1 ~= s2, "expand_spaceship: Score s1 ~= s2")
    )");

    lua_close(L);
    return rc;
}
