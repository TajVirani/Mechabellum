# Self-play and simulation research

This note records what the game exposes for offline simulation (TODO P2) and how a self-play environment could be built on it. Everything here was found read-only in game 2.0.0.5; nothing has been injected into or patched in the game.

## Ground rules

The [Mechabellum wiki's mod page](https://mechabellum.wiki.gg/wiki/Mod) states that client-side mods run through MelonLoader are tolerated at the player's own risk, that mods which send data to the server are bannable, and that anything beyond quality-of-life changes is a grey area until the developers make a final statement. A simulation environment must therefore:

- run only local matches (`BattleSetting.IsLocalGame`), never online or ranked play, and never send anything to the server;
- stay separate from the read-only collector in this package, which keeps working without any mod;
- be opt-in: it needs MelonLoader installed in the game folder, which the player does themselves.

## What the game provides

| Class | Relevant members | What it suggests |
| --- | --- | --- |
| `GameRiver.BattleSetting : BattleInfo` | `prepareTime` 0x80, `deployTime` 0x84, `fightTime` 0x88, `players` 0xA0, `maxRound` 0xB0, `battleRecord` 0xC0, `NetworkOverride` 0xC8, `IsLocalGame` 0xC9 | A match is configured from a setting object that can carry a whole battle record and run locally |
| `GameRiver.Client.ReplaySimulateMatch : ReplayMatchBase` | | A match type that simulates from a battle record rather than playing one back frame by frame |
| `GameRiver.Client.ReplayAIMatch : ReplayMatchBase` | | Replay-driven matches with AI players |
| `GameRiver.Client.AIMatch : MatchClient` | `enableAITest` 0x148 | An AI test match mode |
| `GameRiver.Client.AI.AIManager` | `battleSituation`, `aiControllers`, `actionDelayTime` | The built-in AI that plays deployments |
| `GameRiver.Client.MatchClient` | `fastFightSimulation` 0xD9 | Fights can be simulated without real-time playback |
| `GameRiver.Fight.FightController` | `Tick`, `TickRecord`, `fightCalculator`, `fightSetting` | Fights advance in discrete ticks |

Replays store each round's starting state and the players' actions, not the fight itself, yet play back every fight identically. The fight engine is therefore deterministic given the starting board and the battle's random state, which is what makes simulation from a written battle record plausible.

## Proposed design

1. **Positions in, results out.** A position is written as a `.grbr`-style `BattleRecord` (the XML this package already parses): both players' `PlayerSnapshotData` for the round, plus the random state. Customizing positions then means editing XML, not driving the UI.
2. **A MelonLoader mod** (C#, built against MelonLoader's generated Il2Cpp interop assemblies) starts a `ReplaySimulateMatch` from such a record with `IsLocalGame` set and `fastFightSimulation` on, waits for the fight to end, and writes the resulting record or fight report to disk. A file-based queue (input folder → output folder) lets this package submit batches without any network traffic.
3. **AI-versus-AI matches.** For whole matches the mod would run an `AIMatch` with both seats on `AIManager`, record the `.grbr` the game already saves, and stamp it with the random seed, both strategy versions and the game build.
4. **Fidelity first.** Before generated data is used, re-simulate a set of real replays from their recorded starting states and require the simulated fight reports (score, surviving mechs, destroyed crystals) to match the recorded ones exactly. That check doubles as the "continuous calibration against real replays" item and should run after every game update.

## What is needed before building it

- MelonLoader installed in the game folder (the wiki's Mod Manager does this). Its first launch generates the interop assemblies, which also give the method signatures this read-only scan could not list.
- A .NET SDK to build the mod; this machine has the .NET runtime but no SDK.
- A decision on how the mod is distributed and kept apart from online play.

Until then, the dataset tooling that does not depend on the simulator is in place: `mecha dataset-stats` builds the version index, removes duplicate matches, filters abnormal ones and reports distributions for any replay folder, real or generated, and `mecha evaluate` scores a model on a real-replay test set only.
