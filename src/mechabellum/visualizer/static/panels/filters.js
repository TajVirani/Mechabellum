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

// Built once; observe() updates classes, chips and values in place, so a focused date input keeps its focus and
// whatever the user is typing across summaries/hello events.
export function mount(container) {
  const p = panelShell(container, "filters", null, { className: "filter-bar" });
  const modeButtons = MODES.map(([key, label]) => h("button", { type: "button", "data-mode": key, onclick: () => ui.filters.mode.set(key) }, label));
  const allChip = h("button", { type: "button", class: "chip", "data-version": "all", onclick: () => ui.filters.versions.set([]) }, "All");
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Game version" }, allChip);
  const toggleVersion = (v) => {
    const set = new Set(ui.filters.versions.peek());
    set.has(v) ? set.delete(v) : set.add(v);
    ui.filters.versions.set([...set]);
  };
  const dateInput = (key) => h("input", { type: "date", class: "date-input", "data-filter": key, onchange: (e) => ui.filters[key].set(e.target.value) });
  const from = dateInput("from");
  const to = dateInput("to");
  const clear = h("button", { type: "button", class: "btn ghost small", onclick: () => ui.filters.assign({ from: "", to: "" }) }, "Clear");
  const playerName = h("span", { class: "player-name" });
  const player = h(
    "div",
    { class: "filter-group player" },
    h("span", { class: "filter-label" }, "Player"),
    playerName,
    h("button", { type: "button", class: "btn ghost small", onclick: () => ui.showSetup.set(true) }, "Change"),
  );
  replace(
    p.body,
    h("div", { class: "filter-group" }, h("span", { class: "filter-label" }, "Mode"), h("div", { class: "seg", role: "group", "aria-label": "Mode" }, modeButtons)),
    h("div", { class: "filter-group versions" }, h("span", { class: "filter-label" }, "Version"), chips),
    h("div", { class: "filter-group" }, h("span", { class: "filter-label" }, "Dates"), from, h("span", { class: "muted" }, "to"), to, clear),
    player,
  );

  let versionList = "";
  observe(() => {
    const f = ui.filters.get();
    const id = store.localPlayerId.get();
    const all = allLocalMatches();
    const summaries = store.summaries.get();
    const versions = [...new Set(all.map((m) => versionKey(m.s)))];
    const dates = all.map((m) => m.s.date).filter(Boolean).sort();

    for (const btn of modeButtons) btn.className = btn.dataset.mode === f.mode ? "on" : "";
    // Rebuild the chips only when the set of versions changes; otherwise just toggle their state.
    if (versions.join("\n") !== versionList) {
      versionList = versions.join("\n");
      chips.replaceChildren(allChip, ...versions.map((v) => h("button", { type: "button", class: "chip", "data-version": v, onclick: () => toggleVersion(v) }, v)));
    }
    for (const chip of chips.children) {
      const v = chip.dataset.version;
      chip.classList.toggle("on", v === "all" ? !f.versions.length : f.versions.includes(v));
    }
    for (const [input, value] of [
      [from, f.from],
      [to, f.to],
    ]) {
      if (document.activeElement !== input && input.value !== value) input.value = value;
      if (dates.length) {
        input.min = dates[0];
        input.max = dates[dates.length - 1];
      }
    }
    clear.hidden = !(f.from || f.to);
    player.hidden = !id;
    playerName.textContent = id ? lastName(summaries, id) || id : "";
    playerName.title = id || "";
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
