from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score

from ..contracts import MatchSnapshot
from ..features import build_features

RATING_TIER_WIDTH = 250
CALIBRATION_BINS = 10


@dataclass(frozen=True)
class EvaluationRows:
    """One row per (snapshot, perspective): the label is whether that perspective's player won."""

    x: np.ndarray
    y: np.ndarray
    battle_ids: np.ndarray
    snapshots: list[MatchSnapshot]
    perspectives: np.ndarray

    @classmethod
    def from_snapshots(cls, snapshots: Sequence[MatchSnapshot]) -> EvaluationRows:
        rows: list[np.ndarray] = []
        labels: list[int] = []
        battle_ids: list[str] = []
        expanded: list[MatchSnapshot] = []
        perspectives: list[int] = []
        for snapshot in snapshots:
            if snapshot.outcome is None or snapshot.match.battle_id is None:
                raise ValueError("Snapshot is missing outcome or match.battleId.")
            for perspective in (0, 1):
                rows.append(build_features(snapshot, perspective))
                labels.append(int(perspective == snapshot.outcome.winner_index))
                battle_ids.append(snapshot.match.battle_id)
                expanded.append(snapshot)
                perspectives.append(perspective)
        return cls(
            np.vstack(rows),
            np.asarray(labels, dtype=np.int8),
            np.asarray(battle_ids),
            expanded,
            np.asarray(perspectives, dtype=np.int64),
        )

    def subset(self, indices: np.ndarray) -> EvaluationRows:
        return EvaluationRows(
            self.x[indices],
            self.y[indices],
            self.battle_ids[indices],
            [self.snapshots[i] for i in indices],
            self.perspectives[indices],
        )


def metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float | None]:
    """Accuracy, ROC AUC, log loss and Brier score; AUC is None when only one class is present."""
    both_classes = len(set(labels.tolist())) == 2
    return {
        "accuracy": float(accuracy_score(labels, probabilities >= 0.5)),
        "rocAuc": float(roc_auc_score(labels, probabilities)) if both_classes else None,
        "logLoss": float(log_loss(labels, probabilities, labels=[0, 1])),
        "brier": float(brier_score_loss(labels, probabilities)),
    }


def calibration_table(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, object]:
    """Reliability bins of equal width and the sample-weighted expected calibration error."""
    edges = np.linspace(0.0, 1.0, CALIBRATION_BINS + 1)
    bins = np.clip(np.digitize(probabilities, edges[1:-1]), 0, CALIBRATION_BINS - 1)
    rows = []
    error = 0.0
    for index in range(CALIBRATION_BINS):
        mask = bins == index
        if not mask.any():
            continue
        predicted = float(probabilities[mask].mean())
        observed = float(labels[mask].mean())
        error += mask.sum() / len(labels) * abs(predicted - observed)
        rows.append(
            {
                "range": [float(edges[index]), float(edges[index + 1])],
                "samples": int(mask.sum()),
                "meanPredicted": predicted,
                "observedWinRate": observed,
            }
        )
    return {"expectedCalibrationError": float(error), "bins": rows}


def rating_tier(snapshot: MatchSnapshot) -> str:
    ratings = [player.rating for player in snapshot.players]
    if any(rating is None for rating in ratings):
        return "unknown"
    mean = sum(rating for rating in ratings if rating is not None) / len(ratings)
    low = int(mean // RATING_TIER_WIDTH) * RATING_TIER_WIDTH
    return f"{low}-{low + RATING_TIER_WIDTH - 1}"


BREAKDOWNS: dict[str, Callable[[MatchSnapshot], object]] = {
    "round": lambda snapshot: snapshot.match.round,
    "map": lambda snapshot: snapshot.match.map_id,
    "replayVersion": lambda snapshot: snapshot.game_build.replay_version,
    "gameMode": lambda snapshot: snapshot.match.game_mode,
    "ratingTier": rating_tier,
}


def evaluation_report(rows: EvaluationRows, probabilities: np.ndarray) -> dict[str, object]:
    report: dict[str, object] = {
        "samples": int(len(rows.y)),
        "matches": len(set(rows.battle_ids.tolist())),
        "metrics": metrics(rows.y, probabilities),
        "calibration": calibration_table(rows.y, probabilities),
    }
    for name, key in BREAKDOWNS.items():
        values = np.asarray([str(key(snapshot)) for snapshot in rows.snapshots])
        groups = {}
        for value in sorted(set(values.tolist()), key=_natural_key):
            mask = values == value
            groups[value] = {
                "samples": int(mask.sum()),
                "matches": len(set(rows.battle_ids[mask].tolist())),
                **metrics(rows.y[mask], probabilities[mask]),
            }
        report[f"by{name[0].upper()}{name[1:]}"] = groups
    return report


def evaluate_model(dataset_path: Path, model_path: Path) -> dict[str, object]:
    """Evaluate a saved model on every usable snapshot of a dataset, which should not overlap its training data."""
    from ..datasets import load_training_snapshots
    from ..features import feature_names
    from ..models import load_artifact, win_probabilities

    snapshots = load_training_snapshots(dataset_path)
    if not snapshots:
        raise ValueError("The dataset contains no usable snapshots.")
    artifact = load_artifact(model_path, feature_names())
    rows = EvaluationRows.from_snapshots(snapshots)
    report = evaluation_report(rows, win_probabilities(artifact, rows.snapshots, rows.perspectives.tolist()))
    return {"datasetPath": str(dataset_path.resolve()), "model": str(model_path.resolve()), **report}


def _natural_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.lstrip("-").isdigit() else (1, value)
