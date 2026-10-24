# Project architecture

The repository contains one installable Python package and one unified command entry point. Source code is layered into data collection, data contracts, datasets, features, models, training, inference, and the command line.

```text
Mechabellum/
├─ README.md
├─ TODO.md
├─ pyproject.toml
├─ contracts/
│  ├─ match-snapshot/v2/            (v1/ kept as a record)
│  │  ├─ schema.json
│  │  └─ fight-over.example.json
│  └─ bridge/v1/bridge.proto
├─ mods/MechaBridge/                (MelonLoader mod, C#)
├─ src/mechabellum/
│  ├─ bridge/
│  ├─ collector/
│  │  ├─ memory/
│  │  │  ├─ windows_process.py
│  │  │  ├─ il2cpp_reader.py
│  │  │  ├─ layouts.py
│  │  │  └─ live_source.py
│  │  ├─ replay/
│  │  │  ├─ extractor.py
│  │  │  └─ parser.py
│  │  ├─ locator.py
│  │  ├─ tournament.py
│  │  ├─ unit_catalog.py
│  │  └─ versions.py
│  ├─ contracts/
│  ├─ datasets/
│  ├─ features/
│  ├─ models/
│  ├─ training/
│  ├─ inference/
│  └─ cli/
├─ tests/
├─ docs/
├─ data/
└─ artifacts/
```

## Data flow

```text
                     ┌─ replay extractor/parser ─┐
Mechabellum data ────┤                            ├─→ MatchSnapshot v2
                     └─ Windows memory source ───┘             │
                                                                ├─→ JSON / JSONL
                                                                ├─→ feature extraction
                                                                ├─→ model training
                                                                └─→ inference
```

The MechaBridge mod adds tournament replays to the replay directory, where the replay parser reads them like any other; [Data sources](data-sources.md) covers each channel.

`MatchSnapshot v2` is the only output type of the collection layer and the only position input type for downstream modules. The typed models enforce runtime field constraints; the JSON Schema handles persistence and cross-process data validation.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `collector.memory` | Process lookup, Windows API, IL2CPP primitive reads, version layouts, and live snapshots |
| `collector.replay` | Safe extraction of replay XML, parsing round state and final results |
| `collector.tournament` | Walking the tournament history newest first and downloading replays through a bridge |
| `collector.locator`, `collector.versions` | Finding the game, its replay directory and replay files; parsing version strings |
| `bridge` | Client for the MechaBridge mod's protobuf WebSocket protocol |
| `contracts` | `MatchSnapshot` typed models, serialization, and schema validation |
| `datasets` | JSONL reading/writing, batch replay directory export, and failure statistics |
| `features` | Deterministically ordered, player-symmetric features generated from full snapshots |
| `models` | Versioned artifacts for the model, feature signature, and training metadata |
| `training` | Splitting by `battleId` group, training, hyperparameter selection, and evaluation |
| `inference` | Single-snapshot prediction, round-by-round timeline, and live prediction |
| `cli` | `mecha` command, arguments, output encoding, and error boundary |

## Dependency direction

The allowed primary dependency directions are:

```text
collector ─→ contracts
datasets  ─→ collector.replay + collector.locator + contracts
features  ─→ contracts
models    ─→ features
training  ─→ datasets + features + models
inference ─→ contracts + features + models
cli       ─→ the public entry points above, and bridge
```

`collector.tournament` takes any object with the bridge's methods, so it does not import `bridge` or protobuf.

The collection layer does not depend on machine learning components. `numpy`, `scikit-learn`, and `joblib` are in the optional `ml` extra, and `protobuf` and `websockets` in the optional `bridge` extra, so the base install can perform replay and live collection on its own.

## Contract rules

- New persisted fields go into the corresponding version's JSON Schema first, then into the Pydantic models and both collection sources.
- Field semantics stay stable within a schema version; incompatible changes are published as a new version directory.
- Unknown game IDs keep their raw numeric values; unknown or unavailable fields use explicit nulls.
- Each JSONL line contains one complete `MatchSnapshot`; snapshots from the same match are linked by `match.battleId`.
- Model artifacts store feature names and contract information, and the feature signature is checked on load.

## Local directories

`data/` holds replay-derived JSONL and experiment data; `artifacts/` holds models and reports. Neither is under version control. One-off reverse engineering output goes in the system temp directory.

## Test boundaries

- Contract tests: schema validation, aliases, and serialization round trips
- Replay tests: embedded XML extraction, parsing, round selection, and dataset export
- Memory tests: IL2CPP string/list reads, process module enumeration, and the live root object
- Tournament tests: the fetch walk against a fake bridge, and the bridge client's framing (skipped without the `bridge` extra)
- Feature tests: probability symmetry when players are swapped
- Pipeline tests: training on synthetic data, saving, loading, and predicting with the model
