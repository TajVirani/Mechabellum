"""Positioning style of one board: Aggro / Standard / Defense, lateral shape, flank, screen and death ball.

Every statistic is in the board owner's frame (`UnitToken.depth` from the midline into the owner's half, `x` with the
owner's left negative), weighted by `sell_supply`, and counts only formations whose primary role the unit role table
(`visualizer/unit_roles.json`, from research/unit-roles.md) knows when it asks for a role. Main formations stand at
depth >= 0; flank formations, in the strips past the other side's main region, at depth < 0.

A statistic that a board cannot have (no Damage units for a screen, one chaff formation for layering) is None, never
0: the feature builder turns None into a value of 0 plus a `*_known` mask.

The thresholds sit at the natural breaks of the 2.0 tournament data (docs/experiments.md, 2026-10-24 positioning).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from importlib.resources import files

from .geometry import LANE_EDGE, TOWER_DEPTH, UnitToken

# Depth style.
AGGRO_FRONT = 30.0  # a front line at the region's edge (a 20 m-deep formation stands at 20)
AGGRO_MEAN = 110.0
AGGRO_FORWARD_DEPTH = 100.0
AGGRO_FORWARD_SHARE = 0.5
DEFENSE_REAR_SHARE = 0.75  # share of main supply at or behind the tower line (TOWER_DEPTH)
# Lateral shape.
SIDE_LANE_SHARE = 0.6
SIDE_MEAN_X = 100.0
DIAGONAL_FRONT_GAP = 100.0
DIAGONAL_MIN_LANE_SHARE = 0.15
# Flank.
GOSPEL_FLANK_SHARE = 0.25
# Screen: Damage behind Chaff + Tank.
SCREENED_GAP = 40.0
EXPOSED_GAP = -20.0
LAYERED_CHAFF_STD = 50.0
# Death ball: Damage packed around its centroid.
DEATH_BALL_RADIUS = 80.0
DEATH_BALL_SHARE = 0.5

# Formations whose footprint is not square (qbisi/mechcore config/units/*.yaml `formation.footprint`); rotating a
# square formation changes nothing, so only these count towards the rotated share. Rotated, a wide formation stands
# as a column: narrow and deep.
NON_SQUARE_UNITS = frozenset({6, 7, 8, 9, 10, 12, 13, 16, 20, 22, 25, 28, 30})

DEPTH_STYLES = ("aggro", "standard", "defense")
LATERAL_STYLES = ("side", "diagonal", "balanced")
SCREEN_STYLES = ("screened", "neutral", "exposed")


def _load_primary_roles() -> dict[int, str]:
    text = files("mechabellum").joinpath("visualizer/unit_roles.json").read_text(encoding="utf-8")
    return {int(unit_id): entry["primary"] for unit_id, entry in json.loads(text).items()}


PRIMARY_ROLES: dict[int, str] = _load_primary_roles()


@dataclass(frozen=True)
class BoardStyle:
    supply: float
    front_depth: float | None  # main formations only
    mean_depth: float | None
    forward_share: float  # main supply share at depth < AGGRO_FORWARD_DEPTH
    rear_share: float  # main supply share at depth >= TOWER_DEPTH
    side_share: float  # the heavier side lane's share of main supply
    mean_x: float  # supply-weighted lateral centre of the main formations; owner's left is negative
    heavy_lane: int  # -1 left, 0 centre, 1 right: the lane holding the most main supply, in the owner's frame
    diagonal_gap: float | None  # |left front - right front| when both side lanes hold DIAGONAL_MIN_LANE_SHARE
    flank_share: float  # share of all supply at depth < 0
    rotated_share: float | None  # share of non-square main supply that is rotated
    screen_gap: float | None  # mean depth of Damage minus mean depth of Chaff + Tank (main formations)
    chaff_layering: float | None  # supply-weighted standard deviation of chaff depth, two or more chaff formations
    damage_compactness: float | None  # share of Damage supply within DEATH_BALL_RADIUS of the Damage centroid
    depth_style: str
    lateral_style: str
    screen_style: str | None
    layered: bool | None
    death_ball: bool | None

    @property
    def flanking(self) -> bool:
        return self.flank_share > 0

    @property
    def gospel_flank(self) -> bool:
        return self.flank_share >= GOSPEL_FLANK_SHARE


def _weight(token: UnitToken) -> float:
    return float(max(token.value, 0))


def _total(tokens: Sequence[UnitToken]) -> float:
    return sum(_weight(token) for token in tokens)


def _weighted_mean(tokens: Sequence[UnitToken], value: Callable[[UnitToken], float]) -> float | None:
    """Supply-weighted mean of `value(token)`; the plain mean when every formation is worth 0; None when empty."""
    if not tokens:
        return None
    total = _total(tokens)
    if total == 0:
        return sum(value(token) for token in tokens) / len(tokens)
    return sum(value(token) * _weight(token) for token in tokens) / total


def _share(tokens: Sequence[UnitToken], total: float) -> float:
    return 0.0 if total == 0 else _total(tokens) / total


def _role(tokens: Sequence[UnitToken], *roles: str) -> list[UnitToken]:
    return [token for token in tokens if PRIMARY_ROLES.get(token.unit_id) in roles]


def owner_frame(tokens: Sequence[UnitToken]) -> list[UnitToken]:
    """One side's tokens with `x` in its owner's frame: the opponent's x is mirrored, since it faces the other way."""
    return [token if token.side == 0 else replace(token, x=-token.x) for token in tokens]


