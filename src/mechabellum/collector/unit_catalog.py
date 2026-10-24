import json
from importlib.resources import files
from typing import Any

UNIT_NAMES: dict[int, str] = {
    1: "Fortress",
    2: "Marksman",
    3: "Vulcan",
    4: "Melting Point",
    5: "Rhino",
    6: "Wasp",
    7: "Mustang",
    8: "Steel Ball",
    9: "Fang",
    10: "Crawler",
    11: "Overlord",
    12: "Stormcaller",
    13: "Sledgehammer",
    14: "Hacker",
    15: "Arclight",
    16: "Phoenix",
    17: "War Factory",
    18: "Wraith",
    19: "Scorpion",
    20: "Fire Badger",
    21: "Sabertooth",
    22: "Typhoon",
    23: "Sandworm",
    24: "Tarantula",
    25: "Phantom Ray",
    26: "Farseer",
    27: "Raiden",
    28: "Hound",
    29: "Abyss",
    30: "Void Eye",
    31: "Vortex",
    32: "Centurion",
    2002: "Mountain",
}


# Names and prices from game 2.0.0.4 (https://github.com/qbisi/mechcore), with names of ids that build no longer holds
# from game 1.8.0.3 (https://github.com/mechstats/mech-data). Ids neither holds, such as AsyncBattle's, are unknown.
_GAME_NAMES = json.loads(files(__package__).joinpath("game_names.json").read_text(encoding="utf-8"))
GAME_NAMES_VERSION: str = _GAME_NAMES["gameVersion"]


def _table(key: str) -> dict[int, Any]:
    return {int(item_id): value for item_id, value in _GAME_NAMES[key].items()}


OFFICER_NAMES: dict[int, str] = _table("officers")
EQUIPMENT_NAMES: dict[int, str] = _table("equipment")
TECHNOLOGY_NAMES: dict[int, str] = _table("technologies")
COMMANDER_SKILL_NAMES: dict[int, str] = _table("commanderSkills")
BLUEPRINT_NAMES: dict[int, str] = _table("blueprints")
ENERGY_TOWER_SKILL_NAMES: dict[int, str] = _table("energyTowerSkills")
MAP_NAMES: dict[int, str] = _table("maps")
ADVANCE_TEAM_NAMES: dict[int, str] = _table("advanceTeams")
UNIT_CARD_NAMES: dict[int, str] = _table("unitCards")
# Per unit: supply, unlockSupply, upgradeSupply and members (squad size); keys absent where the game has no price.
UNIT_PRICES: dict[int, dict[str, int]] = _table("unitPrices")
UNIT_TECHNOLOGIES: dict[int, list[int]] = _table("unitTechnologies")
TECHNOLOGY_SUPPLY: dict[int, int] = _table("technologySupply")
# Cards with a price of their own; the rest sell at their card level's price.
CARD_SUPPLY: dict[int, int] = _table("cardSupply")


def _name(table: dict[int, str], item_id: int, kind: str) -> str:
    return table.get(item_id, f"Unknown {kind} ({item_id})")


def unit_name(unit_id: int) -> str:
    return _name(UNIT_NAMES, unit_id, "unit")


def officer_name(officer_id: int) -> str:
    return _name(OFFICER_NAMES, officer_id, "specialist")


def equipment_name(equipment_id: int) -> str:
    return _name(EQUIPMENT_NAMES, equipment_id, "equipment")


def technology_name(technology_id: int) -> str:
    return _name(TECHNOLOGY_NAMES, technology_id, "technology")


def commander_skill_name(skill_id: int) -> str:
    return _name(COMMANDER_SKILL_NAMES, skill_id, "commander skill")


def blueprint_name(blueprint_id: int) -> str:
    return _name(BLUEPRINT_NAMES, blueprint_id, "blueprint")


def energy_tower_skill_name(skill_id: int) -> str:
    return _name(ENERGY_TOWER_SKILL_NAMES, skill_id, "energy tower skill")


def map_name(map_id: int) -> str:
    return _name(MAP_NAMES, map_id, "map")


def advance_team_name(advance_team_id: int) -> str:
    return _name(ADVANCE_TEAM_NAMES, advance_team_id, "opening lineup")


def card_name(card_id: int) -> str:
    """Name a reinforcement card: a specialist, equipment, technology, commander skill, blueprint, or units."""
    for table in (
        OFFICER_NAMES,
        EQUIPMENT_NAMES,
        TECHNOLOGY_NAMES,
        COMMANDER_SKILL_NAMES,
        BLUEPRINT_NAMES,
        UNIT_CARD_NAMES,
        UNIT_NAMES,
    ):
        if card_id in table:
            return table[card_id]
    return f"Unknown card ({card_id})"
