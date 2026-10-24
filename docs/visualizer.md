# Visualizer v1 spec

`mecha visualize` serves the **Visualizer** (see `GLOSSARY.md`): a local browser app with a **Stats view** (the Local Player's own history) and a **Current Match view** (the match in progress). This is the handoff spec the v1 build follows. The decisions behind it are in the Visualizer wayfinding map (`.scratch/visualizer/map.md`, untracked) and in [ADR 0001](adr/0001-no-build-frontend-vendored-libraries.md).

v1 is a best guess, meant to be iterated on. Where this spec says "agent's guess", the Local Player hasn't reviewed the choice yet.

## Hard rule

Read only. The Visualizer reads replays, live memory and the MechaBridge status, and **never sends anything to the game server**. Showing anything the server already sent to the client is allowed. The MechaBridge connection is used only for `StatusRequest`; the Visualizer never issues replay fetches or any other request that makes the game contact its servers.

## Command

```
mecha visualize [--port 8765] [--no-browser] [--replay-dir DIR] [--data-dir DIR]
                [--player-id ID] [--playback FILE] [--playback-speed 1.0]
                [--model artifacts/win_model.joblib] [--no-live]
```

- **`--replay-dir`**: defaults to `locate_game().replay_directory`, scanned **recursively**, so tournament replays fetched into `Replay/<version>/` count too. Files: `*.grbr` (including `*.rep.grbr`).
- **`--data-dir`**: defaults to `%LOCALAPPDATA%\mechabellum-analytics\`. It holds `visualizer.sqlite` (cache) and `visualizer.json` (config: `localPlayerId`). Tests point it at a temp dir.
- **`--player-id`**: sets and persists the Local Player id.
- **`--playback FILE`**: replays a `mecha live-record` JSONL file as the live source instead of reading memory, paced by the frames' `capturedAtUtc` divided by `--playback-speed`. `0` means as fast as possible, and the view keeps the final state. Used for development, tests and demos.
- **`--no-live`**: no live source at all (Stats view only).
- **`--model`**: without the `ml` extra or the artifact, the server still runs and the win-probability panel shows "model unavailable".
- Binds `127.0.0.1` only. It prints the URL, then opens the browser unless `--no-browser` is given. The URL comes out at once: the replay folder is indexed in the background (see **Indexing**).
- `Taskfile.yml` at the repo root wraps it: `task visualize`, `task visualize:playback FILE=…`, `task vendor`, `task test`, `task test:e2e`.

## Package

`src/mechabellum/visualizer/`, with dependency layering `cli → visualizer → collector, contracts, features, inference, models` (and `bridge`, optional). No web framework: stdlib `http.server.ThreadingHTTPServer`, Server-Sent Events, `sqlite3`.

| Module | Holds |
| --- | --- |
| `server.py` | HTTP server, static files, `/events` SSE, `/api/local-player` |
| `hub.py` | Current state plus fan-out to SSE clients; catch-up on connect |
| `summaries.py` | Replay → Match Summary, the `SUMMARY_VERSION` constant |
| `cache.py` | sqlite cache of summaries and captured ratings |
| `watcher.py` | Indexes the replay folder at start-up (on its own thread), then polls it every ~2 s; a file is parsed once its size is unchanged over two polls |
| `live.py` | Live source thread (memory or playback): retry, prediction at fight end, rating capture, Local Player detection, status |
| `roles.py` + `unit_roles.json` | The unit → role table, plus composition maths |
| `baseline.py` | Winning-board role baseline per game mode, by round and overall |
| `bridge_status.py` | Optional MechaBridge `StatusRequest` probe (game version, online). Silently absent when the `bridge` extra isn't installed or the mod isn't running |
| `static/` | `index.html`, `app.js`, `store.js`, `panels/*.js`, `style.css`, `vendor/` |

Static files ship as package data.

## Data model

### Match Summary

One per replay, built server-side, cached by (path, size, mtime, `SUMMARY_CACHE_KEY`). The cache key combines `SUMMARY_VERSION` with a hash of `unit_roles.json`, `game_names.json` and the known game-version table, so a change to any of them rebuilds the cached summaries. Only 1v1 (`VS_1_1`) replays with a known winner become summaries; others are recorded as skipped so they aren't re-parsed. JSON, camelCase:

```jsonc
{
  "battleId": "20261015--134519702",
  "date": "2026-10-15",            // from battleId's leading YYYYMMDD
  "replayPath": "…",
  "replayVersion": 2331,
  "gameVersion": "2.0.0.4.2331",   // from the replay's folder name or game_names.json's gameVersion+replayVersion when known, else null
  "gameMode": "Normal",            // or "AsyncBattle"
  "mapId": 1001,
  "rounds": 8,                     // last round played
  "winnerIndex": 1,
  "players": [
    {
      "playerId": "281474976710769865",
      "name": "Sleep Deprived",
      "won": true,
      "specialistId": 20024, "specialistName": "Speed Specialist",   // or null
      "openingId": 9901, "openingName": "3 Void Eye + 2 Tarantula", "openingLead": "Void Eye",  // or null
      "fieldedUnitIds": [28, 7, 2],                                  // on the board in any round, deduplicated
      "fightResults": ["Lose", "Win", …],                            // per fight, in order
      "finalHp": 4369,
      "composition": [ { "round": 1, "supply": 1000, "roles": {"chaff": 0.2, …}, "air": 0.0, "hitsAir": 0.3, "bodies": 30 }, … ]
    }
  ]
}
```

- **Specialist:** the id in round 1's `officerIds` whose name (`game_names.json` `officers`) is also an `advanceTeams` name that isn't a unit lineup, i.e. it doesn't start with a digit. If more than one id qualifies, the first one wins. Unknown ids (AsyncBattle) fall back to the first round-1 id with the name `Unknown specialist (<id>)`.
- **Opening:** `openingLineup.advanceTeamId`, named via `advanceTeams`. `openingLead` is the unit after the leading `"3 "` (`"3 Arclight + 2 Sledgehammer"` → `"Arclight"`). Unknown ids show as `Unknown opening (<id>)`.
- **Names:** use the `collector/unit_catalog.py` helpers. Unknown ids keep their `Unknown … (<id>)` labels.

### Roles

`unit_roles.json` holds the table from `research/unit-roles.md` (branch `research/unit-roles`). Each entry is `{id: {primary, secondary|null, air: bool, hitsAir: bool}}`. The roles, in this fixed order and with these colours: `chaff`, `chaffClear`, `damage`, `tank`, `support`. A unit missing from the table counts as `unknown`, its own sixth slice.

**Composition** for a board is supply-weighted: each unit's `sellSupply` divided by the board total. `air` and `hitsAir` are supply shares, not part of the 100%. `bodies` is the member count (from `unitPrices[...].members`, falling back to 1). An empty board has all shares 0 and supply 0.

### Baseline

Average composition of **winning** boards over every summary (all players, not only the Local Player), kept **per game mode** (`gameMode`; a summary without one counts as `Normal`). Modes never mix: AsyncBattle's unit ids aren't in the role table, so mixing them in would make a large share of every board "unknown". For each mode:
- **by round:** `byRound[r]` is the mean of the winners' round-`r` compositions, with `n`.
- **overall:** the mean over all winner round-compositions.

`byMode` always holds `Normal` (empty when no summary is Normal), plus every other mode that appears. It's recomputed whenever summaries change. Rounds with `n < 5` are flagged `thin`.

### Ratings

Replays have no rating. While a live source runs, the first non-null `rating` seen for each (`battleId`, `playerId`) is stored in sqlite as that battle's pre-match rating. A battle's **rating change** is the Local Player's rating at their next captured battle minus this one. It's unknown for the latest battle.

### Local Player

`localPlayerId` comes from config.
- **Suggestion:** the `playerId` in the most summaries, if it's in ≥60% of them. Sent as `suggestedPlayerId` in `hello`, and again in `config` whenever it changes (as rows arrive during indexing, or as replays come and go).
- **Live:** if no id is set and a live frame's `player_id` matches the suggestion, the live view uses that player but doesn't persist the id.
- **Setting the id:** the browser can set it with `POST /api/local-player {"playerId": "…"}` (to localhost only, never to the game), or by hand on the CLI.

### Indexing

`mecha visualize` binds and prints its URL before reading any replay. The watcher thread then scans the folder once:
1. It stats every replay and looks each one up in the cache. The cached summaries go out together, as one `summaries` event.
2. It parses the rest one by one (replays directly in the folder before version subfolders, which can hold thousands of fetched tournament replays; newest first within each), sending the new rows as `summary` upserts in batches (at most every ~0.5 s, and once at the end), each batch followed by one `baseline`.
3. After each step, `status.indexing` carries the progress `{done, total}`: files handled (cached, parsed or skipped) out of all files.

Polling starts once the scan is done. A cold first run over a thousand replays takes over a minute to index, but the page is usable at once and the Stats panels fill in as rows arrive.

## SSE events (`GET /events`)

Each event is `event: <name>` plus `data: <json>`. On connect, the server sends the **catch-up** in this order: `hello`, `summaries`, `baseline`, `ratings`, `status`, then `frame` and `predictions` if a match is current. After that it sends incremental events. The browser store must be rebuildable from the stream alone; on reconnect it replaces state from the next catch-up.

| Event | Data |
| --- | --- |
| `hello` | `{serverVersion, localPlayerId, suggestedPlayerId, modelAvailable, replayDir, liveSource: "memory" \| "playback" \| "none"}` |
| `summaries` | `{rows: [MatchSummary]}`: the full set. Also resent whenever a summary goes away (its replay was deleted, or now is skipped); the browser replaces its rows |
| `summary` | `{row: MatchSummary}`: upsert by `battleId` |
| `baseline` | `{byMode: {"Normal": {byRound: {"1": {roles, air, hitsAir, bodies, n, thin}, …}, overall: {…}}, "AsyncBattle": {…}}}` |
| `ratings` | `{byBattle: {battleId: {playerId: rating}}}`: full |
| `rating` | `{battleId, playerId, rating}` |
| `frame` | `{snapshot: <MatchSnapshot v2 JSON>, localIndex: 0 \| 1 \| null, composition: [<composition per player>], boardAsOfLastFight: [bool, bool]}` |
| `predictions` | `{battleId, rows: [{round, leftWinProbability, swing}]}`: full for the current match. "Left" is the Local Player, or player 0 when spectating |
| `prediction` | `{battleId, round, leftWinProbability, swing}` |
| `status` | `{state: "waiting" \| "live" \| "retrying" \| "no_game" \| "layout_mismatch" \| "playback_done" \| "off", detail, gameVersion, bridge: "online" \| "offline" \| "absent", indexing: {done, total} \| null}`. `indexing` is the start-up scan's progress (`total` is null until the files are counted; `done == total` once finished) and null without a replay folder. Sent after each indexing batch |
| `config` | `{localPlayerId, suggestedPlayerId}`: sent when the Local Player is set and whenever the suggestion changes |

**Slow clients:** each client's queue holds at most ~256 pending events. A client that falls further behind is dropped; its stream ends and the browser reconnects to a fresh catch-up.

**When events fire:**
- **Frames** are deduplicated like `record_live_snapshots` (ignoring capture time).
- **Predictions** fire once per (`battleId`, `round`), on the first `fight_over` frame where both boards have units. The snapshot passes through `FightOverHistory` first, exactly as `mecha live-predict` does it. `swing` is the change since the previous round's prediction (0 for the first).
- **`boardAsOfLastFight[i]`** is true for the opponent during `deploying` while playing.

## Stats view

Built in the browser from `summaries`, `ratings` and `localPlayerId`.
- **Which matches count:** summaries containing `localPlayerId`. Until an id is set, a setup card offers the suggested id (with the name it last played under) and a text field.
- **Filters** (global, applying to every panel): mode (All / Normal / Async), game version (multi-select, default all) and date range (whole days).
- **Win rates** always show n. Rows with n < 5 are dimmed.
- **Updates:** a new `summary` recomputes every panel, and the new row slides into Recent matches with a brief highlight (not for rows arriving during indexing).
- **Indexing:** while `status.indexing` shows the scan running, the top bar shows a small "Indexing replays 12/66" chip, and the panels fill in as rows arrive. The setup card's suggestion follows `config`.

The seven panels:
1. **Record:** games, W–L, win rate, current streak.
2. **Units:** for each unit, matches fielded, pick rate, and win rate when fielded. Sortable.
3. **Specialists:** games, W–L, win rate.
4. **Openings:** grouped by `openingLead` by default, with a toggle to exact `openingName`.
5. **History graph** (ECharts): rolling win rate over the last 20 matches, the Local Player's rating on a second axis where captured, and a vertical mark line where `gameVersion` (or `replayVersion`) changes, labelled with the version.
6. **Record per opponent:** latest name, games, W–L, last played, latest captured rating. Sorted by games.
7. **Recent matches:** newest first, the last 50. Columns:
   - date, mode, opponent
   - specialist, opening
   - result, rounds
   - a W/L dot strip
   - rating change

## Current Match view

The view opens on Stats and auto-switches to Current Match when a match goes live: only while the status is `live` and the frame's `battleId` is new to this page. A `retrying` → `live` flap within the same match doesn't switch again, and loading the page onto a match that's already over (status not `live`) stays on Stats. A tab bar switches between them by hand. Left is the Local Player in blue, right is the opponent in red. When spectating, left is player 0 and both sides show names only.

1. **Header:** names, ratings, round, phase, HP (`reactorCore`), supply and income for both sides.
2. **Win probability** (ECharts): the left player's probability per round, with a 50% midline and swing markers sized by `|swing|`. Shows "model unavailable" when `modelAvailable` is false.
3. **Board composition by role:**
   - For each player, a horizontal stacked bar of role shares, with Air and Hits-air percentages and bodies.
   - Beside it, the baseline bar for the same round, marked "thin" when `n < 5`. The baseline is the one for the live match's `gameMode` (`baseline.byMode[gameMode]`), falling back to `Normal`; its tag names the mode.
   - A toggle switches between **This round** and **Whole match**. Whole match means the mean of this match's compositions so far, against that mode's `overall`.
   - Below, a per-round line chart of the left player's role shares, with the baseline as dashed lines.
4. **Army value and HP:** per-round lines for both players, from the frames at each fight's end.
5. **Boards:** each player's units grouped by type, with count, level and a role-coloured chip. Marked "as of last fight" when `boardAsOfLastFight`.
6. **This round's offer:** `reinforcementOffer` card names, while playing only.

A status banner covers waiting, no game, retrying, layout mismatch and playback done.

## Design

Agent's guess, from `research/visual-language.md` (branch `research/visual-language`):
- dark navy panels with an orange brand accent
- the left side blue, the right side red
- 45° cut corners on panels (`clip-path`)
- the font stack `"Xolonium", "Akrobat", "Rajdhani", "Segoe UI", sans-serif` (no web fonts fetched at runtime)

Unit icons aren't in v1; use text tiles. Colours are CSS custom properties in one `:root` block. The layout works from 1280 px wide down to 1024 px.

## Frontend

Plain HTML, CSS and ES modules, with no build step (ADR 0001):
- **Vendored:** Legend-State `3.0.0-beta.48` `index.mjs` and Apache ECharts `6.1.0` `dist/echarts.esm.min.js`, in `static/vendor/`. `task vendor` re-downloads them.
- **Before importing Legend-State**, the page sets `globalThis.process = { env: { NODE_ENV: "production" } }`.
- **State:** one root observable store, written only by SSE event handlers. Panels render through `observe()` effects.
- **Test hooks:** every panel's root element has `data-panel="<name>"`, and renders `data-state="ready" | "empty"`. The e2e tests depend on these.

## Tests

- **Unit tests (`tests/test_visualizer_*.py`):**
  - summaries from fixture replays
  - specialist and opening rules
  - composition and baseline maths
  - cache invalidation
  - the hub's catch-up order
  - SSE framing
  - playback pacing at speed 0
- **End-to-end (`tests/e2e/`, pytest marker `e2e`):**
  - The test starts `mecha visualize --no-browser --port 0 --data-dir <tmp> --replay-dir tests/fixtures/replays --playback tests/fixtures/live/playing-match.sample.jsonl --playback-speed 0 --player-id <fixture id>` as a subprocess, then drives it with Playwright on the installed Chrome (`channel="chrome"`, headless).
  - It checks that every Stats panel reaches `ready` with plausible numbers, that the filters change the counts, and that the view auto-switches to Current Match.
  - It checks the header names, the predictions chart points (or "model unavailable"), the composition bars summing to 100%, and the baseline shown. It also checks no console errors and no requests leave 127.0.0.1.
  - It skips cleanly when Playwright or Chrome is missing.
- **Fixtures:**
  - A few small real 1v1 replays from the Local Player's folder.
  - A down-sampled copy of a real `live-record` recording: every phase change plus the first `fight_over` per round, a few hundred KB at most.

## Open items

- AsyncBattle unit ids (50xx) may be 5000 + the base unit id; unverified, so they stay "unknown" in `unit_roles.json`.
