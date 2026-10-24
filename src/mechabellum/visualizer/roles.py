"""The unit -> role table (`unit_roles.json`, from research/unit-roles.md) and board composition maths."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from ..collector.unit_catalog import UNIT_NAMES, UNIT_PRICES, unit_name
from ..contracts import UnitDeployment

ROLES = ("chaff", "chaffClear", "damage", "tank", "support")
UNKNOWN_ROLE = "unknown"
# The share bar's slices, in display order: the five roles, then units missing from the table.
SLICES = (*ROLES, UNKNOWN_ROLE)


@dataclass(frozen=True)
class UnitRole:
    primary: str
    secondary: str | None
    air: bool
    hits_air: bool


def _load_roles() -> dict[int, UnitRole]:
    data = json.loads(files(__package__).joinpath("unit_roles.json").read_text(encoding="utf-8"))
    table = {}
    for unit_id, entry in data.items():
        if entry["primary"] not in ROLES or entry["secondary"] not in (*ROLES, None):
            raise ValueError(f"unit_roles.json: unknown role for unit {unit_id}")
        table[int(unit_id)] = UnitRole(entry["primary"], entry["secondary"], bool(entry["air"]), bool(entry["hitsAir"]))
    return table


UNIT_ROLES: dict[int, UnitRole] = _load_roles()


def unit_role(unit_id: int) -> str:
    role = UNIT_ROLES.get(unit_id)
    return UNKNOWN_ROLE if role is None else role.primary


def empty_composition(round_number: int | None = None) -> dict[str, Any]:
    composition: dict[str, Any] = {} if round_number is None else {"round": round_number}
    composition.update({"supply": 0, "roles": dict.fromkeys(SLICES, 0.0), "air": 0.0, "hitsAir": 0.0, "bodies": 0})
    return composition


def board_composition(units: Sequence[UnitDeployment], round_number: int | None = None) -> dict[str, Any]:
    """Supply-weighted role shares of one board.

    Each unit counts its `sellSupply` over the board total. `air` and `hitsAir` are supply shares outside the 100%;
    `bodies` counts squad members. An empty board has supply 0 and every share 0.
    """
    composition = empty_composition(round_number)
    total = sum(max(unit.sell_supply, 0) for unit in units)
    composition["supply"] = total
    composition["bodies"] = sum(int(UNIT_PRICES.get(unit.unit_id, {}).get("members", 1)) for unit in units)
    if total <= 0:
        return composition
    roles = composition["roles"]
    for unit in units:
        share = max(unit.sell_supply, 0) / total
        role = UNIT_ROLES.get(unit.unit_id)
        roles[UNKNOWN_ROLE if role is None else role.primary] += share
        if role is not None and role.air:
            composition["air"] += share
        if role is not None and role.hits_air:
            composition["hitsAir"] += share
    return composition


def mean_composition(compositions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The mean of non-empty compositions, with `n` the number averaged; empty boards are left out."""
    items = [item for item in compositions if item.get("supply", 0) > 0]
    mean: dict[str, Any] = {"roles": dict.fromkeys(SLICES, 0.0), "air": 0.0, "hitsAir": 0.0, "bodies": 0.0}
    mean["n"] = len(items)
    if not items:
        return mean
    for item in items:
        for role in SLICES:
            mean["roles"][role] += item["roles"].get(role, 0.0)
        mean["air"] += item["air"]
        mean["hitsAir"] += item["hitsAir"]
        mean["bodies"] += item["bodies"]
    count = len(items)
    mean["roles"] = {role: value / count for role, value in mean["roles"].items()}
    mean["air"] /= count
    mean["hitsAir"] /= count
    mean["bodies"] /= count
    return mean


def catalog() -> dict[str, Any]:
    """`/catalog.json`: every known unit's name, roles, flags and squad size, plus the share bar's slice order."""
    units = {}
    for unit_id in sorted(set(UNIT_NAMES) | set(UNIT_ROLES)):
        role = UNIT_ROLES.get(unit_id)
        units[str(unit_id)] = {
            "name": unit_name(unit_id),
            "primary": UNKNOWN_ROLE if role is None else role.primary,
            "secondary": None if role is None else role.secondary,
            "air": False if role is None else role.air,
            "hitsAir": False if role is None else role.hits_air,
            "members": int(UNIT_PRICES.get(unit_id, {}).get("members", 1)),
        }
    return {"units": units, "roles": list(SLICES)}
