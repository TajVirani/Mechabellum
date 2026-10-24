"""Feature schema 2: a player-symmetric description of a fight_over position.

Every feature is "perspective player minus opponent" unless noted, so swapping perspectives negates the vector.
Values a source cannot provide are never silently zero: each such input contributes a `*_known` mask, set when
both players' values are known, and the value itself is 0 only when the mask is 0.

Map, game mode and version are the same for both players, so they cancel in a difference model; the token models
take them as match context instead.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from ..contracts import MatchSnapshot, PlayerSnapshot
from .geometry import BANDS, LANES, UnitToken, band, lane, unit_tokens

FEATURE_SCHEMA_VERSION = 2
UNIT_IDS = (*range(1, 33), 2002)
NEIGHBOUR_RADIUS = 60.0
PROTECTION_DEPTH = 120.0


@dataclass(frozen=True)
class _Feature:
    name: str
    compute: Callable[[MatchSnapshot, int, list[UnitToken]], float]


def _diff(value: Callable[[PlayerSnapshot], float]) -> Callable[[MatchSnapshot, int, list[UnitToken]], float]:
    return lambda snapshot, perspective, _: (
        value(snapshot.players[perspective]) - value(snapshot.players[1 - perspective])
    )


def _optional_diff(
    value: Callable[[PlayerSnapshot], float | None],
) -> tuple[
    Callable[[MatchSnapshot, int, list[UnitToken]], float], Callable[[MatchSnapshot, int, list[UnitToken]], float]
]:
    """A difference that is only defined when both players have the value, plus its mask."""

    def known(snapshot: MatchSnapshot, perspective: int, _: list[UnitToken]) -> float:
        return float(all(value(player) is not None for player in snapshot.players))

    def difference(snapshot: MatchSnapshot, perspective: int, tokens: list[UnitToken]) -> float:
        if not known(snapshot, perspective, tokens):
            return 0.0
        own, other = value(snapshot.players[perspective]), value(snapshot.players[1 - perspective])
        return float(own or 0) - float(other or 0)

    return difference, known


def _share(left: float, right: float) -> float:
    total = abs(left) + abs(right)
    return 0.0 if total == 0 else (left - right) / total


def _side(tokens: list[UnitToken], side: int) -> list[UnitToken]:
    return [token for token in tokens if token.side == side]


def _token_diff(
    value: Callable[[list[UnitToken]], float],
) -> Callable[[MatchSnapshot, int, list[UnitToken]], float]:
    return lambda _, __, tokens: value(_side(tokens, 0)) - value(_side(tokens, 1))


# ---- per-player board statistics over tokens -------------------------------------------------------------------


def _value(tokens: Sequence[UnitToken]) -> float:
    return float(sum(token.value for token in tokens))


def _front_depth(tokens: Sequence[UnitToken]) -> float:
    return min((token.depth for token in tokens), default=0.0)


def _mean_depth(tokens: Sequence[UnitToken]) -> float:
    total = _value(tokens)
    if not tokens:
        return 0.0
    if total == 0:
        return sum(token.depth for token in tokens) / len(tokens)
    return sum(token.depth * token.value for token in tokens) / total


def _depth_spread(tokens: Sequence[UnitToken]) -> float:
    if len(tokens) < 2:
        return 0.0
    depths = [token.depth for token in tokens]
    mean = sum(depths) / len(depths)
    return math.sqrt(sum((depth - mean) ** 2 for depth in depths) / len(depths))


def _lane_share(index: int) -> Callable[[Sequence[UnitToken]], float]:
    def share(tokens: Sequence[UnitToken]) -> float:
        total = _value(tokens)
        return 0.0 if total == 0 else _value([token for token in tokens if lane(token) == index]) / total

    return share


def _density(tokens: Sequence[UnitToken]) -> float:
    """Mean distance to the nearest friendly formation; 0 with fewer than two formations."""
    if len(tokens) < 2:
        return 0.0
    points = np.asarray([(token.x, token.depth) for token in tokens])
    distances = np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(distances, np.inf)
    return float(distances.min(axis=1).mean())


def _protected_share(tokens: Sequence[UnitToken]) -> float:
    """Value share of formations with a friendly formation in front of them in the same column."""
    total = _value(tokens)
    if total == 0:
        return 0.0
    protected = 0.0
    for token in tokens:
        if any(
            0 < token.depth - other.depth <= PROTECTION_DEPTH and abs(token.x - other.x) <= NEIGHBOUR_RADIUS
            for other in tokens
            if other is not token
        ):
            protected += token.value
    return protected / total


def _first_contact_share(tokens: Sequence[UnitToken]) -> float:
    """Value share of the formations that meet the enemy first: within one neighbour radius of the front line."""
    total = _value(tokens)
    if total == 0:
        return 0.0
    front = _front_depth(tokens)
    return _value([token for token in tokens if token.depth - front <= NEIGHBOUR_RADIUS]) / total


def _unknown_units(tokens: Sequence[UnitToken]) -> float:
    return float(sum(not token.known_unit for token in tokens))


# ---- cross-player matchups --------------------------------------------------------------------------------------


def _lane_value_diff(index: int) -> Callable[[MatchSnapshot, int, list[UnitToken]], float]:
    def difference(_: MatchSnapshot, __: int, tokens: list[UnitToken]) -> float:
        own = _value([token for token in _side(tokens, 0) if lane(token) == index])
        other = _value([token for token in _side(tokens, 1) if lane(token) == index])
        return _share(own, other)

    return difference


def _lane_gap(index: int) -> tuple[Callable[..., float], Callable[..., float]]:
    """Distance between the two front lines in a lane, and a mask for both sides having a formation there."""

    def present(_: MatchSnapshot, __: int, tokens: list[UnitToken]) -> float:
        return float(all(any(lane(token) == index for token in _side(tokens, side)) for side in (0, 1)))

    def gap(snapshot: MatchSnapshot, perspective: int, tokens: list[UnitToken]) -> float:
        if not present(snapshot, perspective, tokens):
            return 0.0
        own = _front_depth([token for token in _side(tokens, 0) if lane(token) == index])
        other = _front_depth([token for token in _side(tokens, 1) if lane(token) == index])
        return own + other

    return gap, present


def _lane_front_diff(index: int) -> Callable[[MatchSnapshot, int, list[UnitToken]], float]:
    """Who holds the lane further forward: the opponent's front depth minus the perspective player's."""

    def difference(_: MatchSnapshot, __: int, tokens: list[UnitToken]) -> float:
        own = [token for token in _side(tokens, 0) if lane(token) == index]
        other = [token for token in _side(tokens, 1) if lane(token) == index]
        if not own or not other:
            return 0.0
        return _front_depth(other) - _front_depth(own)

    return difference


def _zone_value(lane_index: int, band_index: int) -> Callable[[list[UnitToken]], float]:
    return lambda tokens: _value([token for token in tokens if lane(token) == lane_index and band(token) == band_index])


# ---- economy, items and history ---------------------------------------------------------------------------------


def _length(value: Callable[[PlayerSnapshot], Sequence[object] | None]) -> Callable[[PlayerSnapshot], float | None]:
    return lambda player: None if value(player) is None else float(len(value(player) or []))


def _fight_value(result: str) -> float:
    return 1.0 if result == "Win" else -1.0 if result == "Lose" else 0.0


def _win_rate(player: PlayerSnapshot) -> float | None:
    history = player.fight_result_history
    if not history:
        return None
    return sum(_fight_value(result) for result in history) / len(history)


def _streak(player: PlayerSnapshot) -> float | None:
    history = player.fight_result_history
    if not history:
        return None
    last = history[-1]
    count = 0
    for result in reversed(history):
        if result != last:
            break
        count += 1
    return _fight_value(last) * count


def _core_change(player: PlayerSnapshot) -> float | None:
    """Core lost in the last fight (0 when it was not damaged); unknown before two values exist."""
    history = player.reactor_core_history
    if not history or len(history) < 2:
        return None
    return float(history[-1] - history[-2])


def _supply_trend(player: PlayerSnapshot) -> float | None:
    history = player.supply_history
    if not history or len(history) < 2:
        return None
    return float(history[-1] - history[-2])


def _report(field: str) -> Callable[[PlayerSnapshot], float | None]:
    def value(player: PlayerSnapshot) -> float | None:
        report = player.last_fight_report
        item = None if report is None else getattr(report, field)
        return None if item is None else float(item)

    return value


def _active_skills(player: PlayerSnapshot) -> float | None:
    if player.commander_skills is None:
        return None
    return float(sum(bool(skill.is_active) for skill in player.commander_skills))


def _cooldowns(player: PlayerSnapshot) -> float | None:
    if player.commander_skills is None:
        return None
    return float(sum(skill.cooldown_rounds or 0 for skill in player.commander_skills))


def _choice(player: PlayerSnapshot) -> float | None:
    choice = player.reinforcement_choice
    return None if choice is None else 1.0 if choice.status == "chosen" else -1.0


def _tower_levels(player: PlayerSnapshot) -> float | None:
    return None if player.tower_strengthen_levels is None else float(sum(player.tower_strengthen_levels))


def _pool_size(player: PlayerSnapshot) -> float | None:
    if player.unlocked_unit_ids is None or player.locked_unit_ids is None:
        return None
    return float(len(player.unlocked_unit_ids) + len(player.locked_unit_ids))


def _investment(player: PlayerSnapshot) -> float:
    """Supply tied up in the board plus supply still unspent."""
    return float(sum(unit.sell_supply for unit in player.units) + (player.supply or 0))


def _feature_list() -> list[_Feature]:
    features: list[_Feature] = [
        _Feature("core_diff", _diff(lambda player: float(player.reactor_core or 0))),
        _Feature(
            "core_share_diff",
            lambda snapshot, perspective, _: _share(
                float(snapshot.players[perspective].reactor_core or 0),
                float(snapshot.players[1 - perspective].reactor_core or 0),
            ),
        ),
        _Feature("supply_diff", _diff(lambda player: float(player.supply or 0))),
        _Feature("investment_diff", _diff(_investment)),
        _Feature(
            "investment_share_diff",
            lambda snapshot, perspective, _: _share(
                _investment(snapshot.players[perspective]), _investment(snapshot.players[1 - perspective])
            ),
        ),
        _Feature("previous_fight_diff", _diff(lambda player: _fight_value(player.previous_fight_result or ""))),
        _Feature("formation_count_diff", _diff(lambda player: float(len(player.units)))),
        _Feature("unit_diversity_diff", _diff(lambda player: float(len({unit.unit_id for unit in player.units})))),
        _Feature("level_sum_diff", _diff(lambda player: float(sum(unit.display_level for unit in player.units)))),
        _Feature(
            "experience_log_diff",
            _diff(lambda player: math.log1p(sum(unit.experience for unit in player.units))),
        ),
        _Feature(
            "board_equipment_diff", _diff(lambda player: float(sum(len(unit.equipment) for unit in player.units)))
        ),
        _Feature(
            "technology_count_diff",
            _diff(lambda player: float(sum(len(item.technology_ids) for item in player.active_technologies))),
        ),
        _Feature("unknown_unit_diff", _token_diff(_unknown_units)),
        # Positioning, each in the owner's own frame.
        _Feature("front_depth_diff", _token_diff(_front_depth)),
        _Feature("mean_depth_diff", _token_diff(_mean_depth)),
        _Feature("depth_spread_diff", _token_diff(_depth_spread)),
        _Feature("density_diff", _token_diff(_density)),
        _Feature("protected_share_diff", _token_diff(_protected_share)),
        _Feature("first_contact_share_diff", _token_diff(_first_contact_share)),
    ]
    for index, name in enumerate(LANES):
        features.append(_Feature(f"lane_{name}_share_diff", _token_diff(_lane_share(index))))
        features.append(_Feature(f"lane_{name}_value_matchup", _lane_value_diff(index)))
        features.append(_Feature(f"lane_{name}_front_matchup", _lane_front_diff(index)))
        gap, present = _lane_gap(index)
        features.append(_Feature(f"lane_{name}_gap", gap))
        features.append(_Feature(f"lane_{name}_contested", present))
    for lane_index, lane_name in enumerate(LANES):
        for band_index, band_name in enumerate(BANDS):
            features.append(
                _Feature(f"zone_{lane_name}_{band_name}_value_diff", _token_diff(_zone_value(lane_index, band_index)))
            )
    optional: list[tuple[str, Callable[[PlayerSnapshot], float | None]]] = [
        ("max_core", lambda player: None if player.max_reactor_core is None else float(player.max_reactor_core)),
        ("income", lambda player: None if player.round_supply_income is None else float(player.round_supply_income)),
        ("unlocked_count", _length(lambda player: player.unlocked_unit_ids)),
        ("pool_size", _pool_size),
        ("inventory_count", _length(lambda player: player.equipment_inventory)),
        ("officer_count", _length(lambda player: player.officer_ids)),
        ("commander_skill_count", _length(lambda player: player.commander_skills)),
        ("active_skill_count", _active_skills),
        ("skill_cooldown_sum", _cooldowns),
        ("contraption_count", _length(lambda player: player.contraptions)),
        ("building_count", _length(lambda player: player.buildings)),
        ("tower_strengthen_sum", _tower_levels),
        ("blueprint_count", _length(lambda player: player.blueprint_ids)),
        ("energy_tower_skill_count", _length(lambda player: player.energy_tower_skill_ids)),
        ("card_choice", _choice),
        ("win_rate", _win_rate),
        ("streak", _streak),
        ("last_core_change", _core_change),
        ("last_supply_change", _supply_trend),
        ("last_fight_score", _report("score")),
        ("last_fight_alive_mechs", _report("alive_mech_count")),
        ("last_fight_crystals", _report("destroyed_crystal_count")),
    ]
    for name, value in optional:
        difference, known = _optional_diff(value)
        features.append(_Feature(f"{name}_diff", difference))
        features.append(_Feature(f"{name}_known", known))
    for unit_id in UNIT_IDS:
        own_side = _unit_stat(unit_id)
        features.extend(
            _Feature(f"unit_{unit_id}_{stat}_diff", own_side(stat))
            for stat in ("count", "level", "value", "technology")
        )
    return features


def _unit_stat(unit_id: int) -> Callable[[str], Callable[[MatchSnapshot, int, list[UnitToken]], float]]:
    def stat(name: str) -> Callable[[MatchSnapshot, int, list[UnitToken]], float]:
        def value(tokens: list[UnitToken]) -> float:
            matching = [token for token in tokens if token.unit_id == unit_id]
            if name == "count":
                return float(len(matching))
            if name == "level":
                return float(sum(token.level for token in matching))
            if name == "value":
                return _value(matching)
            return float(sum(len(token.technology_ids) for token in matching))

        return _token_diff(value)

    return stat


_FEATURES = _feature_list()
# Round-scaled copies let the weight of the core, economy and board differences grow as the match goes on.
_ROUND_SCALED = ("core_share_diff", "investment_share_diff", "previous_fight_diff", "formation_count_diff")


def feature_names() -> list[str]:
    return [feature.name for feature in _FEATURES] + [f"log_round_x_{name}" for name in _ROUND_SCALED]


# Context features describe both players at once (masks, lane gaps), so they are equal from either perspective.
SYMMETRIC_FEATURES = frozenset(name for name in feature_names() if name.endswith(("_known", "_gap", "_contested")))


def build_features(snapshot: MatchSnapshot, perspective: int = 0) -> np.ndarray:
    if len(snapshot.players) != 2:
        raise ValueError("The win probability model only supports two-player positions.")
    if perspective not in (0, 1):
        raise ValueError("perspective must be 0 or 1.")
    tokens = unit_tokens(snapshot, perspective)
    values = {feature.name: feature.compute(snapshot, perspective, tokens) for feature in _FEATURES}
    round_scale = math.log1p(max(1, snapshot.match.round))
    scaled = [round_scale * values[name] for name in _ROUND_SCALED]
    return np.asarray([*values.values(), *scaled], dtype=np.float64)
