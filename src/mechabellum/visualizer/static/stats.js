// Stats view derivations: pure functions over Match Summaries, the ratings map and the Local Player id.

export function versionKey(summary) {
  return summary.gameVersion || (summary.replayVersion != null ? `build ${summary.replayVersion}` : "unknown");
}

// The Local Player's matches, chronological, each as {s, me, opp, won}. Filters are applied when given.
export function localMatches(summaries, localPlayerId, filters) {
  if (!localPlayerId) return [];
  const out = [];
  for (const s of summaries || []) {
    const players = s.players || [];
    const meIndex = players.findIndex((p) => p.playerId === localPlayerId);
    if (meIndex < 0) continue;
    if (filters && !passes(s, filters)) continue;
    const me = players[meIndex];
    const opp = players[1 - meIndex] || players.find((_, i) => i !== meIndex) || null;
    out.push({ s, me, opp, won: !!me.won });
  }
  return out;
}

function passes(s, f) {
  if (f.mode === "normal" && s.gameMode !== "Normal") return false;
  if (f.mode === "async" && s.gameMode !== "AsyncBattle") return false;
  if (f.versions && f.versions.length && !f.versions.includes(versionKey(s))) return false;
  // An undated row can't be placed in a date range, so it fails any active date filter.
  if ((f.from || f.to) && !s.date) return false;
  if (f.from && s.date < f.from) return false;
  if (f.to && s.date > f.to) return false;
  return true;
}

export function record(matches) {
  const wins = matches.filter((m) => m.won).length;
  return { games: matches.length, wins, losses: matches.length - wins };
}

export function streak(matches) {
  if (!matches.length) return null;
  const last = matches[matches.length - 1].won;
  let n = 0;
  for (let i = matches.length - 1; i >= 0 && matches[i].won === last; i--) n++;
  return { won: last, n };
}

// Group matches by a key; rows sorted by games desc then name.
export function groupRecord(matches, keyOf, labelOf) {
  const groups = new Map();
  for (const m of matches) {
    const key = keyOf(m);
    let g = groups.get(key);
    if (!g) {
      g = { key, label: labelOf(m), games: 0, wins: 0 };
      groups.set(key, g);
    }
    g.games++;
    if (m.won) g.wins++;
  }
  return [...groups.values()]
    .map((g) => ({ ...g, losses: g.games - g.wins }))
    .sort((a, b) => b.games - a.games || String(a.label).localeCompare(String(b.label)));
}

export function myRating(ratings, battleId, playerId) {
  const r = ratings?.[battleId]?.[playerId];
  return r == null ? null : r;
}

// battleId -> rating change: the Local Player's rating at their next captured battle minus this one's.
// Computed over all of the Local Player's matches (unfiltered), so filters don't change the numbers.
export function ratingChanges(allMatches, ratings, playerId) {
  const out = new Map();
  let next = null;
  for (let i = allMatches.length - 1; i >= 0; i--) {
    const id = allMatches[i].s.battleId;
    const r = myRating(ratings, id, playerId);
    if (r == null) continue;
    if (next != null) out.set(id, next - r);
    next = r;
  }
  return out;
}

export function rollingWinRate(matches, window = 20) {
  const out = [];
  let wins = 0;
  for (let i = 0; i < matches.length; i++) {
    if (matches[i].won) wins++;
    if (i >= window && matches[i - window].won) wins--;
    out.push(wins / Math.min(i + 1, window));
  }
  return out;
}

export function opponents(matches, ratings) {
  const groups = new Map();
  for (const m of matches) {
    if (!m.opp) continue;
    const id = m.opp.playerId || `name:${m.opp.name}`;
    let g = groups.get(id);
    if (!g) {
      g = { id, name: m.opp.name, games: 0, wins: 0, lastPlayed: m.s.date, rating: null };
      groups.set(id, g);
    }
    g.games++;
    if (m.won) g.wins++;
    // Matches are chronological, so later rows overwrite with the latest name, date and rating.
    g.name = m.opp.name;
    g.lastPlayed = m.s.date;
    const r = myRating(ratings, m.s.battleId, m.opp.playerId);
    if (r != null) g.rating = r;
  }
  return [...groups.values()]
    .map((g) => ({ ...g, losses: g.games - g.wins }))
    .sort((a, b) => b.games - a.games || String(b.lastPlayed).localeCompare(String(a.lastPlayed)));
}
