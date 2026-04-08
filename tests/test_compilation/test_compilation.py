"""Compilation tests — generate bindings from combined.hpp, compile with zig c++.

Each test:
  1. Generates binding code for a specific output format.
  2. Prepends ``#include "combined.hpp"`` so class types are available.
  3. Compiles with ``zig c++ -fsyntax-only`` (syntax check only, no linking).
     For pybind11 and luabridge3, minimal stub headers in tests/stubs/ are used
     via ``-I`` so the real libraries are not required.

Tests are skipped when zig is not installed.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).parent
STUBS = HERE.parent / "stubs"
HEADER = HERE / "combined.hpp"

ZIG_AVAILABLE = shutil.which("zig") is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate(module, output_config: object) -> str:
    from tsujikiri.generator import Generator
    buf = io.StringIO()
    Generator(output_config).generate(module, buf)
    return buf.getvalue()


def _syntax_check(source: str, extra_args: list[str] | None = None) -> tuple[bool, str]:
    """Write *source* to a temp file and compile with zig c++ -fsyntax-only."""
    args = extra_args or []
    with tempfile.NamedTemporaryFile(suffix=".cpp", mode="w", delete=False, dir=HERE) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        result = subprocess.run(
            ["zig", "c++", "-fsyntax-only", "-std=c++17"] + args + [str(tmp)],
            capture_output=True, text=True,
        )
        return result.returncode == 0, result.stderr
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# C API — pure C header, no external dependencies
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not ZIG_AVAILABLE, reason="zig not installed")
class TestCApiCompilation:
    def test_c_api_syntax_check(self, compiled_module, c_api_output_config):
        generated = _generate(compiled_module, c_api_output_config)
        # Include the original header so C++ types are visible
        source = f'#include "{HEADER}"\n{generated}'
        ok, stderr = _syntax_check(source)
        assert ok, f"C API syntax check failed:\n{stderr}\n\nGenerated:\n{generated}"

    def test_c_api_shape_handle(self, compiled_module, c_api_output_config):
        generated = _generate(compiled_module, c_api_output_config)
        assert "Shape_t" in generated
        assert "Shape_create" in generated
        assert "Shape_destroy" in generated

    def test_c_api_instance_method_has_self(self, compiled_module, c_api_output_config):
        generated = _generate(compiled_module, c_api_output_config)
        assert "Shape_t self" in generated

    def test_c_api_method_args_no_double_comma(self, compiled_module, c_api_output_config):
        generated = _generate(compiled_module, c_api_output_config)
        assert ",," not in generated

    def test_c_api_method_args_no_trailing_comma(self, compiled_module, c_api_output_config):
        generated = _generate(compiled_module, c_api_output_config)
        for line in generated.splitlines():
            stripped = line.strip()
            if stripped.endswith(");"):
                assert not stripped.endswith(",);"), f"Trailing comma in: {stripped}"


# ---------------------------------------------------------------------------
# pybind11 — syntax check with stub headers
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not ZIG_AVAILABLE, reason="zig not installed")
class TestPybind11Compilation:
    def _pybind_source(self, generated: str) -> str:
        return (
            f'#include "{HEADER}"\n'
            + generated.replace(
                "#include <pybind11/pybind11.h>",
                f'#include "{STUBS}/pybind11_stubs/pybind11/pybind11.h"',
            )
        )

    def test_pybind11_syntax_check(self, compiled_module, pybind11_output_config):
        generated = _generate(compiled_module, pybind11_output_config)
        source = self._pybind_source(generated)
        ok, stderr = _syntax_check(source)
        assert ok, f"pybind11 syntax check failed:\n{stderr}\n\nGenerated:\n{generated}"

    def test_pybind11_contains_class_bindings(self, compiled_module, pybind11_output_config):
        generated = _generate(compiled_module, pybind11_output_config)
        assert "py::class_<mylib::Shape>" in generated
        assert "py::class_<mylib::Circle, mylib::Shape>" in generated
        assert "py::class_<mylib::Calculator>" in generated

    def test_pybind11_contains_enum(self, compiled_module, pybind11_output_config):
        generated = _generate(compiled_module, pybind11_output_config)
        assert "py::enum_<mylib::Color>" in generated
        assert '.value("Red"' in generated

    def test_pybind11_overloaded_static_cast(self, compiled_module, pybind11_output_config):
        generated = _generate(compiled_module, pybind11_output_config)
        assert "static_cast<int (mylib::Calculator::*)(int, int)>" in generated

    def test_pybind11_static_method(self, compiled_module, pybind11_output_config):
        generated = _generate(compiled_module, pybind11_output_config)
        assert 'def_static("max"' in generated


# ---------------------------------------------------------------------------
# LuaBridge3 — syntax check with stub headers
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not ZIG_AVAILABLE, reason="zig not installed")
class TestLuaBridge3Compilation:
    def _lb3_source(self, generated: str) -> str:
        return (
            f'#include "{HEADER}"\n'
            + generated.replace(
                "#include <LuaBridge/LuaBridge.h>",
                f'#include "{STUBS}/luabridge3_stubs/LuaBridge/LuaBridge.h"',
            )
        )

    def test_luabridge3_syntax_check(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        source = self._lb3_source(generated)
        ok, stderr = _syntax_check(source)
        assert ok, f"LuaBridge3 syntax check failed:\n{stderr}\n\nGenerated:\n{generated}"

    def test_luabridge3_contains_begin_class(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.beginClass<mylib::Shape>("Shape")' in generated

    def test_luabridge3_derived_class(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.deriveClass<mylib::Circle, mylib::Shape>("Circle")' in generated

    def test_luabridge3_constructors(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert "addConstructor<void (*)()>" in generated

    def test_luabridge3_overloaded_method_cast(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert "static_cast<int (mylib::Calculator::*)(int, int)>" in generated

    def test_luabridge3_enum_namespace(self, compiled_module, luabridge3_output_config):
        generated = _generate(compiled_module, luabridge3_output_config)
        assert '.beginNamespace("Color")' in generated
        assert ".endNamespace()" in generated
