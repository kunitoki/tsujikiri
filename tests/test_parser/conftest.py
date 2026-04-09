"""Local fixtures for test_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def parser_input_config():
    from tsujikiri.configurations import load_input_config
    return load_input_config(HERE / "combined.input.yml")


@pytest.fixture(scope="module")
def parsed_module(parser_input_config):
    from tsujikiri.parser import parse_translation_unit
    entries = parser_input_config.get_source_entries()
    return parse_translation_unit(entries[0].source, parser_input_config.filters.namespaces, "combined")


@pytest.fixture(scope="module")
def nested_parsed_module():
    from tsujikiri.configurations import SourceConfig
    from tsujikiri.parser import parse_translation_unit
    src = SourceConfig(path=str(HERE / "nested_types.hpp"), parse_args=["-std=c++17"])
    return parse_translation_unit(src, ["mylib"], "nested")
