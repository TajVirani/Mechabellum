import json
from pathlib import Path

from mechabellum.contracts import MatchSnapshot, validate_snapshot
from mechabellum.inference.live_history import FightOverHistory

ROOT = Path(__file__).resolve().parents[1]


def _frame(battle_id: str, round_number: int, cores: tuple[int, int]) -> MatchSnapshot:
    data = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    data["match"]["battleId"] = battle_id
    data["match"]["round"] = round_number
    for player, core in zip(data["players"], cores, strict=True):
        player["reactorCore"] = core
        player["supply"] = round_number * 10
        player["reactorCoreHistory"] = None
        player["supplyHistory"] = None
    return validate_snapshot(data)


def test_histories_fill_only_after_every_fight_was_seen() -> None:
    history = FightOverHistory()
    first = history.update(_frame("a", 1, (4500, 4000)))
    assert first.players[0].reactor_core_history == [4500]
    second = history.update(_frame("a", 2, (4500, 3200)))
    assert second.players[1].reactor_core_history == [4000, 3200]
    assert second.players[1].supply_history == [10, 20]

    # A new match joined at round 3 has no record of fights 1 and 2.
    joined = history.update(_frame("b", 3, (3000, 2000)))
    assert joined.players[0].reactor_core_history is None
