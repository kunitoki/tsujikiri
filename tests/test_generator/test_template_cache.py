"""Tests for TemplateCache — per-run sharing of format templates and compiled bytecode."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable, List, Optional

import jinja2
import pytest

import tsujikiri.generator as generator_mod
from tsujikiri.configurations import OutputConfig
from tsujikiri.generator import Generator, ItemFirstEnvironment, TemplateCache
from tsujikiri.tir import TIRModule


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


def _render(cfg: OutputConfig, module: TIRModule, cache: Optional[TemplateCache] = None, **kwargs: Any) -> str:
    buf = io.StringIO()
    Generator(cfg, template_cache=cache, **kwargs).generate(module, buf)
    return buf.getvalue()


class TestSharedCompilation:
    def test_second_generator_compiles_nothing(
        self, make_ir_module: Callable[..., TIRModule], luabridge3_output_config: OutputConfig, compiled: List[str]
    ) -> None:
        cache = TemplateCache()
        first = _render(luabridge3_output_config, make_ir_module(), cache)
        assert compiled == ["main.tpl"]
        second = _render(luabridge3_output_config, make_ir_module(), cache)
        assert compiled == ["main.tpl"]
        assert first == second

    def test_without_shared_cache_every_generator_compiles(
        self, make_ir_module: Callable[..., TIRModule], luabridge3_output_config: OutputConfig, compiled: List[str]
    ) -> None:
        _render(luabridge3_output_config, make_ir_module())
        _render(luabridge3_output_config, make_ir_module())
        assert compiled == ["main.tpl", "main.tpl"]

    def test_default_cache_is_per_generator(self, luabridge3_output_config: OutputConfig) -> None:
        a = Generator(luabridge3_output_config)
        b = Generator(luabridge3_output_config)
        assert isinstance(a.template_cache, TemplateCache)
        assert a.template_cache is not b.template_cache

    def test_explicit_cache_is_kept(self, luabridge3_output_config: OutputConfig) -> None:
        cache = TemplateCache()
        assert Generator(luabridge3_output_config, template_cache=cache).template_cache is cache


class TestNoCrossContamination:
    def test_two_formats_sharing_main_tpl_stay_correct(
        self,
        make_ir_module: Callable[..., TIRModule],
        luabridge3_output_config: OutputConfig,
        pybind11_output_config: OutputConfig,
        luals_output_config: OutputConfig,
        compiled: List[str],
    ) -> None:
        """``main.tpl`` has a different source per format: each must compile once and never leak."""
        expected = {
            "lb": _render(luabridge3_output_config, make_ir_module()),
            "py": _render(pybind11_output_config, make_ir_module()),
            "ls": _render(luals_output_config, make_ir_module()),
        }
        compiled.clear()

        cache = TemplateCache()
        for _ in range(2):
            assert _render(luabridge3_output_config, make_ir_module(), cache) == expected["lb"]
            assert _render(pybind11_output_config, make_ir_module(), cache) == expected["py"]
            assert _render(luals_output_config, make_ir_module(), cache) == expected["ls"]
        assert compiled == ["main.tpl", "main.tpl", "main.tpl"]

    def test_override_per_group_renders_its_own_source(
        self, make_ir_module: Callable[..., TIRModule], luabridge3_output_config: OutputConfig, compiled: List[str]
    ) -> None:
        """Different ``template_extends`` per group share the name ``__override__.tpl``."""
        cache = TemplateCache()
        a = '{% extends "luabridge3.tpl" %}{% block prologue %}// GROUP A\n{% endblock %}'
        b = '{% extends "luabridge3.tpl" %}{% block prologue %}// GROUP B\n{% endblock %}'

        out_a = _render(luabridge3_output_config, make_ir_module(), cache, template_extends=a)
        out_b = _render(luabridge3_output_config, make_ir_module(), cache, template_extends=b)
        again_a = _render(luabridge3_output_config, make_ir_module(), cache, template_extends=a)

        assert "// GROUP A" in out_a and "// GROUP B" not in out_a
        assert "// GROUP B" in out_b and "// GROUP A" not in out_b
        assert again_a == out_a
        # The parent is compiled once; each distinct override source once.
        assert sorted(n for n in compiled if n is not None) == [
            "__override__.tpl",
            "__override__.tpl",
            "luabridge3.tpl",
        ]

    def test_override_and_plain_render_share_parent(
        self, make_ir_module: Callable[..., TIRModule], luabridge3_output_config: OutputConfig, compiled: List[str]
    ) -> None:
        cache = TemplateCache()
        override = '{% extends "luabridge3.tpl" %}{% block prologue %}// OV\n{% endblock %}'
        plain = _render(luabridge3_output_config, make_ir_module(), cache)
        overridden = _render(luabridge3_output_config, make_ir_module(), cache, template_extends=override)
        assert "// OV" not in plain
        assert "// OV" in overridden
        assert plain == _render(luabridge3_output_config, make_ir_module())

    @pytest.mark.parametrize("fmt", ["luabridge3", "pybind11", "luals"])
    def test_output_matches_with_and_without_shared_cache(
        self, make_ir_module: Callable[..., TIRModule], fmt: str, request: pytest.FixtureRequest
    ) -> None:
        cfg = request.getfixturevalue(f"{fmt}_output_config")
        cache = TemplateCache()
        fresh = _render(cfg, make_ir_module())
        assert _render(cfg, make_ir_module(), cache) == fresh
        assert _render(cfg, make_ir_module(), cache) == fresh


class TestFormatTemplates:
    def test_contains_builtin_formats(self) -> None:
        table = TemplateCache().format_templates([])
        assert "luabridge3.tpl" in table
        assert "pybind11.tpl" in table
        assert "main.tpl" not in table

    def test_returns_independent_copies(self) -> None:
        cache = TemplateCache()
        first = cache.format_templates([])
        first["main.tpl"] = "mutated"
        first["luabridge3.tpl"] = "mutated"
        second = cache.format_templates([])
        assert "main.tpl" not in second
        assert second["luabridge3.tpl"] != "mutated"
        assert first is not second

    def test_loads_format_files_once_per_extra_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        loaded: List[Path] = []
        original = generator_mod.load_output_config

        def _spy(path: Path) -> OutputConfig:
            loaded.append(path)
            return original(path)

        monkeypatch.setattr(generator_mod, "load_output_config", _spy)
        (tmp_path / "custom.output.yml").write_text("format_name: custom\ntemplate: 'X'\n", encoding="utf-8")

        cache = TemplateCache()
        cache.format_templates([])
        builtin_loads = len(loaded)
        assert builtin_loads > 0
        cache.format_templates([])
        assert len(loaded) == builtin_loads

        cache.format_templates([tmp_path])
        assert len(loaded) == 2 * builtin_loads + 1
        assert cache.format_templates([tmp_path])["custom.tpl"] == "X"
        assert len(loaded) == 2 * builtin_loads + 1

    def test_extra_dirs_are_keyed_separately(self, tmp_path: Path) -> None:
        (tmp_path / "custom.output.yml").write_text("format_name: custom\ntemplate: 'X'\n", encoding="utf-8")
        cache = TemplateCache()
        assert "custom.tpl" not in cache.format_templates([])
        assert cache.format_templates([tmp_path])["custom.tpl"] == "X"
        assert "custom.tpl" not in cache.format_templates([])

    def test_extends_only_format_gets_passthrough(self, tmp_path: Path) -> None:
        (tmp_path / "pt.output.yml").write_text("format_name: pt\nextends: luabridge3\n", encoding="utf-8")
        table = TemplateCache().format_templates([tmp_path])
        assert table["pt.tpl"] == '{% extends "luabridge3.tpl" %}'

    def test_builtin_wins_over_extra_dir_collision(self, tmp_path: Path) -> None:
        (tmp_path / "luabridge3.output.yml").write_text(
            "format_name: luabridge3\ntemplate: '// IMPOSTOR'\n", encoding="utf-8"
        )
        assert TemplateCache().format_templates([tmp_path])["luabridge3.tpl"] != "// IMPOSTOR"

    def test_first_extra_dir_wins(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a", tmp_path / "b"
        first.mkdir()
        second.mkdir()
        (first / "c.output.yml").write_text("format_name: c\ntemplate: 'FIRST'\n", encoding="utf-8")
        (second / "c.output.yml").write_text("format_name: c\ntemplate: 'SECOND'\n", encoding="utf-8")
        assert TemplateCache().format_templates([first, second])["c.tpl"] == "FIRST"

    def test_skips_formats_without_template_or_extends(self, tmp_path: Path) -> None:
        (tmp_path / "empty.output.yml").write_text("format_name: empty\n", encoding="utf-8")
        assert "empty.tpl" not in TemplateCache().format_templates([tmp_path])

    def test_skips_malformed_format_files(self, tmp_path: Path) -> None:
        (tmp_path / "bad.output.yml").write_text("{ invalid yaml: [", encoding="utf-8")
        (tmp_path / "good.output.yml").write_text("format_name: good\ntemplate: 'G'\n", encoding="utf-8")
        assert TemplateCache().format_templates([tmp_path])["good.tpl"] == "G"

    def test_malformed_builtin_is_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "broken.output.yml").write_text("{ invalid yaml: [", encoding="utf-8")
        (tmp_path / "ok.output.yml").write_text("format_name: ok\ntemplate: 'OK'\n", encoding="utf-8")
        monkeypatch.setattr(generator_mod, "_FORMATS_DIR", tmp_path)
        assert TemplateCache().format_templates([]) == {"ok.tpl": "OK"}

    def test_extends_only_extra_dir_format_renders_through_shared_cache(
        self, make_ir_module: Callable[..., TIRModule], tmp_path: Path
    ) -> None:
        (tmp_path / "passthrough.output.yml").write_text(
            "format_name: passthrough\nextends: luabridge3\n", encoding="utf-8"
        )
        override = '{% extends "passthrough.tpl" %}{% block prologue %}// PT\n{% endblock %}'
        cfg = OutputConfig(format_name="passthrough", template="")
        cache = TemplateCache()
        for _ in range(2):
            out = _render(cfg, make_ir_module(), cache, extra_dirs=[tmp_path], template_extends=override)
            assert "// PT" in out


class TestBytecodeCache:
    def _env(self, cache: TemplateCache) -> ItemFirstEnvironment:
        return ItemFirstEnvironment(bytecode_cache=cache.bytecode_cache)

    def test_key_depends_on_name_and_source(self) -> None:
        cache = TemplateCache()
        env = self._env(cache)
        bcc = cache.bytecode_cache
        main = bcc.get_bucket(env, "main.tpl", None, "same")
        alias = bcc.get_bucket(env, "luabridge3.tpl", None, "same")
        other = bcc.get_bucket(env, "main.tpl", None, "different")
        assert len({main.key, alias.key, other.key}) == 3

    def test_key_is_stable_across_environments(self) -> None:
        cache = TemplateCache()
        bcc = cache.bytecode_cache
        a = bcc.get_bucket(self._env(cache), "main.tpl", None, "src")
        b = bcc.get_bucket(self._env(cache), "main.tpl", None, "src")
        assert a.key == b.key

    def test_miss_then_hit(self) -> None:
        cache = TemplateCache()
        bcc = cache.bytecode_cache
        env = self._env(cache)
        bucket = bcc.get_bucket(env, "t.tpl", None, "hello")
        assert bucket.code is None
        bucket.code = env.compile("hello", "t.tpl")
        bcc.set_bucket(bucket)
        hit = bcc.get_bucket(self._env(cache), "t.tpl", None, "hello")
        assert hit.code is bucket.code

    def test_caches_are_independent(self) -> None:
        a, b = TemplateCache(), TemplateCache()
        env = self._env(a)
        bucket = a.bytecode_cache.get_bucket(env, "t.tpl", None, "hello")
        bucket.code = env.compile("hello", "t.tpl")
        a.bytecode_cache.set_bucket(bucket)
        assert b.bytecode_cache.get_bucket(self._env(b), "t.tpl", None, "hello").code is None


class TestPerGeneratorFilters:
    """Compiled code is shared, but ``map_type`` is bound per Generator."""

    def test_constant_map_type_is_not_folded_into_shared_code(self, make_ir_module: Callable[..., TIRModule]) -> None:
        template = '{{ "X" | map_type }}|{% set t = "X" | map_type %}{{ t }}'
        first = OutputConfig(format_name="fa", template=template, type_mappings={"X": "A"})
        second = OutputConfig(format_name="fb", template=template, type_mappings={"X": "B"})
        cache = TemplateCache()
        assert _render(first, make_ir_module(), cache) == "A|A"
        assert _render(second, make_ir_module(), cache) == "B|B"
        assert _render(first, make_ir_module(), cache) == "A|A"

    def test_shared_parent_uses_each_generators_mappings(
        self, make_ir_module: Callable[..., TIRModule], tmp_path: Path
    ) -> None:
        (tmp_path / "base.output.yml").write_text(
            "format_name: base\ntemplate: '{% block b %}{{ \"X\" | map_type }}{% endblock %}'\n", encoding="utf-8"
        )
        child = '{% extends "base.tpl" %}'
        cache = TemplateCache()
        a = OutputConfig(format_name="ca", template=child, type_mappings={"X": "A"})
        b = OutputConfig(format_name="cb", template=child, type_mappings={"X": "B"})
        assert _render(a, make_ir_module(), cache, extra_dirs=[tmp_path]) == "A"
        assert _render(b, make_ir_module(), cache, extra_dirs=[tmp_path]) == "B"
