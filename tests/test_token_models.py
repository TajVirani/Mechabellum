import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")

from mechabellum.contracts import validate_snapshot
from mechabellum.datasets import write_snapshots
from mechabellum.features import feature_names
from mechabellum.inference import predict_snapshot
from mechabellum.models import load_artifact
from mechabellum.training.deep import train_token_model

ROOT = Path(__file__).resolve().parents[1]


def _dataset(tmp_path: Path) -> tuple[Path, list]:
    example = json.loads((ROOT / "contracts/match-snapshot/v2/fight-over.example.json").read_text(encoding="utf-8"))
    snapshots = []
    for index in range(12):
        data = deepcopy(example)
        data["match"]["battleId"] = f"20261024--{67100000 + index}"
        winner = index % 2
        data["outcome"] = {
            "winnerIndex": winner,
            "winnerPlayerId": data["players"][winner]["playerId"],
            "winnerName": data["players"][winner]["name"],
        }
        # The winner fields the bigger army, mirrored to its own half of the board.
        unit = dict(example["players"][0]["units"][0])
        data["players"][winner]["units"] = [dict(unit, y=unit["y"] * (1 if winner == 0 else -1))] * (2 + index % 3)
        data["players"][1 - winner]["units"] = []
        snapshots.append(validate_snapshot(data))
    path = tmp_path / "dataset.jsonl"
    write_snapshots(path, snapshots)
    return path, snapshots


@pytest.mark.parametrize("architecture", ["deepsets", "transformer", "gnn"])
def test_token_models_train_save_and_predict_symmetrically(tmp_path: Path, architecture: str) -> None:
    dataset, snapshots = _dataset(tmp_path)
    output = tmp_path / f"model_{architecture}.pt"
    metadata = train_token_model(dataset, output, architecture=architecture, epochs=3, patience=3, width=16)
    assert metadata["testMatchCount"] >= 1
    artifact = load_artifact(output, feature_names())
    result = predict_snapshot(artifact, snapshots[0], output)
    probabilities = [item["winProbability"] for item in result["predictions"]]
    assert abs(sum(probabilities) - 1.0) < 1e-6
    # Antisymmetric by construction: each perspective's probability is one minus the other's.
    raw = artifact["model"].win_probabilities([snapshots[0], snapshots[0]], [0, 1])
    np.testing.assert_allclose(raw.sum(), 1.0, atol=1e-6)
