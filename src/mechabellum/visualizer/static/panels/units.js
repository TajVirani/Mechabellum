// Stats 2. Units: per unit, matches fielded, pick rate and win rate when fielded. Sortable by column.
import { observe } from "../vendor/legend-state.mjs";
import { ui } from "../store.js";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { unitInfo } from "../roles.js";
import { h, panelShell, replace, empty, pct, winRate, smallSample } from "../ui.js";

const COLUMNS = [
  { key: "name", label: "Unit", dir: 1 },
  { key: "fielded", label: "Fielded", dir: -1 },
  { key: "pickRate", label: "Pick", dir: -1 },
  { key: "winRate", label: "Win rate", dir: -1 },
];

export function mount(container) {
  const p = panelShell(container, "units", "Units", { className: "scroll-panel" });
  observe(() => {
    const matches = filteredMatches();
    const sort = ui.unitsSort.get();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const byUnit = new Map();
    for (const m of matches) {
      for (const id of new Set(m.me.fieldedUnitIds || [])) {
        let row = byUnit.get(id);
        if (!row) byUnit.set(id, (row = { ...unitInfo(id), fielded: 0, wins: 0 }));
        row.fielded++;
        if (m.won) row.wins++;
      }
    }
    const rows = [...byUnit.values()].map((r) => ({ ...r, pickRate: r.fielded / matches.length, winRate: r.wins / r.fielded }));
    const k = sort.key;
    rows.sort((a, b) => {
      const c = k === "name" ? a.name.localeCompare(b.name) : a[k] - b[k];
      return c * sort.dir || b.fielded - a.fielded || a.name.localeCompare(b.name);
    });
    const head = h(
      "tr",
      null,
      COLUMNS.map((c) =>
        h(
          "th",
          {
            class: `sortable ${c.key === "name" ? "" : "num"} ${c.key === k ? (sort.dir > 0 ? "asc" : "desc") : ""}`,
            "data-sort": c.key,
            onclick: () => ui.unitsSort.set({ key: c.key, dir: c.key === k ? -sort.dir : c.dir }),
          },
          c.label,
        ),
      ),
    );
    const body = rows.map((r) =>
      h(
        "tr",
        { class: smallSample(r.fielded) ? "dim" : "", "data-unit-id": r.id },
        h("td", null, h("span", { class: `role-dot role-${r.primary}` }), r.name),
        h("td", { class: "num" }, r.fielded),
        h("td", { class: "num" }, pct(r.pickRate)),
        h("td", { class: "num" }, winRate(r.wins, r.fielded)),
      ),
    );
    replace(p.body, rows.length ? h("table", { class: "data-table" }, h("thead", null, head), h("tbody", null, body)) : empty("No units fielded."));
    p.setState(rows.length ? "ready" : "empty");
  });
}
