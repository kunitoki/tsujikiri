from pathlib import Path

import clang.cindex as cindex

from tsujikiri.parser import _is_inline_namespace
from tsujikiri.configurations import SourceConfig
from tsujikiri.parser import parse_translation_unit

FIXTURE = Path(__file__).parent / "nested_namespaces.hpp"


def _parse_fixture() -> "cindex.TranslationUnit":
    idx = cindex.Index.create()
    return idx.parse(str(FIXTURE), args=["-x", "c++", "-std=c++20"])


def test_inline_namespace_detected() -> None:
    tu = _parse_fixture()
    outer = next(c for c in tu.cursor.get_children() if c.spelling == "outer")
    children = list(outer.get_children())
    v2 = next(c for c in children if c.spelling == "v2")
    assert _is_inline_namespace(v2) is True


def test_regular_namespace_not_inline() -> None:
    tu = _parse_fixture()
    outer = next(c for c in tu.cursor.get_children() if c.spelling == "outer")
    children = list(outer.get_children())
    inner = next(c for c in children if c.spelling == "inner")
    assert _is_inline_namespace(inner) is False


# --- scope traversal integration tests ---


def test_nested_namespace_filter() -> None:
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=["outer::inner"], module_name="test")
    names = [c.name for c in module.classes]
    assert "Deep" in names
    assert "Inlined" not in names
    assert "Direct" not in names
    assert "GlobalClass" not in names


def test_inline_namespace_transparent_under_parent() -> None:
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=["outer"], module_name="test")
    names = [c.name for c in module.classes]
    assert "Direct" in names
    assert "Inlined" in names  # inline namespace is transparent under outer
    assert "Deep" not in names  # non-inline nested not included without outer::inner


def test_global_scope_empty_filter() -> None:
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=[], module_name="test")
    names = [c.name for c in module.classes]
    fn_names = [f.name for f in module.functions]
    assert "GlobalClass" in names
    assert "global_func" in fn_names


def test_namespace_path_stored_fully_qualified() -> None:
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=["outer::inner"], module_name="test")
    deep = next(c for c in module.classes if c.name == "Deep")
    assert deep.namespace == "outer::inner"
    assert deep.qualified_name == "outer::inner::Deep"


def test_function_in_namespace_appends_namespace() -> None:
    """parser.py line 630: namespace added to module.namespaces for in-namespace free function."""
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=["outer::inner"], module_name="test")
    fn_names = [f.name for f in module.functions]
    assert "inner_func" in fn_names
    assert "outer::inner" in module.namespaces


def test_enum_in_namespace_appends_namespace() -> None:
    """parser.py line 637: namespace added to module.namespaces for in-namespace enum (no prior function)."""
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    # "enumonly" has only an enum and no functions, so line 637 is the first to add this namespace
    module = parse_translation_unit(source, namespaces=["enumonly"], module_name="test")
    enum_names = [e.name for e in module.enums]
    assert "Status" in enum_names
    assert "enumonly" in module.namespaces


def test_forward_declaration_not_collected() -> None:
    """parser.py line 644: forward declarations (not definitions) are skipped."""
    source = SourceConfig(path=str(FIXTURE), parse_args=["-std=c++20"])
    module = parse_translation_unit(source, namespaces=[], module_name="test")
    names = [c.name for c in module.classes]
    # ForwardDeclared is declared but not defined — must not appear in classes
    assert "ForwardDeclared" not in names
