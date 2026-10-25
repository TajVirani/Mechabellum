// Current Match 8. Against their board: for each unit type the opponent fields now (most supply first), my units
// that did well when an opponent fielded it, from the indexed replays (the `counters` of the `recommendations`
// event, for this round's band). Only entries at or above the minimum sample, with their n. Observed, not causal.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { unitInfo } from "../roles.js";
import { h, panelShell, replace, empty, pct, num } from "../ui.js";
import { pts, ASSOCIATION_LABEL } from "../insights.js";
import { currentRecommendations, orderedPlayers } from "./recommendations.js";

const BAND_LABELS = { early: "rounds 1–3", mid: "rounds 4–7", late: "rounds 8+", all: "all rounds" };

export function mount(container) {
  const p = panelShell(container, "live-counters", "Against their board", { className: "live-counters-panel" });

  observe(() => {
    const frame = store.frame.get();
    const rec = currentRecommendations();
    if (!frame) {
      replace(p.body, empty("No match yet."));
      p.setState("empty");
      return;
    }
    if (!rec) {
      replace(p.body, empty("Counters come with the next deployment or fight end."));
      p.setState("empty");
      return;
    }
    const players = orderedPlayers(rec, frame);
    const spectating = players.length > 1;
    let suggestions = 0;
    const blocks = players.map((player) => {
      const items = (player.counters || []).filter((c) => c.rows.length);
      suggestions += items.reduce((n, c) => n + c.rows.length, 0);
      return h(
        "div",
        { class: "counter-block", "data-player-index": player.index },
        spectating ? h("div", { class: "rec-player" }, `${player.name || `Player ${player.index + 1}`} vs. their board`) : null,
        items.length
          ? h(
              "ul",
              { class: "counter-list" },
              items.map((c) =>
                h(
                  "li",
                  { class: "counter-item", "data-enemy-unit-id": c.enemyUnitId },
                  h("div", { class: "counter-enemy" }, h("span", { class: `role-dot role-${unitInfo(c.enemyUnitId).primary}` }), `They have ${c.enemyName}`, h("span", { class: "small muted" }, ` · my win rate ${pct(c.baselineWinRate)} (n=${num(c.n)})`)),
                  h(
                    "div",
                    { class: "counter-picks" },
                    c.rows.map((r) =>
                      h(
                        "span",
                        { class: `counter-pick-chip ${r.owned ? "owned" : ""}`, "data-unit-id": r.unitId, title: `${r.name}: ${pct(r.winRate, 1)} over n=${r.n}${r.owned ? " (on your board)" : ""}` },
                        h("span", { class: `role-dot role-${unitInfo(r.unitId).primary}` }),
                        r.name,
                        h("span", { class: "lift up" }, ` ${pts(r.delta, 0)}`),
                        h("span", { class: "small muted" }, ` n=${num(r.n)}`),
                      ),
                    ),
                  ),
                ),
              ),
            )
          : empty("No unit reaches the minimum sample against their current units."),
      );
    });
    replace(
      p.body,
      blocks,
      h("p", { class: "small muted rec-note" }, `${ASSOCIATION_LABEL} From the indexed replays, ${BAND_LABELS[rec.counterBand] || rec.counterBand}, minimum n=${rec.minSample}. ★ marks units on your board.`),
    );
    p.root.dataset.suggestions = String(suggestions);
    p.setState(suggestions ? "ready" : "empty");
  });
}
