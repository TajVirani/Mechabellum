import json
from copy import deepcopy
from pathlib import Path

import pytest

from mechabellum.contracts import validate_snapshot
from mechabellum.training.targets import RewardConfig, fight_advantage, next_fight_advantages, reward

ROOT = Path(__file__).resolve().parents[1]


def _snapshot(round_number: int, scores: tuple[int, int], alive: tuple[int, int]):
    data = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    data = deepcopy(data)
    data["match"]["round"] = round_number
    for player, score, survivors in zip(data["players"], scores, alive, strict=True):
        player["lastFightReport"] = {
            "score": score,
            "deadScore": 0,
            "aliveMechCount": survivors,
            "destroyedCrystalCount": 0,
        }
    return validate_snapshot(data)


def test_fight_advantage_mixes_damage_and_survivors_and_is_antisymmetric() -> None:
    snapshot = _snapshot(3, (600, 0), (4, 0))
    assert fight_advantage(snapshot, 0) == pytest.approx(1.0)
    assert fight_advantage(snapshot, 1) == pytest.approx(-1.0)
    close = _snapshot(3, (300, 100), (2, 2))
    assert fight_advantage(close, 0) == pytest.approx(0.7 * 0.5)


def test_next_fight_advantage_comes_from_the_following_snapshot() -> None:
    targets = next_fight_advantages([_snapshot(3, (0, 0), (1, 1)), _snapshot(4, (500, 0), (3, 0))])
    assert targets[("example-battle", 3, 0)] == pytest.approx(1.0)
    assert targets[("example-battle", 4, 0)] is None


def test_round_rewards_never_flip_the_final_result() -> None:
    config = RewardConfig(gamma=0.9, round_weight=0.9)
    assert reward(False, [1.0] * 20, config) < 0
    assert reward(True, [-1.0] * 20, config) > 0
    assert reward(True, [], config) == 1.0
    with pytest.raises(ValueError):
        RewardConfig(round_weight=1.0)
