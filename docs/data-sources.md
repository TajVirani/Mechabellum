# Data sources

The package gets game data through three channels. Each one feeds the same contract, `MatchSnapshot v2` ([contracts/README.md](../contracts/README.md)), directly or through replay files.

| Channel | Provides | Stance | How it knows the game version | Commands |
| --- | --- | --- | --- | --- |
| Replay files (`.grbr`) | `fight_over` snapshots of every round of a finished match, with the winner | Reads files only | The replay's `Version` (the replay format, e.g. 2340); a replay inside a version folder also gets the game version from the folder name | `latest`, `parse`, `dump`, `export-dataset`, `dataset-stats` |
| Live memory (`collector/memory/`) | Snapshots of the match being played or spectated, as it happens | Read-only: `ReadProcessMemory` with `PROCESS_VM_READ` and `PROCESS_QUERY_INFORMATION`; nothing is injected or written | SHA256 of `GameAssembly.dll`, matched exactly against a layout in `layouts.py` ([Memory layout](memory-layout.md)) | `live-probe`, `live`, `live-watch`, `live-record`, `live-predict` |
| MechaBridge mod (`mods/MechaBridge/`) | Past tournament replays, downloaded as replay files | Runs inside the game and only calls the game's own functions that the tournament history window uses, one at a time and at least `ServerRequestIntervalMs` apart (1.5 s by default); it never sends game data of its own and does not touch the match | `StatusReply.game_version`, the game's `Application.version` (e.g. "2.0.0.5.2340") | `fetch-replays` |

The bridge produces no snapshots itself: `fetch-replays` saves `.grbr` files, and the replay parser turns them into snapshots like any other replay.

## Version strings

`collector/versions.py` holds the one parser for version strings. The game's `Application.version` is "<game version>.<replay format>":

| Name | Example | Where it appears |
| --- | --- | --- |
| Application version | `2.0.0.5.2340` | Replay download folders, server replay paths (`2.0.0.5.2340/<id>.rep`), `StatusReply.game_version`, `fetch-replays --versions` |
| Game version | `2.0.0.5` | MatchSnapshot `gameBuild.gameVersion`, `MemoryLayout.game_version`, `live-probe`'s `layoutGameVersion` |
| Replay format | `2340` | A replay's `Version`, MatchSnapshot `gameBuild.replayVersion`, `MemoryLayout.replay_version` |

Live snapshots fill both `gameVersion` and `replayVersion` from the layout. Replay snapshots always fill `replayVersion`, and fill `gameVersion` only for a replay in a folder named after an application version whose replay format matches the file; the game's own saves at the top of the replay directory leave it `null`.

## Replay directory

The game keeps replays in `<game>\ProjectDatas\Replay`:

- matches the player plays or spectates are saved at the top level, as `<replay format>_<battle id>_[A]VS[B].grbr`;
- downloaded replays, from the in-game download button or `fetch-replays`, go to `<application version>\<id>.rep.grbr`.

`mecha probe` and the commands that default to the replay directory find it from the running `Mechabellum.exe` or the Steam library (`collector/locator.py`). `fetch-replays` uses the directory the mod reports (`FileUtility.ReplayDirectoryFullPath`), which is the same folder. `export-dataset` and `dataset-stats` read the whole tree, so fetched replays are included; `latest` only looks at the top level, so it shows the last match you played or spectated, not the last download. A match saved in both places is counted once, by battle id.

Tournament replays have `GameMode` `Competition` (the game's word for tournaments; the bridge protocol keeps it). The replay file does not record the winner. Checked on all 1,033 tournament replays of 2.0.0.4.2331 (828 of them 1v1):

- `teamRanks` is empty in every `MatchSnapshotData`, and no `MatchSnapshotData` has `lastFightResult` reports;
- `roundFightResult` is empty, and `preRoundFightResult` is `Win` for both players in every round of every 1v1 replay, so it is only a default value;
- the last round record is written before the deciding fight, as in every replay, so no reactor core reaches 0;
- the game's protobuf copy of the download, saved next to it as `<id>.rep.bak`, ends at the same round record and has no result field either.

The winner is in the tournament history instead: each `RoundRecord` that `RequestHistoryMatchDetail` returns has `Win`, `MyHp`, `EnemyHp` and the `ReplayPath`. A replay is listed once per player, so the mod takes the winner's and loser's user ids from `Win` and reports them with the replay paths. `fetch-replays` writes them to `<id>.rep.result.json` next to the replay (`winner_user_id`, `loser_user_id`, and the tournament as `source`) and keeps a result file that already exists (`collector/replay/result.py`). The parser takes the player whose id matches `winner_user_id`, so `export-dataset` trains on these replays.

### Winners of the replays the game saves

The parser decides the winner of a replay in this order (`_winner_index` in `collector/replay/parser.py`):

1. a result file next to the replay;
2. a surrender: a `PAD_GiveUp` action in one player's round records, so the other player of a 1v1 wins (it agrees with the tournament result on all 35 surrendered tournament replays of 2331 and 2340);
3. the deciding fight's result, from format 2340 on: `roundFightResult` in every round record holds the whole match's history, ending with the last fight, which no round record follows. A spectated match can lack the first fights, but the history still ends with the last one (checked against the reactor-core drops of 120 fights in 16 top-level 2340 replays).

Otherwise the winner is unknown. Formats before 2340 write each fight's result in the next round record, so the deciding fight is never recorded, and a 2331 match that did not end by surrender has no known winner. `teamRanks` is not a result: it is the reactor-core standing as of the previous round record, so it names the player who led one fight before the end. Labelling winners with it gave the wrong winner for 4 of 16 top-level 2340 1v1 replays and for 4 of 6 AsyncBattle 1v1 replays, where the core counts lives and the opponent's counter falls with each of your wins. The older replays need a result file per match. The game's personal match history could supply them: `PowerRecordProxy.RequestFPDetail` returns `FpRecord.ResponseFPDetail`, a list of `Common.FightRecord` with the time, map, `Reason` (an `EFightReason`, such as `GiveUp`) and, for lobby matches, the players' user ids and `Win`. It has no battle id, so a record would be matched to its replay by opponent, map and time. Nothing reads it yet.

A replay without a result file (downloaded before result files existed, or by a mod build that does not report results) still has no winner: `export-dataset` leaves it out and reports how many 1v1 matches it skipped for that, and `dataset-stats` lists it as `no winner`. `fetch-replays` writes the missing file for every replay it passes that is already on disk, so `fetch-replays --full` labels a whole backfill. The rounds parse either way, so `dump` and `parse` work on every tournament replay.

## Live data

Live data comes from the memory reader into `MatchSnapshot v2` and stays that way for now. The bridge protocol reserves Envelope field numbers 100 and up for live game events, so the website can use the same connection later. When that happens:

- the events carry `MatchSnapshot v2` documents, validated against the same JSON Schema, with the same field semantics, including `null` for unknown; there is no second schema for live data;
- the first step is to relay snapshots the memory reader built (`source.type` stays `memory`); if the mod later reads match state itself, its snapshots get their own `source.type` value and must agree field by field with memory and replay snapshots of the same match, checked the way [Memory layout](memory-layout.md#build-updates) checks a new build;
- the mod keeps its stance: it only reads match state and calls the game's own functions, and sends nothing to the game's servers that the game would not.

None of this needs a change to the mod today. A live event is a new Envelope field in `contracts/bridge/v1/bridge.proto` and a rebuild of the mod.
