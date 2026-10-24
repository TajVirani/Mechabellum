# Mechabellum Analytics

A research project for Mechabellum spectator analytics. It combines `.grbr` replay parsing, read-only live collection on Windows, versioned match snapshot data, dataset generation, model training, and round-by-round final win probability inference in a single Python package.

The project uses `MatchSnapshot v2` as its formal data boundary:

```text
.grbr replay ─────┐
                  ├─ collector ─→ MatchSnapshot v2 ─→ datasets ─→ training ─→ model
live process ─────┘                        └──────────────────────→ inference
```

Runtime modules pass strongly typed Python objects directly; data is saved and exchanged as versioned JSON or JSONL validated against a JSON Schema.

## Contribute to the public replay collection

> [!IMPORTANT]
> We are publicly collecting replays that Mechabellum automatically saves for players. They are used to expand
> cross-version research data, improve the parser, and train and evaluate non-commercial game analysis models.

See the **[replay collection repository](https://github.com/FogMoe/Mechabellum-Replays)** for details, or
**[upload a replay](https://github.com/FogMoe/Mechabellum-Replays/issues/new?template=replay-upload.yml)** directly.

## Features

- Parse `.grbr` replays and output a `fight_over` snapshot for each round
- Read both players' deployments while spectating via Windows `ReadProcessMemory`
- Record players, rounds, economy, units, levels, experience, coordinates, equipment (up to two items per unit), technologies, fight history, card offers and choices, commander skills, officers, buildings, contraptions, and unlocked units
- Export a replay directory as a `MatchSnapshot v2` JSONL dataset
- Split training and test sets by whole match and train a player-symmetric win probability baseline
- Compute final win probabilities for a single position, a full match timeline, or live at the end of each round's fight

## Installation

Requires Python 3.11 or later. Live memory collection is Windows-only; replay processing and the model pipeline run on other Python platforms.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e .
```

The base install provides replay and live collection. Install the `ml` extra for training and inference, and the `dev` extra as well for a development environment:

```powershell
.venv\Scripts\python -m pip install -e ".[ml]"
.venv\Scripts\python -m pip install -e ".[ml,dev]"
```

## Usage

Locate the game, replay directory, and logs:

```powershell
.venv\Scripts\mecha probe
```

Read the latest replay, or export a trainable dataset:

```powershell
.venv\Scripts\mecha latest --json
.venv\Scripts\mecha export-dataset --output data\match-snapshots.v2.jsonl
```

Check the memory layout, read one live snapshot, or continuously watch for changes:

```powershell
.venv\Scripts\mecha live-probe
.venv\Scripts\mecha live --json
.venv\Scripts\mecha live-watch --json --interval 500
```

Train a model and view round-by-round win probabilities for a match:

```powershell
.venv\Scripts\mecha train --dataset data\match-snapshots.v2.jsonl
.venv\Scripts\mecha timeline data\match-snapshots.v2.jsonl
```

While spectating, output both players' final win probabilities when each round's fight ends:

```powershell
.venv\Scripts\mecha live-predict --model artifacts\win_model.joblib
```

Download past tournament replays, newest first, through the [MechaBridge mod](mods/MechaBridge/README.md) (needs MelonLoader and `pip install -e ".[bridge]"`). It defaults to the running game's version and stops after 10 replays in a row that are already on disk, or at the first replay older than every requested version:

```powershell
.venv\Scripts\mecha fetch-replays
.venv\Scripts\mecha fetch-replays --versions 2.0.0.5.2340 2.0.0.4.2331
```

`--full` ignores the 10-in-a-row rule and walks to the oldest requested version, skipping replays already on disk; use it to resume a backfill that was interrupted.

All commands and options are listed by `.venv\Scripts\mecha --help` and each subcommand's `--help`.

## Project structure

```text
Mechabellum/
├─ pyproject.toml
├─ contracts/match-snapshot/v2/     # JSON Schema and example (v1 kept as a record)
├─ contracts/bridge/v1/             # Protobuf protocol between the mod, the CLI and the website
├─ mods/MechaBridge/                 # MelonLoader mod that serves the bridge protocol in game
├─ src/mechabellum/
│  ├─ bridge/                        # Bridge protocol client
│  ├─ collector/                     # Replay, live memory and tournament data sources
│  ├─ contracts/                     # Strongly typed MatchSnapshot
│  ├─ datasets/                      # JSONL reading/writing and replay export
│  ├─ features/                      # Player-symmetric baseline features
│  ├─ models/                        # Model artifact format
│  ├─ training/                      # Training and evaluation
│  ├─ inference/                     # Single-position, timeline, and live inference
│  └─ cli/                           # Unified mecha command
├─ tests/
├─ docs/
├─ data/                             # Local data, not committed
└─ artifacts/                        # Local models, not committed
```

See [Architecture](docs/architecture.md) for module boundaries and dependency direction, [Memory layout](docs/memory-layout.md) for live build versions and offsets, and [TODO](TODO.md) for upcoming features.

## Data contract

The specification is at [contracts/match-snapshot/v2/schema.json](contracts/match-snapshot/v2/schema.json), with a readable example at [fight-over.example.json](contracts/match-snapshot/v2/fight-over.example.json); [contracts/README.md](contracts/README.md) explains snapshot timing and field semantics. Collection, datasets, training, and inference entry points all use the same set of Pydantic models and run JSON Schema validation at persistence boundaries.

## Verification

```powershell
.venv\Scripts\ruff check src tests
.venv\Scripts\pytest -q
```

Live collection depends on a supported game build and `GameAssembly.dll` hash; game 2.0.0.5 (replay format 2340) and 1.11.0.2a are supported. After a game update, run `mecha live-probe` first and complete version validation as described in the memory layout document.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md), which permits only the non-commercial uses defined in the license. Commercial use is not covered by this license.
