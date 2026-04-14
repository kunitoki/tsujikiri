cmake_minimum_required(VERSION 3.20)
project(tsujikiri_combined C CXX)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/common.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_lua.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_luabridge3.cmake")

set(_input    "${CMAKE_CURRENT_SOURCE_DIR}/combined.input.yml")
set(_header   "${CMAKE_CURRENT_SOURCE_DIR}/combined.hpp")
set(_gen_lb3  "${CMAKE_CURRENT_BINARY_DIR}/combined_luabridge3.cpp")
set(_manifest "${CMAKE_CURRENT_BINARY_DIR}/combined.manifest")
set(_gen_lua  "${CMAKE_CURRENT_BINARY_DIR}/combined_luals.lua")

add_custom_command(
    OUTPUT  "${_gen_lb3}"
    COMMAND tsujikiri
            -i "${_input}"
            --target luabridge3 "${_gen_lb3}"
            --manifest-file    "${_manifest}"
    DEPENDS "${_input}" "${_header}" ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaBridge3 bindings for combined..."
    VERBATIM)

add_custom_command(
    OUTPUT  "${_gen_lua}"
    COMMAND tsujikiri -i "${_input}" --target luals "${_gen_lua}"
    DEPENDS "${_input}" "${_header}" ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaLS stubs for combined..."
    VERBATIM)

add_executable(test_combined_luabridge3
    "${_gen_lb3}"
    "${_gen_lua}"
    "${CMAKE_CURRENT_SOURCE_DIR}/luabridge3_main.cpp")
target_include_directories(test_combined_luabridge3 PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(test_combined_luabridge3 PRIVATE LuaBridge3::LuaBridge3)
