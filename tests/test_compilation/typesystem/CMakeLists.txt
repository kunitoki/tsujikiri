cmake_minimum_required(VERSION 3.20)
project(tsujikiri_typesystem C CXX)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/common.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_lua.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_luabridge3.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_pybind11.cmake")

set(_input   "${CMAKE_CURRENT_SOURCE_DIR}/typesystem.input.yml")
set(_headers "${CMAKE_CURRENT_SOURCE_DIR}/types.hpp")
set(_include_parent "${CMAKE_CURRENT_SOURCE_DIR}/..")

# typesystem — luabridge3
set(_gen_lb3 "${CMAKE_CURRENT_BINARY_DIR}/typesystem_luabridge3.cpp")
add_custom_command(
    OUTPUT  "${_gen_lb3}"
    COMMAND tsujikiri -i "${_input}" --target luabridge3 "${_gen_lb3}"
    DEPENDS "${_input}" ${_headers} ${TSUJIKIRI_SOURCES}
    COMMENT "Generating LuaBridge3 bindings for typesystem..."
    VERBATIM)
add_executable(test_typesystem_luabridge3 "${_gen_lb3}" "${CMAKE_CURRENT_SOURCE_DIR}/luabridge3_main.cpp")
target_include_directories(test_typesystem_luabridge3 PRIVATE "${_include_parent}")
target_link_libraries(test_typesystem_luabridge3 PRIVATE LuaBridge3::LuaBridge3)

# typesystem — pybind11
set(_gen_py "${CMAKE_CURRENT_BINARY_DIR}/typesystem_pybind11.cpp")
add_custom_command(
    OUTPUT  "${_gen_py}"
    COMMAND tsujikiri -i "${_input}" --target pybind11 "${_gen_py}"
    DEPENDS "${_input}" ${_headers} ${TSUJIKIRI_SOURCES}
    COMMENT "Generating pybind11 bindings for typesystem..."
    VERBATIM)
pybind11_add_module(typesystem_py "${_gen_py}")
target_include_directories(typesystem_py PRIVATE "${_include_parent}")
set_target_properties(typesystem_py PROPERTIES
    OUTPUT_NAME "typesystem"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/python_modules")
