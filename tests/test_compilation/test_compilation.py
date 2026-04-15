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
        "--no-warn-unused-cli",
        "-Wno-dev",
    ]
    # Visual Studio (multi-config) generator: specify 64-bit architecture and
    # skip CMAKE_BUILD_TYPE (it is ignored by multi-config generators anyway).
    if sys.platform == "win32":
        cmake_args += ["-A", "x64"]
    else:
        cmake_args += ["-DCMAKE_BUILD_TYPE=Release"]
    for name, dep in _DEPS.items():
        cmake_args.append(f"-DFETCHCONTENT_SOURCE_DIR_{name.upper()}={dep['src_dir']}")
    result = subprocess.run(cmake_args, capture_output=True, text=True)
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

    def test_combined(self) -> None:
        assert _cmake_configure("combined"), "combined cmake configure failed"
        assert _cmake_build_all("combined"), "combined build failed"
        assert _run_executable("combined", "test_combined_luabridge3"), "combined luabridge3 run failed"

    def test_geo(self) -> None:
        assert _cmake_configure("geo"), "geo cmake configure failed"
        assert _cmake_build_all("geo"), "geo build failed"
        assert _run_executable("geo", "test_geo_luabridge3"), "geo luabridge3 run failed"
        assert _run_pybind11_verify("geo"), "geo pybind11 verify failed"

    def test_engine(self) -> None:
        assert _cmake_configure("engine"), "engine cmake configure failed"
        assert _cmake_build_all("engine"), "engine build failed"
        assert _run_executable("engine", "test_engine_luabridge3"), "engine luabridge3 run failed"
        assert _run_pybind11_verify("engine"), "engine pybind11 verify failed"

    def test_audio(self) -> None:
        assert _cmake_configure("audio"), "audio cmake configure failed"
        assert _cmake_build_all("audio"), "audio build failed"
        assert _run_executable("audio", "test_audio_luabridge3"), "audio luabridge3 run failed"
        assert _run_pybind11_verify("audio"), "audio pybind11 verify failed"

    def test_samplebinding(self) -> None:
        assert _cmake_configure("samplebinding"), "samplebinding cmake configure failed"
        assert _cmake_build_all("samplebinding"), "samplebinding build failed"
        assert _run_pybind11_verify("samplebinding"), "samplebinding pybind11 verify failed"

    def test_typesystem(self) -> None:
        assert _cmake_configure("typesystem"), "typesystem cmake configure failed"
        assert _cmake_build_all("typesystem"), "typesystem build failed"
        assert _run_executable("typesystem", "test_typesystem_luabridge3"), "typesystem luabridge3 run failed"
        assert _run_pybind11_verify("typesystem"), "typesystem pybind11 verify failed"
