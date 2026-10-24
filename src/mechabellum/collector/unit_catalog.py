import json
from importlib.resources import files

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


# Names extracted from game 1.8.0.3 by https://github.com/mechstats/mech-data; ids added since then are unknown.
_GAME_NAMES = json.loads(files(__package__).joinpath("game_names.json").read_text(encoding="utf-8"))
GAME_NAMES_VERSION: str = _GAME_NAMES["gameVersion"]


def _table(key: str) -> dict[int, str]:
    return {int(item_id): name for item_id, name in _GAME_NAMES[key].items()}


OFFICER_NAMES = _table("officers")
EQUIPMENT_NAMES = _table("equipment")
TECHNOLOGY_NAMES = _table("technologies")
ADVANCE_TEAM_NAMES = _table("advanceTeams")


def unit_name(unit_id: int) -> str:
    return UNIT_NAMES.get(unit_id, f"Unknown unit ({unit_id})")


def officer_name(officer_id: int) -> str:
    return OFFICER_NAMES.get(officer_id, f"Unknown specialist ({officer_id})")


def equipment_name(equipment_id: int) -> str:
    return EQUIPMENT_NAMES.get(equipment_id, f"Unknown equipment ({equipment_id})")


def technology_name(technology_id: int) -> str:
    return TECHNOLOGY_NAMES.get(technology_id, f"Unknown technology ({technology_id})")


def advance_team_name(advance_team_id: int) -> str:
    return ADVANCE_TEAM_NAMES.get(advance_team_id, f"Unknown opening lineup ({advance_team_id})")


def card_name(card_id: int) -> str:
    """Name a reinforcement card, which can be a specialist, equipment, technology, or unit."""
    for table in (OFFICER_NAMES, EQUIPMENT_NAMES, TECHNOLOGY_NAMES, UNIT_NAMES):
        if card_id in table:
            return table[card_id]
    return f"Unknown card ({card_id})"
