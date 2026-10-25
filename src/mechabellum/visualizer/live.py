"""The live source thread (game memory or a `live-record` playback) and what it derives from each frame.

For every distinct frame: rating capture, Local Player detection, board composition, the `frame` event, and a win
prediction at each fight's end, made exactly as `mecha live-predict` makes it.
"""

from __future__ import annotations

import json
import sys
import threading
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Protocol

from ..collector.memory.live_source import ObserverStateError
from ..collector.memory.recorder import SnapshotSource
from ..collector.unit_catalog import card_name
from ..contracts import MODEL_SNAPSHOT_PHASE, MatchSnapshot, snapshot_to_dict
from ..inference.live_history import FightOverHistory
from .bridge_status import BridgeStatus, probe_bridge
from .cache import SummaryCache
from .hub import Hub
from .roles import board_composition

READ_INTERVAL_SECONDS = 0.5
ATTACH_RETRY_SECONDS = 3.0
BRIDGE_PROBE_SECONDS = 15.0
# Consecutive failed reads after which the process is assumed gone and re-attached.
REATTACH_AFTER_FAILURES = 10


class WinPredictor(Protocol):
    def __call__(self, snapshot: MatchSnapshot) -> list[float]: ...


def model_looks_available(model_path: Path) -> bool:
    """A quick guess, without importing the model stack: the artifact exists and the `ml` extra is installed."""
    modules = ("torch",) if model_path.suffix == ".pt" else ("joblib", "sklearn", "numpy")
    return model_path.is_file() and all(find_spec(module) is not None for module in modules)


def load_model(model_path: Path) -> dict[str, Any] | None:
    """The trained model artifact, or None without the `ml` extra or the artifact."""
    try:
        from ..inference import load_artifact

        return load_artifact(model_path)
    except Exception:
        return None


def load_predictor(model_path: Path) -> WinPredictor | None:
    """The trained model's per-player win probabilities, or None without the `ml` extra or the artifact."""
    artifact = load_model(model_path)
    return None if artifact is None else predictor_from_artifact(artifact, model_path)


def predictor_from_artifact(artifact: dict[str, Any], model_path: Path) -> WinPredictor:
    """Per-player win probabilities from a loaded artifact, as `mecha live-predict` computes them."""
    from ..inference import predict_snapshot

    def predict(snapshot: MatchSnapshot) -> list[float]:
        result = predict_snapshot(artifact, snapshot, model_path)
        return [float(item["winProbability"]) for item in result["predictions"]]

    return predict


