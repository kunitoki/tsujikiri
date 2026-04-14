"""CMake compilation tests — build generated bindings and run them.

Each test in TestCMakeBuild compiles a scenario's generated C++/pybind11 code
via CMake and verifies the resulting executable or Python extension works at
runtime.  FetchContent dependencies are pre-cloned once by _fetch_all_deps()
so cmake never races to clone the same repo from multiple xdist workers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent

CMAKE_AVAILABLE = shutil.which("cmake") is not None

_SCENARIOS = ["combined", "geo", "engine", "audio", "samplebinding", "typesystem"]
_SHARED_DEPS_DIR = HERE / "_deps"

_DEPS: dict[str, dict[str, str | Path]] = {
    "lua": {
        "url": "https://github.com/lua/lua.git",
        "tag": "v5.4.8",
        "src_dir": _SHARED_DEPS_DIR / "lua-src",
    },
    "luabridge3": {
        "url": "https://github.com/kunitoki/LuaBridge3.git",
        "tag": "master",
        "src_dir": _SHARED_DEPS_DIR / "luabridge3-src",
    },
    "pybind11": {
        "url": "https://github.com/pybind/pybind11.git",
        "tag": "v2.13.6",
        "src_dir": _SHARED_DEPS_DIR / "pybind11-src",
    },
}


def _scenario_dir(scenario: str) -> Path:
    return HERE / scenario


def _build_dir(scenario: str) -> Path:
    return HERE / scenario / "build"


def _python_modules_dir(scenario: str) -> Path:
    return _build_dir(scenario) / "python_modules"


# ---------------------------------------------------------------------------
# CMake helpers
# ---------------------------------------------------------------------------

def _fetch_all_deps() -> None:
    """Shallow-clone every FetchContent dependency into _deps/ if not already present.

    Running git clone here (once, serially) avoids the race that occurs when
    multiple cmake configure processes try to clone into the same directory at
    the same time — which causes 'shallow.lock already exists' failures.
    """
    _SHARED_DEPS_DIR.mkdir(parents=True, exist_ok=True)
    for name, dep in _DEPS.items():
        src_dir = dep["src_dir"]
        assert isinstance(src_dir, Path)
        if (src_dir / ".git").exists():
            continue
        if src_dir.exists():
            shutil.rmtree(src_dir)  # remove partial/corrupt clone
        result = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--branch", str(dep["tag"]),
                "--single-branch",
                str(dep["url"]),
                str(src_dir),
            ],
            capture_output=True,
            text=True,
        )
        print(result.stdout + result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone dep '{name}': {result.stderr}")


def _cmake_configure(scenario: str) -> bool:
    """Configure a scenario's isolated build dir.

    Deps are pre-cloned by _fetch_all_deps(); cmake is pointed at the local
    source dirs via FETCHCONTENT_SOURCE_DIR_<NAME> so it never clones anything.
    """
    build_dir = _build_dir(scenario)
    build_dir.mkdir(parents=True, exist_ok=True)
    if (build_dir / "CMakeCache.txt").exists():
        return True
    cmake_args = [
        "cmake",
        "-S", str(_scenario_dir(scenario)),
        "-B", str(build_dir),
        f"-DFETCHCONTENT_BASE_DIR={_SHARED_DEPS_DIR}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-Wno-dev",
    ]
    for name, dep in _DEPS.items():
        cmake_args.append(f"-DFETCHCONTENT_SOURCE_DIR_{name.upper()}={dep['src_dir']}")
    result = subprocess.run(cmake_args, capture_output=True, text=True)
    print(result.stdout + result.stderr)
    return result.returncode == 0


def _cmake_build(scenario: str, target: str) -> bool:
    """Build a single target inside a scenario's isolated build dir."""
    cmd = ["cmake", "--build", str(_build_dir(scenario)), "--target", target]
    # Multi-config generators (MSVC on Windows, Xcode on macOS) need an
    # explicit config; single-config generators (Ninja/Make on Linux) do not.
    if sys.platform != "linux":
        cmd += ["--config", "Release"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout + result.stderr)
    return result.returncode == 0


def _cmake_build_all(scenario: str) -> bool:
    """Build all targets for a scenario.

    A sentinel file skips the build on repeated calls so individual
    _cmake_build() calls in tests are fast (cmake no-ops when up-to-date).
    """
    sentinel = _build_dir(scenario) / ".build_complete"
    if sentinel.exists():
        return True
    cmd = ["cmake", "--build", str(_build_dir(scenario))]
    if sys.platform != "linux":
        cmd += ["--config", "Release"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout + result.stderr)
    if result.returncode == 0:
        sentinel.touch()
    return result.returncode == 0


def _run_executable(scenario: str, name: str) -> bool:
    """Run a built executable from a scenario's build directory."""
    build_dir = _build_dir(scenario)
    suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [
        build_dir / f"{name}{suffix}",
        build_dir / "Release" / f"{name}{suffix}",
        build_dir / "Debug" / f"{name}{suffix}",
    ]
    exe = next((p for p in candidates if p.exists()), None)
    if exe is None:
        print(f"executable not found: {name}")
        return False
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode == 0


