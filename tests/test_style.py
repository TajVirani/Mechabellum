import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from mechabellum.contracts import validate_snapshot
from mechabellum.features import (
    STYLE_CONTINUOUS_FEATURES,
    STYLE_LABEL_FEATURES,
    UnitToken,
    build_features,
    feature_names,
    symmetric_features,
    unit_tokens,
)
from mechabellum.features.geometry import board_sign
from mechabellum.features.style import board_style, crossfire, headbutt, heavy_side, owner_frame

ROOT = Path(__file__).resolve().parents[1]
# Primary roles in visualizer/unit_roles.json: Crawler chaff, Marksman damage, Fortress tank, Rhino damage (square).
CRAWLER, MARKSMAN, FORTRESS, RHINO = 10, 2, 1, 5


def _token(unit_id: int, x: float, depth: float, value: int = 100, rotated: bool = False, side: int = 0) -> UnitToken:
    return UnitToken(
        side=side,
        unit_id=unit_id,
        known_unit=True,
        level=1,
        experience=0,
        value=value,
        technology_ids=(),
        equipment_ids=(),
        x=x,
        depth=depth,
        is_rotated=rotated,
        round_count=1,
    )


def test_depth_styles() -> None:
    aggro = board_style([_token(CRAWLER, 0, 20), _token(MARKSMAN, 0, 60), _token(MARKSMAN, 40, 80)])
    assert aggro.depth_style == "aggro"
    # Half the main supply ahead of 100 m is aggro even with the front line held back.
    assert board_style([_token(MARKSMAN, 0, 90), _token(MARKSMAN, 40, 250)]).depth_style == "aggro"
    defense = board_style([_token(CRAWLER, 0, 150), _token(MARKSMAN, 0, 200), _token(MARKSMAN, 40, 260, 300)])
    assert (defense.depth_style, defense.rear_share) == ("defense", 0.8)
    standard = board_style([_token(CRAWLER, 0, 100), _token(MARKSMAN, 0, 140), _token(MARKSMAN, 40, 200)])
    assert standard.depth_style == "standard"
    # An empty board is standard and has no front line.
    assert (board_style([]).depth_style, board_style([]).front_depth) == ("standard", None)


def test_lateral_styles() -> None:
    side = board_style([_token(CRAWLER, -200, 100), _token(MARKSMAN, -150, 150), _token(MARKSMAN, 0, 150)])
    assert (side.lateral_style, heavy_side(side), side.heavy_lane) == ("side", -1, -1)
    diagonal = board_style([_token(CRAWLER, -200, 20), _token(MARKSMAN, 200, 200), _token(MARKSMAN, 0, 120)])
    assert (diagonal.lateral_style, diagonal.diagonal_gap) == ("diagonal", 180.0)
    balanced = board_style([_token(CRAWLER, -200, 100), _token(MARKSMAN, 200, 120), _token(MARKSMAN, 0, 120)])
    assert balanced.lateral_style == "balanced"
    assert heavy_side(balanced) == 0


def test_flank_share_and_gospel() -> None:
    # Flank formations stand past the other side's main region: negative depth.
    light = board_style([_token(CRAWLER, -330, -100, 50), _token(MARKSMAN, 0, 150, 450)])
    assert (light.flank_share, light.flanking, light.gospel_flank) == (0.1, True, False)
    heavy = board_style([_token(CRAWLER, -330, -100, 200), _token(MARKSMAN, 0, 150, 400)])
    assert heavy.gospel_flank
    # Flank formations stay out of the main-region statistics.
    assert (heavy.front_depth, heavy.mean_depth) == (150, 150)


def test_screen_layering_and_death_ball() -> None:
    screened = board_style([_token(CRAWLER, 0, 40), _token(FORTRESS, 60, 60), _token(MARKSMAN, 0, 150)])
    assert (screened.screen_gap, screened.screen_style) == (100.0, "screened")
    exposed = board_style([_token(MARKSMAN, 0, 20), _token(CRAWLER, 0, 150)])
    assert (exposed.screen_gap, exposed.screen_style) == (-130.0, "exposed")
    # No Damage formation: the screen is unknown, not zero.
    assert board_style([_token(CRAWLER, 0, 40)]).screen_gap is None

    layered = board_style([_token(CRAWLER, 0, 20), _token(CRAWLER, 0, 200)])
    assert (layered.chaff_layering, layered.layered) == (90.0, True)
    assert board_style([_token(CRAWLER, 0, 20)]).layered is None

    ball = board_style([_token(MARKSMAN, 0, 150), _token(MARKSMAN, 30, 150)])
    assert (ball.damage_compactness, ball.death_ball) == (1.0, True)
    spread = board_style([_token(MARKSMAN, -250, 150), _token(MARKSMAN, 250, 150)])
    assert (spread.damage_compactness, spread.death_ball) == (0.0, False)


def test_rotated_share_counts_only_non_square_formations() -> None:
    style = board_style(
        [_token(CRAWLER, 0, 50, rotated=True), _token(CRAWLER, 50, 50), _token(RHINO, 0, 100, rotated=True)]
    )
    assert style.rotated_share == 0.5
    assert board_style([_token(RHINO, 0, 100, rotated=True)]).rotated_share is None