class LiveProcessor:
    """Turns live frames into hub events: frames, ratings and per-round predictions."""

    def __init__(self, hub: Hub, cache: SummaryCache, predictor: WinPredictor | None = None) -> None:
        self._hub = hub
        self._cache = cache
        self._predictor = predictor
        self._lock = threading.Lock()
        self._previous: str | None = None
        self._history = FightOverHistory()
        self._emitted: set[tuple[str | None, int]] = set()
        self._battle_id: str | None = None
        # One per predicted round: {"round", "probabilities": [player 0, player 1]}.
        self._rounds: list[dict[str, Any]] = []
        self._snapshot: MatchSnapshot | None = None

    def process(self, snapshot: MatchSnapshot) -> bool:
        """Handle one frame; False when it only differs from the previous one in its capture time."""
        with self._lock:
            stable = snapshot.model_copy(
                update={"source": snapshot.source.model_copy(update={"captured_at_utc": None})}
            )
            fingerprint = json.dumps(snapshot_to_dict(stable), separators=(",", ":"))
            if fingerprint == self._previous:
                return False
            self._previous = fingerprint
            # A frame without a battle id (read between matches) doesn't start a new battle.
            battle_id = snapshot.match.battle_id
            if self._snapshot is None or (battle_id is not None and battle_id != self._battle_id):
                self._battle_id = snapshot.match.battle_id
                self._rounds = []
                self._hub.set_predictions(self._battle_id, [])
            self._capture_ratings(snapshot)
            self._snapshot = snapshot
            local = self._local_index(snapshot)
            self._hub.set_frame(self._frame(snapshot, local))
            self._predict(snapshot, local)
            return True

    def set_predictor(self, predictor: WinPredictor | None) -> None:
        with self._lock:
            self._predictor = predictor

    def refresh_local_player(self) -> None:
        """Re-send the current frame and predictions after the Local Player id changed."""
        with self._lock:
            if self._snapshot is None:
                return
            local = self._local_index(self._snapshot)
            self._hub.set_frame(self._frame(self._snapshot, local))
            self._hub.set_predictions(self._battle_id, self._prediction_rows(local))

    def _capture_ratings(self, snapshot: MatchSnapshot) -> None:
        battle_id = snapshot.match.battle_id
        if battle_id is None:
            return
        for player in snapshot.players:
            if player.player_id is None or player.rating is None:
                continue
            if self._cache.store_rating(battle_id, player.player_id, player.rating):
                self._hub.add_rating(battle_id, player.player_id, player.rating)

    def _local_index(self, snapshot: MatchSnapshot) -> int | None:
        """The Local Player's index; without a configured id, the suggested id counts (but isn't persisted)."""
        player_id = self._hub.local_player_id or self._hub.suggested_player_id
        if player_id is None:
            return None
        return next((index for index, player in enumerate(snapshot.players) if player.player_id == player_id), None)

    def _frame(self, snapshot: MatchSnapshot, local: int | None) -> dict[str, Any]:
        deploying = snapshot.match.phase == "deploying"
        return {
            "snapshot": snapshot_to_dict(snapshot),
            "localIndex": local,
            # Names of `snapshot.match.reinforcementOffer`, in the same order.
            "offerNames": [card_name(card_id) for card_id in snapshot.match.reinforcement_offer or []],
            "composition": [board_composition(player.units, snapshot.match.round) for player in snapshot.players],
            # While playing, memory shows the opponent's board as it was at the last fight until this one starts.
            "boardAsOfLastFight": [
                local is not None and deploying and index != local for index in range(len(snapshot.players))
            ],
        }

    def _predict(self, snapshot: MatchSnapshot, local: int | None) -> None:
        key = (self._battle_id, snapshot.match.round)
        # The board is cleared when the match ends, so skip fight_over frames without units (as live-predict does).
        ready = snapshot.match.phase == MODEL_SNAPSHOT_PHASE and all(player.units for player in snapshot.players)
        if not ready or key in self._emitted or self._predictor is None:
            return
        self._emitted.add(key)
        try:
            probabilities = self._predictor(self._history.update(snapshot))
        except Exception as error:
            print(f"Visualizer: prediction failed: {error}", file=sys.stderr, flush=True)
            return
        self._rounds.append({"round": snapshot.match.round, "probabilities": probabilities})
        self._hub.add_prediction(self._battle_id, self._prediction_rows(local)[-1])

    def _prediction_rows(self, local: int | None) -> list[dict[str, Any]]:
        """Rows from the left player's view: the Local Player, or player 0 when spectating."""
        left = local or 0
        rows = []
        previous: float | None = None
        for item in self._rounds:
            probability = item["probabilities"][left]
            rows.append(
                {
                    "round": item["round"],
                    "leftWinProbability": probability,
                    "swing": 0.0 if previous is None else probability - previous,
                }
            )
            previous = probability
        return rows


