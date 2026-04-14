# Fetch pybind11 (header-only) and make its CMake targets available.
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6
    GIT_SHALLOW    TRUE)
FetchContent_MakeAvailable(pybind11)

# Disable LTO for pybind11 modules in test scenarios. pybind11 enables -flto
# by default when GCC supports it, but this causes /usr/bin/strip to fail on
# some Linux configurations (GCC 13 LTO + cmake 4.x output path mismatch).
set(PYBIND11_LTO_CXX_FLAGS "" CACHE STRING "" FORCE)
set(PYBIND11_LTO_LINKER_FLAGS "" CACHE STRING "" FORCE)
