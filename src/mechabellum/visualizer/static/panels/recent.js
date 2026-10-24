// Stats 7. Recent matches: newest first, the last 50. A new `summary` row slides in with a brief highlight.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { filteredMatches, allLocalMatches, statsEmptyReason } from "../selectors.js";
import { ratingChanges } from "../stats.js";
import { h, panelShell, replace, empty, signed } from "../ui.js";

const MODE = { Normal: "Normal", AsyncBattle: "Async" };

export function mount(container) {
  const p = panelShell(container, "recent", "Recent matches", { className: "scroll-panel" });
  const highlighted = new Set();
  observe(() => {
    const matches = filteredMatches();
    const all = allLocalMatches();
    const ratings = store.ratings.get();
    const playerId = store.localPlayerId.get();
    const newest = store.lastSummaryId.get();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const changes = ratingChanges(all, ratings, playerId);
    const rows = matches.slice(-50).reverse();
    replace(
      p.body,
      h(
        "table",
        { class: "data-table recent-table" },
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            ["Date", "Mode", "Opponent", "Specialist", "Opening", "Result", "Rounds", "Fights", "Rating ±"].map((c, i) => h("th", { class: i === 6 || i === 8 ? "num" : "" }, c)),
          ),
        ),
        h(
          "tbody",
          null,
          rows.map((m) => {
            const id = m.s.battleId;
            const isNew = id === newest && !highlighted.has(id);
            if (isNew) highlighted.add(id);
            const change = changes.has(id) ? changes.get(id) : null;
            return h(
              "tr",
              { class: isNew ? "is-new" : "", "data-battle-id": id },
              h("td", null, m.s.date),
              h("td", null, MODE[m.s.gameMode] || m.s.gameMode || "—"),
              h("td", { class: "name-cell", title: m.opp?.name }, m.opp?.name ?? "—"),
              h("td", { class: "name-cell", title: m.me.specialistName }, m.me.specialistName ?? "—"),
              h("td", { class: "name-cell", title: m.me.openingName }, m.me.openingName ?? "—"),
              h("td", null, h("span", { class: `result ${m.won ? "win" : "loss"}` }, m.won ? "Win" : "Loss")),
              h("td", { class: "num" }, m.s.rounds ?? "—"),
              h("td", null, dots(m.me.fightResults)),
              h("td", { class: `num ${change > 0 ? "up" : change < 0 ? "down" : ""}` }, change == null ? "—" : signed(change)),
            );
          }),
        ),
      ),
    );
    p.setState("ready");
  });
}

function dots(results) {
  return h(
    "span",
    { class: "dot-strip", title: (results || []).join(" ") },
    (results || []).map((r) => h("i", { class: r === "Win" ? "w" : r === "Lose" ? "l" : "d" })),
  );
}
