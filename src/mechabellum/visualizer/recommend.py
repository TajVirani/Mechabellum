"""Live recommended purchases: `mecha recommend`'s ranking, run on the current match's frames.

On each new deploying or fight_over frame (deduplicated on what the ranking depends on), a worker thread ranks the
candidate buys, unlocks, upgrades, technologies and offered cards with `inference.actions` for the Local Player, or
for both players when spectating, and sends one `recommendations` event. Moves are left out. The ranking is the win
model's static judgement of the changed board: no fight is simulated.

Each player's entry also lists counters against the opponent's current units: from the indexed replays, which of
my units did well when the opponent fielded that unit (insights.py). That part needs no model.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Sequence
from typing import Any

from ..collector.unit_catalog import card_name, technology_name, unit_name
from ..contracts import MODEL_SNAPSHOT_PHASE, MatchSnapshot
from ..inference.actions import ActionCatalog, RankedAction, candidate_actions, rank_actions
from ..inference.live_history import FightOverHistory
from .baseline import DEFAULT_MODE
from .cache import SummaryCache
from .hub import Hub
from .insights import ASSOCIATION_NOTE, MIN_SAMPLE, Insights, SummaryFilter, round_band
from .live import LiveProcessor, WinPredictor

RECOMMEND_PHASES = ("deploying", MODEL_SNAPSHOT_PHASE)
TOP_ACTIONS = 8
COUNTER_SUGGESTIONS = 3
RANKING_NOTE = "The win model's static judgement of the changed board; no fight is simulated."

Ranker = Callable[..., tuple[float, list[RankedAction]]]


def recommendation_rows(ranked: Sequence[RankedAction], top: int = TOP_ACTIONS) -> list[dict[str, Any]]:
    """The best `top` actions, moves left out, keeping the best placement per unit (buys, unlocks, upgrades)."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in ranked:
        action = item.action
        parameters = action.parameters
        if action.kind == "move":
            continue
        if action.kind in ("buy", "unlock"):
            unit_id = parameters["unitId"]
            key: tuple[Any, ...] = (action.kind, unit_id)
            label = f"{'Buy' if action.kind == 'buy' else 'Unlock'} {unit_name(unit_id)}"
            ids = {"unitId": unit_id}
        elif action.kind == "upgrade":
            unit_id = parameters.get("unitId")
            key = (action.kind, unit_id if unit_id is not None else parameters["formation"])
            label = f"Upgrade {unit_name(unit_id)}" if unit_id is not None else action.description
            ids = {"unitId": unit_id, "formation": parameters["formation"]}
        elif action.kind == "technology":
            unit_id, technology = parameters["unitId"], parameters["technologyId"]
            key = (action.kind, technology)
            label = f"{technology_name(technology)} ({unit_name(unit_id)})"
            ids = {"unitId": unit_id, "technologyId": technology}
        else:
            key = (action.kind, parameters["itemId"])
            label = f"Pick {card_name(parameters['itemId'])}"
            ids = {"itemId": parameters["itemId"], "effect": parameters.get("effect")}
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "kind": action.kind,
                "label": label,
                **ids,
                "cost": action.estimated_cost,
                "winProbability": item.win_probability,
                "gain": item.gain,
                "description": action.description,
            }
        )
        if len(rows) >= top:
            break
    return rows


def rank_player(
    artifact: dict[str, Any],
    snapshot: MatchSnapshot,
    perspective: int,
    catalog: ActionCatalog,
    cards: Sequence[int] = (),
    *,
    top: int = TOP_ACTIONS,
    rank: Ranker = rank_actions,
) -> dict[str, Any]:
    """`mecha recommend` for one player, without moves: the baseline and the best rows."""
    candidates = [
        action
        for action in candidate_actions(snapshot, perspective, catalog, cards, unlocks=True)
        if action.kind != "move"
    ]
    # Upgrades only name their formation; carry the unit id so rows can group by unit.
    units = snapshot.players[perspective].units
    for action in candidates:
        if action.kind == "upgrade":
            action.parameters.setdefault("unitId", units[action.parameters["formation"]].unit_id)
    baseline, ranked = rank(artifact, snapshot, perspective, candidates)
    return {"baselineWinProbability": baseline, "candidates": len(candidates), "rows": recommendation_rows(ranked, top)}


