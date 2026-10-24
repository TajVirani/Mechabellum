from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .token_model import TOKEN_ARTIFACT_SUFFIX


def create_artifact(model: Any, feature_names: list[str]) -> dict[str, Any]:
    return {"model": model, **artifact_metadata(feature_names)}


def artifact_metadata(feature_names: list[str]) -> dict[str, Any]:
    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
    from ..features import FEATURE_SCHEMA_VERSION

    return {
        "featureNames": feature_names,
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION,
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "snapshotPhase": MODEL_SNAPSHOT_PHASE,
    }


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path, expected_feature_names: list[str]) -> dict[str, Any]:
    """Load a linear (.joblib) or token (.pt) model artifact and check it matches this code's contracts."""
    if path.suffix == TOKEN_ARTIFACT_SUFFIX:
        from .token_model import load_token_artifact

        artifact = load_token_artifact(path)
    else:
        import joblib

        artifact = joblib.load(path)
    expected = artifact_metadata(expected_feature_names)
    if artifact.get("featureSchemaVersion") != expected["featureSchemaVersion"]:
        raise ValueError("Model feature schema version does not match the code; please retrain.")
    if artifact.get("featureNames") != expected_feature_names:
        raise ValueError("Model feature version does not match the code; please retrain.")
    if artifact.get("matchSnapshotSchemaVersion") != expected["matchSnapshotSchemaVersion"]:
        raise ValueError("Model MatchSnapshot contract version does not match the code; please retrain.")
    if artifact.get("snapshotPhase") != expected["snapshotPhase"]:
        raise ValueError("Model was trained on a different snapshot phase; please retrain.")
    return artifact


def win_probabilities(artifact: dict[str, Any], snapshots: Sequence[Any], perspectives: Sequence[int]) -> np.ndarray:
    """Probability that each row's perspective player wins, for either artifact kind."""
    model = artifact["model"]
    if artifact.get("kind") == "token":
        return model.win_probabilities(snapshots, perspectives)
    from ..features import build_features

    rows = np.vstack(
        [build_features(snapshot, perspective) for snapshot, perspective in zip(snapshots, perspectives, strict=True)]
    )
    return model.predict_proba(rows)[:, 1]
