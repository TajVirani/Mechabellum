// Filter bar: mode (All / Normal / Async), game version (multi-select, none selected = all) and a date range in
// whole days. The filters live in `ui` and apply to every Stats panel.
import { observe } from "../vendor/legend-state.mjs";
import { store, ui } from "../store.js";
import { allLocalMatches } from "../selectors.js";
import { versionKey } from "../stats.js";
import { h, panelShell, replace } from "../ui.js";

const MODES = [
  ["all", "All"],
  ["normal", "Normal"],
  ["async", "Async"],
];

export function mount(container) {
  const p = panelShell(container, "filters", null, { className: "filter-bar" });
  observe(() => {
    const f = ui.filters.get();
    const id = store.localPlayerId.get();
    const all = allLocalMatches();
    const summaries = store.summaries.get();
    const versions = [...new Set(all.map((m) => versionKey(m.s)))];
    const dates = all.map((m) => m.s.date).sort();
    const me = id ? lastName(summaries, id) : null;

    const toggleVersion = (v) => {
      const set = new Set(f.versions);
      set.has(v) ? set.delete(v) : set.add(v);
      ui.filters.versions.set([...set]);
    };
    replace(
      p.body,
      h(
        "div",
        { class: "filter-group" },
        h("span", { class: "filter-label" }, "Mode"),
        h(
          "div",
          { class: "seg", role: "group", "aria-label": "Mode" },
          MODES.map(([key, label]) => h("button", { type: "button", class: f.mode === key ? "on" : "", "data-mode": key, onclick: () => ui.filters.mode.set(key) }, label)),
        ),
      ),
      h(
        "div",
        { class: "filter-group versions" },
        h("span", { class: "filter-label" }, "Version"),
        h(
          "div",
          { class: "chips", role: "group", "aria-label": "Game version" },
          h("button", { type: "button", class: `chip ${f.versions.length ? "" : "on"}`, "data-version": "all", onclick: () => ui.filters.versions.set([]) }, "All"),
          versions.map((v) => h("button", { type: "button", class: `chip ${f.versions.includes(v) ? "on" : ""}`, "data-version": v, onclick: () => toggleVersion(v) }, v)),
        ),
      ),
      h(
        "div",
        { class: "filter-group" },
        h("span", { class: "filter-label" }, "Dates"),
        h("input", { type: "date", class: "date-input", "data-filter": "from", value: f.from, min: dates[0], max: dates[dates.length - 1], onchange: (e) => ui.filters.from.set(e.target.value) }),
        h("span", { class: "muted" }, "to"),
        h("input", { type: "date", class: "date-input", "data-filter": "to", value: f.to, min: dates[0], max: dates[dates.length - 1], onchange: (e) => ui.filters.to.set(e.target.value) }),
        f.from || f.to
          ? h("button", { type: "button", class: "btn ghost small", onclick: () => ui.filters.assign({ from: "", to: "" }) }, "Clear")
          : null,
      ),
      h(
        "div",
        { class: "filter-group player" },
        id
          ? [h("span", { class: "filter-label" }, "Player"), h("span", { class: "player-name", title: id }, me || id), h("button", { type: "button", class: "btn ghost small", onclick: () => ui.showSetup.set(true) }, "Change")]
          : null,
      ),
    );
    p.setState(all.length ? "ready" : "empty");
  });
}

function lastName(summaries, playerId) {
  for (let i = summaries.length - 1; i >= 0; i--) {
    const p = (summaries[i].players || []).find((x) => x.playerId === playerId);
    if (p) return p.name;
  }
  return null;
}
