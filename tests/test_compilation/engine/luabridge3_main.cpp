/// luabridge3_main.cpp — engine scenario: multi-namespace (math + engine) LuaBridge3 test.
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
#include <cstdio>

extern void register_engine(lua_State* L);

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
    register_engine(L);

    int rc = 0;

    // Vec3 from math namespace — registered under engine module namespace
    rc |= run_script(L, R"(
        local v = engine.Vec3(3.0, 4.0, 0.0)
        assert(math.abs(v:length() - 5.0) < 0.001, "Vec3 length " .. v:length())
        assert(math.abs(v.x - 3.0) < 0.001, "Vec3.x field")
        assert(math.abs(v.y - 4.0) < 0.001, "Vec3.y field")
        assert(math.abs(v.z - 0.0) < 0.001, "Vec3.z field")
    )");

    // Vec3 static factories
    rc |= run_script(L, R"(
        local z = engine.Vec3.zero()
        assert(z:length() == 0.0, "Vec3.zero length")
        local u = engine.Vec3.up()
        assert(math.abs(u.y - 1.0) < 0.001, "Vec3.up y=1")
    )");

    // Vec3 add and scale methods
    rc |= run_script(L, R"(
        local a = engine.Vec3(1.0, 0.0, 0.0)
        local b = engine.Vec3(0.0, 1.0, 0.0)
        local c = a:add(b)
        assert(math.abs(c.x - 1.0) < 0.001, "Vec3 add x")
        assert(math.abs(c.y - 1.0) < 0.001, "Vec3 add y")
        local d = a:scale(3.0)
        assert(math.abs(d.x - 3.0) < 0.001, "Vec3 scale x")
    )");

    // Entity basic boolean methods
    rc |= run_script(L, R"(
        local e = engine.Entity()
        assert(e:is_active(), "Entity is_active default true")
        e:set_active(false)
        assert(not e:is_active(), "Entity set_active false")
        e:set_active(true)
        assert(e:is_active(), "Entity set_active true")
    )");

    // Entity with Vec3 position (cross-namespace usage)
    rc |= run_script(L, R"(
        local v = engine.Vec3(1.0, 2.0, 3.0)
        local e = engine.Entity()
        e:set_position(v)
        local pos = e:get_position()
        assert(math.abs(pos.x - 1.0) < 0.001, "Entity position.x")
        assert(math.abs(pos.y - 2.0) < 0.001, "Entity position.y")
        assert(math.abs(pos.z - 3.0) < 0.001, "Entity position.z")
    )");

    // Player: derived from Entity, extra health fields
    rc |= run_script(L, R"(
        local p = engine.Player()
        assert(math.abs(p:get_health() - 100.0) < 0.001, "Player default health")
        p:take_damage(30.0)
        assert(math.abs(p:get_health() - 70.0) < 0.001, "Player after damage")
        assert(p:is_alive(), "Player alive after 30 damage")
        p:take_damage(200.0)
        assert(not p:is_alive(), "Player dead after lethal damage")
    )");

    // Player inherits Entity methods
    rc |= run_script(L, R"(
        local p = engine.Player()
        assert(p:is_active(), "Player is_active via Entity default")
        p:set_active(false)
        assert(not p:is_active(), "Player set_active via Entity")
    )");

    // Player move uses Vec3 (cross-namespace interop)
    rc |= run_script(L, R"(
        local p = engine.Player()
        local dir = engine.Vec3(1.0, 0.0, 0.0)
        p:move(dir)
        local pos = p:get_position()
        assert(math.abs(pos.x - 1.0) < 0.001, "Player moved x")
    )");

    // Free functions: dot and cross product
    rc |= run_script(L, R"(
        local a = engine.Vec3(1.0, 0.0, 0.0)
        local b = engine.Vec3(0.0, 1.0, 0.0)
        local d = engine.dot(a, b)
        assert(math.abs(d - 0.0) < 0.001, "dot(x,y) == 0")
        local d2 = engine.dot(a, a)
        assert(math.abs(d2 - 1.0) < 0.001, "dot(x,x) == 1")
        local c_vec = engine.cross(a, b)
        assert(math.abs(c_vec.z - 1.0) < 0.001, "cross(x,y).z == 1")
    )");

    lua_close(L);
    return rc;
}
