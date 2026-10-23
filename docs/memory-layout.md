# Live match memory layout

Live collection is implemented in `src/mechabellum/collector/memory/`. `windows_process.py` wraps process and module enumeration, `OpenProcess`, `ReadProcessMemory`, and `CloseHandle`; `il2cpp_reader.py` reads pointers, value types, strings, lists, and type information; `layouts.py` stores build-specific addresses and field offsets; `live_source.py` converts the object graph into `MatchSnapshot v1`.

The process handle uses the following access rights:

- `PROCESS_VM_READ` (`0x0010`)
- `PROCESS_QUERY_INFORMATION` (`0x0400`)

## Supported version

| Item | Value |
| --- | --- |
| Replay format | 2119 |
| Game version | 1.11.0.2a |
| `GameAssembly.dll` SHA256 | `0FE278BC3A1DD6FF55A51DB2807CCD73ED16A1FE390FE72FFA013F0AEFF495F1` |
| `MatchClient` class global RVA | `0x3C799F8` |

This layout has been verified in an actual `WatchMatch` for both players' names, round, unit IDs, formation count, levels, experience, coordinates, orientation, supply, core value, and previous round result.

## Root object

```text
GameAssembly + 0x3C799F8
  → MatchClient Il2CppClass
  → static_fields (+0xB8)
  → MatchClient.Current (+0x08)
```

`live-probe` verifies the module hash, root type, and current match object. `MatchClient.Current` is null in the lobby; once a readable spectated or played match starts, `live` reads deployment state from its base class fields.

## Main fields

| Object | Field | Offset |
| --- | --- | ---: |
| `Match` | `battleInfo` | `0x30` |
| `Match` | `RoundCount` | `0x64` |
| `Match` | `playerManager` | `0x70` |
| `PlayerManager` | `playerControllers` | `0x18` |
| `PlayerController` | `unitManager` | `0x20` |
| `PlayerController` | `player` | `0x128` |
| `PlayerController` | `teamController` | `0x130` |
| `PlayerController` | `teamSystem` | `0x148` |
| `Player` | `playerAgent` | `0xE0` |
| `Player` | `State` | `0x108` |
| `PlayerAgent` | `technologyManagers` | `0x100` |
| `TeamSystem` | `teamControllers` | `0x28` |
| `UnitManager` | `units` | `0x38` |
| `UnitTechnologyManager` | `technologies` | `0x10` |
| `UnitTechnologyManager` | `UnitID` | `0x18` |
| `ActivableItem/Technology` | `isActive` | `0x18` |
| `CardElement` | `unitData` | `0x10` |
| `CardElement` | `equipment` | `0x28` |
| `CardElement` | `mapElement` | `0x38` |
| `CardElement` | `mechTeam` | `0x48` |
| `CardElement` | `sellSupply` | `0x60` |
| `GRObject/CardData` | `id` | `0x10` |
| `MapElement` | `bound` (`RectInt`) | `0x18` |
| `MapElement` | `isRotate` | `0x2C` |
| `MechTeam` | `level` | `0x2C` |
| `MechTeam` | `expFloat` (`FPoint Q32.32`) | `0x38` |
| `MechTeam` | `roundCount` | `0x50` |

## Build updates

`LiveMemorySource.attach()` computes the SHA256 of `GameAssembly.dll` and only selects an exactly matching layout. When adapting to a new build, add a separate layout record in `layouts.py` and complete the following checks:

1. `mecha live-probe` returns the `MatchClient` root type and the target layout;
2. `Current` is null in the lobby;
3. While spectating, verify both players' names, formation count, unit IDs, levels, economy, and coordinates;
4. Phase and deployment changes across consecutive rounds are read reliably;
5. The final snapshot from the same match's replay matches the live output fields;
6. Memory unit tests and live integration tests all pass.
