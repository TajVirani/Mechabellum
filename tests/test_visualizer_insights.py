from __future__ import annotations

import pytest

from mechabellum.collector.unit_catalog import UNIT_TECHNOLOGIES
from mechabellum.visualizer.hub import Hub
from mechabellum.visualizer.insights import (
    ALL_BANDS,
    Insights,
    SummaryFilter,
    counter_table,
    observations,
    round_band,
    wilson_interval,
    winning_boards,
)

HOUND, MARKSMAN, MUSTANG, CRAWLER = 28, 2, 7, 10
TECH = UNIT_TECHNOLOGIES[HOUND][0]


def board(round_number: int, units: list[int], technologies: list[int] | None = None) -> dict:
    return {"round": round_number, "unitIds": units, "technologyIds": technologies or []}


def summary(battle: str, winner: int, boards: list[list[dict]], mode: str = "Normal", **extra) -> dict:
    return {
        "battleId": battle,
        "replayPath": f"{battle}.grbr",
        "gameMode": mode,
        "date": "2026-10-20",
        "gameVersion": "2.0.0.5.2340",
        "players": [
            {"playerId": f"p{index}", "won": index == winner, "boards": player_boards}
            for index, player_boards in enumerate(boards)
        ],
        **extra,
    }


def by_unit(rows: list[dict], key: str = "unitId") -> dict[int, dict]:
    return {row[key]: row for row in rows}


def test_round_bands() -> None:
    assert [round_band(r) for r in (1, 3, 4, 7, 8, 12)] == ["early", "early", "mid", "mid", "late", "late"]


def test_wilson_interval() -> None:
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(8, 10)
    # Reference values for 8/10 at 95%.
    assert (low, high) == (pytest.approx(0.4902, abs=1e-4), pytest.approx(0.9433, abs=1e-4))
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == pytest.approx(1.0)
    narrow = wilson_interval(800, 1000)
    assert narrow[1] - narrow[0] < high - low


def test_each_match_and_player_counts_once_per_band() -> None:
    # Player 0 keeps Hound for all three early rounds: one early observation, not three.
    rows = [
        summary(
            "b1",
            0,
            [
                [board(1, [HOUND]), board(2, [HOUND]), board(3, [HOUND, MARKSMAN]), board(4, [MUSTANG])],
                [board(1, [CRAWLER]), board(2, [CRAWLER]), board(3, [CRAWLER]), board(4, [CRAWLER])],
            ],
        )
    ]
    early = observations(rows, "early")
    assert len(early) == 2
    mine = next(item for item in early if item.player_id == "p0")
    assert mine.units == {HOUND, MARKSMAN} and mine.opponent_units == {CRAWLER} and mine.won
    assert len(observations(rows, "mid")) == 2
    assert observations(rows, "late") == []
    # A repeated battle id (the same match saved twice) is counted once.
    assert len(observations(rows + rows, "early")) == 2
    assert [item.player_id for item in observations(rows, "early", player_id="p1")] == ["p1"]


def test_pick_rate_win_rate_and_lift() -> None:
    # Four matches; Hound appears for the winner in 3 and the loser in 1.
    rows = [
        summary("b1", 0, [[board(1, [HOUND], [TECH])], [board(1, [MARKSMAN])]]),
        summary("b2", 0, [[board(2, [HOUND])], [board(2, [MARKSMAN])]]),
        summary("b3", 1, [[board(1, [MARKSMAN])], [board(1, [HOUND, MARKSMAN])]]),
        summary("b4", 1, [[board(1, [HOUND])], [board(1, [MUSTANG])]]),
    ]
    table = winning_boards(observations(rows, "early"), min_sample=3)
    assert (table["n"], table["wins"], table["baselineWinRate"]) == (8, 4, 0.5)
    units = by_unit(table["units"])
    fang = units[HOUND]
    assert (fang["n"], fang["wins"]) == (4, 3)
    assert fang["pickRate"] == pytest.approx(4 / 8)
    assert fang["winRate"] == pytest.approx(0.75)
    assert fang["lift"] == pytest.approx(0.25)
    assert fang["interval"] == pytest.approx(list(wilson_interval(3, 4)))
    crawler = units[MARKSMAN]
    assert (crawler["n"], crawler["wins"], crawler["lift"]) == (4, 1, pytest.approx(-0.25))
    # Mustang has one observation: below the minimum sample, so it is thin and sorted last.
    assert units[MUSTANG]["thin"] is True and not fang["thin"]
    assert [row["unitId"] for row in table["units"]] == [HOUND, MARKSMAN, MUSTANG]
    technology = by_unit(table["technologies"], "technologyId")[TECH]
    assert (technology["unitId"], technology["n"], technology["wins"], technology["thin"]) == (HOUND, 1, 1, True)


