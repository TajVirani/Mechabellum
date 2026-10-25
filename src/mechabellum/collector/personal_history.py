"""Label the player's own replays with results from the game's personal match history.

The game saves the player's own matches at the top level of the replay folder, and many of them do not record who
won. The match history (the profile's power record tab, `PersonalHistoryRequest` in the bridge protocol) does, but
its records carry no battle id. A record is matched to a replay by the players, the map and the time: the record's
`time` against the replay file's modification time, which the game sets when it saves the replay at the match's end.

What the record's `win` holds is not confirmed. Two readings are supported:

- "index": `win` is the winning player's index, compared with each player's `index`.
- "flag": `win` is nonzero when the record's own player (the one whose index equals the record's `index`) won.

For a two-player record the readings name the same winner when the record's own index is not 0, so those records
can be labeled either way. For the others the reading is chosen by calibration: matched replays whose own data says
who won (a surrender, or the last fight in formats since 2340) show which reading agrees.
"""

from __future__ import annotations

import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from .replay.result import result_path, write_result

WinReading = Literal["index", "flag"]
READINGS: tuple[WinReading, ...] = ("index", "flag")
DEFAULT_TOLERANCE_SECONDS = 45 * 60
DEFAULT_MIN_AGREEMENTS = 3
# Real user ids are large (281474976710829150); asynchronous battles name the recorded opponent 1, 2, ...
_REAL_USER_ID_MIN = 1 << 32
_KIND_NAMES = {1: "lobby", 2: "competition", 3: "level", 4: "course", 5: "chaos_faction"}


@dataclass(frozen=True)
class HistoryPlayer:
    user_id: int
    index: int
    name: str


@dataclass(frozen=True)
class HistoryRecord:
    """One match history record: the bridge's PersonalMatch."""

    time: int
    map_id: int
    kind: str
    win: int
    index: int
    players: tuple[HistoryPlayer, ...]
    reason_name: str = ""
    point: int = 0
    elo_point: int = 0

    @classmethod
    def from_proto(cls, match: Any) -> HistoryRecord:
        return cls(
            time=match.time,
            map_id=match.map_id,
            kind=_KIND_NAMES.get(match.kind, "unknown"),
            win=match.win,
            index=match.index,
            players=tuple(HistoryPlayer(player.user_id, player.index, player.name) for player in match.players),
            reason_name=match.reason_name,
            point=match.point,
            elo_point=match.elo_point,
        )

    @property
    def me(self) -> HistoryPlayer | None:
        mine = [player for player in self.players if player.index == self.index]
        return mine[0] if len(mine) == 1 else None

    @property
    def opponent(self) -> HistoryPlayer | None:
        """The other player of a two-player record."""
        me = self.me
        if me is None or len(self.players) != 2:
            return None
        return next(player for player in self.players if player is not me)

    @property
    def is_duel(self) -> bool:
        return self.kind in ("lobby", "competition") and self.opponent is not None

    def winner(self, reading: WinReading) -> HistoryPlayer | None:
        """The winner under one reading of `win`; None when the record does not name one under it."""
        if not self.is_duel:
            return None
        if reading == "index":
            named = [player for player in self.players if player.index == self.win]
            return named[0] if len(named) == 1 else None
        return self.me if self.win != 0 else self.opponent

    @property
    def readings_agree(self) -> bool:
        winner = self.winner("index")
        return winner is not None and winner == self.winner("flag")


@dataclass(frozen=True)
class ReplayInfo:
    path: Path
    # The file's modification time, Unix seconds.
    end_time: float
    map_id: int | None
    player_ids: tuple[str, ...]
    player_names: tuple[str, ...]
    # The winner's player id from the replay's own data, None when it does not say or a result file decided it.
    known_winner_id: str | None
    has_result: bool

    @classmethod
    def read(cls, path: Path) -> ReplayInfo:
        from .replay import parse_replay

        replay = parse_replay(path)
        has_result = result_path(path).is_file()
        winner = None
        if not has_result and replay.winner_index is not None:
            winner = replay.players[replay.winner_index].player_id
        return cls(
            path=path,
            end_time=path.stat().st_mtime,
            map_id=replay.map_id,
            player_ids=tuple(player.player_id or "" for player in replay.players),
            player_names=tuple(player.name for player in replay.players),
            known_winner_id=winner,
            has_result=has_result,
        )

    def seat_of(self, record: HistoryRecord) -> dict[int, int] | None:
        """Record player user id -> replay player position, when this replay is the record's two players."""
        me, opponent = record.me, record.opponent
        if me is None or opponent is None or len(self.player_ids) != 2:
            return None
        mine = [at for at, player_id in enumerate(self.player_ids) if player_id == str(me.user_id)]
        if len(mine) != 1:
            return None
        other = 1 - mine[0]
        other_id = self.player_ids[other]
        if _is_real_user_id(other_id):
            if other_id != str(opponent.user_id):
                return None
        elif self.player_names[other].casefold() != opponent.name.casefold():
            return None
        return {me.user_id: mine[0], opponent.user_id: other}


