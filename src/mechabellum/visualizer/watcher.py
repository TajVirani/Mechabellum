"""Polls the replay folder (recursively) and turns new or changed replays into Match Summaries."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .cache import CachedSummary, SummaryCache
from .summaries import SkippedReplay, summarize_replay

POLL_SECONDS = 2.0
REPLAY_PATTERN = "*.grbr"


def replay_paths(replay_dir: Path) -> list[Path]:
    """Every `*.grbr` (including `*.rep.grbr`) under the folder, version subfolders too, in a stable order."""
    return sorted(replay_dir.rglob(REPLAY_PATTERN), key=lambda path: path.relative_to(replay_dir).as_posix().casefold())


class ReplayWatcher:
    """Summarises the replays in `replay_dir`, through the cache.

    `scan_existing` reads what is there at start-up. After that, `poll` runs every ~2 s: a new or changed file is
    parsed once its size and mtime are unchanged over two polls, so a replay the game is still writing is left
    alone. Each new summary goes to `on_summary`.
    """

    def __init__(
        self,
        replay_dir: Path,
        cache: SummaryCache,
        on_summary: Callable[[dict[str, Any]], None],
        *,
        interval_seconds: float = POLL_SECONDS,
    ) -> None:
        self._dir = replay_dir
        self._cache = cache
        self._on_summary = on_summary
        self._interval = interval_seconds
        self._known: dict[Path, tuple[int, int]] = {}
        self._pending: dict[Path, tuple[int, int]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan_existing(self) -> list[dict[str, Any]]:
        """Summaries of every replay present now, parsing only those the cache doesn't hold."""
        summaries = []
        for path, state in self._states().items():
            self._known[path] = state
            summary = self._summarize(path, state)
            if summary is not None:
                summaries.append(summary)
        return summaries

    def poll(self) -> list[dict[str, Any]]:
        """One poll: the summaries of files that became stable since the last one."""
        states = self._states()
        ready = []
        for path, state in states.items():
            if self._known.get(path) == state:
                self._pending.pop(path, None)
                continue
            if self._pending.get(path) == state:
                ready.append(path)
            else:
                self._pending[path] = state
        for path in list(self._pending):
            if path not in states:
                del self._pending[path]
        summaries = []
        for path in ready:
            state = self._pending.pop(path)
            self._known[path] = state
            summary = self._summarize(path, state)
            if summary is not None:
                summaries.append(summary)
                self._on_summary(summary)
        return summaries

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="replay-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except OSError:
                # The folder can vanish or be locked briefly; the next poll tries again.
                continue

    def _states(self) -> dict[Path, tuple[int, int]]:
        states = {}
        for path in replay_paths(self._dir) if self._dir.is_dir() else []:
            try:
                stat = path.stat()
            except OSError:
                continue
            states[path] = (stat.st_size, stat.st_mtime_ns)
        return states

    def _summarize(self, path: Path, state: tuple[int, int]) -> dict[str, Any] | None:
        size, mtime_ns = state
        cached = self._cache.lookup(path, size, mtime_ns)
        if cached is None:
            try:
                cached = CachedSummary(summarize_replay(path, self._dir), None)
            except SkippedReplay as reason:
                cached = CachedSummary(None, str(reason))
            except Exception as error:
                # Unreadable replays are recorded too, so they are only retried once the file changes.
                cached = CachedSummary(None, f"unreadable: {error}")
            self._cache.store(path, size, mtime_ns, cached)
        return cached.summary
