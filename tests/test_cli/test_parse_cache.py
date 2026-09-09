"""Tests for parse_cache.py — parse memoisation and worker isolation."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest
import yaml

from tsujikiri.configurations import SourceConfig, load_input_config
from tsujikiri.ir import IRModule
from tsujikiri.parse_cache import ParseCache, ParseKey, ParseResult, parse_worker
from tsujikiri.tir import upgrade_module

HERE = Path(__file__).parent


def _key(path: Path, namespaces=("simple",), module_name: str = "m", **kwargs) -> ParseKey:
    source = SourceConfig(path=str(path), parse_args=["-std=c++17"], **kwargs)
    return ParseKey.from_source(source, list(namespaces), module_name)


# ---------------------------------------------------------------------------
# ParseKey identity
# ---------------------------------------------------------------------------


class TestParseKeyDistinctness:
    """Every field participates in the key; two parses must never collide."""

    def test_identical_sources_produce_equal_keys(self) -> None:
        assert _key(HERE / "simple.hpp") == _key(HERE / "simple.hpp")
        assert hash(_key(HERE / "simple.hpp")) == hash(_key(HERE / "simple.hpp"))

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("parse_args", ["-std=c++20"]),
            ("include_paths", ["/somewhere"]),
            ("system_include_paths", ["/elsewhere"]),
            ("defines", ["FOO=1"]),
        ],
    )
    def test_source_field_change_makes_a_distinct_key(self, field_name: str, value: list) -> None:
        base = SourceConfig(path=str(HERE / "simple.hpp"), parse_args=["-std=c++17"])
        other = SourceConfig(path=str(HERE / "simple.hpp"), parse_args=["-std=c++17"])
        setattr(other, field_name, value)
        assert ParseKey.from_source(base, ["simple"], "m") != ParseKey.from_source(other, ["simple"], "m")

    def test_path_change_makes_a_distinct_key(self) -> None:
        assert _key(HERE / "simple.hpp") != _key(HERE / "multi_out_a.hpp")

    def test_namespaces_change_makes_a_distinct_key(self) -> None:
        """Same header, different namespace filter ⇒ different IR ⇒ different key."""
        assert _key(HERE / "simple.hpp", namespaces=("simple",)) != _key(HERE / "simple.hpp", namespaces=("other",))

    def test_module_name_change_makes_a_distinct_key(self) -> None:
        assert _key(HERE / "simple.hpp", module_name="a") != _key(HERE / "simple.hpp", module_name="b")

    def test_to_source_round_trips(self) -> None:
        source = SourceConfig(
            path="a.hpp",
            parse_args=["-std=c++17"],
            include_paths=["/i"],
            system_include_paths=["/s"],
            defines=["D=1"],
        )
        rebuilt = ParseKey.from_source(source, ["ns"], "m").to_source()
        assert rebuilt == source

    def test_key_is_picklable(self) -> None:
        key = _key(HERE / "simple.hpp")
        assert pickle.loads(pickle.dumps(key)) == key


class TestParseKeyFromEffectiveSource:
    """Keys must be built from effective_source so global settings are included."""

    def test_global_parse_args_reach_the_key(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "two.input.yml"
        cfg_path.write_text(
            yaml.dump(
                {
                    "parse_args": ["-std=c++17", "-DGLOBAL=1"],
                    "sources": [{"path": str(HERE / "simple.hpp")}],
                }
            ),
            encoding="utf-8",
        )
        config = load_input_config(cfg_path)
        entry = config.get_source_entries()[0]
        key = ParseKey.from_source(config.effective_source(entry), ["simple"], "m")
        assert "-DGLOBAL=1" in key.parse_args

    def test_two_configs_differing_only_globally_produce_distinct_keys(self, tmp_path: Path) -> None:
        keys = []
        for extra in ("-DA=1", "-DB=1"):
            cfg_path = tmp_path / f"cfg{extra}.input.yml"
            cfg_path.write_text(
                yaml.dump(
                    {
                        "parse_args": ["-std=c++17", extra],
                        "sources": [{"path": str(HERE / "simple.hpp")}],
                    }
                ),
                encoding="utf-8",
            )
            config = load_input_config(cfg_path)
            entry = config.get_source_entries()[0]
            keys.append(ParseKey.from_source(config.effective_source(entry), ["simple"], "m"))
        assert keys[0] != keys[1]


# ---------------------------------------------------------------------------
# parse_worker — runs directly in-process, exactly as it does in a subprocess
# ---------------------------------------------------------------------------


class TestParseWorker:
    def test_returns_pre_upgrade_ir_module(self) -> None:
        result = parse_worker(_key(HERE / "simple.hpp"), False)
        assert isinstance(result, ParseResult)
        assert type(result.module) is IRModule
        assert [c.name for c in result.module.classes] == ["Widget"]

    def test_quiet_worker_writes_nothing(self) -> None:
        assert parse_worker(_key(HERE / "simple.hpp"), False).stderr_text == ""

    def test_verbose_output_is_captured_not_written(self, capsys) -> None:
        result = parse_worker(_key(HERE / "simple.hpp"), True)
        assert "[parse]" in result.stderr_text
        # Nothing escaped to the real stderr.
        assert "[parse]" not in capsys.readouterr().err

    def test_clang_errors_are_collected(self) -> None:
        result = parse_worker(_key(HERE / "broken.hpp", namespaces=()), False)
        assert result.clang_errors
        assert any("strict test error" in e for e in result.clang_errors)

    def test_missing_source_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_worker(_key(tmp_path / "nope.hpp"), False)

    def test_result_survives_a_pickle_round_trip(self) -> None:
        """ParseResult crosses a process boundary; shared identity must survive."""
        result = parse_worker(_key(HERE / "simple.hpp"), False)
        restored = pickle.loads(pickle.dumps(result))
        assert [c.name for c in restored.module.classes] == ["Widget"]
        # pickle's memo keeps the two references to one object identical.
        assert restored.module.classes[0] is restored.module.class_by_name["Widget"]


# ---------------------------------------------------------------------------
# ParseCache
# ---------------------------------------------------------------------------


class TestParseCacheCounters:
    def test_first_get_is_a_miss_and_second_is_a_hit(self) -> None:
        cache = ParseCache()
        key = _key(HERE / "simple.hpp")
        first = cache.get(key)
        assert (cache.hits, cache.misses) == (0, 1)
        second = cache.get(key)
        assert (cache.hits, cache.misses) == (1, 1)
        assert first is second

    def test_distinct_keys_both_miss(self) -> None:
        cache = ParseCache()
        cache.get(_key(HERE / "multi_out_a.hpp", namespaces=("alpha",)))
        cache.get(_key(HERE / "multi_out_b.hpp", namespaces=("alpha",)))
        assert (cache.hits, cache.misses) == (0, 2)

    def test_prefetch_fills_the_cache_so_get_hits(self) -> None:
        cache = ParseCache()
        key = _key(HERE / "simple.hpp")
        cache.prefetch([key])
        assert (cache.hits, cache.misses) == (0, 1)
        cache.get(key)
        assert (cache.hits, cache.misses) == (1, 1)

    def test_prefetch_deduplicates_repeated_keys(self) -> None:
        cache = ParseCache()
        key = _key(HERE / "simple.hpp")
        cache.prefetch([key, key, key])
        assert cache.misses == 1

    def test_prefetch_skips_already_cached_keys(self) -> None:
        cache = ParseCache()
        key = _key(HERE / "simple.hpp")
        cache.get(key)
        cache.prefetch([key])
        assert cache.misses == 1

    def test_clang_errors_are_appended_once_on_the_miss_only(self) -> None:
        """A hit must not re-report errors, or --strict would count duplicates."""
        cache = ParseCache()
        key = _key(HERE / "broken.hpp", namespaces=())
        errors: list[str] = []
        cache.get(key, errors)
        after_miss = len(errors)
        assert after_miss > 0
        cache.get(key, errors)
        assert len(errors) == after_miss

    def test_verbose_stderr_is_replayed_once_on_the_miss_only(self, capsys) -> None:
        cache = ParseCache(verbose=True)
        key = _key(HERE / "simple.hpp")
        cache.get(key)
        assert capsys.readouterr().err.count("[parse]") == 2  # args line + IR-built line
        cache.get(key)
        assert "[parse]" not in capsys.readouterr().err


class TestParseCacheIsolation:
    """The cache hands out one shared IRModule; upgraded trees must not alias."""

    @pytest.fixture
    def two_modules(self):
        cache = ParseCache()
        key = _key(HERE / "simple.hpp")
        return upgrade_module(cache.get(key)), upgrade_module(cache.get(key))

    def test_upgrades_are_distinct_objects(self, two_modules) -> None:
        first, second = two_modules
        assert first is not second
        assert first.classes[0] is not second.classes[0]

    def test_emit_is_not_shared(self, two_modules) -> None:
        first, second = two_modules
        first.classes[0].emit = False
        assert second.classes[0].emit is True

    def test_properties_are_not_shared(self, two_modules) -> None:
        """The exact aliasing hazard that rules out caching a TIRModule."""
        from tsujikiri.ir import IRProperty

        first, second = two_modules
        first.classes[0].properties.append(IRProperty(name="p", getter="getId"))
        assert second.classes[0].properties == []

    def test_class_code_injections_are_not_shared(self, two_modules) -> None:
        from tsujikiri.ir import IRCodeInjection

        first, second = two_modules
        first.classes[0].code_injections.append(IRCodeInjection(position="beginning", code="// x"))
        assert second.classes[0].code_injections == []

    def test_module_code_injections_are_not_shared(self, two_modules) -> None:
        from tsujikiri.ir import IRCodeInjection

        first, second = two_modules
        first.code_injections.append(IRCodeInjection(position="beginning", code="// x"))
        assert second.code_injections == []

    def test_method_rename_is_not_shared(self, two_modules) -> None:
        first, second = two_modules
        first.classes[0].methods[0].rename = "renamed"
        assert second.classes[0].methods[0].rename is None

    def test_appending_a_function_is_not_shared(self, two_modules) -> None:
        """Guards the declared-functions injection against cross-target leakage."""
        first, second = two_modules
        before = len(second.functions)
        first.functions.append(first.functions[0])
        assert len(second.functions) == before
