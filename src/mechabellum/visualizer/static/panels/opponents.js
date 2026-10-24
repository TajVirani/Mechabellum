// Stats 6. Record per opponent: latest name, games, W–L, last played, latest captured rating. Sorted by games.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { opponents } from "../stats.js";
import { h, panelShell, replace, empty, winRate, wl, smallSample } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "opponents", "Record per opponent", { className: "scroll-panel" });
  observe(() => {
    const matches = filteredMatches();
    const ratings = store.ratings.get();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const rows = opponents(matches, ratings);
    replace(
      p.body,
      h(
        "table",
        { class: "data-table" },
        h(
          "thead",
          null,
          h("tr", null, h("th", null, "Opponent"), h("th", { class: "num" }, "Games"), h("th", { class: "num" }, "W–L"), h("th", { class: "num" }, "Win rate"), h("th", null, "Last played"), h("th", { class: "num" }, "Rating")),
        ),
        h(
          "tbody",
          null,
          rows.map((r) =>
            h(
              "tr",
              { class: smallSample(r.games) ? "dim" : "", "data-player-id": r.id },
              h("td", { class: "name-cell", title: r.name }, r.name),
              h("td", { class: "num" }, r.games),
              h("td", { class: "num" }, wl(r.wins, r.losses)),
              h("td", { class: "num" }, winRate(r.wins, r.games)),
              h("td", null, r.lastPlayed),
              h("td", { class: "num" }, r.rating ?? "—"),
            ),
          ),
        ),
      ),
    );
    p.setState("ready");
  });
}
