import io
import json
from datetime import UTC, datetime
from pathlib import Path

from mechabellum.collector.memory import ObserverStateError, record_live_snapshots
from mechabellum.contracts import MatchSnapshot, validate_snapshot

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(round_number: int, second: int) -> MatchSnapshot:
    data = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    data["source"] = {"type": "memory", "uri": "memory://Mechabellum/1", "capturedAtUtc": None}
    data["match"]["round"] = round_number
    snapshot = validate_snapshot(data)
    captured = datetime(2026, 10, 23, 12, 0, second, tzinfo=UTC)
    return snapshot.model_copy(update={"source": snapshot.source.model_copy(update={"captured_at_utc": captured})})


class ScriptedSource:
    def __init__(self, steps: list[MatchSnapshot | Exception]) -> None:
        self.steps = steps

    def read_snapshot(self) -> MatchSnapshot:
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_recorder_writes_distinct_snapshots_and_survives_read_errors() -> None:
    source = ScriptedSource(
        [
            _snapshot(3, 0),
            _snapshot(3, 1),  # Same state, later capture time: skipped.
            OSError("partial ReadProcessMemory"),
            ObserverStateError("No match is currently running."),
            ObserverStateError("No match is currently running."),
            _snapshot(4, 2),
        ]
    )
    output = io.StringIO()
    messages: list[str] = []
    stats = record_live_snapshots(
        source,
        output,
        interval_seconds=0,
        should_stop=lambda _: not source.steps,
        on_message=messages.append,
        sleep=lambda _: None,
    )
    lines = [validate_snapshot(json.loads(line)) for line in output.getvalue().splitlines()]
    assert [snapshot.match.round for snapshot in lines] == [3, 4]
    assert all(snapshot.source.captured_at_utc is not None for snapshot in lines)
    assert (stats.written, stats.skipped_unchanged, stats.read_errors) == (2, 1, 1)
    # Repeated messages are reported once.
    assert messages == ["Read failed, retrying: partial ReadProcessMemory", "No match is currently running."]
