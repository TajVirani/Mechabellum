import json
import os
import shutil
from pathlib import Path

import pytest

pytest.importorskip("google.protobuf")

from mechabellum.bridge import bridge_pb2 as pb  # noqa: E402
from mechabellum.collector.personal_history import (  # noqa: E402
    Calibration,
    HistoryPlayer,
    HistoryRecord,
    ReplayInfo,
    calibrate,
    choose_reading,
    label_own_replays,
    label_with,
    match_records,
)
from mechabellum.collector.replay import parse_replay  # noqa: E402
from mechabellum.collector.replay.result import read_winner_user_id, result_path  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "replays"
ME = 281474976710829150
RIVAL = 281474976711274040
OTHER = 281474976711259303
T0 = 1_792_800_000


def record(
    time: int = T0,
    map_id: int = 1001,
    win: int = 0,
    index: int = 0,
    opponent: int = RIVAL,
    opponent_name: str = "miro",
    kind: str = "lobby",
) -> HistoryRecord:
    return HistoryRecord(
        time=time,
        map_id=map_id,
        kind=kind,
        win=win,
        index=index,
        players=(HistoryPlayer(ME, index, "Sleep Deprived"), HistoryPlayer(opponent, 1 - index, opponent_name)),
    )


def replay(
    name: str = "a.grbr",
    end_time: float = T0,
    map_id: int = 1001,
    players: tuple[str, ...] = (str(ME), str(RIVAL)),
    names: tuple[str, ...] = ("Sleep Deprived", "miro"),
    known_winner: str | None = None,
    directory: Path = Path("."),
    has_result: bool = False,
) -> ReplayInfo:
    return ReplayInfo(directory / name, end_time, map_id, players, names, known_winner, has_result)


def test_winner_readings_differ_only_when_the_records_own_index_is_zero() -> None:
    mine_first_won_by_index = record(win=0, index=0)
    assert mine_first_won_by_index.winner("index").user_id == ME
    assert mine_first_won_by_index.winner("flag").user_id == RIVAL
    assert not mine_first_won_by_index.readings_agree

    for win in (0, 1):
        second = record(win=win, index=1)
        assert second.readings_agree
        assert second.winner("index") == second.winner("flag")
    assert record(win=1, index=1).winner("flag").user_id == ME
    assert record(win=0, index=1).winner("index").user_id == RIVAL


def test_lobby_and_competition_records_are_duels_but_team_and_level_records_are_not() -> None:
    assert record(kind="lobby").is_duel
    assert record(kind="competition").is_duel
    assert not record(kind="level").is_duel
    team = HistoryRecord(T0, 2001, "lobby", 0, 0, tuple(HistoryPlayer(ME + at, at, f"p{at}") for at in range(4)))
    assert not team.is_duel and team.winner("index") is None

    report = match_records([record(kind="level"), team], [replay()])
    assert len(report.not_duels) == 2 and not report.pairings


def test_matching_respects_the_time_tolerance_and_map() -> None:
    replays = [replay(end_time=T0 + 40 * 60)]
    assert len(match_records([record()], replays, tolerance_seconds=45 * 60).pairings) == 1
    assert len(match_records([record()], replays, tolerance_seconds=30 * 60).unmatched) == 1
    assert len(match_records([record(map_id=1011)], replays, tolerance_seconds=45 * 60).unmatched) == 1


def test_matching_needs_the_same_opponent() -> None:
    assert match_records([record(opponent=OTHER)], [replay()]).unmatched
    # Not a replay of the player at all.
    assert match_records([record()], [replay(players=(str(OTHER), str(RIVAL)))]).unmatched


def test_asynchronous_opponents_match_by_name_and_keep_the_replays_ids() -> None:
    async_replay = replay(players=(str(ME), "1"), names=("Sleep Deprived", "PianoCaT"))
    report = match_records([record(opponent_name="pianocat", win=0, index=1)], [async_replay])
    assert len(report.pairings) == 1
    assert report.pairings[0].replay_winner_id("index") == "1"
    assert match_records([record(opponent_name="juggmant")], [async_replay]).unmatched


