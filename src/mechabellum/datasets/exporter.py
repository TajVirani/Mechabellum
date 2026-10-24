from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..collector.replay import parse_replay, select_round
from ..contracts import MatchSnapshot
from .jsonl import write_snapshots


@dataclass(frozen=True)
class ExportSummary:
    replay_file_count: int
    match_count: int
    snapshot_count: int
    failure_count: int
    failures: tuple[str, ...]


def export_replay_directory(replay_directory: Path, output_path: Path) -> ExportSummary:
    if not replay_directory.is_dir():
        raise NotADirectoryError(f"Replay directory does not exist: {replay_directory}")
    paths = sorted(replay_directory.glob("*.grbr"), key=lambda path: path.name.casefold())
    snapshots: list[MatchSnapshot] = []
    matches = 0
    failures: list[str] = []
    seen_battles: set[str] = set()
    for path in paths:
        try:
            replay = parse_replay(path)
            if len(replay.players) != 2 or replay.match_mode != "VS_1_1" or replay.winner_index is None:
                continue
            # The same match can be saved more than once; keep the first file so it is not counted twice.
            if replay.battle_id is not None:
                if replay.battle_id in seen_battles:
                    continue
                seen_battles.add(replay.battle_id)
            matches += 1
            snapshots.extend(select_round(replay, round_number) for round_number in replay.snapshot_rounds)
        except Exception as error:
            failures.append(f"{path.name}: {error}")
    write_snapshots(output_path, snapshots)
    return ExportSummary(len(paths), matches, len(snapshots), len(failures), tuple(failures))
