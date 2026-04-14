cmake_minimum_required(VERSION 3.20)
project(tsujikiri_geo C CXX)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/common.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_lua.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_luabridge3.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_pybind11.cmake")

set(_input   "${CMAKE_CURRENT_SOURCE_DIR}/geo.input.yml")
set(_headers "${CMAKE_CURRENT_SOURCE_DIR}/base.hpp"
             "${CMAKE_CURRENT_SOURCE_DIR}/shapes.hpp")
# Parent dir is needed on the include path so generated code can use "geo/base.hpp" etc.
set(_include_parent "${CMAKE_CURRENT_SOURCE_DIR}/..")

# geo — luabridge3
set(_gen_lb3 "${CMAKE_CURRENT_BINARY_DIR}/geo_luabridge3.cpp")
add_custom_command(
    OUTPUT  "${_gen_lb3}"
    COMMAND tsujikiri -i "${_input}" --target luabridge3 "${_gen_lb3}"
    DEPENDS "${_input}" ${_headers} ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaBridge3 bindings for geo..."
    VERBATIM)
add_executable(test_geo_luabridge3 "${_gen_lb3}" "${CMAKE_CURRENT_SOURCE_DIR}/luabridge3_main.cpp")
target_include_directories(test_geo_luabridge3 PRIVATE "${_include_parent}")
target_link_libraries(test_geo_luabridge3 PRIVATE LuaBridge3::LuaBridge3)

# geo — pybind11
set(_gen_py "${CMAKE_CURRENT_BINARY_DIR}/geo_pybind11.cpp")
add_custom_command(
    OUTPUT  "${_gen_py}"
    COMMAND tsujikiri -i "${_input}" --target pybind11 "${_gen_py}"
    DEPENDS "${_input}" ${_headers} ${TSUJIKIRI_SOURCES}
    COMMENT "Generating pybind11 bindings for geo..."
    VERBATIM)
pybind11_add_module(geo_py "${_gen_py}")
target_include_directories(geo_py PRIVATE "${_include_parent}")
set_target_properties(geo_py PROPERTIES
    OUTPUT_NAME "geo"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/python_modules")
