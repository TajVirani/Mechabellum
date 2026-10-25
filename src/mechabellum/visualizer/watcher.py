"""Polls the replay folder (recursively) and turns new or changed replays into Match Summaries."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..collector.replay.result import result_path
from .cache import CachedSummary, SummaryCache
from .summaries import SkippedReplay, summarize_replay

POLL_SECONDS = 2.0
REPLAY_PATTERN = "*.grbr"
# During the start-up scan, newly parsed summaries go out at most this often (and once at the end).
INDEX_BATCH_SECONDS = 0.5

# on_indexed(rows, done, total, replace): the cached rows first (replace=True), then batches of newly parsed ones.
IndexCallback = Callable[[list[dict[str, Any]], int, int, bool], None]


def replay_paths(replay_dir: Path) -> list[Path]:
    """Every `*.grbr` (including `*.rep.grbr`) under the folder, version subfolders too, in a stable order."""
    return sorted(replay_dir.rglob(REPLAY_PATTERN), key=lambda path: path.relative_to(replay_dir).as_posix().casefold())


def replay_state(path: Path) -> tuple[int, int]:
    """(size, mtime) of a replay as the watcher and cache see it; raises OSError when the replay can't be read.

    A tournament replay's winner can arrive later in a result file beside it, and that counts as a change: the
    result file's size is added to the replay's and the newer of the two mtimes is used. The size matters when
    the result file keeps an older mtime than the replay, as a copy that preserves times (copy2, robocopy) does.
    """
    stat = path.stat()
    size, mtime_ns = stat.st_size, stat.st_mtime_ns
    try:
        result = result_path(path).stat()
    except OSError:
        return size, mtime_ns
    return size + result.st_size, max(mtime_ns, result.st_mtime_ns)


class ReplayWatcher:
    """Summarises the replays in `replay_dir`, through the cache.

    `scan_existing` reads what is there at start-up; `start` runs it on the watcher thread first (reporting to
    `on_indexed`) unless it already ran, so the server can serve while a cold cache is filled. After that, `poll`
    runs every ~2 s: a new or changed file is parsed once its size and mtime are unchanged over two polls, so a
    replay the game is still writing is left alone. Each new summary goes to `on_summary`. When a summary goes
    away (its replay was deleted, or now is skipped), the whole remaining set goes to `on_summaries` instead.
    """

    def __init__(
        self,
        replay_dir: Path,
        cache: SummaryCache,
        on_summary: Callable[[dict[str, Any]], None],
        *,
        on_summaries: Callable[[list[dict[str, Any]]], None] | None = None,
        on_indexed: IndexCallback | None = None,
        interval_seconds: float = POLL_SECONDS,
    ) -> None:
        self._dir = replay_dir
        self._cache = cache
        self._on_summary = on_summary
        self._on_summaries = on_summaries
        self._on_indexed = on_indexed
        # Set once the start-up scan has finished (or failed); polls only start after it.
        self.indexed = threading.Event()
        # The current summary of every known replay that makes one.
        self._summaries: dict[Path, dict[str, Any]] = {}
        self._interval = interval_seconds
        self._known: dict[Path, tuple[int, int]] = {}
        self._pending: dict[Path, tuple[int, int]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan_existing(self, on_indexed: IndexCallback | None = None) -> list[dict[str, Any]]:
        """Summaries of every replay present now, parsing only those the cache doesn't hold.

        With `on_indexed`, the cached summaries are reported first in one call, then the parsed ones in batches,
        each with the scan's progress (files done, files total). A stop request ends the scan early.
        """
        try:
            states = self._states()
            total = len(states)
            todo: list[tuple[Path, tuple[int, int]]] = []
            cached_rows = []
            for path, state in states.items():
                cached = self._cache.lookup(path, *state)
                if cached is None:
                    todo.append((path, state))
                    continue
                self._known[path] = state
                if cached.summary is not None:
                    self._summaries[path] = cached.summary
                    cached_rows.append(cached.summary)
            # The Local Player's own replays (directly in the folder) first, newest first: version subfolders can
            # hold thousands of fetched tournament replays that would otherwise keep the Stats view empty for minutes.
            todo.sort(key=lambda item: (item[0].parent != self._dir, -item[1][1]))
            done = total - len(todo)
            if on_indexed is not None:
                on_indexed(cached_rows, done, total, True)
            batch: list[dict[str, Any]] = []
            flushed = time.monotonic()
            for path, state in todo:
                if self._stop.is_set():
                    break
                summary = self._summarize(path, state)
                self._known[path] = state
                done += 1
                if summary is not None:
                    self._summaries[path] = summary
                    batch.append(summary)
                if on_indexed is not None and (done == total or time.monotonic() - flushed >= INDEX_BATCH_SECONDS):
                    on_indexed(batch, done, total, False)
                    batch, flushed = [], time.monotonic()
            return [self._summaries[path] for path in states if path in self._summaries]
        finally:
            self.indexed.set()

    def summaries(self) -> list[dict[str, Any]]:
        return list(self._summaries.values())

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
        removed = False
        for path in [path for path in self._known if path not in states]:
            del self._known[path]
            self._cache.forget(path)
            removed = self._summaries.pop(path, None) is not None or removed
        summaries = []
        for path in ready:
            state = self._pending.pop(path)
            self._known[path] = state
            summary = self._summarize(path, state)
            if summary is not None:
                self._summaries[path] = summary
                summaries.append(summary)
            else:
                removed = self._summaries.pop(path, None) is not None or removed
        if removed and self._on_summaries is not None:
            # Upserts can't express a removal, so resend the full set (it already holds this poll's new rows).
            self._on_summaries(self.summaries())
        else:
            for summary in summaries:
                self._on_summary(summary)
        return summaries

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="replay-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop polling; with a timeout, also wait (that long at most) for a poll in progress to finish."""
        self._stop.set()
        if timeout is not None and self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _run(self) -> None:
        if not self.indexed.is_set():
            try:
                self.scan_existing(self._on_indexed)
            except Exception as error:
                # Files the scan never reached are picked up by the polls, as if they were new.
                print(f"Visualizer: replay scan failed: {error!r}", file=sys.stderr, flush=True)
                if self._on_indexed is not None:
                    done = len(self._known)
                    self._on_indexed([], done, done, False)
        while not self._stop.wait(self._interval):
            try:
                self.poll()
            except Exception as error:
                # The folder can vanish or be locked briefly, or the cache can be busy; never let one bad poll end
                # the watcher. The next poll tries again.
                print(f"Visualizer: replay poll failed: {error!r}", file=sys.stderr, flush=True)

    def _states(self) -> dict[Path, tuple[int, int]]:
        states = {}
        for path in replay_paths(self._dir) if self._dir.is_dir() else []:
            try:
                states[path] = replay_state(path)
            except OSError:
                continue
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
