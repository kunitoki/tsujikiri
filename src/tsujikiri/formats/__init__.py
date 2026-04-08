"""Built-in output format discovery and resolution.

Built-in formats live as ``*.output.yml`` files in this package directory.
Third-party formats are referenced by filesystem path.

Usage::

    from tsujikiri.formats import list_builtin_formats, resolve_format_path
    from tsujikiri.configurations import load_output_config

    path = resolve_format_path("luabridge3")          # built-in
    path = resolve_format_path("/path/to/my.output.yml")  # user-supplied
    config = load_output_config(path)
"""

from __future__ import annotations

from pathlib import Path
from typing import List

_FORMATS_DIR = Path(__file__).parent


def list_builtin_formats() -> List[str]:
    """Return names of all built-in output formats (without the ``.output.yml`` suffix)."""
    return sorted(
        p.name.replace(".output.yml", "")
        for p in _FORMATS_DIR.glob("*.output.yml")
    )


def resolve_format_path(name_or_path: str) -> Path:
    """Resolve a format specifier to a Path.

    If *name_or_path* matches a built-in format name (e.g. ``"luabridge3"``),
    the corresponding bundled YAML file is returned.
    Otherwise the value is treated as a filesystem path.

    Raises ``FileNotFoundError`` if neither matches.
    """
    # 1. Try built-in
    candidate = _FORMATS_DIR / f"{name_or_path}.output.yml"
    if candidate.exists():
        return candidate

    # 2. Treat as filesystem path
    fs_path = Path(name_or_path)
    if fs_path.exists():
        return fs_path

    available = ", ".join(list_builtin_formats())
    raise FileNotFoundError(
        f"Output format not found: '{name_or_path}'. "
        f"Built-in formats: {available}. "
        f"Or provide an absolute/relative path to a .output.yml file."
    )
