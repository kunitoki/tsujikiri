"""Post-generation output formatters.

The registry maps a language name (as declared in a ``.output.yml`` file under
the ``language:`` key) to the CLI command used to format the generated source.

Currently registered:
  - ``cpp`` → ``clang-format``
"""

from __future__ import annotations

import subprocess
from typing import Dict, List, Optional

_REGISTRY: Dict[str, str] = {
    "cpp": "clang-format",
}


def get_formatter_command(language: str) -> Optional[str]:
    """Return the formatter executable for *language*, or ``None`` if unregistered."""
    return _REGISTRY.get(language)


def format_content(content: str, language: str, extra_args: Optional[List[str]] = None) -> str:
    """Format *content* using the registered formatter for *language*.

    The formatter is invoked with ``-`` as the filename so it reads from stdin
    and writes to stdout — no temporary file is created.

    Returns *content* unchanged when no formatter is registered for *language*.

    Raises :class:`subprocess.CalledProcessError` if the formatter exits with a
    non-zero status, and :class:`FileNotFoundError` if the formatter binary is
    not found on ``PATH``.
    """
    cmd = get_formatter_command(language)
    if cmd is None:
        return content

    argv = [cmd] + (extra_args or []) + ["-"]
    result = subprocess.run(argv, input=content, capture_output=True, text=True, check=True)
    return result.stdout
