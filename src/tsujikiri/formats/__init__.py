"""Built-in output format discovery and resolution.

Built-in formats live as ``*.output.yml`` files in this package directory.
Third-party formats are referenced by filesystem path or a name matched in
user-supplied extra directories.

Usage::

    from tsujikiri.formats import list_builtin_formats, resolve_format_path, apply_format_inheritance
    from tsujikiri.configurations import load_output_config

    path = resolve_format_path("luabridge3")                      # built-in
    path = resolve_format_path("myfmt", extra_dirs=[Path("/d")])  # extra dir
    path = resolve_format_path("/path/to/my.output.yml")          # file path
    config = load_output_config(path)
    config = apply_format_inheritance(config, extra_dirs=[Path("/d")])
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set

if TYPE_CHECKING:
    from tsujikiri.configurations import OutputConfig

_FORMATS_DIR = Path(__file__).parent


def list_builtin_formats(extra_dirs: Optional[List[Path]] = None) -> List[str]:
    """Return names of all discoverable output formats (without the ``.output.yml`` suffix).

    Searches the built-in package directory first, then any *extra_dirs*.
    """
    dirs = [_FORMATS_DIR] + (list(extra_dirs) if extra_dirs else [])
    return sorted(
        p.name.replace(".output.yml", "")
        for d in dirs
        for p in d.glob("*.output.yml")
    )


def resolve_format_path(name_or_path: str, extra_dirs: Optional[List[Path]] = None) -> Path:
    """Resolve a format specifier to a Path.

    Resolution order:
    1. Built-in formats bundled with the package.
    2. Extra directories supplied by the caller (searched in order).
    3. Treat *name_or_path* as a direct filesystem path.

    Raises ``FileNotFoundError`` if none of the above match.
    """
    # 1. Try built-in
    candidate = _FORMATS_DIR / f"{name_or_path}.output.yml"
    if candidate.exists():
        return candidate

    # 2. Try extra directories
    for d in (extra_dirs or []):
        candidate = d / f"{name_or_path}.output.yml"
        if candidate.exists():
            return candidate

    # 3. Treat as filesystem path
    fs_path = Path(name_or_path)
    if fs_path.exists():
        return fs_path

    available = ", ".join(list_builtin_formats(extra_dirs))
    raise FileNotFoundError(
        f"Output format not found: '{name_or_path}'. "
        f"Built-in formats: {available}. "
        f"Or provide an absolute/relative path to a .output.yml file."
    )


def apply_format_inheritance(
    config: "OutputConfig",
    extra_dirs: Optional[List[Path]] = None,
    _seen: Optional[Set[str]] = None,
) -> "OutputConfig":
    """Merge base format properties into *config* when ``extends`` is set.

    Merging rules (child wins on collision):
    - ``type_mappings``: base entries fill gaps not present in child.
    - ``operator_mappings``: same.
    - ``unsupported_types``: union; child entries come first, duplicates removed.
    - ``language``: inherited from base when child's value is empty.
    - ``template``: child's template is kept unchanged (should contain ``{% extends %}``.

    Inheritance is resolved recursively so a chain A → B → C works correctly.
    Cycles are detected and raise ``ValueError``.
    """
    if not config.extends:
        return config

    from tsujikiri.configurations import load_output_config

    seen: Set[str] = _seen or set()
    if config.format_name in seen:
        raise ValueError(
            f"Circular format inheritance detected: '{config.format_name}' is part of a cycle."
        )
    seen = seen | {config.format_name}

    base_path = resolve_format_path(config.extends, extra_dirs=extra_dirs)
    base = load_output_config(base_path)
    base = apply_format_inheritance(base, extra_dirs=extra_dirs, _seen=seen)

    merged_type_mappings = {**base.type_mappings, **config.type_mappings}
    merged_operator_mappings = {**base.operator_mappings, **config.operator_mappings}

    seen_types: Set[str] = set()
    merged_unsupported: List[str] = []
    for t in config.unsupported_types + base.unsupported_types:
        if t not in seen_types:
            seen_types.add(t)
            merged_unsupported.append(t)

    config.type_mappings = merged_type_mappings
    config.operator_mappings = merged_operator_mappings
    config.unsupported_types = merged_unsupported
    if not config.language:
        config.language = base.language

    return config
