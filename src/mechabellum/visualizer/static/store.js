// The one root store. Only SSE event handlers write it (`applyEvent` plus the connection state set by app.js);
// panels only read it inside observe() effects. A `hello` event starts a catch-up and replaces all state, so the
// store can always be rebuilt from the stream alone.
//
// View-only state (active tab, filters, toggles, sort order) lives in `ui`, which the stream never touches.

import { observable, batch } from "./vendor/legend-state.mjs";
import { compositionOf } from "./roles.js";

function initialState(connection = "connecting") {
  return {
    connection, // "connecting" | "open" | "lost"
    hello: null, // {serverVersion, localPlayerId, suggestedPlayerId, modelAvailable, replayDir, liveSource}
    //   (`config` keeps suggestedPlayerId current, so the store matches a fresh catch-up)
    localPlayerId: null,
    summaries: [], // MatchSummary rows, oldest first
    lastSummaryId: null, // battleId of the latest incremental `summary` upsert (for the Recent highlight)
    baseline: null, // {byMode: {"Normal": {byRound: {"1": {...}}, overall: {...}}, "AsyncBattle": {...}}}
    ratings: {}, // {battleId: {playerId: rating}}
    status: null, // {state, detail, gameVersion, bridge, indexing: {done, total} | null}
    frame: null, // {snapshot, localIndex, composition, boardAsOfLastFight}
    match: null, // per-round history of the current match, built from frames: {battleId, rounds: {r: {...}}}
    predictions: { battleId: null, rows: [] },
    recommendations: null, // latest `recommendations` payload: {battleId, round, phase, modelAvailable, players: [...]}
  };
}

export const store = observable(initialState());

export const ui = observable({
  view: "stats", // "stats" | "current"
  filters: { mode: "all", versions: [], from: "", to: "" },
  openingsGroup: "lead", // "lead" | "name"
  compositionScope: "round", // "round" | "match"
  unitsSort: { key: "fielded", dir: -1 },
  showSetup: false,
  // What winning boards have / Counters (Stats): fetched from /api/winning-boards and /api/counters.
  insightsBand: "mid", // "early" | "mid" | "late"
  insightsKind: "units", // "units" | "technologies"
  insightsScope: "all", // "all" (every indexed replay) | "me" (the Local Player's side only)
  insightsShowThin: false,
  countersBand: "all", // "all" | "early" | "mid" | "late"
  countersEnemy: null, // unit id, or null for the most observed enemy unit
});

// Chronological order: battleId is `YYYYMMDD--<ms into the day>`.
export function battleKey(battleId) {
  const [day, rest] = String(battleId).split("--");
  return [day || "", Number(rest) || 0];
}

export function compareBattleIds(a, b) {
  const [da, ta] = battleKey(a);
  const [db, tb] = battleKey(b);
  return da < db ? -1 : da > db ? 1 : ta - tb;
}

// True while the server's start-up scan of the replay folder is still running.
export function isIndexing(status) {
  const ix = status?.indexing;
  return !!ix && (ix.total == null || ix.done < ix.total);
}

// The winning-board baseline for a game mode, falling back to Normal's: {mode, byRound, overall} or null.
export function baselineFor(baseline, gameMode) {
  const byMode = baseline?.byMode || {};
  const mode = gameMode && byMode[gameMode] ? gameMode : "Normal";
  return byMode[mode] ? { mode, ...byMode[mode] } : null;
}

function sortRows(rows) {
  return [...rows].sort((a, b) => compareBattleIds(a.battleId, b.battleId));
}

export function setConnection(state) {
  store.connection.set(state);
}

// The frame's composition entry for player i: an object, or a per-round list (take this round's or the last).
function compositionFor(frame, i) {
  const snapshot = frame.snapshot;
  const round = snapshot?.match?.round ?? 0;
  const entry = frame.composition?.[i];
  if (Array.isArray(entry)) {
    return entry.find((c) => c.round === round) || entry[entry.length - 1] || compositionOf(snapshot.players[i]?.units, round);
  }
  return entry || compositionOf(snapshot?.players?.[i]?.units, round);
}

function armyValue(player) {
  return (player?.units || []).reduce((sum, u) => sum + Math.max(0, u.sellSupply || 0), 0);
}

