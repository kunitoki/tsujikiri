extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>

#include "combined.hpp"

extern void register_combined(lua_State* L);

int main()
{
    lua_State* L = luaL_newstate();
    luaL_openlibs(L);

    register_combined(L);

    lua_close(L);
    return 0;
}
