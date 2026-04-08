"""Local fixtures for test_compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).parent
STUBS = Path(__file__).parent.parent / "stubs"


@pytest.fixture(scope="module")
def compilation_input_config():
    from tsujikiri.configurations import load_input_config
    cfg = load_input_config(HERE / "combined.input.yml")
    cfg.source.path = str(HERE / "combined.hpp")
    return cfg


@pytest.fixture(scope="module")
def compiled_module(compilation_input_config):
    from tsujikiri.filters import FilterEngine
    from tsujikiri.parser import parse_translation_unit
    module = parse_translation_unit(compilation_input_config, "combined")
    FilterEngine(compilation_input_config.filters).apply(module)
    return module