def test_several_candidates_or_a_shared_replay_are_ambiguous() -> None:
    two = [replay("a.grbr", T0 - 10 * 60), replay("b.grbr", T0 + 10 * 60)]
    report = match_records([record()], two)
    assert len(report.ambiguous) == 1 and len(report.ambiguous[0][1]) == 2

    shared = match_records([record(time=T0), record(time=T0 + 5 * 60)], [replay()])
    assert len(shared.ambiguous) == 2 and not shared.pairings


def test_calibration_picks_the_reading_the_replays_agree_with() -> None:
    # Records whose own index is 0 tell the readings apart; the replays say who really won.
    pairs = match_records(
        [record(time=T0 + at * 3600, win=0, index=0) for at in range(3)],
        [replay(f"{at}.grbr", T0 + at * 3600, known_winner=str(ME)) for at in range(3)],
    ).pairings
    calibration = calibrate(pairs)
    assert calibration.agree == {"index": 3, "flag": 0}
    assert calibration.disagree == {"index": 0, "flag": 3}
    assert calibration.informative == 3
    assert choose_reading(calibration, None).reading == "index"

    flag_pairs = match_records(
        [record(time=T0 + at * 3600, win=1, index=0) for at in range(3)],
        [replay(f"{at}.grbr", T0 + at * 3600, known_winner=str(ME)) for at in range(3)],
    ).pairings
    assert choose_reading(calibrate(flag_pairs), None).reading == "flag"


def test_choose_reading_without_enough_or_with_contradicting_evidence() -> None:
    none = Calibration({"index": 0, "flag": 0}, {"index": 0, "flag": 0}, 0)
    assert not choose_reading(none, None).usable
    assert choose_reading(none, "flag").reading == "flag"
    agreeing_only = Calibration({"index": 5, "flag": 5}, {"index": 0, "flag": 0}, 0)
    choice = choose_reading(agreeing_only, None)
    assert choice.usable and choice.reading is None
    contradicted = Calibration({"index": 4, "flag": 4}, {"index": 1, "flag": 1}, 0)
    assert not choose_reading(contradicted, None).usable


def test_label_with_writes_results_and_keeps_existing_ones(tmp_path: Path) -> None:
    for name in ("cal0.grbr", "cal1.grbr", "cal2.grbr", "new.grbr", "kept.grbr", "split.grbr"):
        (tmp_path / name).write_bytes(b"")
    result_path(tmp_path / "kept.grbr").write_text(json.dumps({"winner_user_id": str(RIVAL)}), encoding="utf-8")
    calibration_records = [record(time=T0 + at * 3600, win=0, index=0) for at in range(3)]
    replays = [replay(f"cal{at}.grbr", T0 + at * 3600, known_winner=str(ME), directory=tmp_path) for at in range(3)]
    records = [
        *calibration_records,
        record(time=T0 + 10 * 3600, win=1, index=1),
        record(time=T0 + 11 * 3600, win=0, index=1),
        record(time=T0 + 12 * 3600, win=0, index=0),
    ]
    replays += [
        replay("new.grbr", T0 + 10 * 3600, directory=tmp_path),
        replay("kept.grbr", T0 + 11 * 3600, directory=tmp_path, has_result=True),
        replay("split.grbr", T0 + 12 * 3600, directory=tmp_path),
    ]

    dry = label_with(records, replays, dry_run=True)
    assert dry.labeled == 5 and not result_path(tmp_path / "new.grbr").exists()

    summary = label_with(records, replays)
    assert summary.choice is not None and summary.choice.reading == "index"
    assert (summary.labeled, summary.kept, summary.undecided) == (5, 1, 0)
    assert read_winner_user_id(tmp_path / "new.grbr") == str(ME)
    assert read_winner_user_id(tmp_path / "split.grbr") == str(ME)
    assert read_winner_user_id(tmp_path / "kept.grbr") == str(RIVAL)
    payload = json.loads(result_path(tmp_path / "new.grbr").read_text(encoding="utf-8"))
    assert payload["loser_user_id"] == str(RIVAL) and payload["source"].startswith("personal history lobby")

    forced = label_with(records, replays, force=True)
    assert forced.kept == 0 and read_winner_user_id(tmp_path / "kept.grbr") == str(RIVAL)
    assert json.loads(result_path(tmp_path / "kept.grbr").read_text(encoding="utf-8"))["source"].startswith(
        "personal history"
    )


