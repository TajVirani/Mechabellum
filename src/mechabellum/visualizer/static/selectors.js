// Tracked reads for panels: call these inside observe() so the effect re-runs when their inputs change.

import { store, ui } from "./store.js";
import { localMatches } from "./stats.js";

// The Local Player's matches after the global filters.
export function filteredMatches() {
  return localMatches(store.summaries.get(), store.localPlayerId.get(), ui.filters.get());
}

// The Local Player's matches with no filters (rating changes, version list).
export function allLocalMatches() {
  return localMatches(store.summaries.get(), store.localPlayerId.get(), null);
}

// Why a Stats panel has nothing to show, or null when it has matches.
export function statsEmptyReason(matches) {
  if (!store.hello.get()) return "Connecting to the Visualizer server…";
  if (!store.localPlayerId.get()) return "Choose your player id to see your stats.";
  if (!store.summaries.get().length) return "No 1v1 replays found yet.";
  if (!matches.length) return "No matches for these filters.";
  return null;
}
