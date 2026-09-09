"""Golden-diff matrix: generated output must not depend on how it was produced.

Since the parse cache hands one shared ``IRModule`` to several consumers, the
risk is that state belonging to one target leaks into another.  Every test here
asserts a per-target property that a leak would break — most sharply, that an
injected property or code block appears **exactly once** per output.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tsujikiri.cli import main

HERE = Path(__file__).parent

INJECTED_CODE = "// injected-once-marker"
# The generator snake-cases binding names, so "injectedProp" is emitted as this.
PROP_MARKER = "injected_prop"


def _run(*args: str) -> tuple[str, str]:
    stdout, stderr = StringIO(), StringIO()
    with patch("sys.argv", ["tsujikiri", *args]):
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            main()
    return stdout.getvalue(), stderr.getvalue()


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


DECLARED_FUNCTIONS = [
    {
        "name": "declaredHelper",
        "namespace": "alpha",
        "return_type": "void",
        "parameters": [{"name": "x", "type": "int"}],
    }
]

TRANSFORMS = [
    {"stage": "inject_property", "class": "Foo", "name": "injectedProp", "getter": "getX"},
    {"stage": "inject_code", "target": "module", "position": "beginning", "code": INJECTED_CODE},
]


def _one_source_config(with_declared: bool, with_transforms: bool) -> dict:
    """Single source, so each injection has an unambiguous expected count of 1.

    ``inject_code`` with ``target: module`` runs once per source module and the
    modules are then merged, so a two-source config emits it twice — existing
    behaviour, unrelated to caching.
    """
    data: dict = {
        "sources": [{"path": str(HERE / "multi_out_a.hpp"), "parse_args": ["-std=c++17"]}],
        "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
    }
    if with_declared:
        data["typesystem"] = {"declared_functions": DECLARED_FUNCTIONS}
    if with_transforms:
        data["transforms"] = TRANSFORMS
    return data


def _single_output_config(with_declared: bool, with_transforms: bool) -> dict:
    data: dict = {
        "sources": [
            {
                "path": str(HERE / "multi_out_a.hpp"),
                "parse_args": ["-std=c++17"],
                "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
            },
            {"path": str(HERE / "multi_out_b.hpp"), "parse_args": ["-std=c++17"]},
        ],
        "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
    }
    if with_declared:
        data["typesystem"] = {"declared_functions": DECLARED_FUNCTIONS}
    if with_transforms:
        data["transforms"] = TRANSFORMS
    return data


def _group_config(num_groups: int, with_declared: bool, with_transforms: bool) -> dict:
    outputs = [{"name": "group_a", "sources": [str(HERE / "multi_out_a.hpp")]}]
    if num_groups == 2:
        outputs.append({"name": "group_b", "sources": [str(HERE / "multi_out_b.hpp")]})
    data: dict = {
        "outputs": outputs,
        "parse_args": ["-std=c++17"],
        "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
    }
    if with_declared:
        data["typesystem"] = {"declared_functions": DECLARED_FUNCTIONS}
    if with_transforms:
        data["transforms"] = TRANSFORMS
    return data


# ---------------------------------------------------------------------------
# Single-output mode
# ---------------------------------------------------------------------------


class TestSingleOutputIdentity:
    @pytest.mark.parametrize("with_declared", [False, True])
    @pytest.mark.parametrize("with_transforms", [False, True])
    @pytest.mark.parametrize("jobs", ["1", "2"])
    def test_rerunning_produces_identical_output(
        self, tmp_path: Path, with_declared: bool, with_transforms: bool, jobs: str
    ) -> None:
        cfg = _write(tmp_path, "single.input.yml", _single_output_config(with_declared, with_transforms))
        first, _ = _run("-i", str(cfg), "-t", "luabridge3", "-", "-j", jobs)
        second, _ = _run("-i", str(cfg), "-t", "luabridge3", "-", "-j", jobs)
        assert first == second
        assert "Foo" in first and "Bar" in first

    @pytest.mark.parametrize("with_transforms", [False, True])
    def test_injected_code_appears_exactly_once(self, tmp_path: Path, with_transforms: bool) -> None:
        cfg = _write(tmp_path, "one.input.yml", _one_source_config(False, with_transforms))
        out, _ = _run("-i", str(cfg), "-t", "luabridge3", "-")
        assert out.count(INJECTED_CODE) == (1 if with_transforms else 0)

    def test_injected_property_appears_exactly_once(self, tmp_path: Path) -> None:
        """The regression test for IRModule aliasing across consumers."""
        cfg = _write(tmp_path, "one.input.yml", _one_source_config(False, True))
        out, _ = _run("-i", str(cfg), "-t", "luabridge3", "-")
        assert out.count(PROP_MARKER) == 1

    def test_declared_function_appears_exactly_once(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "one.input.yml", _one_source_config(True, False))
        out, _ = _run("-i", str(cfg), "-t", "luabridge3", "-")
        assert out.count("declaredHelper") == 1


class TestMultiTargetIdentity:
    """Two targets share a cached parse; each must get a complete, private module."""

    def test_second_target_also_receives_declared_functions(self, tmp_path: Path) -> None:
        """3.D: before the rewire, only target 0 got them."""
        cfg = _write(tmp_path, "single.input.yml", _single_output_config(True, False))
        first, second = tmp_path / "first.cpp", tmp_path / "second.cpp"
        _run("-i", str(cfg), "-t", "luabridge3", str(first), "-t", "luabridge3", str(second))
        assert first.read_text().count("declaredHelper") == 1
        assert second.read_text().count("declaredHelper") == 1

    def test_two_targets_of_one_format_are_identical(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "single.input.yml", _single_output_config(True, True))
        first, second = tmp_path / "first.cpp", tmp_path / "second.cpp"
        _run("-i", str(cfg), "-t", "luabridge3", str(first), "-t", "luabridge3", str(second))
        assert first.read_text() == second.read_text()

    def test_injections_are_not_duplicated_across_targets(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "one.input.yml", _one_source_config(True, True))
        first, second = tmp_path / "first.cpp", tmp_path / "second.cpp"
        _run("-i", str(cfg), "-t", "luabridge3", str(first), "-t", "luabridge3", str(second))
        for path in (first, second):
            text = path.read_text()
            assert text.count(INJECTED_CODE) == 1
            assert text.count(PROP_MARKER) == 1
            assert text.count("declaredHelper") == 1

    def test_two_distinct_formats_each_stay_complete(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "one.input.yml", _one_source_config(True, True))
        cpp, lua = tmp_path / "out.cpp", tmp_path / "out.lua"
        _run("-i", str(cfg), "-t", "luabridge3", str(cpp), "-t", "luals", str(lua))
        assert cpp.read_text().count(PROP_MARKER) == 1
        assert "Foo" in lua.read_text()

    def test_target_order_does_not_change_either_output(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "single.input.yml", _single_output_config(True, True))
        a_first, b_first = tmp_path / "a1.cpp", tmp_path / "b1.lua"
        _run("-i", str(cfg), "-t", "luabridge3", str(a_first), "-t", "luals", str(b_first))
        b_second, a_second = tmp_path / "b2.lua", tmp_path / "a2.cpp"
        _run("-i", str(cfg), "-t", "luals", str(b_second), "-t", "luabridge3", str(a_second))
        assert a_first.read_text() == a_second.read_text()
        assert b_first.read_text() == b_second.read_text()


# ---------------------------------------------------------------------------
# Output-group mode
# ---------------------------------------------------------------------------


class TestOutputGroupIdentity:
    @pytest.mark.parametrize("num_groups", [1, 2])
    @pytest.mark.parametrize("jobs", ["1", "2"])
    def test_groups_are_stable_across_runs(self, tmp_path: Path, num_groups: int, jobs: str) -> None:
        cfg = _write(tmp_path, "groups.input.yml", _group_config(num_groups, True, True))
        results = []
        for run in range(2):
            outdir = tmp_path / f"out{run}{jobs}{num_groups}"
            _run("-i", str(cfg), "-t", "luabridge3", f"{outdir}/", "-j", jobs)
            results.append({p.name: p.read_text() for p in sorted(outdir.iterdir())})
        assert results[0] == results[1]
        assert len(results[0]) == num_groups

    def test_each_group_gets_its_injection_exactly_once(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "groups.input.yml", _group_config(2, False, True))
        outdir = tmp_path / "out"
        _run("-i", str(cfg), "-t", "luabridge3", f"{outdir}/")
        contents = [p.read_text() for p in sorted(outdir.iterdir())]
        assert len(contents) == 2
        for text in contents:
            assert text.count(INJECTED_CODE) == 1
        # inject_property targets class Foo, which lives only in group_a.
        assert sum(text.count(PROP_MARKER) for text in contents) == 1

    def test_two_targets_over_groups_are_independent(self, tmp_path: Path) -> None:
        cfg = _write(tmp_path, "groups.input.yml", _group_config(2, False, True))
        first, second = tmp_path / "first", tmp_path / "second"
        _run("-i", str(cfg), "-t", "luabridge3", f"{first}/", "-t", "luabridge3", f"{second}/")
        for name in ("group_a.cpp", "group_b.cpp"):
            assert (first / name).read_text() == (second / name).read_text()
            assert (first / name).read_text().count(INJECTED_CODE) == 1

    def test_a_source_shared_by_two_groups_is_parsed_once(self, tmp_path: Path) -> None:
        """Same key in both groups ⇒ one [parse] line, two complete outputs."""
        shared = str(HERE / "multi_out_a.hpp")
        cfg = _write(
            tmp_path,
            "shared.input.yml",
            {
                "outputs": [
                    {"name": "group_a", "sources": [shared]},
                    {"name": "group_b", "sources": [shared]},
                ],
                "parse_args": ["-std=c++17"],
                "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
            },
        )
        outdir = tmp_path / "out"
        _, stderr = _run("-i", str(cfg), "-t", "luabridge3", f"{outdir}/", "-v")
        assert stderr.count("multi_out_a.hpp: args=") == 1
        assert (outdir / "group_a.cpp").read_text() == (outdir / "group_b.cpp").read_text()
        assert "Foo" in (outdir / "group_a.cpp").read_text()


# ---------------------------------------------------------------------------
# Cache-key correctness: same path, different namespace filter
# ---------------------------------------------------------------------------


class TestFormatOverrideNamespaces:
    """A format override that narrows namespaces must not reuse the wider parse."""

    def test_override_namespaces_produce_a_separate_parse(self, tmp_path: Path) -> None:
        cfg = _write(
            tmp_path,
            "override.input.yml",
            {
                "sources": [{"path": str(HERE / "multi_out_a.hpp"), "parse_args": ["-std=c++17"]}],
                "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
                "format_overrides": {
                    "luals": {
                        "filters": {"namespaces": ["nonexistent"], "constructors": {"include": False}},
                    }
                },
            },
        )
        cpp, lua = tmp_path / "out.cpp", tmp_path / "out.lua"
        _, stderr = _run("-i", str(cfg), "-t", "luabridge3", str(cpp), "-t", "luals", str(lua), "-v")
        # Two different namespace filters ⇒ two distinct keys ⇒ two parses.
        assert stderr.count("multi_out_a.hpp: args=") == 2
        assert "Foo" in cpp.read_text()
        assert "Foo" not in lua.read_text()

    def test_matching_namespaces_reuse_one_parse(self, tmp_path: Path) -> None:
        cfg = _write(
            tmp_path,
            "same.input.yml",
            {
                "sources": [{"path": str(HERE / "multi_out_a.hpp"), "parse_args": ["-std=c++17"]}],
                "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
            },
        )
        cpp, lua = tmp_path / "out.cpp", tmp_path / "out.lua"
        _, stderr = _run("-i", str(cfg), "-t", "luabridge3", str(cpp), "-t", "luals", str(lua), "-v")
        assert stderr.count("multi_out_a.hpp: args=") == 1


# ---------------------------------------------------------------------------
# Per-source entry filters
# ---------------------------------------------------------------------------


class TestPerSourceFilters:
    def test_entry_filters_are_honoured_and_keyed_separately(self, tmp_path: Path) -> None:
        """Two entries for one file differing only by filters ⇒ two parses."""
        path = str(HERE / "multi_out_a.hpp")
        cfg = _write(
            tmp_path,
            "entry_filters.input.yml",
            {
                "sources": [
                    {
                        "path": path,
                        "parse_args": ["-std=c++17"],
                        "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
                    },
                    {
                        "path": path,
                        "parse_args": ["-std=c++17"],
                        "filters": {"namespaces": ["nonexistent"], "constructors": {"include": False}},
                    },
                ],
            },
        )
        out, stderr = _run("-i", str(cfg), "-t", "luabridge3", "-", "-v")
        assert stderr.count("multi_out_a.hpp: args=") == 2
        assert out.count("Foo") >= 1
