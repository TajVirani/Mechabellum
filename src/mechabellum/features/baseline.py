from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from ..contracts import MatchSnapshot, PlayerSnapshot

UNIT_IDS = (*range(1, 32), 2002)


@dataclass
class UnitStats:
    count: float = 0.0
    level: float = 0.0
    sell_supply: float = 0.0
    technology: float = 0.0


@dataclass
class PlayerStats:
    core: float
    supply: float
    previous_fight: float
    formation_count: float
    unit_diversity: float
    board_sell_supply: float
    level_sum: float
    experience: float
    equipment_count: float
    technology_count: float
    mean_abs_x: float
    mean_abs_y: float
    x_span: float
    y_span: float
    by_unit: dict[int, UnitStats] = field(default_factory=dict)


def feature_names() -> list[str]:
    names = [
        "core_diff",
        "core_share_diff",
        "supply_diff",
        "supply_share_diff",
        "previous_fight_diff",
        "formation_count_diff",
        "unit_diversity_diff",
        "board_sell_supply_diff",
        "board_value_share_diff",
        "level_sum_diff",
        "experience_log_diff",
        "equipment_count_diff",
        "technology_count_diff",
        "mean_abs_x_diff",
        "mean_abs_y_diff",
        "x_span_diff",
        "y_span_diff",
        "log_round_x_core_share_diff",
        "log_round_x_supply_share_diff",
        "log_round_x_previous_fight_diff",
        "log_round_x_board_value_share_diff",
        "log_round_x_formation_count_diff",
    ]
    for unit_id in UNIT_IDS:
        names.extend(
            (
                f"unit_{unit_id}_count_diff",
                f"unit_{unit_id}_level_diff",
                f"unit_{unit_id}_sell_supply_diff",
                f"unit_{unit_id}_technology_diff",
            )
        )
    return names


def build_features(snapshot: MatchSnapshot, perspective: int = 0) -> np.ndarray:
    if len(snapshot.players) != 2:
        raise ValueError("The win probability model only supports two-player positions.")
    if perspective not in (0, 1):
        raise ValueError("perspective must be 0 or 1.")

    own = _player_stats(snapshot.players[perspective])
    opponent = _player_stats(snapshot.players[1 - perspective])
    round_scale = math.log1p(max(1, snapshot.match.round))
    core_share_diff = _share_diff(own.core, opponent.core)
    supply_share_diff = _share_diff(own.supply, opponent.supply)
    previous_fight_diff = own.previous_fight - opponent.previous_fight
    board_value_share_diff = _share_diff(own.board_sell_supply, opponent.board_sell_supply)
    formation_count_diff = own.formation_count - opponent.formation_count

    values = [
        own.core - opponent.core,
        core_share_diff,
        own.supply - opponent.supply,
        supply_share_diff,
        previous_fight_diff,
        formation_count_diff,
        own.unit_diversity - opponent.unit_diversity,
        own.board_sell_supply - opponent.board_sell_supply,
        board_value_share_diff,
        own.level_sum - opponent.level_sum,
        math.log1p(own.experience) - math.log1p(opponent.experience),
        own.equipment_count - opponent.equipment_count,
        own.technology_count - opponent.technology_count,
        own.mean_abs_x - opponent.mean_abs_x,
        own.mean_abs_y - opponent.mean_abs_y,
        own.x_span - opponent.x_span,
        own.y_span - opponent.y_span,
        round_scale * core_share_diff,
        round_scale * supply_share_diff,
        round_scale * previous_fight_diff,
        round_scale * board_value_share_diff,
        round_scale * formation_count_diff,
    ]

    for unit_id in UNIT_IDS:
        own_unit = own.by_unit.get(unit_id, UnitStats())
        opponent_unit = opponent.by_unit.get(unit_id, UnitStats())
        values.extend(
            (
                own_unit.count - opponent_unit.count,
                own_unit.level - opponent_unit.level,
                own_unit.sell_supply - opponent_unit.sell_supply,
                own_unit.technology - opponent_unit.technology,
            )
        )
    return np.asarray(values, dtype=np.float64)


def _player_stats(player: PlayerSnapshot) -> PlayerStats:
    by_unit: dict[int, UnitStats] = {}
    xs: list[float] = []
    ys: list[float] = []
    board_sell_supply = 0.0
    level_sum = 0.0
    experience = 0.0
    equipment_count = 0.0
    for unit in player.units:
        if unit.unit_id not in UNIT_IDS:
            continue
        stats = by_unit.setdefault(unit.unit_id, UnitStats())
        stats.count += 1.0
        stats.level += unit.display_level
        stats.sell_supply += unit.sell_supply
        board_sell_supply += unit.sell_supply
        level_sum += unit.display_level
        experience += unit.experience
        equipment_count += float(unit.equipment_id > 0)
        xs.append(unit.x)
        ys.append(unit.y)

    technology_count = 0.0
    for technology_set in player.active_technologies:
        count = float(len(technology_set.technology_ids))
        technology_count += count
        if technology_set.unit_id in UNIT_IDS:
            by_unit.setdefault(technology_set.unit_id, UnitStats()).technology += count

    return PlayerStats(
        core=float(player.reactor_core or 0),
        supply=float(player.supply or 0),
        previous_fight=_fight_result(player.previous_fight_result),
        formation_count=float(len(player.units)),
        unit_diversity=float(len(by_unit)),
        board_sell_supply=board_sell_supply,
        level_sum=level_sum,
        experience=experience,
        equipment_count=equipment_count,
        technology_count=technology_count,
        mean_abs_x=_mean_abs(xs),
        mean_abs_y=_mean_abs(ys),
        x_span=_span(xs),
        y_span=_span(ys),
        by_unit=by_unit,
    )


def _share_diff(left: float, right: float) -> float:
    total = abs(left) + abs(right)
    return 0.0 if total == 0 else (left - right) / total


def _fight_result(value: str | None) -> float:
    normalized = (value or "").strip().lower()
    return 1.0 if normalized == "win" else -1.0 if normalized == "lose" else 0.0


def _mean_abs(values: Sequence[float]) -> float:
    return 0.0 if not values else sum(abs(value) for value in values) / len(values)


def _span(values: Sequence[float]) -> float:
    return 0.0 if not values else max(values) - min(values)