def _run_pybind11_verify(scenario: str) -> bool:
    """Run a scenario's pybind11_verify.py with PYTHONPATH pointing to its modules."""
    script = _scenario_dir(scenario) / "pybind11_verify.py"
    py_dir = _python_modules_dir(scenario)
    dirs = [py_dir] + [
        py_dir / cfg
        for cfg in ("Release", "Debug")
        if (py_dir / cfg).exists()
    ]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(d) for d in dirs)}
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
# CMake build + run tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CMAKE_AVAILABLE, reason="cmake not installed")
@pytest.mark.xdist_group("cmake_build")
class TestCMakeBuild:
    """CMake build tests — compile and run every scenario."""

    @pytest.fixture(scope="class", autouse=True)
    def cmake_configured(self) -> None:
        """Clone deps once, configure every scenario, then build all upfront."""
        _fetch_all_deps()
        for scenario in _SCENARIOS:
            assert _cmake_configure(scenario), f"{scenario} cmake configure failed"
        for scenario in _SCENARIOS:
            assert _cmake_build_all(scenario), f"{scenario} cmake build failed"

    # --- combined ---

    def test_combined_luabridge3_builds(self) -> None:
        assert _cmake_build("combined", "test_combined_luabridge3"), "combined luabridge3 build failed"

    def test_combined_luabridge3_runs(self) -> None:
        _cmake_build("combined", "test_combined_luabridge3")
        assert _run_executable("combined", "test_combined_luabridge3"), "combined luabridge3 run failed"

    # --- geo ---

    def test_geo_luabridge3_builds(self) -> None:
        assert _cmake_build("geo", "test_geo_luabridge3"), "geo luabridge3 build failed"

    def test_geo_luabridge3_runs(self) -> None:
        _cmake_build("geo", "test_geo_luabridge3")
        assert _run_executable("geo", "test_geo_luabridge3"), "geo luabridge3 run failed"

    def test_geo_pybind11_builds(self) -> None:
        assert _cmake_build("geo", "geo_py"), "geo pybind11 build failed"

    def test_geo_pybind11_runs(self) -> None:
        _cmake_build("geo", "geo_py")
        assert _run_pybind11_verify("geo"), "geo pybind11 verify failed"

    # --- engine ---

    def test_engine_luabridge3_builds(self) -> None:
        assert _cmake_build("engine", "test_engine_luabridge3"), "engine luabridge3 build failed"

    def test_engine_luabridge3_runs(self) -> None:
        _cmake_build("engine", "test_engine_luabridge3")
        assert _run_executable("engine", "test_engine_luabridge3"), "engine luabridge3 run failed"

    def test_engine_pybind11_builds(self) -> None:
        assert _cmake_build("engine", "engine_py"), "engine pybind11 build failed"

    def test_engine_pybind11_runs(self) -> None:
        _cmake_build("engine", "engine_py")
        assert _run_pybind11_verify("engine"), "engine pybind11 verify failed"

    # --- audio ---

    def test_audio_luabridge3_builds(self) -> None:
        assert _cmake_build("audio", "test_audio_luabridge3"), "audio luabridge3 build failed"

    def test_audio_luabridge3_runs(self) -> None:
        _cmake_build("audio", "test_audio_luabridge3")
        assert _run_executable("audio", "test_audio_luabridge3"), "audio luabridge3 run failed"

    def test_audio_pybind11_builds(self) -> None:
        assert _cmake_build("audio", "audio_py"), "audio pybind11 build failed"

    def test_audio_pybind11_runs(self) -> None:
        _cmake_build("audio", "audio_py")
        assert _run_pybind11_verify("audio"), "audio pybind11 verify failed"

    # --- samplebinding ---

    def test_samplebinding_pybind11_builds(self) -> None:
        assert _cmake_build("samplebinding", "samplebinding_py"), "samplebinding pybind11 build failed"

    def test_samplebinding_pybind11_runs(self) -> None:
        _cmake_build("samplebinding", "samplebinding_py")
        assert _run_pybind11_verify("samplebinding"), "samplebinding pybind11 verify failed"

    # --- typesystem ---

    def test_typesystem_luabridge3_builds(self) -> None:
        assert _cmake_build("typesystem", "test_typesystem_luabridge3"), "typesystem luabridge3 build failed"

    def test_typesystem_luabridge3_runs(self) -> None:
        _cmake_build("typesystem", "test_typesystem_luabridge3")
        assert _run_executable("typesystem", "test_typesystem_luabridge3"), "typesystem luabridge3 run failed"

    def test_typesystem_pybind11_builds(self) -> None:
        assert _cmake_build("typesystem", "typesystem_py"), "typesystem pybind11 build failed"

    def test_typesystem_pybind11_runs(self) -> None:
        _cmake_build("typesystem", "typesystem_py")
        assert _run_pybind11_verify("typesystem"), "typesystem pybind11 verify failed"
