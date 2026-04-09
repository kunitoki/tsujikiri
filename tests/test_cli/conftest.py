"""Local fixtures for test_cli."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent


@pytest.fixture
def simple_input_yml(tmp_path) -> Path:
    """Write a minimal input.yml that points to the local simple.hpp."""
    data = {
        "source": {
            "path": str(HERE / "simple.hpp"),
            "parse_args": ["-std=c++17"],
        },
        "filters": {
            "namespaces": ["simple"],
            "constructors": {"include": True},
        },
    }
    p = tmp_path / "simple.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def no_source_input_yml(tmp_path) -> Path:
    """Input YAML with no source entry — triggers the 'no source defined' error."""
    data = {"filters": {"namespaces": ["simple"]}}
    p = tmp_path / "no_source.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def fmt_filters_input_yml(tmp_path) -> Path:
    """Input YAML with format-level filter override."""
    data = {
        "source": {
            "path": str(HERE / "simple.hpp"),
            "parse_args": ["-std=c++17"],
        },
        "filters": {
            "namespaces": ["simple"],
            "constructors": {"include": True},
        },
        "format_overrides": {
            "luabridge3": {
                "filters": {
                    "namespaces": ["simple"],
                    "constructors": {"include": True},
                },
            },
        },
    }
    p = tmp_path / "fmt_filters.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def fmt_transforms_input_yml(tmp_path) -> Path:
    """Input YAML with format-level transform override."""
    data = {
        "source": {
            "path": str(HERE / "simple.hpp"),
            "parse_args": ["-std=c++17"],
        },
        "filters": {
            "namespaces": ["simple"],
            "constructors": {"include": True},
        },
        "format_overrides": {
            "luabridge3": {
                "transforms": [
                    {"stage": "suppress_class", "pattern": "NonExistent"},
                ],
            },
        },
    }
    p = tmp_path / "fmt_transforms.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def multi_source_with_generation_yml(tmp_path) -> Path:
    """Multi-source input YAML where first source has generation.includes."""
    data = {
        "sources": [
            {
                "path": str(HERE / "simple.hpp"),
                "parse_args": ["-std=c++17"],
                "filters": {
                    "namespaces": ["simple"],
                    "constructors": {"include": True},
                },
                "generation": {
                    "includes": ["<simple_extra.h>"],
                },
            },
        ],
    }
    p = tmp_path / "multi_gen.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


@pytest.fixture
def fmt_generation_input_yml(tmp_path) -> Path:
    """Input YAML with format-level generation prefix/postfix override."""
    data = {
        "source": {
            "path": str(HERE / "simple.hpp"),
            "parse_args": ["-std=c++17"],
        },
        "filters": {
            "namespaces": ["simple"],
            "constructors": {"include": True},
        },
        "format_overrides": {
            "luabridge3": {
                "generation": {
                    "prefix": "// FMT PREFIX\n",
                    "postfix": "// FMT POSTFIX\n",
                },
            },
        },
    }
    p = tmp_path / "fmt_gen.input.yml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p
