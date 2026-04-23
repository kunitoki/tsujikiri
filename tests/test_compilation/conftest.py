"""Local fixtures for test_compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tsujikiri.configurations import load_input_config
from tsujikiri.filters import FilterEngine
from tsujikiri.tir import merge_tir_modules
from tsujikiri.parser import parse_translation_unit
from tsujikiri.transforms import build_pipeline_from_config

HERE = Path(__file__).parent


def _load_module(config_file: Path, module_name: str):
    """Parse all source entries in *config_file* and return the merged IRModule."""
    config = load_input_config(config_file)
    modules = []
    for entry in config.get_source_entries():
        effective = entry.filters if entry.filters is not None else config.filters
        effective_transforms = entry.transforms if entry.transforms is not None else config.transforms
        mod = parse_translation_unit(entry.source, effective.namespaces, module_name, verbose=True)
        FilterEngine(effective).apply(mod)
        build_pipeline_from_config(effective_transforms).run(mod)
        modules.append(mod)
    return merge_tir_modules(modules)


# ---------------------------------------------------------------------------
# combined (original single-namespace, single-header)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def compilation_input_config():
    return load_input_config(HERE / "combined" / "combined.input.yml")


@pytest.fixture(scope="module")
def compiled_module(compilation_input_config):
    entries = compilation_input_config.get_source_entries()
    module = parse_translation_unit(
        entries[0].source,
        compilation_input_config.filters.namespaces,
        "combined",
        verbose=True,
    )
    FilterEngine(compilation_input_config.filters).apply(module)
    return module


# ---------------------------------------------------------------------------
# geo: multi-header, single namespace, Circle/Rectangle inherit from Shape
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def geo_module():
    return _load_module(HERE / "geo" / "geo.input.yml", "geo")


# ---------------------------------------------------------------------------
# engine: multi-header, two namespaces (math + engine), cross-namespace types
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine_module():
    return _load_module(HERE / "engine" / "engine.input.yml", "engine")


@pytest.fixture(scope="module")
def engine_luabridge3_generation():
    config = load_input_config(HERE / "engine" / "engine.input.yml")
    override = config.format_overrides.get("luabridge3")
    return override.generation if override else None


@pytest.fixture(scope="module")
def engine_pybind11_generation():
    config = load_input_config(HERE / "engine" / "engine.input.yml")
    override = config.format_overrides.get("pybind11")
    return override.generation if override else None


# ---------------------------------------------------------------------------
# audio: single header, 3-level hierarchy (AudioNode → AudioEffect → Reverb/Delay)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def audio_module():
    return _load_module(HERE / "audio" / "audio.input.yml", "audio")


# ---------------------------------------------------------------------------
# samplebinding: virtual methods, shared_ptr holder, keep_alive ownership
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def samplebinding_module():
    return _load_module(HERE / "samplebinding" / "samplebinding.input.yml", "samplebinding")


# ---------------------------------------------------------------------------
# typesystem: primitive_types mapping, custom_types unlocking, OSType/int64_t
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def typesystem_module():
    return _load_module(HERE / "typesystem" / "typesystem.input.yml", "typesystem")


# ---------------------------------------------------------------------------
# transforms: full exercise of every transform stage
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def transforms_module():
    return _load_module(HERE / "transforms" / "transforms.input.yml", "transforms")
