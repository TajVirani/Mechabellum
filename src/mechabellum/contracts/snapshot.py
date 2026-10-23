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

MATCH_SNAPSHOT_SCHEMA_VERSION = 1


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
    equipment_id: int
    sell_supply: int
    round_count: int
    durability: int


class UnitTechnologySet(ContractModel):
    unit_id: int = Field(ge=1)
    unit_name: str
    technology_ids: list[int]


class PlayerSnapshot(ContractModel):
    player_id: str | None
    name: str
    team: int | None
    state: str | None
    supply: int | None
    reactor_core: int | None
    previous_fight_result: str | None
    units: list[UnitDeployment]
    active_technologies: list[UnitTechnologySet]


class MatchOutcome(ContractModel):
    winner_index: int = Field(ge=0)
    winner_player_id: str | None
    winner_name: str | None


class MatchSnapshot(ContractModel):
    schema_version: Literal[1] = MATCH_SNAPSHOT_SCHEMA_VERSION
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

    relative = Path("contracts/match-snapshot/v1/schema.json")
    candidates = [
        Path.cwd() / relative,
        Path(sys.prefix) / "share" / "mechabellum" / "contracts" / "match-snapshot" / "v1" / "schema.json",
    ]
    candidates.extend(parent / relative for parent in Path(__file__).resolve().parents)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Could not find contracts/match-snapshot/v1/schema.json.")


@lru_cache(maxsize=8)
def _validator(schema_path: Path) -> Draft202012Validator:
    return Draft202012Validator(load_schema(schema_path), format_checker=FormatChecker())
