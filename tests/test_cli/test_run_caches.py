"""Per-run caches built by ``main()``: compiled templates and resolved group sources.

Every run pins ``-j 1`` so the spies observe all work in-process.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import patch

import jinja2
import pytest
import yaml

from tsujikiri.cli import main
from tsujikiri.configurations import InputConfig

HERE = Path(__file__).parent


def _run(*args: str, expected_exit: Optional[int] = None) -> str:
    stderr = StringIO()
    with patch("sys.argv", ["tsujikiri", *args]), patch("sys.stdout", StringIO()), patch("sys.stderr", stderr):
        try:
            main()
        except SystemExit as e:
            if e.code != expected_exit:
                raise
    return stderr.getvalue()


@pytest.fixture
def compiled(monkeypatch: pytest.MonkeyPatch) -> List[Optional[str]]:
    """Record the template name of every real Jinja2 compilation."""
    names: List[Optional[str]] = []
    original = jinja2.Environment.compile

    def _spy(self: jinja2.Environment, source: Any, name: Optional[str] = None, *args: Any, **kwargs: Any) -> Any:
        names.append(name)
        return original(self, source, name, *args, **kwargs)

    monkeypatch.setattr(jinja2.Environment, "compile", _spy)
    return names


@pytest.fixture
def resolved(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """Record the group name of every resolve_group_sources call."""
    names: List[str] = []
    original = InputConfig.resolve_group_sources

    def _spy(self: InputConfig, group: Any) -> Any:
        names.append(group.name)
        return original(self, group)

    monkeypatch.setattr(InputConfig, "resolve_group_sources", _spy)
    return names


@pytest.fixture
def three_group_yml(tmp_path: Path) -> Path:
    cfg = tmp_path / "groups.input.yml"
    cfg.write_text(
        yaml.dump(
            {
                "outputs": [
                    {"name": "g_a", "sources": [str(HERE / "multi_out_a.hpp")]},
                    {"name": "g_b", "sources": [str(HERE / "multi_out_b.hpp")]},
                    {"name": "g_ab", "sources": [str(HERE / "multi_out_a.hpp"), str(HERE / "multi_out_b.hpp")]},
                ],
                "filters": {"namespaces": ["alpha"]},
                "format_overrides": {
                    "luabridge3": {
                        "template_extends": (
                            '{% extends "luabridge3.tpl" %}{% block prologue %}// OVERRIDDEN\n{% endblock %}'
                        ),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return cfg


class TestTemplateCacheAcrossRun:
    def test_groups_and_targets_compile_each_template_once(
        self, multi_output_input_yml: Path, tmp_path: Path, compiled: List[Optional[str]]
    ) -> None:
        _run(
            "-i",
            str(multi_output_input_yml),
            "-t",
            "luabridge3",
            f"{tmp_path / 'lb'}/",
            "-t",
            "pybind11",
            f"{tmp_path / 'py'}/",
            "-j",
            "1",
        )
        # One main.tpl per format; two groups would otherwise compile each twice.
        assert compiled == ["main.tpl", "main.tpl"]
        assert len(list((tmp_path / "lb").iterdir())) == 2
        assert len(list((tmp_path / "py").iterdir())) == 2

    def test_override_compiled_once_across_groups(
        self, three_group_yml: Path, tmp_path: Path, compiled: List[Optional[str]]
    ) -> None:
        _run("-i", str(three_group_yml), "-t", "luabridge3", f"{tmp_path / 'lb'}/", "-j", "1")
        assert sorted(n for n in compiled if n is not None) == ["__override__.tpl", "luabridge3.tpl"]
        for out in (tmp_path / "lb").iterdir():
            assert "// OVERRIDDEN" in out.read_text(encoding="utf-8")

    def test_single_output_targets_share_compilation(
        self, simple_input_yml: Path, tmp_path: Path, compiled: List[Optional[str]]
    ) -> None:
        a, b = tmp_path / "a.cpp", tmp_path / "b.cpp"
        _run("-i", str(simple_input_yml), "-t", "luabridge3", str(a), "-t", "luabridge3", str(b), "-j", "1")
        assert compiled == ["main.tpl"]
        assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


class TestGroupSourcesResolvedOnce:
    """Each group is resolved by the up-front ``get_source_entries`` validation and
    once more for the run; the count must not grow with passes or targets."""

    @pytest.mark.parametrize("formats", [["luabridge3"], ["luabridge3", "pybind11", "luals"]])
    def test_resolution_count_independent_of_targets(
        self, three_group_yml: Path, tmp_path: Path, resolved: List[str], formats: List[str]
    ) -> None:
        targets = [arg for fmt in formats for arg in ("-t", fmt, f"{tmp_path / fmt}/")]
        _run("-i", str(three_group_yml), *targets, "-j", "1")
        assert sorted(resolved) == ["g_a", "g_a", "g_ab", "g_ab", "g_b", "g_b"]
        for fmt in formats:
            assert len(list((tmp_path / fmt).iterdir())) == 3

    def test_dry_run_resolution_count(self, three_group_yml: Path, tmp_path: Path, resolved: List[str]) -> None:
        _run("-i", str(three_group_yml), "-t", "luabridge3", f"{tmp_path / 'lb'}/", "--dry-run", "-j", "1")
        assert sorted(resolved) == ["g_a", "g_a", "g_ab", "g_ab", "g_b", "g_b"]

    def test_ambiguous_group_source_still_reports_error(self, tmp_path: Path) -> None:
        (tmp_path / "x").mkdir()
        (tmp_path / "y").mkdir()
        for d in ("x", "y"):
            (tmp_path / d / "same.hpp").write_text("namespace alpha { struct S {}; }\n", encoding="utf-8")
        cfg = tmp_path / "amb.input.yml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": [{"path": str(tmp_path / "x" / "same.hpp")}, {"path": str(tmp_path / "y" / "same.hpp")}],
                    "outputs": [{"name": "g", "sources": ["same.hpp"]}],
                    "filters": {"namespaces": ["alpha"]},
                }
            ),
            encoding="utf-8",
        )
        err = _run("-i", str(cfg), "-t", "luabridge3", f"{tmp_path / 'out'}/", "-j", "1", expected_exit=1)
        assert "Ambiguous source reference 'same.hpp'" in err
