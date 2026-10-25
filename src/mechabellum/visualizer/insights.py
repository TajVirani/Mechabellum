"""What winning boards have, and counters: observed associations over the Match Summaries' fight_over boards.

Each (match, player, round band) is one **observation**: the units and technologies the player had on any of their
boards in that band's rounds, the units the opponent had in the same rounds, and whether the player won the match.
Counting once per band keeps a player who kept a unit for five rounds from counting five times.

- **Winning boards:** per unit and technology, the pick rate (share of observations with it), the win rate when
  present with its Wilson 95% interval, and the lift (that win rate minus the band's baseline win rate).
- **Counters:** for my unit X against the opponent's unit Y, my win rate when I field X and they field Y, against
  my baseline when they field Y. An observed association, not a causal effect: good players and late-game boards
  field some units more, whatever they face.

Entries with fewer than `min_sample` observations are flagged `thin`.
"""

from __future__ import annotations

import math
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..collector.unit_catalog import UNIT_TECHNOLOGIES, technology_name, unit_name
from .baseline import DEFAULT_MODE

# Round bands: early 1-3, mid 4-7, late 8+. "all" pools every round of the match.
EARLY_LAST = 3
MID_LAST = 7
BANDS: dict[str, tuple[int, int | None]] = {
    "early": (1, EARLY_LAST),
    "mid": (EARLY_LAST + 1, MID_LAST),
    "late": (MID_LAST + 1, None),
}
ALL_BANDS = "all"
MIN_SAMPLE = 20
WILSON_Z = 1.959963984540054
COUNTER_TOP = 10
ASSOCIATION_NOTE = (
    "Observed association in the indexed replays, not a causal effect: who fields a unit, and when, also matters."
)
# Technology id -> the unit it belongs to (every id belongs to exactly one unit in game_names.json).
TECHNOLOGY_UNITS: dict[int, int] = {
    technology: unit for unit, technologies in UNIT_TECHNOLOGIES.items() for technology in technologies
}


def round_band(round_number: int) -> str:
    """ "early" (1-3), "mid" (4-7) or "late" (8+); round 0 and below count as early."""
    if round_number <= EARLY_LAST:
        return "early"
    return "mid" if round_number <= MID_LAST else "late"


