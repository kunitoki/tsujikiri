# Common settings for all tsujikiri compilation test scenarios.
# CMAKE_CURRENT_LIST_DIR resolves to this file's directory regardless of which
# scenario includes it, so all relative paths here are stable.

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)
set(FETCHCONTENT_UPDATES_DISCONNECTED ON)

if(NOT DEFINED CACHE{FETCHCONTENT_BASE_DIR})
    set(FETCHCONTENT_BASE_DIR "${CMAKE_CURRENT_LIST_DIR}/../_deps"
        CACHE PATH "Shared FetchContent download directory for all tsujikiri test scenarios")
endif()

file(GLOB_RECURSE TSUJIKIRI_SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/../../../src/**/*.py"
    "${CMAKE_CURRENT_LIST_DIR}/../../../src/**/*.yml")
