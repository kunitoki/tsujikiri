# cmake/FetchDependencies.cmake
#
# Fetches third-party libraries required to compile generated bindings.
# Include this file from CMakeLists.txt:
#
#   include(cmake/FetchDependencies.cmake)
#
# After inclusion, the following targets are available:
#   pybind11::module         — pybind11 (header-only)
#   LuaBridge3::LuaBridge3   — LuaBridge3 (header-only, pulls lua)

include(FetchContent)

# --------------------------------------------------------------------------
# pybind11
# --------------------------------------------------------------------------
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(pybind11)

# --------------------------------------------------------------------------
# Lua 5.4  (required by LuaBridge3)
# --------------------------------------------------------------------------
FetchContent_Declare(
    lua
    GIT_REPOSITORY https://github.com/lua/lua.git
    GIT_TAG        v5.4.8
    GIT_SHALLOW    TRUE
)
FetchContent_GetProperties(lua)
if(NOT lua_POPULATED)
    FetchContent_Populate(lua)

    # Build Lua as a static library from its sources
    file(GLOB LUA_SOURCES "${lua_SOURCE_DIR}/*.c")
    list(REMOVE_ITEM LUA_SOURCES
        "${lua_SOURCE_DIR}/lua.c"       # standalone interpreter
        "${lua_SOURCE_DIR}/luac.c"      # Lua compiler
    )

    add_library(lua_static STATIC ${LUA_SOURCES})
    target_include_directories(lua_static PUBLIC "${lua_SOURCE_DIR}")
    # Lua needs these on some platforms
    if(UNIX AND NOT APPLE)
        target_compile_definitions(lua_static PRIVATE LUA_USE_POSIX LUA_USE_DLOPEN)
        target_link_libraries(lua_static PUBLIC dl m)
    endif()

    add_library(Lua::Lua ALIAS lua_static)
endif()

# --------------------------------------------------------------------------
# LuaBridge3
# --------------------------------------------------------------------------
FetchContent_Declare(
    LuaBridge3
    GIT_REPOSITORY https://github.com/kunitoki/LuaBridge3.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE
)
FetchContent_GetProperties(LuaBridge3)
if(NOT luabridge3_POPULATED)
    FetchContent_Populate(LuaBridge3)

    # LuaBridge3 is header-only; just expose the include directory
    add_library(LuaBridge3_headers INTERFACE)
    target_include_directories(LuaBridge3_headers INTERFACE
        "${luabridge3_SOURCE_DIR}/Source"
    )
    target_link_libraries(LuaBridge3_headers INTERFACE Lua::Lua)

    add_library(LuaBridge3::LuaBridge3 ALIAS LuaBridge3_headers)
endif()
