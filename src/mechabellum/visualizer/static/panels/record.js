// Stats 1. Record: games, W–L, win rate, current streak.
import { observe } from "../vendor/legend-state.mjs";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { record, streak } from "../stats.js";
import { h, panelShell, replace, empty, pct } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "record", "Record");
  observe(() => {
    const matches = filteredMatches();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const r = record(matches);
    const s = streak(matches);
    const tile = (label, value, cls = "", key = label) =>
      h("div", { class: `stat-tile ${cls}`, "data-stat": key }, h("div", { class: "stat-value" }, value), h("div", { class: "stat-label" }, label));
    replace(
      p.body,
      h(
        "div",
        { class: "stat-tiles" },
        tile("Games", r.games, "", "games"),
        tile("W–L", h("span", null, h("span", { class: "w" }, r.wins), "–", h("span", { class: "l" }, r.losses)), "", "wl"),
        tile("Win rate", pct(r.wins / r.games), r.games < 5 ? "dim" : "accent", "winrate"),
        tile("Streak", s ? `${s.won ? "W" : "L"}${s.n}` : "—", s ? (s.won ? "win" : "loss") : "", "streak"),
      ),
    );
    p.setState("ready");
  });
}
