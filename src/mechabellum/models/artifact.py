from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .token_model import TOKEN_ARTIFACT_SUFFIX


def create_artifact(model: Any, feature_names: list[str], feature_schema: int | None = None) -> dict[str, Any]:
    return {"model": model, **artifact_metadata(feature_names, feature_schema)}


def artifact_metadata(feature_names: list[str], feature_schema: int | None = None) -> dict[str, Any]:
    from ..contracts import MATCH_SNAPSHOT_SCHEMA_VERSION, MODEL_SNAPSHOT_PHASE
    from ..features import FEATURE_SCHEMA_VERSION

    return {
        "featureNames": feature_names,
        "featureSchemaVersion": FEATURE_SCHEMA_VERSION if feature_schema is None else feature_schema,
        "matchSnapshotSchemaVersion": MATCH_SNAPSHOT_SCHEMA_VERSION,
        "snapshotPhase": MODEL_SNAPSHOT_PHASE,
    }


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    import joblib

    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, path)


def load_artifact(path: Path, expected_feature_names: list[str]) -> dict[str, Any]:
    """Load a linear (.joblib) or token (.pt) model artifact and check it matches this code's contracts.

    `expected_feature_names` are the default schema's. A linear artifact trained on another supported schema (the
    opt-in `--feature-schema 3`) is checked against that schema's names instead, and `win_probabilities` builds its
    features with it.
    """
    if path.suffix == TOKEN_ARTIFACT_SUFFIX:
        from .token_model import load_token_artifact

        artifact = load_token_artifact(path)
    else:
        import joblib

        artifact = joblib.load(path)
    from ..features import FEATURE_SCHEMA_VERSION, SUPPORTED_FEATURE_SCHEMAS, feature_names

    schema = artifact.get("featureSchemaVersion")
    if artifact.get("kind") != "token" and schema != FEATURE_SCHEMA_VERSION and schema in SUPPORTED_FEATURE_SCHEMAS:
        expected_feature_names = feature_names(schema)
        expected = artifact_metadata(expected_feature_names, schema)
    else:
        expected = artifact_metadata(expected_feature_names)
    if schema != expected["featureSchemaVersion"]:
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
    from ..features import FEATURE_SCHEMA_VERSION, build_features

    schema = artifact.get("featureSchemaVersion", FEATURE_SCHEMA_VERSION)
    rows = np.vstack(
        [
            build_features(snapshot, perspective, schema)
            for snapshot, perspective in zip(snapshots, perspectives, strict=True)
        ]
    )
    return model.predict_proba(rows)[:, 1]
