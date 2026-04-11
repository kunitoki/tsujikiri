"""Post-generation output pretty printers.

The registry maps a language name (as declared in a ``.output.yml`` file under
the ``language:`` key) to the CLI command used to pretty print the generated source.

Currently registered:
  - ``cpp`` → ``clang-format``
"""

from __future__ import annotations

import subprocess
from typing import Dict, List, Optional

_REGISTRY: Dict[str, str] = {
    "cpp": "clang-format",
}


def get_pretty_printer_command(language: str) -> Optional[str]:
    """Return the pretty printer executable for *language*, or ``None`` if unregistered."""
    return _REGISTRY.get(language)


def pretty(content: str, language: str, extra_args: Optional[List[str]] = None) -> str:
    """Pretty print *content* using the registered pretty printer for *language*.

    The pretty printer is invoked with ``-`` as the filename so it reads from
    stdin and writes to stdout — no temporary file is created.

    Returns *content* unchanged when no pretty printer is registered for *language*.

    Raises :class:`subprocess.CalledProcessError` if the pretty printer exits
    with a non-zero status, and :class:`FileNotFoundError` if the pretty printer
    binary is not found on ``PATH``.
    """
    cmd = get_pretty_printer_command(language)
    if cmd is None:
        return content

    argv = [cmd] + (extra_args or []) + ["-"]
    result = subprocess.run(argv, input=content, capture_output=True, text=True, check=True)
    return result.stdout
