import json
from pathlib import Path

import numpy as np

from mechabellum.contracts import validate_snapshot
from mechabellum.features import SYMMETRIC_FEATURES, build_features, feature_names, unit_tokens

ROOT = Path(__file__).resolve().parents[1]


def _example() -> dict:
    return json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))


def test_perspectives_mirror_each_other() -> None:
    data = _example()
    data["players"][1]["units"] = [dict(data["players"][0]["units"][0], y=150, x=40)]
    snapshot = validate_snapshot(data)
    first = build_features(snapshot, 0)
    second = build_features(snapshot, 1)
    names = feature_names()
    assert first.shape == (len(names),)
    symmetric = np.asarray([name in SYMMETRIC_FEATURES for name in names])
    np.testing.assert_allclose(first[~symmetric], -second[~symmetric], atol=1e-12)
    np.testing.assert_allclose(first[symmetric], second[symmetric], atol=1e-12)


def test_tokens_use_each_players_own_frame() -> None:
    data = _example()
    # Player B deploys in the positive half; mirrored into A's view, B's unit faces A's in the same lane.
    data["players"][1]["units"] = [dict(data["players"][0]["units"][0], y=150, x=40)]
    snapshot = validate_snapshot(data)
    own, opponent = unit_tokens(snapshot, 0)
    assert (own.side, own.x, own.depth) == (0, -40.0, 150.0)
    assert (opponent.side, opponent.x, opponent.depth) == (1, 40.0, 150.0)
    # From B's side the board is rotated: B's own unit is now on B's left at the same depth.
    b_own = next(token for token in unit_tokens(snapshot, 1) if token.side == 0)
    assert (b_own.x, b_own.depth) == (-40.0, 150.0)


def test_unknown_values_are_masked_not_zeroed() -> None:
    data = _example()
    snapshot = validate_snapshot(data)
    values = dict(zip(feature_names(), build_features(snapshot, 0), strict=True))
    # Replays have no max core; the difference stays 0 and the mask says unknown.
    assert (values["max_core_diff"], values["max_core_known"]) == (0.0, 0.0)
    assert values["last_fight_score_known"] == 1.0
    assert values["last_fight_score_diff"] == 412.0
