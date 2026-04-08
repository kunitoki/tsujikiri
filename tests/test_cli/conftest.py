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
    p.write_text(yaml.dump(data))
    return p