class LiveRecommender:
    """Ranks purchases for the current frame on its own thread and sends `recommendations` through the hub."""

    def __init__(
        self,
        hub: Hub,
        insights: Insights | None = None,
        *,
        catalog: ActionCatalog | None = None,
        top: int = TOP_ACTIONS,
        rank: Ranker = rank_actions,
        min_sample: int = MIN_SAMPLE,
    ) -> None:
        self._hub = hub
        self._insights = insights
        self._catalog = catalog or ActionCatalog.from_game_data()
        self._top = top
        self._rank = rank
        self._min_sample = min_sample
        self._artifact: dict[str, Any] | None = None
        self._condition = threading.Condition()
        self._pending: tuple[MatchSnapshot, int | None] | None = None
        self._last_key: tuple[Any, ...] | None = None
        self._history = FightOverHistory()
        # The last fight_over frame with filled histories, per battle: a deploying frame borrows its histories.
        self._fight_over: dict[str | None, MatchSnapshot] = {}

    def set_artifact(self, artifact: dict[str, Any] | None) -> None:
        with self._condition:
            self._artifact = artifact
            self._last_key = None

    def submit(self, snapshot: MatchSnapshot, local: int | None, *, force: bool = False) -> bool:
        """Queue this frame when it is a deploying or fight_over frame that changes the ranking; True when queued."""
        with self._condition:
            prepared = self._history.update(snapshot)
            if snapshot.match.phase == MODEL_SNAPSHOT_PHASE:
                self._fight_over = {snapshot.match.battle_id: prepared}
            if not _wanted(snapshot):
                return False
            key = _ranking_key(snapshot, local)
            if not force and key == self._last_key:
                return False
            self._last_key = key
            self._pending = (self._with_histories(prepared), local)
            self._condition.notify_all()
            return True

    def run(self, stop: threading.Event, poll_seconds: float = 0.5) -> None:
        """Process queued frames until `stop`; only the latest queued frame is ranked."""
        while not stop.is_set():
            with self._condition:
                if self._pending is None:
                    self._condition.wait(poll_seconds)
            self.flush()

    def flush(self) -> dict[str, Any] | None:
        """Rank the queued frame now, if any, and send it; returns the payload."""
        with self._condition:
            pending, self._pending = self._pending, None
            artifact = self._artifact
        if pending is None:
            return None
        try:
            payload = self.compute(pending[0], pending[1], artifact)
        except Exception as error:
            print(f"Visualizer: recommendations failed: {error}", file=sys.stderr, flush=True)
            return None
        self._hub.set_recommendations(payload)
        return payload

    def compute(self, snapshot: MatchSnapshot, local: int | None, artifact: dict[str, Any] | None) -> dict[str, Any]:
        """The `recommendations` payload for one prepared frame."""
        match = snapshot.match
        fight_over = match.phase == MODEL_SNAPSHOT_PHASE
        perspectives = [local] if local is not None else list(range(len(snapshot.players)))
        players = []
        for index in perspectives:
            # At a fight's end the next round's income isn't known yet; this round's income is the estimate.
            position = _with_budget(snapshot, index) if fight_over else snapshot
            player = position.players[index]
            entry: dict[str, Any] = {
                "index": index,
                "playerId": player.player_id,
                "name": player.name,
                "budget": player.supply,
                "baselineWinProbability": None,
                "candidates": 0,
                "rows": [],
            }
            if artifact is not None:
                cards = (match.reinforcement_offer or []) if index == local else []
                entry.update(
                    rank_player(artifact, position, index, self._catalog, cards, top=self._top, rank=self._rank)
                )
            entry["counters"] = self._counters(snapshot, index)
            players.append(entry)
        return {
            "battleId": match.battle_id,
            "round": match.round,
            "phase": match.phase,
            "localIndex": local,
            "modelAvailable": artifact is not None,
            "budgetEstimated": fight_over,
            "players": players,
            "counterBand": round_band(match.round),
            "minSample": self._min_sample,
            "note": RANKING_NOTE,
            "counterNote": ASSOCIATION_NOTE,
        }

    def _counters(self, snapshot: MatchSnapshot, index: int) -> list[dict[str, Any]]:
        """For each opponent unit type (most supply first): my units that did well against it, non-thin only."""
        if self._insights is None or len(snapshot.players) != 2:
            return []
        mine = {unit.unit_id for unit in snapshot.players[index].units}
        invested: dict[int, int] = {}
        for unit in snapshot.players[1 - index].units:
            invested[unit.unit_id] = invested.get(unit.unit_id, 0) + max(unit.sell_supply, 0)
        enemies = sorted(invested, key=lambda unit: -invested[unit])
        if not enemies:
            return []
        table = self._insights.counters(
            SummaryFilter(mode=snapshot.match.game_mode or DEFAULT_MODE),
            band=round_band(snapshot.match.round),
            enemies=enemies,
            min_sample=self._min_sample,
            top=None,
        )
        out = []
        for entry in table["enemies"]:
            good = [row for row in entry["rows"] if not row["thin"] and row["delta"] > 0][:COUNTER_SUGGESTIONS]
            out.append(
                {
                    **{key: entry[key] for key in ("enemyUnitId", "enemyName", "n", "baselineWinRate", "thin")},
                    "rows": [{**row, "owned": row["unitId"] in mine} for row in good],
                }
            )
        return out

    def _with_histories(self, snapshot: MatchSnapshot) -> MatchSnapshot:
        """A deploying frame with the core and supply histories of the same battle's last fight_over frame."""
        if snapshot.match.phase == MODEL_SNAPSHOT_PHASE:
            return snapshot
        source = self._fight_over.get(snapshot.match.battle_id)
        if source is None or len(source.players) != len(snapshot.players):
            return snapshot
        players = [
            player.model_copy(
                update={
                    "reactor_core_history": player.reactor_core_history or earlier.reactor_core_history,
                    "supply_history": player.supply_history or earlier.supply_history,
                }
            )
            for player, earlier in zip(snapshot.players, source.players, strict=True)
        ]
        return snapshot.model_copy(update={"players": players})


