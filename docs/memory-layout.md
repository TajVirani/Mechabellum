# Live match memory layout

Live collection is implemented in `src/mechabellum/collector/memory/`. `windows_process.py` wraps process and module enumeration, `OpenProcess`, `ReadProcessMemory`, and `CloseHandle`; `il2cpp_reader.py` reads pointers, value types, strings, lists, dictionaries, and type information; `layouts.py` stores build-specific addresses and field offsets as one `MemoryLayout` record per build; `live_source.py` converts the object graph into `MatchSnapshot v2`.

The process handle uses the following access rights; the collector never writes to the game:

- `PROCESS_VM_READ` (`0x0010`)
- `PROCESS_QUERY_INFORMATION` (`0x0400`)

## Supported versions

| Item | 2.0.0.5 | 1.11.0.2a |
| --- | --- | --- |
| Steam build | 26153644 | |
| Replay format | 2340 | 2119 |
| `GameAssembly.dll` SHA256 | `0BC9CE7237E81ACB0A4B7D0819F3E05C8D4E5C299FFC2CDFCF12A3E8E5B8B493` | `0FE278BC3A1DD6FF55A51DB2807CCD73ED16A1FE390FE72FFA013F0AEFF495F1` |
| `MatchClient` class global RVA | `0x3E1C948` | `0x3C799F8` |