def test_summaries_are_filtered_by_mode_version_and_date() -> None:
    rows = [
        summary("b1", 0, [[board(1, [HOUND])], [board(1, [MARKSMAN])]]),
        summary("b2", 0, [[board(1, [HOUND])], [board(1, [MARKSMAN])]], mode="AsyncBattle"),
        summary("b3", 0, [[board(1, [HOUND])], [board(1, [MARKSMAN])]], gameVersion="2.0.0.4.2331"),
    ]
    assert len(observations(rows, "early")) == 4
    assert len(observations(rows, "early", summary_filter=SummaryFilter(mode="AsyncBattle"))) == 2
    only = SummaryFilter(versions=frozenset({"2.0.0.4.2331"}))
    assert {item.battle_id for item in observations(rows, "early", summary_filter=only)} == {"b3"}
    assert observations(rows, "early", summary_filter=SummaryFilter(date_from="2026-10-21")) == []


def test_counter_table_against_the_baseline_when_they_field_y() -> None:
    # Against Crawler: I won 2 of 4 overall; with Hound I won 2 of 2, with Marksman 0 of 2.
    rows = [
        summary("b1", 0, [[board(1, [HOUND])], [board(1, [CRAWLER])]]),
        summary("b2", 0, [[board(1, [HOUND, MUSTANG])], [board(1, [CRAWLER])]]),
        summary("b3", 1, [[board(1, [MARKSMAN])], [board(1, [CRAWLER, MUSTANG])]]),
        summary("b4", 1, [[board(1, [MARKSMAN])], [board(1, [CRAWLER])]]),
    ]
    obs = [item for item in observations(rows, ALL_BANDS) if item.player_id == "p0"]
    table = counter_table(obs, min_sample=2, enemies=[CRAWLER], top=None)
    assert [entry["enemyUnitId"] for entry in table] == [CRAWLER]
    crawler = table[0]
    assert (crawler["n"], crawler["baselineWinRate"]) == (4, 0.5)
    rows_by_unit = by_unit(crawler["rows"])
    assert (rows_by_unit[HOUND]["n"], rows_by_unit[HOUND]["winRate"], rows_by_unit[HOUND]["delta"]) == (2, 1.0, 0.5)
    assert rows_by_unit[MARKSMAN]["delta"] == -0.5
    # Mustang was fielded once against Crawler: thin, so after the others despite its +0.5.
    assert rows_by_unit[MUSTANG]["thin"] and rows_by_unit[MUSTANG]["delta"] == 0.5
    assert [row["unitId"] for row in crawler["rows"]] == [HOUND, MARKSMAN, MUSTANG]
    assert len(counter_table(obs, min_sample=2, enemies=[CRAWLER], top=1)[0]["rows"]) == 1
    # Without a filter every enemy unit is listed, most observed first; an unseen one has n 0.
    assert [entry["enemyUnitId"] for entry in counter_table(obs, 2)] == [CRAWLER, MUSTANG]
    assert counter_table(obs, 2, enemies=[HOUND])[0]["n"] == 0


def test_insights_recompute_when_the_summaries_change() -> None:
    hub = Hub(server_version="t", model_available=False, replay_dir=None, live_source="none", local_player_id=None)
    insights = Insights(hub.summaries_snapshot)
    assert insights.winning_boards(SummaryFilter())["bands"]["early"]["n"] == 0
    hub.set_summaries([summary("b1", 0, [[board(1, [HOUND])], [board(1, [MARKSMAN])]])])
    result = insights.winning_boards(SummaryFilter(), min_sample=1)
    assert result["bands"]["early"]["n"] == 2
    assert result["bands"]["early"]["rounds"] == "1-3" and result["bands"]["late"]["rounds"] == "8+"
    hub.upsert_summary(summary("b2", 1, [[board(5, [HOUND])], [board(5, [MARKSMAN])]]))
    assert insights.winning_boards(SummaryFilter())["bands"]["mid"]["n"] == 2
    counters = insights.counters(SummaryFilter(), enemies=[MARKSMAN], min_sample=1)
    assert counters["enemies"][0]["rows"][0]["unitId"] == HOUND
    assert "not a causal" in counters["note"]
