"""Local fixtures for test_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def parser_input_config():
    from tsujikiri.configurations import load_input_config
    cfg = load_input_config(HERE / "combined.input.yml")
    cfg.source.path = str(HERE / "combined.hpp")
    return cfg


@pytest.fixture(scope="module")
def parsed_module(parser_input_config):
    from tsujikiri.parser import parse_translation_unit
    return parse_translation_unit(parser_input_config, "combined")