function recordFrame(frame) {
  const snapshot = frame.snapshot;
  const previous = store.match.peek();
  // A frame without a battle id (a read between matches' ids) belongs to the current match; don't reset it.
  const battleId = snapshot?.match?.battleId ?? previous?.battleId ?? null;
  const round = snapshot?.match?.round ?? 0;
  const phase = snapshot?.match?.phase;
  const rounds = previous && previous.battleId === battleId ? { ...previous.rounds } : {};
  const players = snapshot?.players || [];
  const entry = { ...(rounds[round] || {}) };
  if (!entry.fightEnd) {
    // Composition, army value and HP come from the round's first fight_over frame (as the server's catch-up
    // history does); until the fight ends, keep the latest frame as a provisional point. Later frames of the same
    // round (repeats, or a cleared board at the match's end) don't move it.
    entry.composition = players.map((_, i) => compositionFor(frame, i));
    entry.army = players.map(armyValue);
    entry.hp = players.map((p) => p.reactorCore ?? null);
    entry.fightEnd = phase === "fight_over";
  }
  rounds[round] = entry;
  // Live frames don't carry histories, but replay-shaped ones do: fill HP for rounds this browser never saw.
  players.forEach((p, i) => {
    (p.reactorCoreHistory || []).forEach((hp, k) => {
      const r = k + 1;
      if (r === round || (rounds[r] && rounds[r].fightEnd)) return;
      const e = { ...(rounds[r] || {}) };
      e.hp = e.hp ? [...e.hp] : players.map(() => null);
      e.hp[i] = hp;
      rounds[r] = e;
    });
  });
  store.match.set({ battleId, rounds });
}

function sameFrame(a, b) {
  if (!a || !b) return false;
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

export function applyEvent(type, data) {
  batch(() => {
    switch (type) {
      case "hello":
        store.set({ ...initialState("open"), hello: data, localPlayerId: data.localPlayerId ?? null });
        break;
      case "summaries":
        store.summaries.set(sortRows(data.rows || []));
        break;
      case "summary": {
        const row = data.row;
        const rows = store.summaries.peek().filter((r) => r.battleId !== row.battleId);
        rows.push(row);
        store.summaries.set(sortRows(rows));
        // Rows arriving during the start-up scan aren't news; only a replay saved later gets the highlight.
        if (!isIndexing(store.status.peek())) store.lastSummaryId.set(row.battleId);
        break;
      }
      case "baseline":
        store.baseline.set(data);
        break;
      case "ratings":
        store.ratings.set(data.byBattle || {});
        break;
      case "rating": {
        // Whole-object writes: battle and player ids look numeric, and path writes could create arrays.
        const all = store.ratings.peek();
        store.ratings.set({ ...all, [data.battleId]: { ...(all[data.battleId] || {}), [data.playerId]: data.rating } });
        break;
      }
      case "status":
        store.status.set(data);
        break;
      case "frame":
        // The catch-up resends the latest round's fight_over frame after the round history; skip exact repeats.
        if (sameFrame(store.frame.peek(), data)) break;
        store.frame.set(data);
        recordFrame(data);
        break;
      case "predictions":
        store.predictions.set({ battleId: data.battleId, rows: [...(data.rows || [])].sort((a, b) => a.round - b.round) });
        break;
      case "prediction": {
        const current = store.predictions.peek();
        const rows = current.battleId === data.battleId ? current.rows.filter((r) => r.round !== data.round) : [];
        rows.push({ round: data.round, leftWinProbability: data.leftWinProbability, swing: data.swing });
        rows.sort((a, b) => a.round - b.round);
        store.predictions.set({ battleId: data.battleId, rows });
        break;
      }
      case "recommendations":
        store.recommendations.set(data);
        break;
      case "config":
        store.localPlayerId.set(data.localPlayerId ?? null);
        if (store.hello.peek()) {
          store.hello.localPlayerId.set(data.localPlayerId ?? null);
          if ("suggestedPlayerId" in data) store.hello.suggestedPlayerId.set(data.suggestedPlayerId ?? null);
        }
        break;
      default:
        break;
    }
  });
}

export const EVENT_TYPES = [
  "hello",
  "summaries",
  "summary",
  "baseline",
  "ratings",
  "rating",
  "status",
  "frame",
  "predictions",
  "prediction",
  "recommendations",
  "config",
];