def test_label_with_leaves_split_records_undecided_without_calibration(tmp_path: Path) -> None:
    replays = [replay(f"{at}.grbr", T0 + at * 3600, directory=tmp_path) for at in range(2)]
    records = [record(time=T0, win=0, index=0), record(time=T0 + 3600, win=0, index=1)]
    assert not label_with(records, replays).choice.usable
    summary = label_with(records, replays, win_means="flag")
    assert (summary.labeled, summary.undecided) == (2, 0)
    assert read_winner_user_id(tmp_path / "0.grbr") == str(RIVAL)


def test_record_from_proto() -> None:
    match = pb.PersonalMatch(
        time=T0,
        map_id=1031,
        kind=pb.PERSONAL_MATCH_KIND_COMPETITION,
        win=1,
        index=1,
        reason_name="GiveUp",
        elo_point=-12,
        players=[
            pb.PersonalMatchPlayer(user_id=ME, index=1, name="Sleep Deprived"),
            pb.PersonalMatchPlayer(user_id=RIVAL, index=0, name="miro"),
        ],
    )
    parsed = HistoryRecord.from_proto(match)
    assert parsed.kind == "competition" and parsed.me.user_id == ME and parsed.opponent.name == "miro"
    assert parsed.winner("index").user_id == ME and parsed.elo_point == -12


class FakeHistoryBridge:
    def __init__(self, matches: list) -> None:
        self.matches = matches

    def personal_history(self) -> pb.PersonalHistoryReply:
        return pb.PersonalHistoryReply(matches=self.matches)


def test_label_own_replays_reads_top_level_replays(tmp_path: Path) -> None:
    """The real 2340 win against Nix calibrates; the 2331 replay against miro gets its result from the history."""
    nix_source = FIXTURES / "2.0.0.5.2340" / "2340_20261024--67160210_[Nix]VS[Sleep Deprived].grbr"
    miro_source = FIXTURES / "2331_20261022--67509180_[Sleep Deprived]VS[miro].grbr"
    nix, miro = tmp_path / nix_source.name, tmp_path / miro_source.name
    shutil.copyfile(nix_source, nix)
    shutil.copyfile(miro_source, miro)
    (tmp_path / "2.0.0.5.2340").mkdir()
    shutil.copyfile(nix_source, tmp_path / "2.0.0.5.2340" / nix_source.name)
    os.utime(nix, (T0, T0))
    os.utime(miro, (T0 + 7200, T0 + 7200))
    nix_replay, miro_replay = parse_replay(nix), parse_replay(miro)
    assert nix_replay.players[nix_replay.winner_index].player_id == str(ME)
    assert miro_replay.winner_index is None

    def match(time: int, replay_match, win: int, index: int) -> pb.PersonalMatch:
        players = [
            pb.PersonalMatchPlayer(user_id=int(player.player_id), index=at, name=player.name)
            for at, player in enumerate(replay_match.players)
        ]
        return pb.PersonalMatch(
            time=time,
            map_id=replay_match.map_id,
            kind=pb.PERSONAL_MATCH_KIND_LOBBY,
            win=win,
            index=index,
            players=players,
        )

    my_seat_vs_miro = [player.player_id for player in miro_replay.players].index(str(ME))
    assert my_seat_vs_miro == 0
    my_seat_vs_nix = [player.player_id for player in nix_replay.players].index(str(ME))
    assert my_seat_vs_nix == 1
    bridge = FakeHistoryBridge(
        [match(T0 - 60, nix_replay, win=1, index=1), match(T0 + 7100, miro_replay, win=0, index=0)]
    )
    # The Nix record reads the same either way, so it confirms both readings and the miro record stays undecided.
    summary = label_own_replays(bridge, tmp_path, min_agreements=1)
    assert len(summary.report.pairings) == 2
    assert (summary.labeled, summary.undecided) == (1, 1)
    assert read_winner_user_id(nix) == str(ME)
    assert not result_path(miro).exists()

    summary = label_own_replays(bridge, tmp_path, win_means="index")
    assert (summary.labeled, summary.kept) == (1, 1)
    assert read_winner_user_id(miro) == str(ME)
    assert parse_replay(miro).winner_index == 0
    assert not result_path(tmp_path / "2.0.0.5.2340" / nix_source.name).exists()
