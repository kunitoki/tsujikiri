cmake_minimum_required(VERSION 3.20)
project(tsujikiri_compilation_tests C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

# Prevent cmake from re-running git fetch/update on every configure after the
# initial download — avoids git lock-file conflicts when multiple processes
# configure the same build directory simultaneously (e.g. under pytest-xdist).
set(FETCHCONTENT_UPDATES_DISCONNECTED ON)

# ============================================================
# Fetch all external dependencies ONCE
# ============================================================

# --- Lua 5.4 (required by LuaBridge3) ---
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

# --- LuaBridge3 ---
set(LUABRIDGE_TESTING OFF CACHE BOOL "Disable LuaBridge3 own tests" FORCE)
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

# --- pybind11 ---
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6
    GIT_SHALLOW    TRUE)
FetchContent_MakeAvailable(pybind11)

# ============================================================
# Track all tsujikiri Python/template sources as implicit deps
# ============================================================
file(GLOB_RECURSE TSUJIKIRI_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/../../src/**/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../src/**/*.yml")

# ============================================================
# Helper macros
# ============================================================

# add_luabridge3_binding_test(
#   NAME         -- unique test name
#   INPUT_FILE   -- absolute path to .input.yml
#   MAIN_SRC     -- absolute path to the *_main.cpp
#   INCLUDE_DIRS -- list of include directories
#   HEADERS      -- header files (for DEPENDS)
# )
macro(add_luabridge3_binding_test)
    cmake_parse_arguments(_LUA "" "NAME;INPUT_FILE;MAIN_SRC" "INCLUDE_DIRS;HEADERS" ${ARGN})

    set(_gen_src "${CMAKE_CURRENT_BINARY_DIR}/${_LUA_NAME}_luabridge3.cpp")

    add_custom_command(
        OUTPUT  "${_gen_src}"
        COMMAND tsujikiri -i "${_LUA_INPUT_FILE}" --target luabridge3 "${_gen_src}"
        DEPENDS "${_LUA_INPUT_FILE}" ${_LUA_HEADERS}
        IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
        COMMENT "Generating LuaBridge3 bindings for ${_LUA_NAME}..."
        VERBATIM)

    add_executable("test_${_LUA_NAME}_luabridge3" "${_gen_src}" "${_LUA_MAIN_SRC}")
    target_include_directories("test_${_LUA_NAME}_luabridge3" PRIVATE ${_LUA_INCLUDE_DIRS})
    target_link_libraries("test_${_LUA_NAME}_luabridge3" PRIVATE LuaBridge3::LuaBridge3)
endmacro()

# add_pybind11_binding_test(
#   NAME         -- unique test name (also becomes the Python import name)
#   INPUT_FILE   -- absolute path to .input.yml
#   INCLUDE_DIRS -- list of include directories
#   HEADERS      -- header files (for DEPENDS)
# )
macro(add_pybind11_binding_test)
    cmake_parse_arguments(_PY "" "NAME;INPUT_FILE" "INCLUDE_DIRS;HEADERS" ${ARGN})

    set(_gen_src "${CMAKE_CURRENT_BINARY_DIR}/${_PY_NAME}_pybind11.cpp")

    add_custom_command(
        OUTPUT  "${_gen_src}"
        COMMAND tsujikiri -i "${_PY_INPUT_FILE}" --target pybind11 "${_gen_src}"
        DEPENDS "${_PY_INPUT_FILE}" ${_PY_HEADERS}
        IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
        COMMENT "Generating pybind11 bindings for ${_PY_NAME}..."
        VERBATIM)

    # Target named <name>_py so it doesn't collide; OUTPUT_NAME sets the import name.
    set(_mod_target "${_PY_NAME}_py")
    pybind11_add_module("${_mod_target}" "${_gen_src}")
    target_include_directories("${_mod_target}" PRIVATE ${_PY_INCLUDE_DIRS})
    set_target_properties("${_mod_target}" PROPERTIES
        OUTPUT_NAME "${_PY_NAME}"
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/python_modules")
endmacro()

# ============================================================
# Test: combined (original single-namespace, single-header)
# ============================================================
set(_combined_input   "${CMAKE_CURRENT_SOURCE_DIR}/combined.input.yml")
set(_combined_headers "${CMAKE_CURRENT_SOURCE_DIR}/combined.hpp")
set(_combined_gen     "${CMAKE_CURRENT_BINARY_DIR}/combined_luabridge3.cpp")
set(_combined_luals   "${CMAKE_CURRENT_BINARY_DIR}/combined_luals.lua")
set(_combined_manifest "${CMAKE_CURRENT_BINARY_DIR}/combined.manifest")

add_custom_command(
    OUTPUT  "${_combined_gen}"
    COMMAND tsujikiri -i "${_combined_input}"
                     --target luabridge3 "${_combined_gen}"
                     --manifest-file "${_combined_manifest}"
    DEPENDS "${_combined_input}" "${_combined_headers}"
    IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaBridge3 bindings for combined..."
    VERBATIM)

add_custom_command(
    OUTPUT  "${_combined_luals}"
    COMMAND tsujikiri -i "${_combined_input}" --target luals "${_combined_luals}"
    DEPENDS "${_combined_input}"
    IMPLICIT_DEPENDS ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaLS bindings for combined..."
    VERBATIM)

add_executable(test_combined_luabridge3
    "${_combined_gen}"
    "${_combined_luals}"
    "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp")
target_include_directories(test_combined_luabridge3 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(test_combined_luabridge3 PRIVATE LuaBridge3::LuaBridge3)

# ============================================================
# Test: geo — multi-header, single namespace, deep inheritance
# ============================================================
set(_geo_dir     "${CMAKE_CURRENT_SOURCE_DIR}/geo")
set(_geo_headers "${_geo_dir}/base.hpp" "${_geo_dir}/shapes.hpp")

add_luabridge3_binding_test(
    NAME         geo
    INPUT_FILE   "${_geo_dir}/geo.input.yml"
    MAIN_SRC     "${_geo_dir}/luabridge3_main.cpp"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_geo_headers})

add_pybind11_binding_test(
    NAME         geo
    INPUT_FILE   "${_geo_dir}/geo.input.yml"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_geo_headers})

# ============================================================
# Test: engine — multi-header, two namespaces (math + engine), cross-references
# ============================================================
set(_engine_dir     "${CMAKE_CURRENT_SOURCE_DIR}/engine")
set(_engine_headers "${_engine_dir}/math_types.hpp" "${_engine_dir}/entity.hpp")

add_luabridge3_binding_test(
    NAME         engine
    INPUT_FILE   "${_engine_dir}/engine.input.yml"
    MAIN_SRC     "${_engine_dir}/luabridge3_main.cpp"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_engine_headers})