def test_pairwise_styles_read_each_board_in_its_owners_frame() -> None:
    # Both rush the perspective player's left lane: the opponent's tokens carry the perspective x.
    own = [_token(CRAWLER, -200, 20), _token(MARKSMAN, -200, 60)]
    other = [_token(CRAWLER, -200, 20, side=1), _token(MARKSMAN, -200, 60, side=1)]
    own_style, other_style = board_style(owner_frame(own)), board_style(owner_frame(other))
    assert other_style.heavy_lane == 1  # the opponent's own right
    assert headbutt(own_style, other_style)
    assert not crossfire(own_style, other_style)
    # Stacked on opposite sides of the board: a crossfire, not a headbutt.
    other = [_token(CRAWLER, 200, 20, side=1), _token(MARKSMAN, 200, 60, side=1)]
    other_style = board_style(owner_frame(other))
    assert crossfire(own_style, other_style)
    assert not headbutt(own_style, other_style)


def _example() -> dict:
    return json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))


def test_schema_3_mirrors_perspectives_and_extends_schema_2() -> None:
    data = _example()
    vulcan = data["players"][0]["units"][0]
    data["players"][0]["units"] += [dict(vulcan, unitId=CRAWLER, x=-330, y=120, sellSupply=100)]
    data["players"][1]["units"] = [
        dict(vulcan, unitId=CRAWLER, x=40, y=20),
        dict(vulcan, unitId=MARKSMAN, x=60, y=150),
        dict(vulcan, unitId=FORTRESS, x=-100, y=200),
    ]
    snapshot = validate_snapshot(data)
    names = feature_names(3)
    assert names[: len(feature_names())] == feature_names()
    assert names[len(feature_names()) :] == [*STYLE_LABEL_FEATURES, *STYLE_CONTINUOUS_FEATURES]
    first, second = build_features(snapshot, 0, 3), build_features(snapshot, 1, 3)
    assert first.shape == (len(names),)
    # The style features mirror between perspectives. (Schema 2's per-lane features use the perspective's lanes for
    # both boards, so with formations off the centre lane they do not.)
    style = slice(len(feature_names()), None)
    symmetric = np.asarray([name in symmetric_features(3) for name in names[style]])
    np.testing.assert_allclose(first[style][~symmetric], -second[style][~symmetric], atol=1e-12)
    np.testing.assert_allclose(first[style][symmetric], second[style][symmetric], atol=1e-12)
    values = dict(zip(names, first, strict=True))
    assert values["flank_share_diff"] == pytest.approx(100 / 500)
    # Player 0 has no Damage formation, so the screen is masked.
    assert (values["screen_depth_gap_known"], values["screen_depth_gap_diff"]) == (0.0, 0.0)
    # Schema 2 is unchanged by default.
    np.testing.assert_array_equal(build_features(snapshot, 0), first[: len(feature_names())])
    with pytest.raises(ValueError, match="feature schema"):
        build_features(snapshot, 0, 4)


def test_flank_heavy_board_keeps_its_frame_with_the_main_region_vote() -> None:
    data = _example()
    main = dict(data["players"][0]["units"][0], x=0, y=200, sellSupply=100)
    # Player B holds the positive half, but three flank formations on A's half outvote its one main formation.
    data["players"][1]["units"] = [main] + [dict(main, unitId=CRAWLER, x=330, y=-250) for _ in range(3)]
    snapshot = validate_snapshot(data)
    player = snapshot.players[1]
    assert board_sign(player, 1) == -1.0  # schema 2's vote
    assert board_sign(player, 1, main_region=True) == 1.0
    own = [token for token in unit_tokens(snapshot, 1, main_region_frame=True) if token.side == 0]
    assert sorted(token.depth for token in own) == [-250.0, -250.0, -250.0, 200.0]


def test_schema_3_model_trains_and_loads(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    from mechabellum.datasets import write_snapshots
    from mechabellum.inference import predict_snapshot
    from mechabellum.models import load_artifact
    from mechabellum.training import train_model

    snapshots = []
    for index in range(10):
        data = deepcopy(_example())
        data["match"]["battleId"] = f"battle-{index}"
        winner = index % 2
        data["outcome"] = {
            "winnerIndex": winner,
            "winnerPlayerId": data["players"][winner]["playerId"],
            "winnerName": data["players"][winner]["name"],
        }
        data["players"][winner]["reactorCore"] += index * 10
        snapshots.append(validate_snapshot(data))
    dataset, model_path = tmp_path / "dataset.jsonl", tmp_path / "model.joblib"
    write_snapshots(dataset, snapshots)
    metadata = train_model(dataset, model_path, seed=7, feature_schema=3)
    assert metadata["featureSchemaVersion"] == 3
    # Callers pass the default schema's names; a schema 3 artifact is checked against its own.
    artifact = load_artifact(model_path, feature_names())
    assert artifact["featureNames"] == feature_names(3)
    result = predict_snapshot(artifact, snapshots[0], model_path)
    assert abs(sum(item["winProbability"] for item in result["predictions"]) - 1.0) < 1e-12