def run_memory(
    processor: LiveProcessor,
    hub: Hub,
    stop: threading.Event,
    *,
    attach: Callable[[], Any] | None = None,
    interval_seconds: float = READ_INTERVAL_SECONDS,
    attach_retry_seconds: float = ATTACH_RETRY_SECONDS,
) -> None:
    """Read the running game until `stop`, re-attaching every few seconds while it isn't running."""
    if attach is None:
        from ..collector.memory import LiveMemorySource

        attach = LiveMemorySource.attach
    source: SnapshotSource | None = None
    failures = 0
    while not stop.is_set():
        if source is None:
            try:
                source = attach()
            except Exception as error:
                state = "layout_mismatch" if "not supported" in str(error) else "no_game"
                hub.update_status(state=state, detail=str(error))
                stop.wait(attach_retry_seconds)
                continue
            failures = 0
            layout = getattr(source, "layout", None)
            game_version = None if layout is None else f"{layout.game_version}.{layout.replay_version}"
            hub.update_status(state="waiting", detail="Attached to Mechabellum.", gameVersion=game_version)
        try:
            snapshot = source.read_snapshot()
        except ObserverStateError as error:
            failures = 0
            hub.update_status(state="waiting", detail=str(error))
        except Exception as error:
            # OSError and ValueError are the reads that fail while the game rebuilds its objects; retry them.
            failures += 1
            state = "layout_mismatch" if "Layout validation failed" in str(error) else "retrying"
            hub.update_status(state=state, detail=f"Read failed, retrying: {error}")
            if failures >= REATTACH_AFTER_FAILURES:
                _close(source)
                source = None
        else:
            failures = 0
            hub.update_status(state="live", detail=None)
            _process(processor, snapshot)
        stop.wait(interval_seconds)
    if source is not None:
        _close(source)


def run_playback(
    processor: LiveProcessor,
    hub: Hub,
    path: Path,
    stop: threading.Event,
    *,
    speed: float = 1.0,
    wait: Callable[[float], object] | None = None,
) -> int:
    """Feed a `live-record` JSONL file through `processor`, paced by `capturedAtUtc / speed` (0: no waiting).

    Returns the number of frames read. The last frame stays current afterwards.
    """
    wait = wait or stop.wait
    hub.update_status(state="waiting", detail=f"Playing back {path.name}.")
    previous = None
    frames = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if stop.is_set():
                return frames
            if not line.strip():
                continue
            try:
                snapshot = MatchSnapshot.model_validate_json(line)
            except ValueError as error:
                print(f"Visualizer: skipped a playback line: {error}", file=sys.stderr, flush=True)
                continue
            captured = snapshot.source.captured_at_utc
            if speed > 0 and previous is not None and captured is not None:
                delay = (captured - previous).total_seconds() / speed
                if delay > 0:
                    wait(delay)
                    if stop.is_set():
                        return frames
            previous = captured or previous
            frames += 1
            build = snapshot.game_build
            game_version = (
                None
                if build.game_version is None
                else build.game_version
                if build.replay_version is None
                else f"{build.game_version}.{build.replay_version}"
            )
            hub.update_status(state="live", detail=None, gameVersion=game_version)
            _process(processor, snapshot)
    hub.update_status(state="playback_done", detail=f"Played back {frames} frames from {path.name}.")
    return frames


def run_bridge_probe(
    hub: Hub,
    stop: threading.Event,
    *,
    probe: Callable[[], BridgeStatus] = probe_bridge,
    interval_seconds: float = BRIDGE_PROBE_SECONDS,
) -> None:
    """Ask MechaBridge for its status (StatusRequest only) every ~15 s."""
    while not stop.is_set():
        status = probe()
        changes: dict[str, Any] = {"bridge": status.state}
        if status.game_version:
            changes["gameVersion"] = status.game_version
        hub.update_status(**changes)
        stop.wait(interval_seconds)


def _process(processor: LiveProcessor, snapshot: MatchSnapshot) -> None:
    try:
        processor.process(snapshot)
    except Exception as error:
        print(f"Visualizer: could not process a live frame: {error}", file=sys.stderr, flush=True)


def _close(source: object) -> None:
    close = getattr(source, "close", None)
    if close is not None:
        try:
            close()
        except Exception:
            pass
