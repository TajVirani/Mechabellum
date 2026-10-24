"""Version index, de-duplication, abnormal-match filtering and distribution statistics for a replay folder.

It works the same for real and generated replays, so generated data can be checked before it is trained on.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..collector.locator import replay_files
from ..collector.replay import ReplayMatch, parse_replay


@dataclass(frozen=True)
class ReplayEntry:
    path: Path
    sha256: str
    battle_id: str | None
    version: int | None
    game_mode: str | None
    match_mode: str | None
    map_id: int | None
    player_count: int
    winner_index: int | None
    rounds: list[int]
    snapshot_rounds: list[int]


def abnormal_reasons(entry: ReplayEntry) -> list[str]:
    """Why a match should not be trained on; empty for a usable 1v1 match."""
    reasons = []
    if entry.player_count != 2 or entry.match_mode != "VS_1_1":
        reasons.append("not 1v1")
    if entry.game_mode == "AsyncBattle":
        reasons.append("AsyncBattle")
    if entry.winner_index is None:
        reasons.append("no winner")
    if len(entry.snapshot_rounds) < 2:
        reasons.append("fewer than 2 fight_over snapshots")
    if entry.rounds and entry.rounds != list(range(entry.rounds[0], entry.rounds[-1] + 1)):
        reasons.append("missing round records")
    return reasons


@dataclass
class DatasetStats:
    replay_files: int = 0
    parse_failures: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    abnormal: dict[str, list[str]] = field(default_factory=dict)
    usable: list[ReplayEntry] = field(default_factory=list)
    versions: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, object]:
        usable = self.usable
        rounds = Counter(max(entry.snapshot_rounds) for entry in usable)
        reasons = Counter(reason for values in self.abnormal.values() for reason in values)
        first_player_wins = sum(entry.winner_index == 0 for entry in usable)
        return {
            "replayFiles": self.replay_files,
            "parseFailures": self.parse_failures,
            "duplicates": len(self.duplicates),
            "abnormalMatches": len(self.abnormal),
            "abnormalReasons": dict(reasons.most_common()),
            "usableMatches": len(usable),
            "usableSnapshots": sum(len(entry.snapshot_rounds) for entry in usable),
            "versionIndex": dict(sorted(self.versions.items())),
            "lastSnapshotRound": dict(sorted(rounds.items())),
            "maps": dict(Counter(str(entry.map_id) for entry in usable).most_common()),
            # A balanced dataset sits near 0.5; far from it suggests a seat or labelling bias.
            "firstPlayerWinRate": first_player_wins / len(usable) if usable else None,
        }


def scan_replays(replay_directory: Path) -> DatasetStats:
    stats = DatasetStats()
    seen_hashes: set[str] = set()
    seen_battles: set[str] = set()
    for path in replay_files(replay_directory):
        name = path.relative_to(replay_directory).as_posix()
        stats.replay_files += 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        try:
            replay = parse_replay(path)
        except Exception as error:
            stats.parse_failures.append(f"{name}: {error}")
            continue
        entry = _entry(path, digest, replay)
        stats.versions[f"{entry.version}/{entry.game_mode}"] += 1
        # The same match can be saved twice (for example by both a player and a spectator).
        if digest in seen_hashes or (entry.battle_id is not None and entry.battle_id in seen_battles):
            stats.duplicates.append(name)
            continue
        seen_hashes.add(digest)
        if entry.battle_id is not None:
            seen_battles.add(entry.battle_id)
        reasons = abnormal_reasons(entry)
        if reasons:
            stats.abnormal[name] = reasons
        else:
            stats.usable.append(entry)
    return stats


def _entry(path: Path, digest: str, replay: ReplayMatch) -> ReplayEntry:
    return ReplayEntry(
        path=path,
        sha256=digest,
        battle_id=replay.battle_id,
        version=replay.version,
        game_mode=replay.game_mode,
        match_mode=replay.match_mode,
        map_id=replay.map_id,
        player_count=len(replay.players),
        winner_index=replay.winner_index,
        rounds=replay.common_rounds,
        snapshot_rounds=replay.snapshot_rounds,
    )
