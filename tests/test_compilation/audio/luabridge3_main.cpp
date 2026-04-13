/// luabridge3_main.cpp — audio scenario: deep 3-level inheritance LuaBridge3 test.
extern "C" {
#include <lua.h>
#include <lualib.h>
#include <lauxlib.h>
} // extern "C"

#include <LuaBridge/LuaBridge.h>
#include <cstdio>

extern void register_audio(lua_State* L);

static int run_script(lua_State* L, const char* code)
{
    if (luaL_dostring(L, code) != LUA_OK) {
        fprintf(stderr, "Lua error: %s\n", lua_tostring(L, -1));
        lua_pop(L, 1);
        return 1;
    }
    return 0;
}

int main()
{
    lua_State* L = luaL_newstate();
    luaL_openlibs(L);
    register_audio(L);

    int rc = 0;

    // AudioNode base class
    rc |= run_script(L, R"(
        local n = audio.AudioNode()
        assert(n:is_enabled(), "AudioNode enabled by default")
        n:set_enabled(false)
        assert(not n:is_enabled(), "AudioNode set_enabled false")
        n:set_enabled(true)
        assert(n:is_enabled(), "AudioNode set_enabled true")
    )");

    // AudioSource (Level 2 — derives AudioNode)
    rc |= run_script(L, R"(
        local s = audio.AudioSource()
        assert(s:get_channels() == 2, "AudioSource default channels")
        s:set_channels(6)
        assert(s:get_channels() == 6, "AudioSource set_channels")
        assert(math.abs(s:get_sample_rate() - 44100.0) < 0.1, "AudioSource default sample_rate")
        assert(s:is_enabled(), "AudioSource is_enabled via AudioNode")
        s:set_enabled(false)
        assert(not s:is_enabled(), "AudioSource set_enabled via AudioNode")
    )");

    // AudioEffect (Level 2 — derives AudioNode)
    rc |= run_script(L, R"(
        local e = audio.AudioEffect()
        assert(math.abs(e:get_mix() - 0.5) < 0.001, "AudioEffect default mix")
        e:set_mix(0.8)
        assert(math.abs(e:get_mix() - 0.8) < 0.001, "AudioEffect set_mix")
        e:set_mix(2.0)
        assert(math.abs(e:get_mix() - 1.0) < 0.001, "AudioEffect set_mix clamps to 1")
        e:set_enabled(false)
        assert(not e:is_enabled(), "AudioEffect set_enabled via AudioNode")
    )");

    // Reverb (Level 3 — derives AudioEffect -> AudioNode)
    rc |= run_script(L, R"(
        local r = audio.Reverb(0.8)
        assert(math.abs(r:get_room_size() - 0.8) < 0.001, "Reverb get_room_size")
        r:set_decay(0.6)
        assert(math.abs(r:get_decay() - 0.6) < 0.001, "Reverb set_decay")
        r:set_mix(0.75)
        assert(math.abs(r:get_mix() - 0.75) < 0.001, "Reverb get_mix via AudioEffect")
        r:set_enabled(false)
        assert(not r:is_enabled(), "Reverb set_enabled via AudioNode")
    )");

    // Reverb static factories
    rc |= run_script(L, R"(
        local room = audio.Reverb.room()
        assert(math.abs(room:get_room_size() - 0.8) < 0.001, "Reverb.room room_size")
        assert(math.abs(room:get_decay() - 0.7) < 0.001, "Reverb.room decay")
        local ch = audio.Reverb.chamber()
        assert(math.abs(ch:get_room_size() - 0.5) < 0.001, "Reverb.chamber room_size")
    )");

    // Delay (Level 3 — derives AudioEffect -> AudioNode)
    rc |= run_script(L, R"(
        local d = audio.Delay(0.25)
        assert(math.abs(d:get_delay_time() - 0.25) < 0.001, "Delay get_delay_time")
        d:set_feedback(0.6)
        assert(math.abs(d:get_feedback() - 0.6) < 0.001, "Delay set_feedback")
        d:set_feedback(1.5)
        assert(math.abs(d:get_feedback() - 1.0) < 0.001, "Delay set_feedback clamps to 1")
        d:set_mix(0.4)
        assert(math.abs(d:get_mix() - 0.4) < 0.001, "Delay get_mix via AudioEffect")
        d:set_enabled(false)
        assert(not d:is_enabled(), "Delay set_enabled via AudioNode")
    )");

    // Delay static factories
    rc |= run_script(L, R"(
        local echo = audio.Delay.echo()
        assert(math.abs(echo:get_delay_time() - 0.5) < 0.001, "Delay.echo delay_time")
        local slap = audio.Delay.slap()
        assert(math.abs(slap:get_delay_time() - 0.1) < 0.001, "Delay.slap delay_time")
    )");

    lua_close(L);
    return rc;
}