@dataclass(frozen=True)
class Pairing:
    record: HistoryRecord
    replay: ReplayInfo
    # Record user id -> replay player position.
    seats: dict[int, int]

    @property
    def offset_seconds(self) -> float:
        return self.record.time - self.replay.end_time

    def replay_winner_id(self, reading: WinReading) -> str | None:
        """The winner under `reading`, as the replay's own player id (asynchronous opponents have their own ids)."""
        winner = self.record.winner(reading)
        if winner is None:
            return None
        return self.replay.player_ids[self.seats[winner.user_id]]

    def replay_loser_id(self, winner_id: str) -> str:
        return next(player_id for player_id in self.replay.player_ids if player_id != winner_id)


@dataclass
class MatchReport:
    pairings: list[Pairing] = field(default_factory=list)
    # Duel records with no replay in the time window: usually matches older than the saved replays.
    unmatched: list[HistoryRecord] = field(default_factory=list)
    # Records with several candidate replays, or whose replay another record also claims.
    ambiguous: list[tuple[HistoryRecord, list[ReplayInfo]]] = field(default_factory=list)
    # Records that are not two-player lobby or tournament matches: team matches, levels, courses.
    not_duels: list[HistoryRecord] = field(default_factory=list)


def match_records(
    records: Iterable[HistoryRecord],
    replays: Sequence[ReplayInfo],
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> MatchReport:
    """Pair each two-player record with the one replay of the same players and map within `tolerance_seconds`."""
    report = MatchReport()
    candidates: list[tuple[HistoryRecord, list[tuple[ReplayInfo, dict[int, int]]]]] = []
    for record in records:
        if not record.is_duel:
            report.not_duels.append(record)
            continue
        found = []
        for replay in replays:
            if replay.map_id != record.map_id or abs(record.time - replay.end_time) > tolerance_seconds:
                continue
            seats = replay.seat_of(record)
            if seats is not None:
                found.append((replay, seats))
        candidates.append((record, found))
    claims: dict[Path, int] = {}
    for _, found in candidates:
        if len(found) == 1:
            claims[found[0][0].path] = claims.get(found[0][0].path, 0) + 1
    for record, found in candidates:
        if not found:
            report.unmatched.append(record)
        elif len(found) > 1 or claims[found[0][0].path] > 1:
            report.ambiguous.append((record, [replay for replay, _ in found]))
        else:
            replay, seats = found[0]
            report.pairings.append(Pairing(record, replay, seats))
    return report


@dataclass(frozen=True)
class Calibration:
    """How often each reading of `win` agrees with the winners matched replays record themselves."""

    agree: dict[str, int]
    disagree: dict[str, int]
    # Checked pairings where the two readings name different winners: only these tell the readings apart.
    informative: int

    def consistent(self) -> list[WinReading]:
        return [reading for reading in READINGS if self.disagree[reading] == 0]


def calibrate(pairings: Iterable[Pairing]) -> Calibration:
    agree = dict.fromkeys(READINGS, 0)
    disagree = dict.fromkeys(READINGS, 0)
    informative = 0
    for pairing in pairings:
        known = pairing.replay.known_winner_id
        if known is None:
            continue
        if not pairing.record.readings_agree:
            informative += 1
        for reading in READINGS:
            winner = pairing.replay_winner_id(reading)
            if winner is None:
                continue
            if winner == known:
                agree[reading] += 1
            else:
                disagree[reading] += 1
    return Calibration(agree, disagree, informative)


@dataclass(frozen=True)
class ReadingChoice:
    # The reading for records whose readings differ; None labels only the records where they agree.
    reading: WinReading | None
    # False when nothing may be written: the calibration contradicts every reading or has too little evidence.
    usable: bool
    reason: str


def choose_reading(
    calibration: Calibration, requested: WinReading | None, min_agreements: int = DEFAULT_MIN_AGREEMENTS
) -> ReadingChoice:
    if requested is not None:
        return ReadingChoice(requested, True, f"--win-means {requested}")
    consistent = calibration.consistent()
    if not consistent:
        return ReadingChoice(None, False, "the replays contradict both readings of win; check the records by hand")
    best = max(calibration.agree[reading] for reading in consistent)
    if best < min_agreements:
        return ReadingChoice(
            None, False, f"only {best} matched replays record their winner; at least {min_agreements} are needed"
        )
    if len(consistent) == 1:
        return ReadingChoice(consistent[0], True, f"calibrated: win is a {_describe(consistent[0])}")
    return ReadingChoice(
        None, True, "no calibration replay tells the readings apart; only records where they agree are labeled"
    )


def _describe(reading: WinReading) -> str:
    return "winning player index" if reading == "index" else "flag that the record's player won"


class HistoryBridge(Protocol):
    def personal_history(self) -> Any: ...


@dataclass
class LabelSummary:
    records: int = 0
    labeled: int = 0
    kept: int = 0
    undecided: int = 0
    choice: ReadingChoice | None = None
    calibration: Calibration | None = None
    report: MatchReport = field(default_factory=MatchReport)
    median_offset_seconds: float | None = None


def own_replays(replay_directory: Path) -> list[Path]:
    """The matches the game saved at the top level of the replay folder; downloads sit in version folders."""
    return sorted(replay_directory.glob("*.grbr"))


def label_own_replays(
    bridge: HistoryBridge,
    replay_directory: Path,
    win_means: WinReading | None = None,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    min_agreements: int = DEFAULT_MIN_AGREEMENTS,
    force: bool = False,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _: None,
) -> LabelSummary:
    """Fetch the match history and write a result file for each matched replay. Existing result files are kept
    unless `force`; `dry_run` writes nothing."""
    records = [HistoryRecord.from_proto(match) for match in bridge.personal_history().matches]
    replays = []
    for path in own_replays(replay_directory):
        try:
            replays.append(ReplayInfo.read(path))
        except Exception as error:
            log(f"unreadable  {path.name}: {error}")
    return label_with(records, replays, win_means, tolerance_seconds, min_agreements, force, dry_run, log)


def label_with(
    records: Sequence[HistoryRecord],
    replays: Sequence[ReplayInfo],
    win_means: WinReading | None = None,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    min_agreements: int = DEFAULT_MIN_AGREEMENTS,
    force: bool = False,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _: None,
) -> LabelSummary:
    summary = LabelSummary(records=len(records))
    report = summary.report = match_records(records, replays, tolerance_seconds)
    calibration = summary.calibration = calibrate(report.pairings)
    choice = summary.choice = choose_reading(calibration, win_means, min_agreements)
    if report.pairings:
        summary.median_offset_seconds = statistics.median(pairing.offset_seconds for pairing in report.pairings)
    for pairing in report.pairings:
        record, replay = pairing.record, pairing.replay
        line = f"{replay.path.name}  {_record_text(record)}  offset {pairing.offset_seconds / 60:+.1f} min"
        winner_id = None
        if choice.usable and record.readings_agree:
            winner_id = pairing.replay_winner_id("index")
        elif choice.usable and choice.reading is not None:
            winner_id = pairing.replay_winner_id(choice.reading)
        if winner_id is None:
            summary.undecided += 1
            log(f"undecided   {line}")
            continue
        if replay.has_result and not force:
            summary.kept += 1
            log(f"kept        {line}")
            continue
        if not dry_run:
            source = f"personal history {record.kind} {record.time}"
            write_result(replay.path, int(winner_id), int(pairing.replay_loser_id(winner_id)), source)
        summary.labeled += 1
        winner_name = replay.player_names[replay.player_ids.index(winner_id)]
        log(f"{'would label' if dry_run else 'labeled':<11} {line}  winner {winner_name}")
    for record in report.unmatched:
        log(f"unmatched   {_record_text(record)}")
    for record, candidates in report.ambiguous:
        names = ", ".join(replay.path.name for replay in candidates)
        log(f"ambiguous   {_record_text(record)}  candidates: {names}")
    for record in report.not_duels:
        log(f"not a duel  {_record_text(record)}")
    return summary


def _record_text(record: HistoryRecord) -> str:
    players = " vs ".join(f"{player.name}#{player.index}" for player in record.players)
    return (
        f"[{record.kind} t={record.time} map {record.map_id} win={record.win} index={record.index} "
        f"{record.reason_name or '-'} point {record.point:+d} elo {record.elo_point:+d}: {players}]"
    )


def _is_real_user_id(player_id: str) -> bool:
    return player_id.isdigit() and int(player_id) >= _REAL_USER_ID_MIN
