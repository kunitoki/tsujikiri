"""pybind11 runtime verification for the audio scenario (3-level inheritance).

Run with: python pybind11_verify.py
Requires PYTHONPATH to contain the directory with the built audio extension module.

Note: constructors taking const char* are avoided — we use default constructors
and test only numeric/boolean API surface to sidestep const char* lifetime issues.
"""
from __future__ import annotations

import sys

import audio  # type: ignore  # noqa: E402


def test_audio_node() -> None:
    n = audio.AudioNode()
    assert n.is_enabled(), "AudioNode enabled by default"
    n.set_enabled(False)
    assert not n.is_enabled(), "AudioNode set_enabled False"
    n.set_enabled(True)
    assert n.is_enabled(), "AudioNode set_enabled True"


def test_audio_source() -> None:
    s = audio.AudioSource()
    assert s.get_channels() == 2, f"AudioSource default channels {s.get_channels()}"
    s.set_channels(6)
    assert s.get_channels() == 6, f"AudioSource set_channels {s.get_channels()}"
    assert abs(s.get_sample_rate() - 44100.0) < 1.0, f"AudioSource sampleRate {s.get_sample_rate()}"
    # inherited from AudioNode
    assert s.is_enabled(), "AudioSource is_enabled via AudioNode"
    s.set_enabled(False)
    assert not s.is_enabled(), "AudioSource set_enabled via AudioNode"


def test_audio_effect() -> None:
    e = audio.AudioEffect()
    assert abs(e.get_mix() - 0.5) < 0.001, f"AudioEffect default mix {e.get_mix()}"
    e.set_mix(0.8)
    assert abs(e.get_mix() - 0.8) < 0.001, f"AudioEffect set_mix {e.get_mix()}"
    e.set_mix(2.0)  # clamped to 1.0
    assert abs(e.get_mix() - 1.0) < 0.001, f"AudioEffect clamp to 1.0 {e.get_mix()}"
    # inherited from AudioNode
    e.set_enabled(False)
    assert not e.is_enabled(), "AudioEffect set_enabled via AudioNode"


def test_reverb_level3_inheritance() -> None:
    r = audio.Reverb(0.8)
    assert abs(r.get_room_size() - 0.8) < 0.001, f"Reverb room_size {r.get_room_size()}"
    r.set_decay(0.6)
    assert abs(r.get_decay() - 0.6) < 0.001, f"Reverb decay {r.get_decay()}"
    # Level 2 (AudioEffect) inherited method
    r.set_mix(0.75)
    assert abs(r.get_mix() - 0.75) < 0.001, f"Reverb mix via AudioEffect {r.get_mix()}"
    # Level 1 (AudioNode) inherited method
    r.set_enabled(False)
    assert not r.is_enabled(), "Reverb set_enabled via AudioNode"


def test_reverb_static_factories() -> None:
    room = audio.Reverb.room()
    assert abs(room.get_room_size() - 0.8) < 0.001, f"Reverb.room() room_size {room.get_room_size()}"
    assert abs(room.get_decay() - 0.7) < 0.001, f"Reverb.room() decay {room.get_decay()}"
    ch = audio.Reverb.chamber()
    assert abs(ch.get_room_size() - 0.5) < 0.001, f"Reverb.chamber() room_size {ch.get_room_size()}"


def test_delay_level3_inheritance() -> None:
    d = audio.Delay(0.25)
    assert abs(d.get_delay_time() - 0.25) < 0.001, f"Delay delay_time {d.get_delay_time()}"
    d.set_feedback(0.6)
    assert abs(d.get_feedback() - 0.6) < 0.001, f"Delay feedback {d.get_feedback()}"
    d.set_feedback(1.5)  # clamped
    assert abs(d.get_feedback() - 1.0) < 0.001, f"Delay feedback clamped {d.get_feedback()}"
    # Level 2 and Level 1 inherited
    d.set_mix(0.4)
    assert abs(d.get_mix() - 0.4) < 0.001, f"Delay mix via AudioEffect {d.get_mix()}"
    d.set_enabled(False)
    assert not d.is_enabled(), "Delay set_enabled via AudioNode"


def test_delay_static_factories() -> None:
    echo = audio.Delay.echo()
    assert abs(echo.get_delay_time() - 0.5) < 0.001, f"Delay.echo() delay_time {echo.get_delay_time()}"
    slap = audio.Delay.slap()
    assert abs(slap.get_delay_time() - 0.1) < 0.001, f"Delay.slap() delay_time {slap.get_delay_time()}"


if __name__ == "__main__":
    test_audio_node()
    test_audio_source()
    test_audio_effect()
    test_reverb_level3_inheritance()
    test_reverb_static_factories()
    test_delay_level3_inheritance()
    test_delay_static_factories()
    print("audio pybind11 bindings: all checks passed")
    sys.exit(0)
