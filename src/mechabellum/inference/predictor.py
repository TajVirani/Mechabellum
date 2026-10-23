from __future__ import annotations

from pathlib import Path
from typing import Any

from ..contracts import MatchSnapshot
from ..features import build_features, feature_names
from ..models import load_artifact as _load_artifact


def load_artifact(model_path: Path) -> dict[str, Any]:
    return _load_artifact(model_path, feature_names())


def predict_snapshot(artifact: dict[str, Any], snapshot: MatchSnapshot, model_path: Path) -> dict[str, Any]:
    if len(snapshot.players) != 2:
        raise ValueError("The win predictor only supports 1v1 positions.")

    model = artifact["model"]
    raw = [float(model.predict_proba(build_features(snapshot, index).reshape(1, -1))[0, 1]) for index in (0, 1)]
    total = sum(raw)
    probabilities = [0.5, 0.5] if total <= 0 else [value / total for value in raw]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "battleId": snapshot.match.battle_id,
        "round": snapshot.match.round,
        "snapshotPhase": snapshot.match.phase,
        "predictions": [
            {
                "playerId": player.player_id,
                "name": player.name,
                "winProbability": probability,
                "winPercent": round(probability * 100, 1),
            }
            for player, probability in zip(snapshot.players, probabilities, strict=True)
        ],
        "model": str(model_path.resolve()),
    }
    if snapshot.match.phase != "battle_start":
        result["warning"] = f"Input phase is {snapshot.match.phase}; the model was trained on battle_start."
    return result
