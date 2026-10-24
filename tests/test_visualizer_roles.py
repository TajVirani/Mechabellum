from __future__ import annotations

import pytest

from mechabellum.collector.unit_catalog import UNIT_PRICES, unit_name
from mechabellum.contracts import UnitDeployment
from mechabellum.visualizer.baseline import compute_baseline
from mechabellum.visualizer.roles import ROLES, SLICES, UNIT_ROLES, board_composition, mean_composition


def unit(unit_id: int, supply: int, index: int = 0) -> UnitDeployment:
    return UnitDeployment(
        unit_id=unit_id,
        unit_name=unit_name(unit_id),
        formation_index=index,
        raw_level=0,
        display_level=1,
        experience=0,
        x=0.0,
        y=-100.0,
        is_rotated=False,
        sell_supply=supply,
        round_count=1,
        equipment=[],
    )


def test_role_table_covers_every_priced_unit() -> None:
    spawned_in_battle = {1001, 1002}
    assert set(UNIT_ROLES) == set(UNIT_PRICES) - spawned_in_battle
    assert all(role.primary in ROLES for role in UNIT_ROLES.values())
    assert sum(role.air for role in UNIT_ROLES.values()) == 7
    assert sum(role.hits_air for role in UNIT_ROLES.values()) == 14
    assert UNIT_ROLES[10].primary == "chaff" and UNIT_ROLES[15].primary == "chaffClear"


def test_composition_is_supply_weighted() -> None:
    # Crawler (chaff, 24 members), Wasp (chaff, air, hits air, 12), Fortress (tank) and an unknown unit.
    board = [unit(10, 100, 0), unit(6, 200, 1), unit(1, 600, 2), unit(999, 100, 3)]
    composition = board_composition(board, 3)

    assert composition["round"] == 3
    assert composition["supply"] == 1000
    assert composition["roles"]["chaff"] == pytest.approx(0.3)
    assert composition["roles"]["tank"] == pytest.approx(0.6)
    assert composition["roles"]["unknown"] == pytest.approx(0.1)
    assert sum(composition["roles"].values()) == pytest.approx(1.0)
    assert composition["air"] == pytest.approx(0.2)
    assert composition["hitsAir"] == pytest.approx(0.2)
    # Members from unitPrices, falling back to 1 for the unknown unit.
    assert composition["bodies"] == 24 + 12 + 1 + 1
    assert list(composition["roles"]) == list(SLICES)


def test_empty_board_has_zero_shares() -> None:
    composition = board_composition([], 1)
    assert composition["supply"] == 0
    assert composition["bodies"] == 0
    assert composition["air"] == composition["hitsAir"] == 0
    assert all(value == 0 for value in composition["roles"].values())


def test_mean_composition_skips_empty_boards() -> None:
    mean = mean_composition(
        [board_composition([unit(10, 100)]), board_composition([unit(1, 400)]), board_composition([])]
    )
    assert mean["n"] == 2
    assert mean["roles"]["chaff"] == pytest.approx(0.5)
    assert mean["roles"]["tank"] == pytest.approx(0.5)
    assert mean["bodies"] == pytest.approx((24 + 1) / 2)


def _summary(
    winner_rounds: list[list[UnitDeployment]], loser_rounds: list[list[UnitDeployment]], mode: str = "Normal"
) -> dict:
    def player(won: bool, rounds: list[list[UnitDeployment]]) -> dict:
        return {
            "playerId": "w" if won else "l",
            "won": won,
            "composition": [board_composition(board, index + 1) for index, board in enumerate(rounds)],
        }

    return {"gameMode": mode, "players": [player(True, winner_rounds), player(False, loser_rounds)]}


def test_baseline_averages_winning_boards_by_round_and_overall() -> None:
    chaff, tank = [unit(10, 100)], [unit(1, 400)]
    summaries = [_summary([chaff, tank], [tank, tank]) for _ in range(5)] + [_summary([tank], [chaff])]
    baseline = compute_baseline(summaries)["byMode"]["Normal"]

    first, second = baseline["byRound"]["1"], baseline["byRound"]["2"]
    assert first["n"] == 6 and first["thin"] is False
    assert first["roles"]["chaff"] == pytest.approx(5 / 6)
    assert first["roles"]["tank"] == pytest.approx(1 / 6)
    assert second["n"] == 5 and second["roles"]["tank"] == pytest.approx(1.0)
    overall = baseline["overall"]
    assert overall["n"] == 11
    assert overall["roles"]["chaff"] == pytest.approx(5 / 11)
    assert set(first) == {"roles", "air", "hitsAir", "bodies", "n", "thin"}


def test_baseline_flags_thin_rounds() -> None:
    baseline = compute_baseline([_summary([[unit(10, 100)]], []) for _ in range(4)])["byMode"]["Normal"]
    assert baseline["byRound"]["1"]["thin"] is True
    # Normal is always there, empty when no summary has it.
    assert list(compute_baseline([])["byMode"]) == ["Normal"]
    assert compute_baseline([])["byMode"]["Normal"]["byRound"] == {}
    assert compute_baseline([])["byMode"]["Normal"]["overall"] == {
        "roles": dict.fromkeys(SLICES, 0.0),
        "air": 0.0,
        "hitsAir": 0.0,
        "bodies": 0.0,
        "n": 0,
        "thin": True,
    }


def test_baseline_keeps_game_modes_apart() -> None:
    chaff, tank = [unit(10, 100)], [unit(1, 400)]
    # AsyncBattle's unit ids aren't in the role table: its boards are all "unknown", and must not dilute Normal's.
    async_board = [unit(5010, 100)]
    summaries = [_summary([chaff], [tank]), _summary([async_board], [tank], "AsyncBattle"), {"players": []}]
    by_mode = compute_baseline(summaries)["byMode"]
    assert set(by_mode) == {"Normal", "AsyncBattle"}
    assert by_mode["Normal"]["overall"]["n"] == 1
    assert by_mode["Normal"]["overall"]["roles"]["unknown"] == 0
    assert by_mode["Normal"]["byRound"]["1"]["roles"]["chaff"] == pytest.approx(1.0)
    assert by_mode["AsyncBattle"]["overall"]["roles"]["unknown"] == pytest.approx(1.0)
