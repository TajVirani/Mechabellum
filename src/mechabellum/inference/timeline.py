from __future__ import annotations

from pathlib import Path
from typing import Any

from ..datasets import load_training_snapshots
from .predictor import load_artifact, predict_snapshot


def render_timeline(dataset_path: Path, model_path: Path, battle_id: str | None = None) -> dict[str, Any]:
    artifact = load_artifact(model_path)
    snapshots = load_training_snapshots(dataset_path)
    if not snapshots:
        raise ValueError("The dataset contains no usable training snapshots.")
    selected_battle_id = battle_id or snapshots[-1].match.battle_id
    selected = sorted(
        (snapshot for snapshot in snapshots if snapshot.match.battle_id == selected_battle_id),
        key=lambda snapshot: snapshot.match.round,
    )
    if not selected:
        raise ValueError(f"Match not found in dataset: {selected_battle_id}")
    outcome = selected[-1].outcome
    if outcome is None:
        raise ValueError("The selected match has no final winner label.")
    rounds = []
    for snapshot in selected:
        prediction = predict_snapshot(artifact, snapshot, model_path)
        rounds.append(
            {
                "round": snapshot.match.round,
                "players": [
                    {"name": item["name"], "winPercent": item["winPercent"]} for item in prediction["predictions"]
                ],
            }
        )
    return {
        "battleId": selected_battle_id,
        "snapshotPhase": "battle_start",
        "finalWinner": outcome.winner_name,
        "rounds": rounds,
    }
