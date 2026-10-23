from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, TextIO

from ...contracts import MatchSnapshot, snapshot_to_json
from .live_source import ObserverStateError


class SnapshotSource(Protocol):
    def read_snapshot(self) -> MatchSnapshot: ...


@dataclass
class RecorderStats:
    written: int = 0
    skipped_unchanged: int = 0
    read_errors: int = 0
    last_error: str | None = None
    matches: set[str | None] = field(default_factory=set)
    # time.monotonic() of the last successful read; None until the first one.
    last_read_at: float | None = None


def record_live_snapshots(
    source: SnapshotSource,
    output: TextIO,
    *,
    interval_seconds: float,
    should_stop: Callable[[RecorderStats], bool] = lambda _: False,
    on_message: Callable[[str], None] = lambda _: None,
    sleep: Callable[[float], None] = time.sleep,
) -> RecorderStats:
    """Append every distinct live snapshot to `output` as one JSONL line, flushed immediately.

    A snapshot counts as unchanged when it differs from the previous one only in its capture time. Reads that
    fail while the game rebuilds its objects (between rounds, or as a match ends) are retried on the next poll.
    """
    stats = RecorderStats()
    previous: str | None = None
    previous_message: str | None = None
    while not should_stop(stats):
        try:
            snapshot = source.read_snapshot()
        except ObserverStateError as error:
            message = str(error)
        except (OSError, ValueError) as error:
            stats.read_errors += 1
            stats.last_error = message = f"Read failed, retrying: {error}"
        else:
            message = None
            stats.last_read_at = time.monotonic()
            stable = snapshot.model_copy(
                update={"source": snapshot.source.model_copy(update={"captured_at_utc": None})}
            )
            fingerprint = snapshot_to_json(stable)
            if fingerprint == previous:
                stats.skipped_unchanged += 1
            else:
                previous = fingerprint
                output.write(snapshot_to_json(snapshot))
                output.write("\n")
                output.flush()
                stats.written += 1
                stats.matches.add(snapshot.match.battle_id)
        if message is not None and message != previous_message:
            on_message(message)
        previous_message = message
        sleep(interval_seconds)
    return stats
