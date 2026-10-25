from __future__ import annotations

from pathlib import Path

import pytest

from mechabellum.visualizer.summaries import (
    SkippedReplay,
    battle_date,
    game_version,
    opening,
    specialist,
    summarize_replay,
)

REPLAYS = Path(__file__).parent / "fixtures" / "replays"
LOCAL_PLAYER = "281474976710829150"


def _local(summary: dict) -> dict:
    return next(player for player in summary["players"] if player["playerId"] == LOCAL_PLAYER)


def test_win_summary_from_fixture_replay() -> None:
    summary = summarize_replay(REPLAYS / "2331_20261022--67509180_[Sleep Deprived]VS[miro].grbr", REPLAYS)

    assert summary["battleId"] == "20261022--67509180"
    assert summary["date"] == "2026-10-22"
    assert summary["replayVersion"] == 2331
    assert summary["gameVersion"] == "2.0.0.4.2331"
    assert summary["gameMode"] == "Normal"
    assert summary["mapId"] == 1032
    assert summary["rounds"] == 5
    assert summary["winnerIndex"] == 0
    me = _local(summary)
    assert me["name"] == "Sleep Deprived"
    assert me["won"] is True
    assert (me["specialistId"], me["specialistName"]) == (10002, "Supply Specialist")
    assert (me["openingId"], me["openingName"], me["openingLead"]) == (9879, "3 Crawler + 2 Sledgehammer", "Crawler")
    # Format 2331 never records the last fight; the winner won it.
    assert me["fightResults"] == ["Win"] * 5
    assert summary["players"][1]["fightResults"] == ["Lose"] * 5
    assert me["finalHp"] == 3600
    assert len(me["fieldedUnitIds"]) == len(set(me["fieldedUnitIds"])) > 0
    assert [item["round"] for item in me["composition"]] == [1, 2, 3, 4]
    for item in me["composition"]:
        assert sum(item["roles"].values()) == pytest.approx(1.0)
        assert item["supply"] > 0 and item["bodies"] > 0


def test_loss_summary_from_fixture_replay() -> None:
    summary = summarize_replay(REPLAYS / "2331_20261023--67519030_[Mordekaiser]VS[Sleep Deprived].grbr", REPLAYS)

    me = _local(summary)
    assert me["won"] is False
    assert summary["winnerIndex"] == 0
    assert summary["players"][0]["won"] is True
    assert me["fightResults"][-1] == "Lose"


def test_version_folder_replay_takes_the_folder_game_version() -> None:
    path = REPLAYS / "2.0.0.5.2340" / "2340_20261024--67160210_[Nix]VS[Sleep Deprived].grbr"
    summary = summarize_replay(path, REPLAYS)

    assert summary["gameVersion"] == "2.0.0.5.2340"
    assert summary["replayVersion"] == 2340
    me = _local(summary)
    assert me["won"] is True
    # Format 2340 records every fight, including the last.
    assert me["fightResults"] == ["Win"] * 6
    assert summary["rounds"] == 6


def test_tournament_replay_without_winner_is_skipped() -> None:
    with pytest.raises(SkippedReplay):
        summarize_replay(REPLAYS / "2.0.0.4.2331" / "7699235027090934905.rep.grbr", REPLAYS)


def test_specialist_rules() -> None:
    # 10002 Supply Specialist is a specialist; 1305001 is equipment, not an officer at all.
    assert specialist([10002]) == (10002, "Supply Specialist")
    assert specialist([10010, 10002]) == (10010, "Quick Supply Specialist")
    assert specialist([10001, 20024]) == (20024, "Speed Specialist")
    # An officer that isn't a specialist ("Quick Cooldown") is not one.
    assert specialist([10001]) is None
    # Unknown ids (AsyncBattle) fall back to the first unknown id.
    assert specialist([20411]) == (20411, "Unknown specialist (20411)")
    assert specialist([]) is None
    assert specialist(None) is None


def test_opening_rules() -> None:
    assert opening(9879) == (9879, "3 Crawler + 2 Sledgehammer", "Crawler")
    assert opening(110) == (110, "Unknown opening (110)", None)
    assert opening(None) is None


def test_battle_date_and_game_version_fallbacks(tmp_path: Path) -> None:
    assert battle_date("20261015--134519702") == "2026-10-15"
    assert battle_date(None) is None
    top = tmp_path / "x.grbr"
    assert game_version(top, 2331, tmp_path) == "2.0.0.4.2331"
    assert game_version(top, 2340, tmp_path) == "2.0.0.5.2340"
    assert game_version(top, 9999, tmp_path) is None
    assert game_version(tmp_path / "2.0.0.6.2350" / "x.grbr", 2350, tmp_path) == "2.0.0.6.2350"
    assert game_version(tmp_path / "misc" / "x.grbr", None, tmp_path) is None


def test_boards_list_unit_and_technology_ids_per_fight_over_round() -> None:
    summary = summarize_replay(REPLAYS / "2331_20261022--67509180_[Sleep Deprived]VS[miro].grbr", REPLAYS)

    for player in summary["players"]:
        boards = player["boards"]
        assert [board["round"] for board in boards] == [item["round"] for item in player["composition"]]
        for board in boards:
            assert board["unitIds"] and len(board["unitIds"]) == len(set(board["unitIds"]))
            assert len(board["technologyIds"]) == len(set(board["technologyIds"]))
        fielded = {unit for board in boards for unit in board["unitIds"]}
        assert fielded <= set(player["fieldedUnitIds"])
    assert any(board["technologyIds"] for player in summary["players"] for board in player["boards"])
