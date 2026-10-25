# MechaBridge

A MelonLoader mod that serves the bridge protocol ([contracts/bridge/v1/bridge.proto](../../contracts/bridge/v1/bridge.proto)) on `ws://127.0.0.1:17615/`. `mecha fetch-replays` uses it to download past tournament replays; the website will use the same connection for live game data.

## What it does in game

Every request runs on Unity's main thread and calls the functions the tournament history window itself uses:

| Request | Game calls |
| --- | --- |
| `ListCompetitionsRequest` | `Protos.Match.RequestHistoryMatch { page }`, sent through the game's `MessageCenterV2.SendMsg`. The window only ever sends this message empty (page 1), and `CompetitionProxy.RequestHistoryMatch()` drops repeats during a resend cooldown, so the mod builds it with the page set. Pages start at 1. On page 1 also `RequestMatchList(1, 1)` for ended mini tournaments, read from `CompetitionController.Instance.C_SystemData.C_MatchListData.MatchBaseInfos` |
| `CompetitionPageRequest` | `CompetitionProxy.RequestHistoryMatchDetail(id, subId, page)`. The reply lists each replay path once, with the winner's and loser's user ids from the ranking's `RoundRecord.Win` |
| `DownloadReplayRequest` | `ReplayProxy.DowloadServerReplay(path)`, then the replay is saved through `FileUtility.SaveBinary` to `Replay\<version>\<id>.rep.grbr`, where the window's download button saves it |

Replies are read by Harmony prefixes on `OnResponseHistoryMatch`, `OnResponseHistoryMatchDetail` and `OnResponseMatchList`; they copy the data and let the game's handler run unchanged. One more prefix skips `Competition_HistoryWindow.RefreshList` while the game handles a detail reply the mod asked for, because the window was never opened and the refresh throws a `NullReferenceException`; replies to the window's own requests refresh it as usual. Requests that reach the game's servers are spaced at least `ServerRequestIntervalMs` apart (default 1500 ms), and run one at a time. The mod never sends game data of its own.

The server accepts connections from the local machine only, and browsers only from pages served by `localhost`.

The class and method names come from the game's IL2CPP metadata (build 2.0.0.5.2340) and from [qbisi/mechcore](https://github.com/qbisi/mechcore), which drives the same functions on macOS. No mechcore code is used.

## Install

1. Install [MelonLoader](https://github.com/LavaGang/MelonLoader) 0.6 or later into the game folder and start the game once, so it generates `MelonLoader\Il2CppAssemblies`.
2. Install the [.NET 6 SDK or later](https://dotnet.microsoft.com/download).
3. Build, pointing `GameDir` at the game folder if it is not `D:\STEAM\steamapps\common\Mechabellum`:

   ```powershell
   dotnet build mods\MechaBridge -c Release -p:GameDir="D:\STEAM\steamapps\common\Mechabellum"
   ```

4. Copy `bin\Release\net6.0\MechaBridge.dll` to `<game>\Mods\` and `Google.Protobuf.dll` from the same folder to `<game>\UserLibs\`.
5. Start the game. The MelonLoader console shows `Listening on ws://127.0.0.1:17615/`.

Settings are in `<game>\UserData\MelonPreferences.cfg` under `[MechaBridge]`: `Port` and `ServerRequestIntervalMs` (minimum 500).

## After a game update

The interop assemblies are regenerated on the next launch. Rebuild the mod; a build error names any game method that was renamed or changed signature. `mecha fetch-replays` checks nothing about the build itself, so test one download after every update.