add_pybind11_binding_test(
    NAME         engine
    INPUT_FILE   "${_engine_dir}/engine.input.yml"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_engine_headers})

# ============================================================
# Test: audio — single header, 3-level deep inheritance
# ============================================================
set(_audio_dir     "${CMAKE_CURRENT_SOURCE_DIR}/audio")
set(_audio_headers "${_audio_dir}/audio.hpp")

add_luabridge3_binding_test(
    NAME         audio
    INPUT_FILE   "${_audio_dir}/audio.input.yml"
    MAIN_SRC     "${_audio_dir}/luabridge3_main.cpp"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_audio_headers})

add_pybind11_binding_test(
    NAME         audio
    INPUT_FILE   "${_audio_dir}/audio.input.yml"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_audio_headers})

# ============================================================
# Test: samplebinding — virtual methods, trampolines, shared_ptr holder, keep_alive
# ============================================================
set(_samplebinding_dir     "${CMAKE_CURRENT_SOURCE_DIR}/samplebinding")
set(_samplebinding_headers "${_samplebinding_dir}/samplebinding.hpp")

add_pybind11_binding_test(
    NAME         samplebinding
    INPUT_FILE   "${_samplebinding_dir}/samplebinding.input.yml"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_samplebinding_headers})

# ============================================================
# Test: typesystem — primitive_types, custom_types, OSType round-trip, int64_t
# ============================================================
set(_typesystem_dir     "${CMAKE_CURRENT_SOURCE_DIR}/typesystem")
set(_typesystem_headers "${_typesystem_dir}/types.hpp")

add_luabridge3_binding_test(
    NAME         typesystem
    INPUT_FILE   "${_typesystem_dir}/typesystem.input.yml"
    MAIN_SRC     "${_typesystem_dir}/luabridge3_main.cpp"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_typesystem_headers})

add_pybind11_binding_test(
    NAME         typesystem
    INPUT_FILE   "${_typesystem_dir}/typesystem.input.yml"
    INCLUDE_DIRS "${CMAKE_CURRENT_SOURCE_DIR}"
    HEADERS      ${_typesystem_headers})
