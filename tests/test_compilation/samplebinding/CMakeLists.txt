cmake_minimum_required(VERSION 3.20)
project(tsujikiri_samplebinding C CXX)

include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/common.cmake")
include("${CMAKE_CURRENT_SOURCE_DIR}/../cmake/fetch_pybind11.cmake")

set(_input   "${CMAKE_CURRENT_SOURCE_DIR}/samplebinding.input.yml")
set(_headers "${CMAKE_CURRENT_SOURCE_DIR}/samplebinding.hpp")
set(_include_parent "${CMAKE_CURRENT_SOURCE_DIR}/..")

# samplebinding — pybind11
set(_gen_py "${CMAKE_CURRENT_BINARY_DIR}/samplebinding_pybind11.cpp")
add_custom_command(
    OUTPUT  "${_gen_py}"
    COMMAND tsujikiri -i "${_input}" --target pybind11 "${_gen_py}"
    DEPENDS "${_input}" ${_headers} ${TSUJIKIRI_SOURCES}
    COMMENT "Generating pybind11 bindings for samplebinding..."
    VERBATIM)
pybind11_add_module(samplebinding_py "${_gen_py}")
target_include_directories(samplebinding_py PRIVATE "${_include_parent}")
set_target_properties(samplebinding_py PROPERTIES
    OUTPUT_NAME "samplebinding"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/python_modules")
