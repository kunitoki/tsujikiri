"""Tests for --jobs / -j: flag parsing, worker-count resolution, and parallel parsing.

Parallel runs must be byte-identical to serial ones, so most assertions here
compare a ``-j N`` run against the same run at ``-j 1``.  Tests that actually
spawn a pool are deliberately few and use tiny headers: CI runners have 2-4
cores and already run the suite under ``pytest -n auto``.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from tsujikiri.cli import _parse_jobs, _resolve_jobs, build_parser, main
from tsujikiri.configurations import SourceConfig
from tsujikiri.parse_cache import ParseCache, ParseKey

HERE = Path(__file__).parent


def _run(*args: str, expected_exit: int | None = None) -> tuple[str, str]:
    """Run main() with given CLI args, capture stdout/stderr."""
    stdout, stderr = StringIO(), StringIO()
    with patch("sys.argv", ["tsujikiri", *args]):
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            try:
                main()
            except SystemExit as e:
                if expected_exit is not None and e.code != expected_exit:
                    raise
    return stdout.getvalue(), stderr.getvalue()


def _key(path: Path, namespaces=("simple",)) -> ParseKey:
    return ParseKey.from_source(SourceConfig(path=str(path), parse_args=["-std=c++17"]), list(namespaces), "m")


@pytest.fixture
def two_source_yml(tmp_path: Path) -> Path:
    """Two tiny headers in one module — the smallest config that can parallelise."""
    cfg = tmp_path / "two.input.yml"
    cfg.write_text(
        yaml.dump(
            {
                "sources": [
                    {"path": str(HERE / "multi_out_a.hpp"), "parse_args": ["-std=c++17"]},
                    {"path": str(HERE / "multi_out_b.hpp"), "parse_args": ["-std=c++17"]},
                ],
                "filters": {"namespaces": ["alpha"], "constructors": {"include": False}},
            }
        ),
        encoding="utf-8",
    )
    return cfg


# ---------------------------------------------------------------------------
# Flag parsing — pure, no pool
# ---------------------------------------------------------------------------


class TestParseJobsFlag:
    def test_default_is_serial(self) -> None:
        assert build_parser().parse_args(["-i", "x", "-t", "f", "-"]).jobs == 1

    @pytest.mark.parametrize("text,expected", [("auto", 0), ("0", 0), ("1", 1), ("4", 4), ("12", 12)])
    def test_accepted_values(self, text: str, expected: int) -> None:
        assert _parse_jobs(text) == expected

    @pytest.mark.parametrize("text", ["nonsense", "", "1.5", "-1", "-4", "two"])
    def test_rejected_values(self, text: str) -> None:
        with pytest.raises(Exception) as exc:
            _parse_jobs(text)
        assert "invalid jobs value" in str(exc.value)

    @pytest.mark.parametrize("flag", ["-j", "--jobs"])
    def test_both_spellings_reach_the_namespace(self, flag: str) -> None:
        assert build_parser().parse_args(["-i", "x", "-t", "f", "-", flag, "3"]).jobs == 3

    def test_auto_through_the_parser(self) -> None:
        assert build_parser().parse_args(["-i", "x", "-t", "f", "-", "-j", "auto"]).jobs == 0

    def test_bad_value_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exc:
            build_parser().parse_args(["-i", "x", "-t", "f", "-", "-j", "nonsense"])
        assert exc.value.code == 2


class TestResolveJobs:
    @pytest.mark.parametrize("jobs,expected", [(1, 1), (2, 2), (12, 12)])
    def test_explicit_counts_pass_through(self, jobs: int, expected: int) -> None:
        assert _resolve_jobs(jobs) == expected

    def test_zero_means_one_per_cpu(self) -> None:
        with patch("os.cpu_count", return_value=7):
            assert _resolve_jobs(0) == 7

    def test_unknown_cpu_count_falls_back_to_one(self) -> None:
        with patch("os.cpu_count", return_value=None):
            assert _resolve_jobs(0) == 1


# ---------------------------------------------------------------------------
# ParseCache pool behaviour
# ---------------------------------------------------------------------------


class TestParseCachePoolDispatch:
    """When the pool is worth using, and when it is skipped."""

    def test_single_missing_key_stays_serial(self) -> None:
        cache = ParseCache(jobs=4)
        with patch("tsujikiri.parse_cache.ProcessPoolExecutor") as pool:
            cache.prefetch([_key(HERE / "simple.hpp")])
        pool.assert_not_called()
        assert cache.misses == 1

    def test_jobs_one_stays_serial_even_with_many_keys(self) -> None:
        cache = ParseCache(jobs=1)
        keys = [_key(HERE / "multi_out_a.hpp", ("alpha",)), _key(HERE / "multi_out_b.hpp", ("alpha",))]
        with patch("tsujikiri.parse_cache.ProcessPoolExecutor") as pool:
            cache.prefetch(keys)
        pool.assert_not_called()
        assert cache.misses == 2

    def test_empty_prefetch_does_nothing(self) -> None:
        cache = ParseCache(jobs=4)
        with patch("tsujikiri.parse_cache.ProcessPoolExecutor") as pool:
            cache.prefetch([])
        pool.assert_not_called()
        assert cache.misses == 0

    def test_duplicate_keys_collapse_below_the_pool_threshold(self) -> None:
        """Two identical keys are one parse, so no pool is spawned."""
        cache = ParseCache(jobs=4)
        key = _key(HERE / "simple.hpp")
        with patch("tsujikiri.parse_cache.ProcessPoolExecutor") as pool:
            cache.prefetch([key, key])
        pool.assert_not_called()
        assert cache.misses == 1


class TestParseCacheParallelPrefetch:
    """Real pool: two tiny headers."""

    @pytest.fixture(scope="class")
    def keys(self):
        return [_key(HERE / "multi_out_a.hpp", ("alpha",)), _key(HERE / "multi_out_b.hpp", ("alpha",))]

    def test_parallel_prefetch_matches_serial(self, keys) -> None:
        serial, parallel = ParseCache(jobs=1), ParseCache(jobs=2)
        serial.prefetch(keys)
        parallel.prefetch(keys)
        assert parallel.misses == serial.misses == 2
        for key in keys:
            assert [c.name for c in parallel.get(key).classes] == [c.name for c in serial.get(key).classes]

    def test_parallel_results_are_usable_and_cached(self, keys) -> None:
        cache = ParseCache(jobs=2)
        cache.prefetch(keys)
        assert cache.misses == 2
        cache.get(keys[0])
        cache.get(keys[1])
        assert cache.hits == 2

    def test_worker_exception_propagates_with_its_type(self, tmp_path: Path) -> None:
        """A missing source must still surface as FileNotFoundError through the pool."""
        cache = ParseCache(jobs=2)
        keys = [_key(HERE / "multi_out_a.hpp", ("alpha",)), _key(tmp_path / "missing.hpp")]
        with pytest.raises(FileNotFoundError):
            cache.prefetch(keys)

    def test_parallel_clang_errors_are_collected(self, tmp_path: Path) -> None:
        cache = ParseCache(jobs=2)
        keys = [_key(HERE / "broken.hpp", ()), _key(HERE / "multi_out_a.hpp", ("alpha",))]
        errors: list[str] = []
        cache.prefetch(keys, errors)
        assert any("strict test error" in e for e in errors)

    def test_parallel_verbose_output_is_ordered_by_submission(self, keys, capsys) -> None:
        """Never as_completed: stderr order follows the key order, not finish order."""
        ParseCache(verbose=True, jobs=2).prefetch(keys)
        err = capsys.readouterr().err
        assert err.index("multi_out_a.hpp") < err.index("multi_out_b.hpp")


# ---------------------------------------------------------------------------
# End-to-end: -j N output must equal -j 1 output
# ---------------------------------------------------------------------------


class TestJobsEndToEnd:
    def test_two_sources_parallel_matches_serial(self, two_source_yml: Path) -> None:
        serial, _ = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "1")
        parallel, _ = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "2")
        assert parallel == serial
        assert "Foo" in serial and "Bar" in serial

    def test_auto_matches_serial(self, two_source_yml: Path) -> None:
        serial, _ = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "1")
        auto, _ = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "auto")
        assert auto == serial

    def test_single_source_parallel_matches_serial(self, simple_input_yml: Path) -> None:
        serial, _ = _run("-i", str(simple_input_yml), "-t", "luabridge3", "-", "-j", "1")
        parallel, _ = _run("-i", str(simple_input_yml), "-t", "luabridge3", "-", "-j", "2")
        assert parallel == serial

    def test_two_targets_parallel_matches_serial(self, two_source_yml: Path, tmp_path: Path) -> None:
        outs = {}
        for jobs in ("1", "2"):
            a, b = tmp_path / f"a{jobs}.cpp", tmp_path / f"b{jobs}.lua"
            _run(
                "-i",
                str(two_source_yml),
                "-t",
                "luabridge3",
                str(a),
                "-t",
                "luals",
                str(b),
                "-j",
                jobs,
            )
            outs[jobs] = (a.read_text(), b.read_text())
        assert outs["1"] == outs["2"]

    def test_output_groups_parallel_matches_serial(self, multi_output_input_yml: Path, tmp_path: Path) -> None:
        results = {}
        for jobs in ("1", "2"):
            outdir = tmp_path / f"out{jobs}"
            _run("-i", str(multi_output_input_yml), "-t", "luabridge3", f"{outdir}/", "-j", jobs)
            results[jobs] = {p.name: p.read_text() for p in sorted(outdir.iterdir())}
        assert results["1"] == results["2"]
        assert set(results["1"]) == {"foo_bindings.cpp", "bar_bindings.cpp"}

    def test_verbose_output_is_stable_across_runs(self, two_source_yml: Path) -> None:
        _, first = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "2", "-v")
        _, second = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "2", "-v")
        assert first == second

    def test_verbose_output_matches_serial(self, two_source_yml: Path) -> None:
        _, serial = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "1", "-v")
        _, parallel = _run("-i", str(two_source_yml), "-t", "luabridge3", "-", "-j", "2", "-v")
        assert parallel == serial

    def test_strict_with_broken_header_exits_1(self, broken_input_yml: Path, tmp_path: Path) -> None:
        out = tmp_path / "out.cpp"
        argv = ["tsujikiri", "-i", str(broken_input_yml), "-t", "luabridge3", str(out), "--strict", "-j", "2"]
        with patch("sys.argv", argv), patch("sys.stdout", StringIO()), patch("sys.stderr", StringIO()):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
        assert not out.exists()

    def test_strict_error_reported_once_per_source_in_group_mode(self, tmp_path: Path) -> None:
        """A source shared by two groups is parsed once, so its error appears once."""
        broken = HERE / "broken.hpp"
        cfg = tmp_path / "groups.input.yml"
        cfg.write_text(
            yaml.dump(
                {
                    "outputs": [
                        {"name": "out_a", "sources": [str(broken)]},
                        {"name": "out_b", "sources": [str(broken)]},
                    ],
                    "filters": {"namespaces": []},
                }
            ),
            encoding="utf-8",
        )
        stderr = StringIO()
        argv = ["tsujikiri", "-i", str(cfg), "-t", "luabridge3", f"{tmp_path / 'out'}/", "--strict", "-v"]
        with patch("sys.argv", argv), patch("sys.stdout", StringIO()), patch("sys.stderr", stderr):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
        assert stderr.getvalue().count("strict test error") == 1

    def test_missing_source_raises_file_not_found(self, tmp_path: Path) -> None:
        cfg = tmp_path / "missing.input.yml"
        cfg.write_text(
            yaml.dump(
                {
                    "sources": [
                        {"path": str(HERE / "multi_out_a.hpp"), "parse_args": ["-std=c++17"]},
                        {"path": str(tmp_path / "nope.hpp"), "parse_args": ["-std=c++17"]},
                    ],
                    "filters": {"namespaces": ["alpha"]},
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(FileNotFoundError):
            _run("-i", str(cfg), "-t", "luabridge3", "-", "-j", "2")
