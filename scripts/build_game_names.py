"""Build src/mechabellum/collector/game_names.json, the id-to-name and price tables.

Names and prices come from qbisi/mechcore, whose config/ is generated from one game build (its GAME_VERSION file
names it). Names of ids that build no longer holds come from mechstats/mech-data (game 1.8.0.3), so older replays
stay readable. Run it again when mechcore moves to a new game version and review the diff:

    .venv\\Scripts\\python scripts\\build_game_names.py [--mechcore-ref <commit>]
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

MECHCORE = "qbisi/mechcore"
MECH_DATA = "mechstats/mech-data"
OUTPUT = Path(__file__).resolve().parents[1] / "src/mechabellum/collector/game_names.json"
LOCALIZED = ("units", "officers", "commander_skills", "equipment", "technologies", "blueprints")
LOCALIZED += ("energy_tower_skills", "maps")
FALLBACK = {"officers": "officers", "equipment": "equipment", "technologies": "techs"}


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def _commit(repository: str, ref: str) -> str:
    return json.loads(_fetch(f"https://api.github.com/repos/{repository}/commits/{ref}"))["sha"]


def _raw(repository: str, commit: str, path: str) -> str:
    return _fetch(f"https://raw.githubusercontent.com/{repository}/{commit}/{path}")


def _section(text: str, name: str) -> str:
    match = re.search(rf"^{name}:\n((?:  .*\n?)*)", text, re.M)
    return match.group(1) if match else ""


def _camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part.title() for part in rest)


def _sorted(table: dict[int, object]) -> dict[str, object]:
    return {str(item_id): value for item_id, value in sorted(table.items())}


def build(mechcore_ref: str) -> dict[str, object]:
    commit = _commit(MECHCORE, mechcore_ref)
    mech_data_commit = _commit(MECH_DATA, "HEAD")
    game_version = _raw(MECHCORE, commit, "GAME_VERSION").strip()

    def config(name: str) -> str:
        return _raw(MECHCORE, commit, f"config/{name}.yaml")

    localization = config("localization")
    names: dict[str, dict[int, str]] = {
        key: {
            int(item_id): en
            for item_id, en in re.findall(r'^  (\d+): \{en: "([^"]*)"', _section(localization, key), re.M)
        }
        for key in LOCALIZED
    }
    for key, file in FALLBACK.items():
        old = json.loads(_raw(MECH_DATA, mech_data_commit, f"data/latest/generated_{file}.json"))["entityMap"]
        for item_id, entity in old.items():
            if entity.get("name") and int(item_id) not in names[key]:
                names[key][int(item_id)] = entity["name"].strip()

    units = names.pop("units")
    teams: dict[int, str] = {}
    for row in re.findall(r"^  - \{(.*)\}$", config("advance_teams"), re.M):
        team_id = int(re.search(r"id: (\d+)", row).group(1))
        members = re.search(r"units: \[([^\]]*)\]", row)
        if members:
            ids = [int(item) for item in members.group(1).split(",")]
            teams[team_id] = " + ".join(f"{ids.count(unit)} {units[unit]}" for unit in dict.fromkeys(ids))
        else:
            teams[team_id] = re.search(r"name: ([^,}]+)", row).group(1).strip()
    names["advance_teams"] = teams

    card_supply = {
        int(item_id): int(supply)
        for item_id, supply in re.findall(r"\{id: (\d+), name: [^}]*?supply: (\d+)\}", config("reinforce_items"))
    }
    unit_cards: dict[int, str] = {}
    pattern = r"\{id: (\d+), name: ([^,]+), supply: (\d+), unit: \d+, squads: (\d+), level: (\d+)"
    for item_id, name, supply, squads, level in re.findall(pattern, config("unit_reinforcements")):
        unit_cards[int(item_id)] = f"{squads} {name.strip()} (level {level})"
        card_supply[int(item_id)] = int(supply)
    names["unit_cards"] = unit_cards

    prices: dict[int, dict[str, int]] = {}
    for block in re.split(r"^  - type: ", config("unit_prices"), flags=re.M)[1:]:
        fields = dict(re.findall(r"^    (\w+): (\d+)", block, re.M))
        prices[int(fields["unit_id"])] = {
            _camel(key): int(fields[key])
            for key in ("supply", "unlock_supply", "upgrade_supply", "members")
            if key in fields
        }
    unit_technologies: dict[int, list[int]] = {}
    technology_supply: dict[int, int] = {}
    for block in re.split(r"^  - type: ", config("unit_techs"), flags=re.M)[1:]:
        unit_id = int(re.search(r"unit_id: (\d+)", block).group(1))
        rows = [(int(item_id), int(supply)) for item_id, supply in re.findall(r"\{id: (\d+), supply: (\d+)\}", block)]
        unit_technologies[unit_id] = [item_id for item_id, _ in rows]
        technology_supply.update(rows)

    return {
        "sources": {
            "primary": f"https://github.com/{MECHCORE}/tree/{commit}/config (game {game_version})",
            "fallback": f"https://github.com/{MECH_DATA}/tree/{mech_data_commit}/data/latest (game 1.8.0.3)",
        },
        "gameVersion": game_version.rsplit(".", 1)[0],
        **{_camel(key): _sorted(table) for key, table in names.items()},
        "unitPrices": _sorted(prices),
        "unitTechnologies": _sorted(unit_technologies),
        "technologySupply": _sorted(technology_supply),
        "cardSupply": _sorted(card_supply),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mechcore-ref", default="HEAD", help="mechcore commit, branch or tag to read.")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    tables = build(args.mechcore_ref)
    with args.output.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(tables, file, ensure_ascii=False, indent=1)
        file.write("\n")
    counts = {key: len(value) for key, value in tables.items() if key != "sources" and isinstance(value, dict)}
    print(f"Wrote {args.output} from {tables['sources']['primary']}: {counts}")


if __name__ == "__main__":
    main()
