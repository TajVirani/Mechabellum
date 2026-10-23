# Data contracts

`match-snapshot/v2/schema.json` defines `MatchSnapshot v2`, shared by collection, persistence, training, and inference. `battle-start.example.json` is a complete example that passes validation against this schema. `match-snapshot/v1/` is kept as a historical record only; the package reads and writes v2 exclusively, and v1 datasets should be regenerated from replays with `mecha export-dataset`.

The contract version is in the path and in the document field `schemaVersion`. Existing field semantics stay stable within a major version; incompatible structural or semantic changes use a new version directory.

Each line of a JSONL dataset holds one complete snapshot, encoded as UTF-8. Both read and write entry points validate the persisted representation against the schema in this directory and construct strongly typed models for use within the package.

## Null means unknown

A `null` value means the source could not provide the field. It is never a stand-in for zero or empty: an empty list means the source reported that nothing is there. For example, replays do not record per-item durability for unit equipment, so it is `null`, while `equipmentInventory` durability comes from the replay as recorded.

## Changes from v1

| Area | v1 | v2 |
| --- | --- | --- |
| Unit equipment | `equipmentId` and `durability` (always 0 in replay formats 2331 and later) | `equipment`: list of `{equipmentId, durability}`; a unit can hold two items |
| `team` | Replays wrote 0 for every player | `null` unless the replay assigns distinct teams |
| `state` | Replays wrote `BattleStart`, live wrote the game enum | One enum for both sources: `Deploying`, `DeployOver`, `Fighting`, `FightOver`, `Unknown` |
| `previousFightResult` | Replays reported `Win` in round 1, and in every round for format 2340 | Derived from `fightResultHistory`; `null` before the first fight |
| New player fields | | `maxReactorCore`, `roundSupplyIncome`, `fightResultHistory`, `equipmentInventory`, `commanderSkills`, `officerIds`, `buildings`, `contraptions`, `blueprintIds`, `energyTowerSkillIds`, `towerStrengthenLevels`, `unlockedUnitIds`, `reinforcementChoice` |
| New match field | | `reinforcementOffer`: the card offer dealt to both players this round |

## Field notes

- `fightResultHistory` lists the results of the fights completed before the snapshot's round, oldest first. Replay format 2340 stores the whole match's history in every round record; the parser truncates it so later results never leak into earlier rounds.
- `reinforcementOffer` and `reinforcementChoice` are aligned by round: `offerIndex` indexes into `reinforcementOffer`. `AsyncBattle` uses a reinforcement shop instead, and its recorded opponent has no choice.
- `maxReactorCore` and `roundSupplyIncome` are current values read from live memory. Replays only store starting values and income settings, so replay snapshots leave them `null`.
