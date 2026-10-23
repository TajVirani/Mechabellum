from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, model_validator

MATCH_SNAPSHOT_SCHEMA_VERSION = 2

FightResult = Literal["Win", "Lose", "Deuce"]
PlayerState = Literal["Deploying", "DeployOver", "Fighting", "FightOver", "Unknown"]


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="forbid", frozen=True)


class GameBuild(ContractModel):
    replay_version: int | None
    game_version: str | None
    game_assembly_sha256: str | None


class SnapshotSource(ContractModel):
    type: Literal["replay", "memory"]
    uri: str
    captured_at_utc: datetime | None


class MatchInfo(ContractModel):
    battle_id: str | None
    map_id: int | None
    game_mode: str | None
    match_mode: str | None
    round: int = Field(ge=0)
    phase: Literal["opening", "deploying", "deploy_over", "battle_start", "fighting", "fight_over", "unknown"]
    reinforcement_offer: list[int] | None


class EquipmentItem(ContractModel):
    equipment_id: int = Field(ge=1)
    durability: int | None


class UnitDeployment(ContractModel):
    unit_id: int = Field(ge=1)
    unit_name: str
    formation_index: int
    raw_level: int = Field(ge=0)
    display_level: int = Field(ge=1)
    experience: int = Field(ge=0)
    x: float
    y: float
    is_rotated: bool
    sell_supply: int
    round_count: int
    equipment: list[EquipmentItem]


class UnitTechnologySet(ContractModel):
    unit_id: int = Field(ge=1)
    unit_name: str
    technology_ids: list[int]


class CommanderSkill(ContractModel):
    skill_id: int = Field(ge=1)
    slot_index: int
    acquired_round: int | None
    cooldown_rounds: int | None
    is_active: bool | None


class Building(ContractModel):
    building_id: int = Field(ge=1)
    index: int
    x: float
    y: float
    durability: list[int] | None


class Contraption(ContractModel):
    contraption_id: int = Field(ge=1)
    index: int
    x: float
    y: float


class ReinforcementChoice(ContractModel):
    status: Literal["chosen", "declined"]
    item_id: int | None
    offer_index: int | None


class PlayerSnapshot(ContractModel):
    player_id: str | None
    name: str
    team: int | None
    state: PlayerState | None
    supply: int | None
    reactor_core: int | None
    max_reactor_core: int | None
    round_supply_income: int | None
    previous_fight_result: FightResult | None
    fight_result_history: list[FightResult] | None
    units: list[UnitDeployment]
    active_technologies: list[UnitTechnologySet]
    equipment_inventory: list[EquipmentItem] | None
    commander_skills: list[CommanderSkill] | None
    officer_ids: list[int] | None
    buildings: list[Building] | None
    contraptions: list[Contraption] | None
    blueprint_ids: list[int] | None
    energy_tower_skill_ids: list[int] | None
    tower_strengthen_levels: list[int] | None
    unlocked_unit_ids: list[int] | None
    reinforcement_choice: ReinforcementChoice | None


class MatchOutcome(ContractModel):
    winner_index: int = Field(ge=0)
    winner_player_id: str | None
    winner_name: str | None


class MatchSnapshot(ContractModel):
    schema_version: Literal[2] = MATCH_SNAPSHOT_SCHEMA_VERSION
    game_build: GameBuild
    source: SnapshotSource
    match: MatchInfo
    players: list[PlayerSnapshot] = Field(min_length=2)
    outcome: MatchOutcome | None = None

    @model_validator(mode="after")
    def validate_outcome_index(self) -> MatchSnapshot:
        if self.outcome is not None and self.outcome.winner_index >= len(self.players):
            raise ValueError("outcome.winnerIndex is out of range for players.")
        return self


def validate_snapshot(data: dict[str, Any], schema_path: Path | None = None) -> MatchSnapshot:
    _validator((schema_path or locate_schema()).resolve()).validate(data)
    return MatchSnapshot.model_validate(data)


def snapshot_to_dict(snapshot: MatchSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json", by_alias=True)


def snapshot_to_json(snapshot: MatchSnapshot, *, indent: int | None = None) -> str:
    data = snapshot_to_dict(snapshot)
    _validator(locate_schema().resolve()).validate(data)
    return json.dumps(data, ensure_ascii=False, separators=None if indent else (",", ":"), indent=indent)


def load_schema(schema_path: Path | None = None) -> dict[str, Any]:
    path = (schema_path or locate_schema()).resolve()
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def locate_schema() -> Path:
    configured = os.environ.get("MECHABELLUM_MATCH_SNAPSHOT_SCHEMA")
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        raise FileNotFoundError(f"File pointed to by MECHABELLUM_MATCH_SNAPSHOT_SCHEMA does not exist: {path}")

    relative = Path("contracts/match-snapshot/v2/schema.json")
    candidates = [
        Path.cwd() / relative,
        Path(sys.prefix) / "share" / "mechabellum" / "contracts" / "match-snapshot" / "v2" / "schema.json",
    ]
    candidates.extend(parent / relative for parent in Path(__file__).resolve().parents)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not find contracts/match-snapshot/v2/schema.json.")


@lru_cache(maxsize=8)
def _validator(schema_path: Path) -> Draft202012Validator:
    return Draft202012Validator(load_schema(schema_path), format_checker=FormatChecker())
