"""Compilation tests — generate bindings and optionally compile + run with CMake.

Each test class either:
  - Checks generated output for expected strings (fast, no build required), or
  - Uses CMake FetchContent to build real executables / Python extension modules
    and runs them to verify the bindings work at runtime.

The cmake build directory (``build/`` next to this file) is persistent so
FetchContent downloads are cached between runs.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent

CMAKE_AVAILABLE = shutil.which("cmake") is not None
CMAKE_BUILD_DIR = HERE / "build"
PYTHON_MODULES_DIR = CMAKE_BUILD_DIR / "python_modules"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(module, output_config, generation=None) -> str:
    from tsujikiri.generator import Generator
    buf = io.StringIO()
    Generator(output_config, generation=generation).generate(module, buf)
    return buf.getvalue()


def _cmake_configure() -> bool:
    """Run cmake configure, serialized via a file lock to avoid parallel conflicts."""
    import fcntl
    CMAKE_BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = CMAKE_BUILD_DIR.parent / ".cmake_configure.lock"
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        # Skip if already configured — FETCHCONTENT_UPDATES_DISCONNECTED makes
        # re-configures fast and safe, but skipping avoids redundant work.
        if (CMAKE_BUILD_DIR / "CMakeCache.txt").exists():
            return True
        result = subprocess.run(
            [
                "cmake",
                "-S", str(HERE),
                "-B", str(CMAKE_BUILD_DIR),
                "-DCMAKE_BUILD_TYPE=Release",
                "-Wno-dev",
            ],
            capture_output=True,
            text=True,
        )
        print(result.stdout + result.stderr)
        return result.returncode == 0


def _cmake_build(target: str) -> bool:
    """Build a specific cmake target."""
    result = subprocess.run(
        ["cmake", "--build", str(CMAKE_BUILD_DIR), "--target", target],
        capture_output=True,
        text=True,
    )
    print(result.stdout + result.stderr)
    return result.returncode == 0


def _run_executable(name: str) -> bool:
    """Run a built executable in the cmake build directory."""
    exe = CMAKE_BUILD_DIR / name
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def _run_pybind11_verify(script: Path) -> bool:
    """Run a pybind11 verify script with PYTHONPATH pointing to built modules."""
    env = {**os.environ, "PYTHONPATH": str(PYTHON_MODULES_DIR)}
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# combined — original single-namespace, single-header (LuaBridge3)
# ---------------------------------------------------------------------------

class TestCombinedLuaBridge3Generation:
    """Fast generation tests for the original combined scenario."""

    def test_begin_class_shape(self, compiled_module, luabridge3_output_config):
        assert '.beginClass<mylib::Shape>("Shape")' in _generate(compiled_module, luabridge3_output_config)

    def test_derive_class_circle(self, compiled_module, luabridge3_output_config):
        assert '.deriveClass<mylib::Circle, mylib::Shape>("Circle")' in _generate(compiled_module, luabridge3_output_config)

    def test_constructors(self, compiled_module, luabridge3_output_config):
        assert "addConstructor<void (*)()>" in _generate(compiled_module, luabridge3_output_config)

    def test_overloaded_method_cast(self, compiled_module, luabridge3_output_config):
        assert "luabridge::overload<int, int>(&mylib::Calculator::add)" in _generate(compiled_module, luabridge3_output_config)

    def test_enum_namespace(self, compiled_module, luabridge3_output_config):
        out = _generate(compiled_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert ".endNamespace()" in out


# ---------------------------------------------------------------------------
# geo — multi-header, single namespace, Circle/Rectangle : Shape
# ---------------------------------------------------------------------------

class TestGeoLuaBridge3Generation:
    """Fast generation tests for the geo multi-header scenario."""

    def test_begin_class_shape(self, geo_module, luabridge3_output_config):
        assert '.beginClass<geo::Shape>("Shape")' in _generate(geo_module, luabridge3_output_config)

    def test_derive_class_circle(self, geo_module, luabridge3_output_config):
        assert '.deriveClass<geo::Circle, geo::Shape>("Circle")' in _generate(geo_module, luabridge3_output_config)

    def test_derive_class_rectangle(self, geo_module, luabridge3_output_config):
        assert '.deriveClass<geo::Rectangle, geo::Shape>("Rectangle")' in _generate(geo_module, luabridge3_output_config)

    def test_color_enum_registered(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in out
        assert "geo::Color::Red" in out
        assert "geo::Color::Green" in out
        assert "geo::Color::Blue" in out

    def test_overloaded_resize(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert "luabridge::overload<double>(&geo::Circle::resize)" in out
        assert "luabridge::overload<double, double>(&geo::Circle::resize)" in out

    def test_static_factory_circle(self, geo_module, luabridge3_output_config):
        assert "&geo::Circle::unit" in _generate(geo_module, luabridge3_output_config)

    def test_static_factory_rectangle(self, geo_module, luabridge3_output_config):
        assert "&geo::Rectangle::square" in _generate(geo_module, luabridge3_output_config)

    def test_free_function_overloads(self, geo_module, luabridge3_output_config):
        out = _generate(geo_module, luabridge3_output_config)
        assert "luabridge::overload<double>(&geo::computeArea)" in out
        assert "luabridge::overload<double, double>(&geo::computeArea)" in out

    def test_no_duplicate_shape_class(self, geo_module, luabridge3_output_config):
        # Multi-source dedup: Shape must appear exactly once in the output
        out = _generate(geo_module, luabridge3_output_config)
        assert out.count('beginClass<geo::Shape>') + out.count('deriveClass<geo::Shape') == 1


class TestGeoPybind11Generation:
    """Fast generation tests for the geo scenario with pybind11."""

    def test_circle_class_with_base(self, geo_module, pybind11_output_config):
        assert "py::class_<geo::Circle, geo::Shape>" in _generate(geo_module, pybind11_output_config)

    def test_rectangle_class_with_base(self, geo_module, pybind11_output_config):
        assert "py::class_<geo::Rectangle, geo::Shape>" in _generate(geo_module, pybind11_output_config)

    def test_color_enum(self, geo_module, pybind11_output_config):
        out = _generate(geo_module, pybind11_output_config)
        assert 'py::enum_<geo::Color>(m, "Color")' in out
        assert ".export_values();" in out

    def test_overloaded_resize_fixed(self, geo_module, pybind11_output_config):
        # Verify the fixed template: no spurious py::overload_cast<...> as 2nd arg
        out = _generate(geo_module, pybind11_output_config)
        assert "py::overload_cast<double>(&geo::Circle::resize)" in out
        assert "py::overload_cast<double, double>(&geo::Circle::resize)" in out

    def test_static_factory(self, geo_module, pybind11_output_config):
        assert '.def_static("unit"' in _generate(geo_module, pybind11_output_config)

    def test_no_duplicate_shape(self, geo_module, pybind11_output_config):
        out = _generate(geo_module, pybind11_output_config)
        assert out.count('py::class_<geo::Shape>') == 1


# ---------------------------------------------------------------------------
# engine — multi-header, two namespaces (math + engine), cross-references
# ---------------------------------------------------------------------------

class TestEngineLuaBridge3Generation:
    """Fast generation tests for the engine multi-namespace scenario."""

    def test_vec3_registered(self, engine_module, luabridge3_output_config):
        assert '.beginClass<math::Vec3>("Vec3")' in _generate(engine_module, luabridge3_output_config)

    def test_entity_registered(self, engine_module, luabridge3_output_config):
        assert '.beginClass<engine::Entity>("Entity")' in _generate(engine_module, luabridge3_output_config)

    def test_player_derives_entity(self, engine_module, luabridge3_output_config):
        assert '.deriveClass<engine::Player, engine::Entity>("Player")' in _generate(engine_module, luabridge3_output_config)

    def test_entity_type_enum(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert '.beginNamespace("EntityType")' in out
        assert "engine::EntityType::Static" in out
        assert "engine::EntityType::Dynamic" in out

    def test_cross_namespace_method(self, engine_module, luabridge3_output_config):
        # setPosition takes math::Vec3 — verify it appears in binding code
        assert "&engine::Entity::setPosition" in _generate(engine_module, luabridge3_output_config)

    def test_free_functions_dot_cross(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert "&math::dot" in out
        assert "&math::cross" in out

    def test_no_duplicate_vec3(self, engine_module, luabridge3_output_config):
        out = _generate(engine_module, luabridge3_output_config)
        assert out.count('beginClass<math::Vec3>') == 1


class TestEnginePybind11Generation:
    """Fast generation tests for the engine scenario with pybind11."""

    def test_vec3_class(self, engine_module, pybind11_output_config):
        assert 'py::class_<math::Vec3>(m, "Vec3")' in _generate(engine_module, pybind11_output_config)

    def test_player_derives_entity(self, engine_module, pybind11_output_config):
        assert "py::class_<engine::Player, engine::Entity>" in _generate(engine_module, pybind11_output_config)

    def test_cross_namespace_binding(self, engine_module, pybind11_output_config):
        assert "&engine::Entity::setPosition" in _generate(engine_module, pybind11_output_config)

    def test_no_duplicate_vec3(self, engine_module, pybind11_output_config):
        out = _generate(engine_module, pybind11_output_config)
        assert out.count('py::class_<math::Vec3>') == 1


# ---------------------------------------------------------------------------
# audio — single header, 3-level deep inheritance chain
# ---------------------------------------------------------------------------

class TestAudioLuaBridge3Generation:
    """Fast generation tests for the audio 3-level hierarchy."""

    def test_audio_node_base_class(self, audio_module, luabridge3_output_config):
        assert '.beginClass<audio::AudioNode>("AudioNode")' in _generate(audio_module, luabridge3_output_config)

    def test_audio_source_derives_node(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::AudioSource, audio::AudioNode>("AudioSource")' in _generate(audio_module, luabridge3_output_config)

    def test_audio_effect_derives_node(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::AudioEffect, audio::AudioNode>("AudioEffect")' in _generate(audio_module, luabridge3_output_config)

    def test_reverb_derives_effect(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::Reverb, audio::AudioEffect>("Reverb")' in _generate(audio_module, luabridge3_output_config)

    def test_delay_derives_effect(self, audio_module, luabridge3_output_config):
        assert '.deriveClass<audio::Delay, audio::AudioEffect>("Delay")' in _generate(audio_module, luabridge3_output_config)

    def test_reverb_static_factories(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert "&audio::Reverb::room" in out
        assert "&audio::Reverb::chamber" in out

    def test_delay_static_factories(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert "&audio::Delay::echo" in out
        assert "&audio::Delay::slap" in out

    def test_node_type_enum(self, audio_module, luabridge3_output_config):
        out = _generate(audio_module, luabridge3_output_config)
        assert '.beginNamespace("NodeType")' in out
        assert "audio::NodeType::Source" in out


class TestAudioPybind11Generation:
    """Fast generation tests for the audio scenario with pybind11."""

    def test_audio_node_class(self, audio_module, pybind11_output_config):
        assert 'py::class_<audio::AudioNode>(m, "AudioNode")' in _generate(audio_module, pybind11_output_config)

    def test_reverb_deep_inheritance(self, audio_module, pybind11_output_config):
        assert "py::class_<audio::Reverb, audio::AudioEffect>" in _generate(audio_module, pybind11_output_config)

    def test_delay_deep_inheritance(self, audio_module, pybind11_output_config):
        assert "py::class_<audio::Delay, audio::AudioEffect>" in _generate(audio_module, pybind11_output_config)

    def test_reverb_static_factories_pybind11(self, audio_module, pybind11_output_config):
        out = _generate(audio_module, pybind11_output_config)
        assert '.def_static("room"' in out
        assert '.def_static("chamber"' in out

    def test_node_type_enum_pybind11(self, audio_module, pybind11_output_config):
        out = _generate(audio_module, pybind11_output_config)
        assert 'py::enum_<audio::NodeType>' in out


# ---------------------------------------------------------------------------
# CMake build + run tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CMAKE_AVAILABLE, reason="cmake not installed")
@pytest.mark.xdist_group("cmake_build")
class TestCMakeBuild:
    """CMake FetchContent build tests — compile and run every scenario."""

    @pytest.fixture(scope="class", autouse=True)
    def cmake_configured(self):
        assert _cmake_configure(), "cmake configure failed"

    # --- combined ---

    def test_combined_luabridge3_builds(self):
        assert _cmake_build("test_combined_luabridge3"), "combined luabridge3 build failed"

    def test_combined_luabridge3_runs(self):
        assert _run_executable("test_combined_luabridge3"), "combined luabridge3 run failed"

    # --- geo ---

    def test_geo_luabridge3_builds(self):
        assert _cmake_build("test_geo_luabridge3"), "geo luabridge3 build failed"

    def test_geo_luabridge3_runs(self):
        assert _run_executable("test_geo_luabridge3"), "geo luabridge3 run failed"

    def test_geo_pybind11_builds(self):
        assert _cmake_build("geo_py"), "geo pybind11 build failed"

    def test_geo_pybind11_runs(self):
        assert _run_pybind11_verify(HERE / "geo" / "pybind11_verify.py"), "geo pybind11 verify failed"

    # --- engine ---

    def test_engine_luabridge3_builds(self):
        assert _cmake_build("test_engine_luabridge3"), "engine luabridge3 build failed"

    def test_engine_luabridge3_runs(self):
        assert _run_executable("test_engine_luabridge3"), "engine luabridge3 run failed"

    def test_engine_pybind11_builds(self):
        assert _cmake_build("engine_py"), "engine pybind11 build failed"

    def test_engine_pybind11_runs(self):
        assert _run_pybind11_verify(HERE / "engine" / "pybind11_verify.py"), "engine pybind11 verify failed"

    # --- audio ---

    def test_audio_luabridge3_builds(self):
        assert _cmake_build("test_audio_luabridge3"), "audio luabridge3 build failed"

    def test_audio_luabridge3_runs(self):
        assert _run_executable("test_audio_luabridge3"), "audio luabridge3 run failed"

    def test_audio_pybind11_builds(self):
        assert _cmake_build("audio_py"), "audio pybind11 build failed"

    def test_audio_pybind11_runs(self):
        assert _run_pybind11_verify(HERE / "audio" / "pybind11_verify.py"), "audio pybind11 verify failed"
