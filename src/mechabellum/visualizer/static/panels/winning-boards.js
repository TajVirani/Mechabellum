// Stats 8. What winning boards have: per unit or technology and round band (early 1–3, mid 4–7, late 8+), the pick
// rate, the win rate when present with its Wilson 95% interval, and the lift over the band's baseline win rate.
// Each match/player counts once per band. Entries below the minimum sample are hidden (or dimmed when shown).
// From GET /api/winning-boards with the global filters; "Mine" limits it to the Local Player's side.
import { observe } from "../vendor/legend-state.mjs";
import { store, ui } from "../store.js";
import { unitInfo } from "../roles.js";
import { h, panelShell, replace, empty, pct, num } from "../ui.js";
import { fetched, filterParams, intervalBar, liftCell, segToggle, thinToggle, ASSOCIATION_LABEL } from "../insights.js";

const BANDS = [
  ["early", "Early 1–3"],
  ["mid", "Mid 4–7"],
  ["late", "Late 8+"],
];

export function mount(container) {
  const p = panelShell(container, "winning-boards", "What winning boards have", { className: "scroll-panel insight-panel" });
  p.tools.append(
    segToggle("Round band", ui.insightsBand, BANDS),
    segToggle("Show", ui.insightsKind, [
      ["units", "Units"],
      ["technologies", "Tech"],
    ]),
    segToggle("Scope", ui.insightsScope, [
      ["all", "All replays"],
      ["me", "Mine"],
    ]),
    thinToggle(),
  );
  const result = fetched(() => `/api/winning-boards?${filterParams()}`);

  observe(() => {
    const { status, data, error } = result.get();
    const band = ui.insightsBand.get();
    const kind = ui.insightsKind.get();
    const showThin = ui.insightsShowThin.get();
    if (!store.summaries.get().length || status === "idle" || (status === "loading" && !data)) {
      replace(p.body, empty(status === "loading" ? "Loading…" : "No 1v1 replays indexed yet."));
      p.setState("empty");
      return;
    }
    if (status === "error") {
      replace(p.body, empty(`Could not load: ${error}`));
      p.setState("empty");
      return;
    }
    const table = data.bands?.[band];
    const rows = (table?.[kind] || []).filter((r) => showThin || !r.thin);
    const hidden = (table?.[kind] || []).length - rows.length;
    const summary = h(
      "p",
      { class: "insight-summary small muted" },
      `${num(table?.n ?? 0)} boards (match × player) in rounds ${table?.rounds ?? ""}, baseline win rate ${pct(table?.baselineWinRate, 1)}. `,
      `Minimum sample n=${data.minSample}${hidden ? `; ${hidden} thinner entries hidden` : ""}. ${ASSOCIATION_LABEL}`,
    );
    if (!rows.length) {
      replace(p.body, summary, empty(table?.n ? "No entries reach the minimum sample." : "No boards in this band."));
      p.setState("empty");
      return;
    }
    const head = h(
      "tr",
      null,
      h("th", null, kind === "units" ? "Unit" : "Technology"),
      h("th", { class: "num" }, "n"),
      h("th", { class: "num" }, "Pick"),
      h("th", null, "Win rate (95%)"),
      h("th", { class: "num" }, "Lift"),
    );
    const body = rows.map((r) => {
      const unitId = r.unitId;
      const info = unitId == null ? null : unitInfo(unitId);
      const name = kind === "units" ? r.name : h("span", null, r.name, info ? h("span", { class: "muted small" }, ` · ${info.name}`) : null);
      return h(
        "tr",
        { class: r.thin ? "dim thin" : "", "data-id": kind === "units" ? r.unitId : r.technologyId, "data-n": r.n },
        h("td", null, info ? h("span", { class: `role-dot role-${info.primary}` }) : null, name),
        h("td", { class: "num" }, num(r.n)),
        h("td", { class: "num" }, pct(r.pickRate)),
        h("td", null, intervalBar(r.winRate, r.interval, table.baselineWinRate)),
        h("td", { class: "num" }, liftCell(r.lift)),
      );
    });
    replace(p.body, summary, h("table", { class: "data-table insight-table" }, h("thead", null, head), h("tbody", null, body)));
    p.setState("ready");
  });
}
