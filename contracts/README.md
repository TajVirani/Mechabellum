# Data contracts

`bridge/v1/bridge.proto` is the protocol the [MechaBridge mod](../mods/MechaBridge/README.md) serves over a local WebSocket, one `Envelope` per binary frame, for the `mecha` CLI and the website. `src/mechabellum/bridge/bridge_pb2.py` is generated from it with `python -m grpc_tools.protoc -I contracts/bridge/v1 --python_out=src/mechabellum/bridge --pyi_out=src/mechabellum/bridge contracts/bridge/v1/bridge.proto` (protoc cannot read `\\wsl.localhost` paths, so run it from a Linux shell or a local copy). The mod compiles the proto at build time.

The rest of this document covers MatchSnapshot.

`match-snapshot/v2/schema.json` defines `MatchSnapshot v2`, shared by collection, persistence, training, and inference. `fight-over.example.json` is a complete example that passes validation against this schema. `match-snapshot/v1/` is kept as a historical record only; the package reads and writes v2 exclusively, and v1 datasets should be regenerated from replays with `mecha export-dataset`.

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
| Replay snapshot timing | Round r's record, labeled `battle_start` | The board at the end of fight r, labeled `fight_over` (see below) |
| New player fields | | `maxReactorCore`, `roundSupplyIncome`, `fightResultHistory`, `equipmentInventory`, `commanderSkills`, `officerIds`, `buildings`, `contraptions`, `blueprintIds`, `energyTowerSkillIds`, `towerStrengthenLevels`, `unlockedUnitIds`, `reinforcementChoice` |
| New match field | | `reinforcementOffer`: the card offer dealt to both players this round |

## Snapshot timing

A replay writes each round's record when that round begins, before income and deployment. Record r + 1 therefore holds the board exactly as it stood when fight r ended; this was confirmed against live memory in game 2.0.0.5, where units, experience, round counts, supply and reactor core matched the live `FightOver` frame field for field. The parser emits that board as round r with phase `fight_over`, together with round r's card offer and choice from record r. The last fight of a match has no following record, so it has no snapshot.

Models train on `fight_over` snapshots, and the live predictor runs on the first `FightOver` frame of each round, while the board is still on the field.

## Field notes

- `fightResultHistory` lists the results of the fights finished at the time of the snapshot, oldest first; a `fight_over` snapshot of round r includes fight r. Replay format 2340 stores the whole match's history in every round record; the parser truncates it so later results never leak into earlier rounds. Live memory only holds the fights since the spectator attached, so the history is `null` when spectating starts mid-match.
- `reinforcementOffer` and `reinforcementChoice` are aligned by round: `offerIndex` indexes into `reinforcementOffer`. `AsyncBattle` uses a reinforcement shop instead, and its recorded opponent has no choice.
- `maxReactorCore` and `roundSupplyIncome` are current values read from live memory. Replays only store starting values and income settings, so replay snapshots leave them `null`.
- `officerIds` lists hidden officers first, then visible ones, in both sources. `towerStrengthenLevels` has one entry per tower, 0 when never strengthened.
- `blueprintIds` and `energyTowerSkillIds` are `null` in live snapshots: memory holds every blueprint and energy tower skill with an active flag, and neither the full lists nor the active subsets match what replays record.
- `formationIndex` is the game's unit index in replays and the list position in live snapshots, so the two can differ once units have been sold. Unit equipment durability is `null` in replays and read from memory live.
