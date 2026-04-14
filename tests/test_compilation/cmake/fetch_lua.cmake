# Fetch and build Lua 5.4 as a static library (Lua::Lua target).
FetchContent_Declare(
    lua
    GIT_REPOSITORY https://github.com/lua/lua.git
    GIT_TAG        v5.4.8
    GIT_SHALLOW    TRUE)
FetchContent_GetProperties(lua)
if(NOT lua_POPULATED)
    FetchContent_Populate(lua)
    add_library(lua_static STATIC "${lua_SOURCE_DIR}/onelua.c")
    target_include_directories(lua_static PUBLIC "${lua_SOURCE_DIR}")
    target_compile_definitions(lua_static PRIVATE -DMAKE_LIB=1)
    if(UNIX AND NOT APPLE)
        target_compile_definitions(lua_static PRIVATE LUA_USE_POSIX LUA_USE_DLOPEN)
        target_link_libraries(lua_static PUBLIC dl m)
    endif()
    add_library(Lua::Lua ALIAS lua_static)
endif()
