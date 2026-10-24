"""Rank candidate actions by how much the win model thinks they help.

There is no simulator: each candidate is applied to a copy of a fight_over position (the board the player
deploys from) and the model scores the result. The ranking is therefore the model's static judgement of the
changed board, not a played-out fight. Unit prices and card effects are learned from replays (see
ActionCatalog), because no id-to-cost table is available yet.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ..contracts import (
    CommanderSkill,
    EquipmentItem,
    MatchSnapshot,
    PlayerSnapshot,
    ReinforcementChoice,
    UnitDeployment,
    UnitTechnologySet,
)
from ..features.geometry import board_sign
from ..models import win_probabilities

ActionKind = Literal["buy", "upgrade", "technology", "move", "card"]
MOVE_STEP = 40.0
BUY_SLOTS = ((-160.0, 120.0), (0.0, 120.0), (160.0, 120.0), (-160.0, 240.0), (0.0, 240.0), (160.0, 240.0))
CardEffect = Literal["equipment", "officer", "commander_skill", "technology", "unknown"]


@dataclass(frozen=True)
class CandidateAction:
    kind: ActionKind
    description: str
    parameters: dict[str, Any]
    estimated_cost: int | None


@dataclass
class ActionCatalog:
    """What replays reveal about actions: unit prices, technologies per unit, and what each card changes."""

    unit_prices: dict[int, int] = field(default_factory=dict)
    unit_technologies: dict[int, list[int]] = field(default_factory=dict)
    card_effects: dict[int, CardEffect] = field(default_factory=dict)

    @classmethod
    def from_snapshots(cls, snapshots: Sequence[MatchSnapshot]) -> ActionCatalog:
        prices: dict[int, Counter[int]] = defaultdict(Counter)
        technologies: dict[int, set[int]] = defaultdict(set)
        effects: dict[int, Counter[str]] = defaultdict(Counter)
        by_round = {(item.match.battle_id, item.match.round): item for item in snapshots}
        for snapshot in snapshots:
            for player in snapshot.players:
                for unit in player.units:
                    prices[unit.unit_id][unit.sell_supply] += 1
                for item in player.active_technologies:
                    technologies[item.unit_id].update(item.technology_ids)
            previous = by_round.get((snapshot.match.battle_id, snapshot.match.round - 1))
            if previous is None:
                continue
            for before, after in zip(previous.players, snapshot.players, strict=False):
                choice = after.reinforcement_choice
                if choice is None or choice.item_id is None:
                    continue
                effects[choice.item_id][_card_effect(before, after, choice.item_id)] += 1
        return cls(
            unit_prices={unit: counts.most_common(1)[0][0] for unit, counts in prices.items()},
            unit_technologies={unit: sorted(values) for unit, values in technologies.items()},
            card_effects={card: counts.most_common(1)[0][0] for card, counts in effects.items()},  # type: ignore[misc]
        )


def _card_effect(before: PlayerSnapshot, after: PlayerSnapshot, card: int) -> str:
    def has(player: PlayerSnapshot, effect: str) -> bool:
        if effect == "equipment":
            return card in {item.equipment_id for item in player.equipment_inventory or []}
        if effect == "officer":
            return card in set(player.officer_ids or [])
        if effect == "commander_skill":
            return card in {skill.skill_id for skill in player.commander_skills or []}
        return card in {tech for item in player.active_technologies for tech in item.technology_ids}

    for effect in ("equipment", "officer", "commander_skill", "technology"):
        if has(after, effect) and not has(before, effect):
            return effect
    return "unknown"


def candidate_actions(
    snapshot: MatchSnapshot, perspective: int, catalog: ActionCatalog, cards: Iterable[int] = ()
) -> list[CandidateAction]:
    player = snapshot.players[perspective]
    actions: list[CandidateAction] = []
    for unit_id in player.unlocked_unit_ids or sorted({unit.unit_id for unit in player.units}):
        for x, depth in BUY_SLOTS:
            actions.append(
                CandidateAction(
                    "buy",
                    f"Buy unit {unit_id} at lane x={x:+.0f}, depth {depth:.0f}",
                    {"unitId": unit_id, "x": x, "depth": depth},
                    catalog.unit_prices.get(unit_id),
                )
            )
    for index, unit in enumerate(player.units):
        actions.append(
            CandidateAction("upgrade", f"Upgrade formation {index} (unit {unit.unit_id})", {"formation": index}, None)
        )
        for dx, ddepth, label in (
            (0, -MOVE_STEP, "forward"),
            (0, MOVE_STEP, "back"),
            (-MOVE_STEP, 0, "left"),
            (MOVE_STEP, 0, "right"),
        ):
            actions.append(
                CandidateAction(
                    "move",
                    f"Move formation {index} (unit {unit.unit_id}) {label}",
                    {"formation": index, "dx": dx, "ddepth": ddepth},
                    0,
                )
            )
    owned = {unit.unit_id for unit in player.units}
    active = {item.unit_id: set(item.technology_ids) for item in player.active_technologies}
    for unit_id in sorted(owned):
        for technology in catalog.unit_technologies.get(unit_id, []):
            if technology not in active.get(unit_id, set()):
                actions.append(
                    CandidateAction(
                        "technology",
                        f"Research technology {technology} for unit {unit_id}",
                        {"unitId": unit_id, "technologyId": technology},
                        None,
                    )
                )
    for card in cards:
        effect = catalog.card_effects.get(card, "unknown")
        actions.append(CandidateAction("card", f"Pick card {card} ({effect})", {"itemId": card, "effect": effect}, 0))
    return actions


def apply_action(snapshot: MatchSnapshot, perspective: int, action: CandidateAction) -> MatchSnapshot:
    """The position after `action`, with every other field unchanged."""
    player = snapshot.players[perspective]
    sign = board_sign(player, perspective)  # -1: the player's half is y < 0
    units = list(player.units)
    technologies = list(player.active_technologies)
    update: dict[str, Any] = {}
    parameters = action.parameters
    if action.kind == "buy":
        unit_id = parameters["unitId"]
        units.append(
            UnitDeployment(
                unit_id=unit_id,
                unit_name=str(unit_id),
                formation_index=len(units),
                raw_level=0,
                display_level=1,
                experience=0,
                x=parameters["x"] * -sign,
                y=parameters["depth"] * sign,
                is_rotated=False,
                sell_supply=action.estimated_cost or 0,
                round_count=0,
                equipment=[],
            )
        )
        if action.estimated_cost:
            update["supply"] = (player.supply or 0) - action.estimated_cost
    elif action.kind == "upgrade":
        unit = units[parameters["formation"]]
        units[parameters["formation"]] = unit.model_copy(
            update={"raw_level": unit.raw_level + 1, "display_level": unit.display_level + 1}
        )
    elif action.kind == "move":
        unit = units[parameters["formation"]]
        # Depth grows away from the midline; in board terms that is -sign * y.
        units[parameters["formation"]] = unit.model_copy(
            update={"x": unit.x + parameters["dx"] * -sign, "y": unit.y + parameters["ddepth"] * sign}
        )
    elif action.kind == "technology":
        unit_id, technology = parameters["unitId"], parameters["technologyId"]
        existing = next((item for item in technologies if item.unit_id == unit_id), None)
        if existing is None:
            technologies.append(UnitTechnologySet(unit_id=unit_id, unit_name=str(unit_id), technology_ids=[technology]))
        else:
            technologies[technologies.index(existing)] = existing.model_copy(
                update={"technology_ids": [*existing.technology_ids, technology]}
            )
    elif action.kind == "card":
        card, effect = parameters["itemId"], parameters["effect"]
        update["reinforcement_choice"] = ReinforcementChoice(status="chosen", item_id=card, offer_index=None)
        if effect == "equipment":
            update["equipment_inventory"] = [
                *(player.equipment_inventory or []),
                EquipmentItem(equipment_id=card, durability=None),
            ]
        elif effect == "officer":
            update["officer_ids"] = [*(player.officer_ids or []), card]
        elif effect == "commander_skill":
            skills = player.commander_skills or []
            update["commander_skills"] = [
                *skills,
                CommanderSkill(
                    skill_id=card, slot_index=len(skills), acquired_round=None, cooldown_rounds=0, is_active=True
                ),
            ]
    update["units"] = units
    update["active_technologies"] = technologies
    players = list(snapshot.players)
    players[perspective] = player.model_copy(update=update)
    return snapshot.model_copy(update={"players": players})


@dataclass(frozen=True)
class RankedAction:
    action: CandidateAction
    win_probability: float
    gain: float


def rank_actions(
    artifact: dict[str, Any],
    snapshot: MatchSnapshot,
    perspective: int,
    candidates: Sequence[CandidateAction],
    round_weight: float = 0.0,
) -> tuple[float, list[RankedAction]]:
    """Baseline win probability and the candidates ordered by how much they improve the position's value.

    The value is the win probability; with `round_weight > 0` and a multi-task token model, the predicted next
    fight advantage is added with that weight, mirroring the reward definition in training/targets.py.
    """
    positions = [snapshot, *(apply_action(snapshot, perspective, action) for action in candidates)]
    probabilities = _symmetric_probabilities(artifact, positions, perspective)
    values = list(probabilities)
    if round_weight > 0 and artifact.get("kind") == "token":
        advantages = artifact["model"].next_fight_advantages(positions, [perspective] * len(positions))
        values = [value + round_weight * float(advantage) for value, advantage in zip(values, advantages, strict=True)]
    baseline = float(probabilities[0])
    ranked = [
        RankedAction(action, float(probability), float(value) - float(values[0]))
        for action, probability, value in zip(candidates, probabilities[1:], values[1:], strict=True)
    ]
    ranked.sort(key=lambda item: item.gain, reverse=True)
    return baseline, ranked


def _symmetric_probabilities(
    artifact: dict[str, Any], positions: Sequence[MatchSnapshot], perspective: int
) -> list[float]:
    own = win_probabilities(artifact, positions, [perspective] * len(positions))
    other = win_probabilities(artifact, positions, [1 - perspective] * len(positions))
    return [float(a / (a + b)) if a + b > 0 else 0.5 for a, b in zip(own, other, strict=True)]
