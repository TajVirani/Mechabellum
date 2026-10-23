import json
from copy import deepcopy
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from mechabellum.contracts import validate_snapshot
from mechabellum.datasets import write_snapshots
from mechabellum.features import feature_names
from mechabellum.inference import predict_snapshot
from mechabellum.models import load_artifact
from mechabellum.training import train_model

ROOT = Path(__file__).resolve().parents[1]


def test_training_and_prediction_pipeline(tmp_path: Path) -> None:
    example = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    snapshots = []
    for index in range(10):
        data = deepcopy(example)
        data["match"]["battleId"] = f"battle-{index}"
        winner = index % 2
        data["outcome"] = {
            "winnerIndex": winner,
            "winnerPlayerId": data["players"][winner]["playerId"],
            "winnerName": data["players"][winner]["name"],
        }
        data["players"][winner]["reactorCore"] += index * 10
        snapshots.append(validate_snapshot(data))

    dataset = tmp_path / "dataset.jsonl"
    model_path = tmp_path / "model.joblib"
    write_snapshots(dataset, snapshots)
    metadata = train_model(dataset, model_path, seed=7)
    artifact = load_artifact(model_path, feature_names())
    result = predict_snapshot(artifact, snapshots[0], model_path)

    assert metadata["usableMatchCount"] == 10
    assert model_path.is_file()
    assert abs(sum(item["winProbability"] for item in result["predictions"]) - 1.0) < 1e-12