class RecommendingProcessor(LiveProcessor):
    """The live processor, also handing each new frame to a LiveRecommender."""

    def __init__(
        self,
        hub: Hub,
        cache: SummaryCache,
        recommender: LiveRecommender,
        predictor: WinPredictor | None = None,
    ) -> None:
        super().__init__(hub, cache, predictor)
        self.recommender = recommender

    def process(self, snapshot: MatchSnapshot) -> bool:
        changed = super().process(snapshot)
        if changed:
            self.recommender.submit(snapshot, self._local_index(snapshot))
        return changed

    def refresh_local_player(self) -> None:
        super().refresh_local_player()
        snapshot = self._snapshot
        if snapshot is not None:
            self.recommender.submit(snapshot, self._local_index(snapshot), force=True)


def _wanted(snapshot: MatchSnapshot) -> bool:
    match = snapshot.match
    if match.phase not in RECOMMEND_PHASES or match.round < 1 or len(snapshot.players) != 2:
        return False
    # The boards are cleared when the match ends; skip fight_over frames without units, as predictions do.
    return match.phase != MODEL_SNAPSHOT_PHASE or all(player.units for player in snapshot.players)


def _ranking_key(snapshot: MatchSnapshot, local: int | None) -> tuple[Any, ...]:
    """What the ranking depends on; unit positions are left out so dragging a formation doesn't re-rank."""
    match = snapshot.match
    players = tuple(
        (
            player.supply,
            tuple(sorted((unit.unit_id, unit.raw_level) for unit in player.units)),
            tuple(sorted(tech for item in player.active_technologies for tech in item.technology_ids)),
            tuple(sorted(player.unlocked_unit_ids or [])),
        )
        for player in snapshot.players
    )
    return (match.battle_id, match.round, match.phase, local, tuple(match.reinforcement_offer or []), players)


def _with_budget(snapshot: MatchSnapshot, index: int) -> MatchSnapshot:
    player = snapshot.players[index]
    if player.supply is None or not player.round_supply_income:
        return snapshot
    players = list(snapshot.players)
    players[index] = player.model_copy(update={"supply": player.supply + player.round_supply_income})
    return snapshot.model_copy(update={"players": players})
