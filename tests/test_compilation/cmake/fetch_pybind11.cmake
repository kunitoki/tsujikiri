# Fetch pybind11 (header-only) and make its CMake targets available.
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG        v2.13.6
    GIT_SHALLOW    TRUE)
FetchContent_MakeAvailable(pybind11)