def wilson_interval(successes: int, n: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    """The Wilson score interval for successes / n; None when n is 0."""
    if n <= 0:
        return None
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class Observation:
    battle_id: str
    player_id: str | None
    won: bool
    units: frozenset[int]
    technologies: frozenset[int]
    opponent_units: frozenset[int]


@dataclass(frozen=True)
class SummaryFilter:
    """Which summaries count: the game mode (modes never mix), and optionally versions and a date range."""

    mode: str = DEFAULT_MODE
    versions: frozenset[str] = frozenset()
    date_from: str | None = None
    date_to: str | None = None

    def passes(self, summary: Mapping[str, Any]) -> bool:
        if (summary.get("gameMode") or DEFAULT_MODE) != self.mode:
            return False
        if self.versions and version_key(summary) not in self.versions:
            return False
        date = summary.get("date")
        if (self.date_from or self.date_to) and not date:
            return False
        if self.date_from and date < self.date_from:
            return False
        return not (self.date_to and date > self.date_to)


def version_key(summary: Mapping[str, Any]) -> str:
    """The Stats view's version filter key (stats.js `versionKey`)."""
    if summary.get("gameVersion"):
        return summary["gameVersion"]
    return "unknown" if summary.get("replayVersion") is None else f"build {summary['replayVersion']}"


def observations(
    summaries: Iterable[Mapping[str, Any]],
    band: str,
    *,
    summary_filter: SummaryFilter | None = None,
    player_id: str | None = None,
) -> list[Observation]:
    """One observation per (match, player) with a board in `band`; only `player_id`'s side when given."""
    if band != ALL_BANDS and band not in BANDS:
        raise ValueError(f"unknown band {band!r}")
    summary_filter = summary_filter or SummaryFilter()
    seen: set[str] = set()
    out: list[Observation] = []
    for summary in summaries:
        battle_id = summary.get("battleId") or summary.get("replayPath") or ""
        players = summary.get("players") or []
        if battle_id in seen or len(players) != 2 or not summary_filter.passes(summary):
            continue
        seen.add(battle_id)
        sides = [_band_boards(player, band) for player in players]
        for index, player in enumerate(players):
            if player_id is not None and player.get("playerId") != player_id:
                continue
            mine, theirs = sides[index], sides[1 - index]
            if not mine:
                continue
            out.append(
                Observation(
                    battle_id=battle_id,
                    player_id=player.get("playerId"),
                    won=bool(player.get("won")),
                    units=frozenset(unit for board in mine for unit in board.get("unitIds", [])),
                    technologies=frozenset(tech for board in mine for tech in board.get("technologyIds", [])),
                    opponent_units=frozenset(unit for board in theirs for unit in board.get("unitIds", [])),
                )
            )
    return out


def _band_boards(player: Mapping[str, Any], band: str) -> list[Mapping[str, Any]]:
    boards = player.get("boards") or []
    if band == ALL_BANDS:
        return list(boards)
    return [board for board in boards if round_band(int(board.get("round", 0))) == band]


def _rate_entry(present: int, wins: int, total: int, baseline: float | None, min_sample: int) -> dict[str, Any]:
    interval = wilson_interval(wins, present)
    win_rate = wins / present if present else None
    return {
        "n": present,
        "wins": wins,
        "pickRate": present / total if total else None,
        "winRate": win_rate,
        "interval": None if interval is None else list(interval),
        "lift": None if win_rate is None or baseline is None else win_rate - baseline,
        "thin": present < min_sample,
    }


def _by_lift(row: Mapping[str, Any]) -> tuple[bool, float, int]:
    return (row["thin"], -(row["lift"] if row["lift"] is not None else -math.inf), -row["n"])


def winning_boards(rows: Sequence[Observation], min_sample: int = MIN_SAMPLE) -> dict[str, Any]:
    """Per unit and per technology: pick rate, win rate when present (Wilson 95%), lift over the baseline.

    Sorted by lift, entries with at least `min_sample` observations first.
    """
    total = len(rows)
    wins = sum(row.won for row in rows)
    baseline = wins / total if total else None
    unit_counts: Counter[int] = Counter()
    unit_wins: Counter[int] = Counter()
    technology_counts: Counter[int] = Counter()
    technology_wins: Counter[int] = Counter()
    for row in rows:
        unit_counts.update(row.units)
        technology_counts.update(row.technologies)
        if row.won:
            unit_wins.update(row.units)
            technology_wins.update(row.technologies)
    units = [
        {"unitId": unit, "name": unit_name(unit), **_rate_entry(n, unit_wins[unit], total, baseline, min_sample)}
        for unit, n in unit_counts.items()
    ]
    technologies = []
    for technology, n in technology_counts.items():
        owner = TECHNOLOGY_UNITS.get(technology)
        technologies.append(
            {
                "technologyId": technology,
                "name": technology_name(technology),
                "unitId": owner,
                "unitName": None if owner is None else unit_name(owner),
                **_rate_entry(n, technology_wins[technology], total, baseline, min_sample),
            }
        )
    units.sort(key=_by_lift)
    technologies.sort(key=_by_lift)
    interval = wilson_interval(wins, total)
    return {
        "n": total,
        "wins": wins,
        "baselineWinRate": baseline,
        "baselineInterval": None if interval is None else list(interval),
        "units": units,
        "technologies": technologies,
    }


def counter_table(
    rows: Sequence[Observation],
    min_sample: int = MIN_SAMPLE,
    *,
    enemies: Iterable[int] | None = None,
    top: int | None = COUNTER_TOP,
) -> list[dict[str, Any]]:
    """Per enemy unit Y: my baseline win rate when they field Y, and each of my units X against it.

    `delta` is the win rate with X against Y minus the baseline against Y. Each Y's rows are sorted by delta,
    entries with at least `min_sample` observations first, and cut to `top` (None: all). Enemies are those given,
    else every Y seen, most observed first.
    """
    against: Counter[int] = Counter()
    against_wins: Counter[int] = Counter()
    pairs: Counter[tuple[int, int]] = Counter()
    pair_wins: Counter[tuple[int, int]] = Counter()
    enemies = None if enemies is None else list(dict.fromkeys(enemies))
    wanted = None if enemies is None else set(enemies)
    for row in rows:
        theirs = row.opponent_units if wanted is None else row.opponent_units & wanted
        if not theirs:
            continue
        against.update(theirs)
        combos = [(mine, enemy) for enemy in theirs for mine in row.units]
        pairs.update(combos)
        if row.won:
            against_wins.update(theirs)
            pair_wins.update(combos)
    order = enemies if enemies is not None else [unit for unit, _ in against.most_common()]
    by_enemy: dict[int, list[dict[str, Any]]] = {enemy: [] for enemy in order}
    for (mine, enemy), n in pairs.items():
        baseline = against_wins[enemy] / against[enemy]
        entry = _rate_entry(n, pair_wins[(mine, enemy)], against[enemy], baseline, min_sample)
        entry["delta"] = entry.pop("lift")
        # "pickRate" here: the share of games against Y in which I fielded X.
        by_enemy[enemy].append({"unitId": mine, "name": unit_name(mine), **entry})
    table = []
    for enemy in order:
        n = against[enemy]
        items = sorted(by_enemy[enemy], key=lambda item: (item["thin"], -item["delta"], -item["n"]))
        interval = wilson_interval(against_wins[enemy], n)
        table.append(
            {
                "enemyUnitId": enemy,
                "enemyName": unit_name(enemy),
                "n": n,
                "baselineWinRate": against_wins[enemy] / n if n else None,
                "baselineInterval": None if interval is None else list(interval),
                "thin": n < min_sample,
                "rows": items if top is None else items[:top],
            }
        )
    return table


class Insights:
    """Winning-board and counter tables over the hub's current summaries, cached until the summaries change.

    `snapshot` returns (generation, summaries); a new generation drops every cached table.
    """

    CACHE_LIMIT = 64

    def __init__(self, snapshot: Callable[[], tuple[int, list[dict[str, Any]]]]) -> None:
        self._snapshot = snapshot
        self._lock = threading.Lock()
        self._generation: int | None = None
        self._cache: dict[tuple[Any, ...], Any] = {}

    def generation(self) -> int:
        """The summaries' current generation; it changes whenever they do."""
        return self._snapshot()[0]

    def winning_boards(
        self,
        summary_filter: SummaryFilter,
        *,
        player_id: str | None = None,
        min_sample: int = MIN_SAMPLE,
    ) -> dict[str, Any]:
        bands = {
            band: winning_boards(self._observations(band, summary_filter, player_id), min_sample) for band in BANDS
        }
        return {
            "mode": summary_filter.mode,
            "playerId": player_id,
            "minSample": min_sample,
            "bands": {band: {"rounds": _band_label(band), **table} for band, table in bands.items()},
        }

    def counters(
        self,
        summary_filter: SummaryFilter,
        *,
        band: str = ALL_BANDS,
        player_id: str | None = None,
        enemies: Sequence[int] | None = None,
        min_sample: int = MIN_SAMPLE,
        top: int | None = COUNTER_TOP,
    ) -> dict[str, Any]:
        rows = self._observations(band, summary_filter, player_id)
        return {
            "mode": summary_filter.mode,
            "band": band,
            "playerId": player_id,
            "minSample": min_sample,
            "n": len(rows),
            "enemies": counter_table(rows, min_sample, enemies=enemies, top=top),
            "note": ASSOCIATION_NOTE,
        }

    def _observations(self, band: str, summary_filter: SummaryFilter, player_id: str | None) -> list[Observation]:
        generation, summaries = self._snapshot()
        key = (band, summary_filter, player_id)
        with self._lock:
            if generation != self._generation:
                self._generation = generation
                self._cache = {}
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = observations(summaries, band, summary_filter=summary_filter, player_id=player_id)
        with self._lock:
            if generation == self._generation:
                if len(self._cache) >= self.CACHE_LIMIT:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = rows
        return rows


def _band_label(band: str) -> str:
    low, high = BANDS[band]
    return f"{low}+" if high is None else f"{low}-{high}"
