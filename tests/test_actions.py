import json
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from mechabellum.contracts import validate_snapshot
from mechabellum.features import unit_tokens
from mechabellum.inference.actions import ActionCatalog, CandidateAction, apply_action, candidate_actions, rank_actions

ROOT = Path(__file__).resolve().parents[1]


def _example() -> dict:
    return json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))


def test_buy_and_move_respect_each_players_frame() -> None:
    data = _example()
    data["players"][1]["units"] = [dict(data["players"][0]["units"][0], y=150, x=40)]
    snapshot = validate_snapshot(data)
    for perspective in (0, 1):
        bought = apply_action(
            snapshot, perspective, CandidateAction("buy", "", {"unitId": 9, "x": -160.0, "depth": 120.0}, 100)
        )
        token = [item for item in unit_tokens(bought, perspective) if item.side == 0 and item.unit_id == 9][0]
        # The new formation lands on the player's own left, 120 into their half, whichever half that is.
        assert (token.x, token.depth) == (-160.0, 120.0)
        assert bought.players[perspective].supply == snapshot.players[perspective].supply - 100
        moved = apply_action(
            snapshot, perspective, CandidateAction("move", "", {"formation": 0, "dx": 0, "ddepth": -40}, 0)
        )
        before = [item for item in unit_tokens(snapshot, perspective) if item.side == 0][0]
        after = [item for item in unit_tokens(moved, perspective) if item.side == 0][0]
        assert after.depth == before.depth - 40


def test_card_effects_are_learned_from_the_next_snapshot() -> None:
    data = _example()
    first = deepcopy(data)
    first["match"]["round"] = 2
    first["players"][0]["officerIds"] = []
    second = deepcopy(data)
    second["players"][0]["officerIds"] = [20035]
    second["players"][0]["reinforcementChoice"] = {"status": "chosen", "itemId": 20035, "offerIndex": 0}
    catalog = ActionCatalog.from_snapshots([validate_snapshot(first), validate_snapshot(second)])
    assert catalog.card_effects[20035] == "officer"
    assert catalog.unit_prices[3] == 400


def test_prices_come_from_the_game_tables_and_limit_candidates() -> None:
    data = _example()
    data["players"][0]["supply"] = 250
    snapshot = validate_snapshot(data)
    catalog = ActionCatalog.from_game_data()
    assert (catalog.unit_prices[28], catalog.upgrade_prices[28], catalog.technology_prices[1001]) == (100, 50, 500)
    assert catalog.card_effects[10010] == "officer"
    candidates = candidate_actions(snapshot, 0, catalog, cards=[300001])
    assert all((action.estimated_cost or 0) <= 250 for action in candidates)
    # A Vulcan costs 400 to buy and 200 to upgrade: the upgrade stays, the purchase does not.
    assert not [action for action in candidates if action.kind == "buy" and action.parameters["unitId"] == 3]
    upgrade = next(action for action in candidates if action.kind == "upgrade")
    assert upgrade.estimated_cost == 200
    assert apply_action(snapshot, 0, upgrade).players[0].supply == 50


def test_ranking_is_sorted_by_gain(tmp_path: Path) -> None:
    from mechabellum.datasets import write_snapshots
    from mechabellum.features import feature_names
    from mechabellum.models import load_artifact
    from mechabellum.training import train_model

    example = _example()
    snapshots = []
    for index in range(10):
        data = deepcopy(example)
        data["match"]["battleId"] = f"battle-{index}"
        winner = index % 2
        data["outcome"] = {"winnerIndex": winner, "winnerPlayerId": None, "winnerName": None}
        data["players"][winner]["reactorCore"] += 300
        data["players"][0]["supply"] = 1000
        snapshots.append(validate_snapshot(data))
    dataset = tmp_path / "dataset.jsonl"
    write_snapshots(dataset, snapshots)
    model = tmp_path / "model.joblib"
    train_model(dataset, model, seed=7)
    artifact = load_artifact(model, feature_names())
    catalog = ActionCatalog.from_snapshots(snapshots)
    candidates = candidate_actions(snapshots[0], 0, catalog, cards=[300001])
    baseline, ranked = rank_actions(artifact, snapshots[0], 0, candidates)
    assert 0 < baseline < 1
    assert len(ranked) == len(candidates)
    gains = [item.gain for item in ranked]
    assert gains == sorted(gains, reverse=True)
    assert {item.action.kind for item in ranked} >= {"buy", "upgrade", "move", "card"}
