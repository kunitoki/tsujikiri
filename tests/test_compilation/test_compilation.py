"""Compilation tests — generate LuaBridge3 bindings and compile with CMake FetchContent.

Each test either:
  - Checks generated output for expected strings (fast, no build), or
  - Generates luabridge3_bindings.cpp, runs cmake configure + build using
    FetchContent to fetch the real LuaBridge3 library (requires cmake).

The cmake build directory (_cmake_build/ next to tests/) is persistent so
FetchContent downloads are cached between runs.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
HEADER = HERE / "combined.hpp"

CMAKE_AVAILABLE = shutil.which("cmake") is not None
CMAKE_BUILD_DIR = HERE / "build"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(module, output_config, generation=None) -> str:
    from tsujikiri.generator import Generator
    buf = io.StringIO()
    Generator(output_config, generation=generation).generate(module, buf)
    return buf.getvalue()


def _cmake_compile_luabridge3() -> tuple[bool, str]:
    """Write bindings to file and compile via CMake FetchContent."""
    cfg = subprocess.run(
        ["cmake", "-S", str(HERE), "-B", str(CMAKE_BUILD_DIR), "-DCMAKE_BUILD_TYPE=Release", "-Wno-dev"],
        capture_output=True, text=True)

    if cfg.returncode != 0:
        return False, cfg.stderr + cfg.stdout

    build = subprocess.run(
        ["cmake", "--build", str(CMAKE_BUILD_DIR), "--target", "test_luabridge3_bindings"],
        capture_output=True, text=True)

    return build.returncode == 0, build.stderr + build.stdout


# ---------------------------------------------------------------------------
# LuaBridge3
# ---------------------------------------------------------------------------

class TestLuaBridge3Generation:
    """Fast tests — check generated output without compiling."""

    def test_contains_begin_class(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.beginClass<mylib::Shape>("Shape")' in generated

    def test_derived_class(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.deriveClass<mylib::Circle, mylib::Shape>("Circle")' in generated

    def test_constructors(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert "addConstructor<void (*)()>" in generated

    def test_overloaded_method_cast(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert "luabridge::overload<int, int>(&mylib::Calculator::add)" in generated

    def test_enum_namespace(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in generated
        assert ".endNamespace()" in generated


@pytest.mark.skipif(not CMAKE_AVAILABLE, reason="cmake not installed")
class TestLuaBridge3CMakeBuild:
    """CMake FetchContent build — compiles against the real LuaBridge3 library."""

    def test_cmake_build(self, compiled_module, luabridge3_output_config, compilation_input_config):
        ok, output = _cmake_compile_luabridge3()
        assert ok, f"LuaBridge3 CMake build failed:\n{output}"
