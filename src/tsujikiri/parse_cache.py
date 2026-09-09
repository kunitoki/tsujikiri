"""Parse each distinct translation unit once per run.

``main()`` needs the same source parsed for the manifest pass and again for every
output target.  Parsing is by far the most expensive step, so results are cached
and, optionally, produced by a pool of worker processes.

Two invariants keep the cache safe and its output stable:

* **The cache holds pre-upgrade** :class:`~tsujikiri.ir.IRModule` **objects.**
  Consumers run :func:`~tsujikiri.tir.upgrade_module` themselves.  Caching a
  ``TIRModule`` and re-upgrading it would alias mutable state — ``upgrade_class``
  passes ``properties`` and ``code_injections`` straight through — so a transform
  applied for one target would leak into another.
* **Workers never write to stderr.**  :func:`parse_worker` captures it and returns
  the text; the cache replays it in submission order.  Serial and parallel runs
  therefore produce byte-identical output.
"""

from __future__ import annotations

import contextlib
import io
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from typing import Dict, List, Optional, Sequence

from tsujikiri.configurations import SourceConfig
from tsujikiri.ir import IRModule
from tsujikiri.parser import parse_translation_unit_ir


@dataclass(frozen=True)
class ParseKey:
    """Identity of one parse: equal keys yield an identical ``IRModule``.

    Every field is a ``str`` or ``tuple[str, ...]``, so the key pickles trivially
    and can be handed to a worker process.

    ``path`` is stored exactly as configured rather than resolved: the parser
    echoes it in ``--verbose`` output, and resolving would change that text.  Two
    different spellings of one file therefore parse twice — a missed cache hit,
    never a wrong result.
    """

    path: str
    parse_args: tuple[str, ...]
    include_paths: tuple[str, ...]
    system_include_paths: tuple[str, ...]
    defines: tuple[str, ...]
    namespaces: tuple[str, ...]
    module_name: str

    @classmethod
    def from_source(cls, source: SourceConfig, namespaces: Sequence[str], module_name: str) -> "ParseKey":
        """Build a key from an *effective* source config.

        Callers must pass ``InputConfig.effective_source(entry)`` so the global
        ``parse_args`` / ``include_paths`` / ``defines`` are already merged in.
        """
        return cls(
            path=source.path,
            parse_args=tuple(source.parse_args),
            include_paths=tuple(source.include_paths),
            system_include_paths=tuple(source.system_include_paths),
            defines=tuple(source.defines),
            namespaces=tuple(namespaces),
            module_name=module_name,
        )

    def to_source(self) -> SourceConfig:
        """Rebuild the ``SourceConfig`` this key was derived from."""
        return SourceConfig(
            path=self.path,
            parse_args=list(self.parse_args),
            include_paths=list(self.include_paths),
            system_include_paths=list(self.system_include_paths),
            defines=list(self.defines),
        )


@dataclass
class ParseResult:
    """One parse's output, including everything it would have written."""

    module: IRModule
    clang_errors: List[str] = field(default_factory=list)
    stderr_text: str = ""


def parse_worker(key: ParseKey, verbose: bool) -> ParseResult:
    """Parse one translation unit and return its result.

    Module-level and free of shared state so it can run in a spawned process.
    stderr is captured rather than written, letting the caller replay it in a
    deterministic order.
    """
    clang_errors: List[str] = []
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        module = parse_translation_unit_ir(
            key.to_source(),
            list(key.namespaces),
            key.module_name,
            verbose=verbose,
            clang_errors=clang_errors,
        )
    return ParseResult(module=module, clang_errors=clang_errors, stderr_text=buffer.getvalue())


class ParseCache:
    """Memoise :func:`parse_worker` results across targets and output groups.

    An instance is threaded through ``main()`` rather than kept in a module
    global, so tests never share state through it.
    """

    def __init__(self, verbose: bool = False, jobs: int = 1) -> None:
        self._results: Dict[ParseKey, ParseResult] = {}
        self._verbose = verbose
        self._jobs = jobs
        self.hits = 0
        self.misses = 0

    def get(self, key: ParseKey, clang_errors: Optional[List[str]] = None) -> IRModule:
        """Return the ``IRModule`` for *key*, parsing it if it is not cached."""
        result = self._results.get(key)
        if result is None:
            self.misses += 1
            self._store(key, parse_worker(key, self._verbose), clang_errors)
            return self._results[key].module
        self.hits += 1
        return result.module

    def prefetch(self, keys: Sequence[ParseKey], clang_errors: Optional[List[str]] = None) -> None:
        """Parse every not-yet-cached key, in parallel when ``jobs > 1``.

        Results are stored and replayed strictly in *keys* order regardless of
        the order workers finish, so ``--verbose`` output and ``--strict`` error
        order do not depend on ``--jobs``.
        """
        missing: List[ParseKey] = []
        for key in keys:
            if key not in self._results and key not in missing:
                missing.append(key)

        if self._jobs > 1 and len(missing) > 1:
            # An explicit spawn context: already the default on macOS and Windows,
            # and forcing it on Linux avoids fork() interacting with libclang's
            # threads while keeping behaviour identical across the CI matrix.
            with ProcessPoolExecutor(max_workers=self._jobs, mp_context=get_context("spawn")) as pool:
                futures = [pool.submit(parse_worker, key, self._verbose) for key in missing]
                for key, future in zip(missing, futures):
                    self.misses += 1
                    self._store(key, future.result(), clang_errors)
        else:
            for key in missing:
                self.misses += 1
                self._store(key, parse_worker(key, self._verbose), clang_errors)

    def _store(self, key: ParseKey, result: ParseResult, clang_errors: Optional[List[str]]) -> None:
        """Cache *result* and emit its diagnostics exactly once, on the miss."""
        self._results[key] = result
        if result.stderr_text:
            sys.stderr.write(result.stderr_text)
        if clang_errors is not None:
            clang_errors.extend(result.clang_errors)
