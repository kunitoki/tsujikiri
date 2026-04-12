cmake_minimum_required(VERSION 3.20)
project(tsujikiri_luabridge3_test C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

# --------------------------------------------------------------------------
# Lua 5.4 (required by LuaBridge3)
# --------------------------------------------------------------------------
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

# --------------------------------------------------------------------------
# LuaBridge3
# --------------------------------------------------------------------------
set(LUABRIDGE_TESTING OFF CACHE BOOL "Enable testing for LuaBridge3")
FetchContent_Declare(
    LuaBridge3
    GIT_REPOSITORY https://github.com/kunitoki/LuaBridge3.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE)
FetchContent_GetProperties(LuaBridge3)
if(NOT luabridge3_POPULATED)
    FetchContent_Populate(LuaBridge3)

    add_library(LuaBridge3_headers INTERFACE)
    target_include_directories(LuaBridge3_headers INTERFACE "${luabridge3_SOURCE_DIR}/Source")
    target_link_libraries(LuaBridge3_headers INTERFACE Lua::Lua)

    add_library(LuaBridge3::LuaBridge3 ALIAS LuaBridge3_headers)
endif()

# --------------------------------------------------------------------------
# LuaBridge3 bindings compilation test
# --------------------------------------------------------------------------
file(GLOB_RECURSE TSUJIKIRI_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/../../src/**/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../src/**/*.yml")
set(INPUT_SOURCE ${CMAKE_CURRENT_SOURCE_DIR}/combined.input.yml)
set(GENERATED_MANIFEST ${CMAKE_CURRENT_BINARY_DIR}/luabridge3_bindings.manifest)
set(GENERATED_SOURCE ${CMAKE_CURRENT_BINARY_DIR}/luabridge3_bindings.cpp)
set(GENERATED_LUALS ${CMAKE_CURRENT_BINARY_DIR}/luabridge3_bindings.lua)

file(GLOB_RECURSE COMBINED_HEADERS "${CMAKE_CURRENT_SOURCE_DIR}/*.hpp")

add_custom_command(
    OUTPUT ${GENERATED_SOURCE}
    COMMAND tsujikiri -i ${INPUT_SOURCE} --target luabridge3 ${GENERATED_SOURCE} --manifest-file ${GENERATED_MANIFEST}
    DEPENDS ${INPUT_SOURCE} ${COMBINED_HEADERS}
    IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaBridge3 bindings with tsujikiri..."
    VERBATIM)

add_custom_command(
    OUTPUT ${GENERATED_LUALS}
    COMMAND tsujikiri -i ${INPUT_SOURCE} --target luals ${GENERATED_LUALS}
    DEPENDS ${INPUT_SOURCE}
    IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaLS bindings with tsujikiri..."
    VERBATIM)

add_executable(test_luabridge3_bindings ${GENERATED_SOURCE} ${GENERATED_LUALS} main.cpp)
target_include_directories(test_luabridge3_bindings PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(test_luabridge3_bindings PRIVATE LuaBridge3::LuaBridge3)
