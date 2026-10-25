from __future__ import annotations

from dataclasses import dataclass

from ..collector.unit_catalog import UNIT_NAMES
from ..contracts import MatchSnapshot, PlayerSnapshot

# The board is x -360..360 and y -310..310 m with the midline at y = 0, and a unit's x/y is its footprint's centre.
# Each side's main region is |x| <= 300 on its own half, from 10 m off the midline; its two flanks are the strips
# 300 < |x| <= 360 on the other side's half, so a flank formation has a negative depth. The towers stand at
# x = +-140, 170 m deep, on every map (qbisi/mechcore config/maps.yaml @ b2c7804).
MAIN_HALF_WIDTH = 300.0
TOWER_DEPTH = 170.0
LANE_EDGE = 100.0
DEPTH_BANDS = (100.0, 200.0)
LANES = ("left", "center", "right")
BANDS = ("front", "middle", "back")


@dataclass(frozen=True)
class UnitToken:
    """One formation seen from `perspective`'s side of the board.

    `x` is the lane position from the perspective player's view (negative is their left) and `depth` is the
    distance from the midline into the token owner's half, so both players' front lines have small depth.
    """

    side: int  # 0 = the perspective player, 1 = the opponent
    unit_id: int
    known_unit: bool
    level: int
    experience: int
    value: int
    technology_ids: tuple[int, ...]
    equipment_ids: tuple[int, ...]
    x: float
    depth: float
    is_rotated: bool
    round_count: int


def board_sign(player: PlayerSnapshot, index: int, *, main_region: bool = False) -> float:
    """-1 when the player deploys in the negative-y half, +1 for the positive half.

    Units decide; buildings are the fallback; with neither, player 0 is assumed to hold the negative half, as in
    every replay seen so far. With `main_region`, only units inside the main region's width (|x| <= 300) vote:
    flank formations stand on the other half, so a flank-heavy board can otherwise outvote its own main region.
    Feature schema 2 keeps the old vote, which turns 1.5% of the 2.0 player snapshots the wrong way round.
    """
    units = player.units
    if main_region:
        units = [unit for unit in units if abs(unit.x) <= MAIN_HALF_WIDTH] or units
    ys = [unit.y for unit in units] or [building.y for building in player.buildings or []]
    if ys:
        return -1.0 if sum(ys) / len(ys) < 0 else 1.0
    return -1.0 if index == 0 else 1.0


def unit_tokens(snapshot: MatchSnapshot, perspective: int, *, main_region_frame: bool = False) -> list[UnitToken]:
    """Both players' formations in `perspective`'s frame; `main_region_frame` picks the frame by main units only."""
    own = snapshot.players[perspective]
    # Rotate the board 180 degrees when the perspective player holds the positive half.
    flip = board_sign(own, perspective, main_region=main_region_frame) > 0
    tokens = []
    for side, index in ((0, perspective), (1, 1 - perspective)):
        player = snapshot.players[index]
        technologies = {item.unit_id: tuple(item.technology_ids) for item in player.active_technologies}
        for unit in player.units:
            x, y = (-unit.x, -unit.y) if flip else (unit.x, unit.y)
            tokens.append(
                UnitToken(
                    side=side,
                    unit_id=unit.unit_id,
                    known_unit=unit.unit_id in UNIT_NAMES,
                    level=unit.display_level,
                    experience=unit.experience,
                    value=unit.sell_supply,
                    technology_ids=technologies.get(unit.unit_id, ()),
                    equipment_ids=tuple(item.equipment_id for item in unit.equipment),
                    x=x,
                    # The perspective player's half is y < 0 after the rotation; the opponent's is y > 0.
                    depth=-y if side == 0 else y,
                    is_rotated=unit.is_rotated,
                    round_count=unit.round_count,
                )
            )
    return tokens


def lane(token: UnitToken) -> int:
    return 0 if token.x < -LANE_EDGE else 2 if token.x > LANE_EDGE else 1


def band(token: UnitToken) -> int:
    return 0 if token.depth < DEPTH_BANDS[0] else 1 if token.depth < DEPTH_BANDS[1] else 2
