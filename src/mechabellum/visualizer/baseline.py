"""Winning-board role baseline: the mean composition of every summary's winner, per game mode, by round and overall."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .roles import mean_composition

THIN_BELOW = 5
# Always present in `byMode`, and the mode a summary without one counts under.
DEFAULT_MODE = "Normal"


def compute_baseline(summaries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """`byMode[mode]` holds that mode's `byRound` and `overall`. Modes never mix: AsyncBattle's unit ids differ."""
    by_mode: dict[str, list[Mapping[str, Any]]] = {DEFAULT_MODE: []}
    for summary in summaries:
        by_mode.setdefault(summary.get("gameMode") or DEFAULT_MODE, []).append(summary)
    return {"byMode": {mode: mode_baseline(rows) for mode, rows in sorted(by_mode.items())}}


def mode_baseline(summaries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """`byRound[r]` averages the winners' round-r boards; `overall` averages all of them. `thin` marks n < 5."""
    by_round: dict[int, list[Mapping[str, Any]]] = {}
    for summary in summaries:
        for player in summary.get("players", []):
            if not player.get("won"):
                continue
            for composition in player.get("composition", []):
                by_round.setdefault(int(composition["round"]), []).append(composition)
    rounds = {str(round_number): _entry(by_round[round_number]) for round_number in sorted(by_round)}
    every = [composition for items in by_round.values() for composition in items]
    return {"byRound": rounds, "overall": _entry(every)}


def _entry(compositions: list[Mapping[str, Any]]) -> dict[str, Any]:
    mean = mean_composition(compositions)
    mean["thin"] = mean["n"] < THIN_BELOW
    return mean