def board_style(tokens: Sequence[UnitToken]) -> BoardStyle:
    """The style of one board; `tokens` are its formations, already in the owner's frame (see `owner_frame`)."""
    main = [token for token in tokens if token.depth >= 0]
    supply = _total(tokens)
    main_supply = _total(main)
    front = min((token.depth for token in main), default=None)
    mean = _weighted_mean(main, lambda token: token.depth)
    forward = _share([token for token in main if token.depth < AGGRO_FORWARD_DEPTH], main_supply)
    rear = _share([token for token in main if token.depth >= TOWER_DEPTH], main_supply)
    lanes = {
        -1: [token for token in main if token.x < -LANE_EDGE],
        0: [token for token in main if -LANE_EDGE <= token.x <= LANE_EDGE],
        1: [token for token in main if token.x > LANE_EDGE],
    }
    lane_shares = {index: _share(items, main_supply) for index, items in lanes.items()}
    side_share = max(lane_shares[-1], lane_shares[1])
    mean_x = _weighted_mean(main, lambda token: token.x) or 0.0
    heavy_lane = max((0, -1, 1), key=lambda index: lane_shares[index]) if main_supply > 0 else 0
    diagonal_gap = None
    if lane_shares[-1] >= DIAGONAL_MIN_LANE_SHARE and lane_shares[1] >= DIAGONAL_MIN_LANE_SHARE:
        diagonal_gap = abs(min(token.depth for token in lanes[-1]) - min(token.depth for token in lanes[1]))
    flank_share = _share([token for token in tokens if token.depth < 0], supply)
    shaped = [token for token in main if token.unit_id in NON_SQUARE_UNITS]
    rotated_share = _weighted_mean(shaped, lambda token: float(token.is_rotated))

    damage = _role(main, "damage")
    screen = _role(main, "chaff", "tank")
    screen_gap = None
    if damage and screen:
        screen_gap = (_weighted_mean(damage, lambda token: token.depth) or 0.0) - (
            _weighted_mean(screen, lambda token: token.depth) or 0.0
        )
    chaff = _role(main, "chaff")
    chaff_layering = None
    if len(chaff) >= 2:
        centre = _weighted_mean(chaff, lambda token: token.depth) or 0.0
        chaff_layering = math.sqrt(_weighted_mean(chaff, lambda token: (token.depth - centre) ** 2) or 0.0)
    damage_compactness = None
    if len(damage) >= 2:
        cx = _weighted_mean(damage, lambda token: token.x) or 0.0
        cy = _weighted_mean(damage, lambda token: token.depth) or 0.0
        near = [token for token in damage if math.hypot(token.x - cx, token.depth - cy) <= DEATH_BALL_RADIUS]
        damage_total = _total(damage)
        damage_compactness = len(near) / len(damage) if damage_total == 0 else _total(near) / damage_total

    aggro = main_supply > 0 and (
        (front is not None and front <= AGGRO_FRONT and mean is not None and mean < AGGRO_MEAN)
        or forward >= AGGRO_FORWARD_SHARE
    )
    defense = main_supply > 0 and rear >= DEFENSE_REAR_SHARE
    depth_style = "aggro" if aggro else "defense" if defense else "standard"
    if side_share >= SIDE_LANE_SHARE or abs(mean_x) > SIDE_MEAN_X:
        lateral_style = "side"
    elif diagonal_gap is not None and diagonal_gap > DIAGONAL_FRONT_GAP:
        lateral_style = "diagonal"
    else:
        lateral_style = "balanced"
    screen_style = None
    if screen_gap is not None:
        screen_style = (
            "screened" if screen_gap >= SCREENED_GAP else "exposed" if screen_gap <= EXPOSED_GAP else "neutral"
        )
    return BoardStyle(
        supply=supply,
        front_depth=front,
        mean_depth=mean,
        forward_share=forward,
        rear_share=rear,
        side_share=side_share,
        mean_x=mean_x,
        heavy_lane=heavy_lane,
        diagonal_gap=diagonal_gap,
        flank_share=flank_share,
        rotated_share=rotated_share,
        screen_gap=screen_gap,
        chaff_layering=chaff_layering,
        damage_compactness=damage_compactness,
        depth_style=depth_style,
        lateral_style=lateral_style,
        screen_style=screen_style,
        layered=None if chaff_layering is None else chaff_layering > LAYERED_CHAFF_STD,
        death_ball=None if damage_compactness is None else damage_compactness >= DEATH_BALL_SHARE,
    )


def heavy_side(style: BoardStyle) -> int:
    """-1 or 1 for the side lane a side-stacked board leans to, from the mean x; 0 when it does not lean."""
    if style.lateral_style != "side":
        return 0
    return -1 if style.mean_x < 0 else 1


def headbutt(own: BoardStyle, other: BoardStyle) -> bool:
    """Both boards Aggro with their weight in the same lane of the board: they meet head on.

    Both styles are in their owners' frames, so the opponent's lane is mirrored: its left lane is the
    perspective player's right.
    """
    return own.depth_style == other.depth_style == "aggro" and own.heavy_lane == -other.heavy_lane


def crossfire(own: BoardStyle, other: BoardStyle) -> bool:
    """Both boards side-stacked on opposite sides of the board, so each heavy side faces the other's light one."""
    own_side, other_side = heavy_side(own), heavy_side(other)
    # In the owners' frames the same board side has opposite signs; opposite board sides have equal signs.
    return own_side != 0 and own_side == other_side