The 2.0.0.5 layout was verified on two spectated `WatchMatch` games, one joined at round 4 and one from round 1. Each `FightOver` frame was compared field by field with the replay of the same match (see [Snapshot timing](../contracts/README.md#snapshot-timing)). Units, levels, experience, round counts, coordinates, equipment, supply, reactor core, technologies, fight history, card offer and choice, inventory, commander skills, officers, buildings, contraptions, tower strengthen levels and unlocked units all matched. The 1.11.0.2a layout is kept unchanged from its original verification and does not read the v2 player fields.

## Root object

```text
GameAssembly + MatchClient class global RVA
  → MatchClient Il2CppClass
  → static_fields (+0xB8)
  → MatchClient.Current (+0x08)
```

`live-probe` verifies the module hash, root type, and current match object. `MatchClient.Current` is null in the lobby; once a readable spectated or played match starts, `live` reads the match state from its base class fields.

## Main fields

| Object | Field | 2.0.0.5 | 1.11.0.2a |
| --- | --- | ---: | ---: |
| `Match` | `battleInfo` | `0x30` | `0x30` |
| `Match` | `RoundCount` | `0x64` | `0x64` |
| `Match` | `playerManager` | `0x70` | `0x70` |
| `PlayerManager` | `playerControllers` | `0x18` | `0x18` |
| `PlayerController` | `unitManager` | `0x30` | `0x20` |
| `PlayerController` | `player` | `0x138` | `0x128` |
| `PlayerController` | `teamController` | `0x140` | `0x130` |
| `PlayerController` | `teamSystem` | `0x158` | `0x148` |
| `PlayerController` | `technologyManager` | `0x1A0` | not read |
| `Player` | `playerAgent` | `0xE8` | `0xE0` |
| `Player` | `supply` | `0xF4` | `0xEC` |
| `Player` | `State` | `0x110` | `0x108` |
| `Player` | `reactorCore` | `0x13C` | `0x134` |
| `Player` | `maxReactorCore` | `0x144` | not read |
| `Player` | `roundSupplyIncome` | `0x14C` | not read |
| `Player` | previous fight result | not present | `0x158` |
| `Player` | `RoundFightResultHistory` (`List<int>`) | `0x160` | not present |
| `PlayerAgent` | `technologyManagers` | not read | `0x100` |
| `TechnologyManager` | `technologyManagers` (`Dictionary<int, UnitTechnologyManager>`) | `0x28` | |
| `TeamSystem` | `teamControllers` | `0x28` | `0x28` |
| `UnitManager` | `units` | `0x38` | `0x38` |
| `UnitTechnologyManager` | `technologies` | `0x10` | `0x10` |
| `UnitTechnologyManager` | `UnitID` | `0x18` | `0x18` |
| `ActivableItem/Technology` | `isActive` | `0x18` | `0x18` |
| `Item` | `itemData` | `0x10` | `0x10` |
| `GRObject` (`CardData`, item data) | `id` | `0x10` | `0x10` |
| `CardElement` | `unitData` | `0x10` | `0x10` |
| `CardElement` | equipment | `0x28` (`List<Equipment>`) | `0x28` (one `Equipment`) |
| `CardElement` | `mapElement` | `0x38` | `0x38` |
| `CardElement` | `mechTeam` | `0x48` | `0x48` |
| `CardElement` | `sellSupply` | `0x60` | `0x60` |
| `Equipment` | `data` | `0x20` | `0x20` |
| `Equipment` | `durability` | `0x30` | `0x30` |
| `MapElement` | `bound` (`RectInt`) | `0x18` | `0x18` |
| `MapElement` | `isRotate` | `0x2C` | `0x2C` |
| `MechTeam` | `level` | `0x2C` | `0x2C` |
| `MechTeam` | `expFloat` (`FPoint Q32.32`) | `0x38` | `0x38` |
| `MechTeam` | `roundCount` | `0x58` | `0x50` |

`State` values are 0 `Deploying`, 1 `DeployOver`, 2 `Fighting`, 3 `FightOver`; fight results are 0 `Win`, 1 `Lose`, 2 `Deuce`. `RoundFightResultHistory` already holds the current round's result once the fight starts and only covers fights since the spectator attached; the reader counts finished fights only and reports `null` when the list is shorter than that.

In 2.0.0.5 the match updates `PlayerController.technologyManager`; `PlayerAgent.technologyManagers` still exists but only holds inactive copies.

## 2.0.0.5 player modules

The v2 player fields come from `PlayerController` managers. Each manager keeps its item list at `+0x28`; an item's id is `itemData (+0x10) → id (+0x10)`.

| Snapshot field | Source |
| --- | --- |
| `reinforcementOffer` | `reinforcementManager (+0x168) → roundReinforceItems (+0x50)`, last inner list; both players hold the same offer |
| `reinforcementChoice` | `reinforcementManager → choosedReinforceItems (+0x58)`, this round's pick, matched against the offer |
| `equipmentInventory` | `equipmentManager (+0x1B8)` items, durability at `+0x30` |
| `commanderSkills` | `commanderSkillManager (+0x198)` items: `coolingRound +0x28`, `getRound +0x30`, `IsActive +0x34`; the slot is the list position |
| `officerIds` | `officerManager (+0x190)`: `invisibleOfficers (+0x30)` then `officers (+0x28)` |
| `buildings` | `constructionManager (+0x1B0) → combinationID2ConstructionMap (+0x40)`, a `SyncDictionary` whose `values` list is at `+0x18`; each `ConstructionElement` has `constructionData +0x18`, `combinationIndex +0x20`, `mapElement +0x28`, `durabilities +0x40` |
| `contraptions` | `contraptionManager (+0x1A8) → fightObjectRecorder (+0x30)`, history `+0x18` and current `+0x20` records: `Index +0x10`, `RecordSource +0x18 → data +0x18 → id`, `Positions +0x20` (`List<Vector2Int>`) |
| `towerStrengthenLevels` | `buildingManager (+0x1C8) → buildings (+0x30)`, each tower's `towerStrengthenData (+0x30)` id, 0 when null |
| `unlockedUnitIds` | `shopManager (+0x1D0) → shop (+0x40) → unlockedUnits (+0x28)`, `CardElement → unitData → id` |

`blueprintIds` comes from `blueprintManager (+0x178)`, whose items are one slot per blueprint line with an `IsActive` byte at `+0x18`. A one-off blueprint (Sticky Oil Bomb 1, Field Recovery 2, Mobile Beacon 3) is flagged active once researched. An enhancement's slot moves to its next tier instead: researching Defense Enhancement turns slot 5 into 501. Replays list the researched ids in ascending order, so a slot past its first tier counts as its base id (`501 // 100 = 5`). This matched the replay in every round of a spectated 2.0.0.5 match (2026-10-24). A flagged final tier (Attack Enhancement II bought, which replays list as 401) has not been seen live.

`energyTowerSkillIds` is left `null` live. `energyTowerManager (+0x1C0)` lists all five skills and flags each one used during the current round (the flags clear when the next round starts). Replays list only some of those skills, by a rule not yet known: in that match, one Rapid Resupply out of more than ten skill uses.

## Build updates

`LiveMemorySource.attach()` computes the SHA256 of `GameAssembly.dll` and only selects an exactly matching layout. When adapting to a new build, add a separate layout record in `layouts.py` and complete the following checks:

1. `mecha live-probe` returns the `MatchClient` root type and the target layout;
2. `Current` is null in the lobby;
3. While spectating from round 1, verify both players' names, units, levels, economy, coordinates, technologies, and fight history;
4. Phase and deployment changes across consecutive rounds are read reliably;
5. Each live `FightOver` frame matches the replay snapshot of the same round from that match's replay;
6. Memory unit tests and live integration tests all pass.

To find moved offsets, scan the module's `.data` section for a pointer to the class named `MatchClient` (the new RVA), then dump each class's IL2CPP field table by name: `Il2CppClass` name `+0x10`, namespace `+0x18`, parent `+0x58`, fields `+0x80`, static fields `+0xB8`; each `FieldInfo` is `0x20` bytes holding name, type, parent and offset.
