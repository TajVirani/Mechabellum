"""Ablations of the multi-task value model: final result only versus added round advantage, at several weights."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..contracts import MatchSnapshot
from ..datasets import load_training_snapshots
from ..features import feature_names
from ..models import load_artifact


def card_ranking_metrics(
    artifact: dict[str, Any],
    snapshots: Sequence[MatchSnapshot],
    battle_ids: set[str],
    round_weight: float = 0.0,
) -> dict[str, object]:
    """Where the model ranks the card each player actually picked, from the position they picked it in.

    For round r the position is the fight_over snapshot of round r - 1 and the candidates are round r's offer.
    Reported separately for the match's eventual winner and loser: a useful ranking should favour the winners'
    picks more than the losers'.
    """
    from ..inference.actions import ActionCatalog, candidate_actions, rank_actions

    catalog = ActionCatalog.from_snapshots(snapshots)
    by_round = {(item.match.battle_id, item.match.round): item for item in snapshots}
    reciprocal: dict[str, list[float]] = {"winner": [], "loser": []}
    for snapshot in snapshots:
        offer = snapshot.match.reinforcement_offer
        if snapshot.match.battle_id not in battle_ids or not offer or snapshot.outcome is None:
            continue
        position = by_round.get((snapshot.match.battle_id, snapshot.match.round - 1))
        if position is None:
            continue
        for perspective, player in enumerate(snapshot.players):
            choice = player.reinforcement_choice
            if choice is None or choice.item_id not in offer:
                continue
            cards = [
                action for action in candidate_actions(position, perspective, catalog, offer) if action.kind == "card"
            ]
            _, ranked = rank_actions(artifact, position, perspective, cards, round_weight)
            order = [item.action.parameters["itemId"] for item in ranked]
            role = "winner" if perspective == snapshot.outcome.winner_index else "loser"
            reciprocal[role].append(1.0 / (order.index(choice.item_id) + 1))
    return {
        role: {"choices": len(values), "meanReciprocalRank": sum(values) / len(values) if values else None}
        for role, values in reciprocal.items()
    }


def run_ablation(
    dataset_path: Path,
    output_directory: Path,
    *,
    architecture: str = "deepsets",
    advantage_weights: Sequence[float] = (0.0, 0.1, 0.3, 1.0),
    round_weights: Sequence[float] = (0.0, 0.3),
    split: str = "group",
    seed: int = 20260711,
    epochs: int = 300,
) -> dict[str, object]:
    """Train one model per advantage loss weight and report calibration and card ranking on the test matches."""
    from .deep import train_token_model

    snapshots = load_training_snapshots(dataset_path)
    rows = []
    for weight in advantage_weights:
        path = output_directory / f"ablation_{architecture}_advantage_{weight:g}.pt"
        metadata = train_token_model(
            dataset_path,
            path,
            architecture=architecture,
            split=split,  # type: ignore[arg-type]
            seed=seed,
            epochs=epochs,
            advantage_weight=weight,
        )
        evaluation = metadata["evaluation"]
        artifact = load_artifact(path, feature_names())
        test_ids = set(metadata["testBattleIds"])  # type: ignore[arg-type]
        rows.append(
            {
                "advantageWeight": weight,
                "metrics": metadata["metrics"],
                "expectedCalibrationError": evaluation["calibration"]["expectedCalibrationError"],  # type: ignore[index]
                "nextFightAdvantage": evaluation.get("nextFightAdvantage"),  # type: ignore[union-attr]
                "cardRanking": {
                    f"roundWeight {round_weight:g}": card_ranking_metrics(artifact, snapshots, test_ids, round_weight)
                    for round_weight in round_weights
                },
            }
        )
    return {"architecture": architecture, "split": split, "seed": seed, "runs": rows}
