"""Round value targets and rewards built from consecutive fight_over snapshots of the same match."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..contracts import MatchSnapshot

DAMAGE_WEIGHT = 0.7
SURVIVOR_WEIGHT = 0.3


def _share(own: float, other: float) -> float:
    total = abs(own) + abs(other)
    return 0.0 if total == 0 else (own - other) / total


def fight_advantage(snapshot: MatchSnapshot, perspective: int) -> float | None:
    """How the fight that `snapshot` closes went for `perspective`, in [-1, 1].

    It mixes the normalized difference in core damage dealt (the fight reports' scores) with the normalized
    difference in surviving mechs; None when either report is missing.
    """
    own = snapshot.players[perspective].last_fight_report
    other = snapshot.players[1 - perspective].last_fight_report
    if own is None or other is None:
        return None
    damage = _share(own.score, other.score)
    if own.alive_mech_count is None or other.alive_mech_count is None:
        return damage
    survivors = _share(own.alive_mech_count, other.alive_mech_count)
    return max(-1.0, min(1.0, DAMAGE_WEIGHT * damage + SURVIVOR_WEIGHT * survivors))


def next_fight_advantages(snapshots: Sequence[MatchSnapshot]) -> dict[tuple[str, int, int], float | None]:
    """(battle id, round, perspective) -> advantage of the following fight, played from this position.

    The last snapshot of a match, or one whose next round is missing, maps to None.
    """
    by_round = {
        (snapshot.match.battle_id, snapshot.match.round): snapshot
        for snapshot in snapshots
        if snapshot.match.battle_id is not None
    }
    targets: dict[tuple[str, int, int], float | None] = {}
    for battle_id, round_number in by_round:
        following = by_round.get((battle_id, round_number + 1))
        for perspective in (0, 1):
            targets[(battle_id, round_number, perspective)] = (  # type: ignore[index]
                None if following is None else fight_advantage(following, perspective)
            )
    return targets


@dataclass(frozen=True)
class RewardConfig:
    """Final win/loss plus discounted, clipped round advantages.

    `round_weight` is the most the round terms can add up to: the discounted sum of clipped advantages is divided
    by its largest possible value, so with `round_weight < 1` no run of local wins can turn a final loss into a
    positive reward.
    """

    gamma: float = 0.9
    round_weight: float = 0.3
    clip: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.round_weight < 1:
            raise ValueError("round_weight must be in [0, 1) so round rewards never outweigh the final result.")
        if not 0 < self.gamma <= 1 or self.clip <= 0:
            raise ValueError("gamma must be in (0, 1] and clip positive.")


DEFAULT_REWARD = RewardConfig()


def reward(final_win: bool, round_advantages: Sequence[float | None], config: RewardConfig = DEFAULT_REWARD) -> float:
    """Reward of one player's trajectory; unknown round advantages count as 0."""
    terms = [
        config.gamma**step * max(-config.clip, min(config.clip, advantage or 0.0)) / config.clip
        for step, advantage in enumerate(round_advantages)
    ]
    largest = sum(config.gamma**step for step in range(len(terms))) or 1.0
    return (1.0 if final_win else -1.0) + config.round_weight * sum(terms) / largest
