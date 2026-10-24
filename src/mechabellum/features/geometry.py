from __future__ import annotations

from dataclasses import dataclass

from ..collector.unit_catalog import UNIT_NAMES
from ..contracts import MatchSnapshot, PlayerSnapshot

# Board coordinates run roughly from -310 to 310 on both axes, with the midline at y = 0.
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


def board_sign(player: PlayerSnapshot, index: int) -> float:
    """-1 when the player deploys in the negative-y half, +1 for the positive half.

    Units decide; buildings are the fallback; with neither, player 0 is assumed to hold the negative half, as in
    every replay seen so far.
    """
    ys = [unit.y for unit in player.units] or [building.y for building in player.buildings or []]
    if ys:
        return -1.0 if sum(ys) / len(ys) < 0 else 1.0
    return -1.0 if index == 0 else 1.0


def unit_tokens(snapshot: MatchSnapshot, perspective: int) -> list[UnitToken]:
    own = snapshot.players[perspective]
    # Rotate the board 180 degrees when the perspective player holds the positive half.
    flip = board_sign(own, perspective) > 0
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
