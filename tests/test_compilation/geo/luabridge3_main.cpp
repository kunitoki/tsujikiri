/// luabridge3_main.cpp — geo scenario: build + runtime test for LuaBridge3 bindings.
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
#include <cstdio>

extern void register_geo(lua_State* L);

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
    register_geo(L);

    int rc = 0;

    // Shape base class construction and basic methods
    rc |= run_script(L, R"(
        local s = geo.Shape()
        assert(s:area() == 0.0, "Shape default area")
        assert(s:perimeter() == 0.0, "Shape default perimeter")
        local s2 = geo.Shape("named")
        assert(s2:type_name() == "Shape", "Shape type_name")
    )");

    // Circle construction, area, perimeter, resize (overloaded)
    rc |= run_script(L, R"(
        local pi = 3.14159265358979
        local c = geo.Circle(5.0)
        assert(math.abs(c:area() - pi * 25.0) < 0.001, "Circle area r=5")
        assert(math.abs(c:perimeter() - 2 * pi * 5.0) < 0.001, "Circle perimeter r=5")
        assert(c:type_name() == "Circle", "Circle type_name")
        c:resize(2.0)
        assert(math.abs(c:get_radius() - 10.0) < 0.001, "Circle resize x1")
        c:resize(1.0, 3.0)
        assert(math.abs(c:get_radius() - 20.0) < 0.001, "Circle resize x2")
    )");

    // Rectangle construction, area, is_square, setters
    rc |= run_script(L, R"(
        local r = geo.Rectangle(3.0, 4.0)
        assert(math.abs(r:area() - 12.0) < 0.001, "Rectangle area")
        assert(math.abs(r:perimeter() - 14.0) < 0.001, "Rectangle perimeter")
        assert(not r:is_square(), "Rectangle is not square")
        r:set_width(4.0)
        assert(r:is_square(), "Rectangle becomes square")
    )");

    // Static factories
    rc |= run_script(L, R"(
        local c = geo.Circle.unit()
        assert(math.abs(c:get_radius() - 1.0) < 0.001, "Circle unit factory")
        local sq = geo.Rectangle.square(7.0)
        assert(sq:is_square(), "Rectangle square factory")
        assert(math.abs(sq:area() - 49.0) < 0.001, "Rectangle square area")
    )");

    // Inheritance: Circle can call Shape methods
    rc |= run_script(L, R"(
        local c = geo.Circle(3.0)
        c:set_scale(2.5)
        assert(math.abs(c:get_scale() - 2.5) < 0.001, "Circle get_scale via Shape")
        c:set_name("my_circle")
        assert(c:get_name() == "my_circle", "Circle get_name via Shape")
    )");

    // Color enum values are accessible
    rc |= run_script(L, R"(
        assert(geo.Color.Red   == 0, "Color.Red == 0")
        assert(geo.Color.Green == 1, "Color.Green == 1")
        assert(geo.Color.Blue  == 2, "Color.Blue == 2")
    )");

    // Free function overloads (use custom raw-string delimiter to avoid )" collision)
    rc |= run_script(L, R"LUA(
        local pi = 3.14159265358979
        local a1 = geo.compute_area(3.0)
        assert(math.abs(a1 - pi * 9.0) < 0.001, "computeArea radius")
        local a2 = geo.compute_area(4.0, 5.0)
        assert(math.abs(a2 - 20.0) < 0.001, "computeArea width height")
    )LUA");

    lua_close(L);
    return rc;
}
