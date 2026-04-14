# Fetch LuaBridge3 (header-only, LuaBridge3::LuaBridge3 target).
# Requires Lua::Lua — include fetch_lua.cmake before this file.
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
