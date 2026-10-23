from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ..contracts import MODEL_SNAPSHOT_PHASE, MatchSnapshot, snapshot_to_json, validate_snapshot


def load_snapshots(path: Path) -> list[MatchSnapshot]:
    snapshots: list[MatchSnapshot] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                snapshots.append(validate_snapshot(json.loads(line)))
            except Exception as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return snapshots


def load_training_snapshots(path: Path) -> list[MatchSnapshot]:
    return [
        snapshot
        for snapshot in load_snapshots(path)
        if len(snapshot.players) == 2
        and snapshot.match.match_mode == "VS_1_1"
        # AsyncBattle pits a player against a recorded opponent with a card shop instead of card offers.
        and snapshot.match.game_mode != "AsyncBattle"
        and snapshot.match.phase == MODEL_SNAPSHOT_PHASE
        and snapshot.outcome is not None
    ]


def write_snapshots(path: Path, snapshots: Iterable[MatchSnapshot]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for snapshot in snapshots:
            stream.write(snapshot_to_json(snapshot))
            stream.write("\n")
            count += 1
    return count
