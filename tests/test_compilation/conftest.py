"""Local fixtures for test_compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def compilation_input_config():
    from tsujikiri.configurations import load_input_config
    return load_input_config(HERE / "combined.input.yml")


@pytest.fixture(scope="module")
def compiled_module(compilation_input_config):
    from tsujikiri.filters import FilterEngine
    from tsujikiri.parser import parse_translation_unit
    entries = compilation_input_config.get_source_entries()
    module = parse_translation_unit(entries[0].source, compilation_input_config.filters.namespaces, "combined")
    FilterEngine(compilation_input_config.filters).apply(module)
    return module
