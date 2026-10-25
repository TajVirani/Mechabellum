// Stats 9. Counters: when the opponent fields unit Y, my win rate with each of my units X, against my baseline
// when they field Y. An observed association, not causal. From GET /api/counters (every enemy unit, all rows) with
// the global filters, a round band and the shared scope / show-thin toggles.
import { observe } from "../vendor/legend-state.mjs";
import { store, ui } from "../store.js";
import { unitInfo } from "../roles.js";
import { h, panelShell, replace, empty, pct, num } from "../ui.js";
import { fetched, filterParams, intervalBar, liftCell, segToggle, ASSOCIATION_LABEL } from "../insights.js";

const BANDS = [
  ["all", "All rounds"],
  ["early", "1–3"],
  ["mid", "4–7"],
  ["late", "8+"],
];

export function mount(container) {
  const p = panelShell(container, "counters", "Counters", { className: "scroll-panel insight-panel" });
  p.tools.append(segToggle("Round band", ui.countersBand, BANDS));
  const result = fetched(() => `/api/counters?${filterParams({ band: ui.countersBand.get(), top: 0 })}`);

  observe(() => {
    const { status, data, error } = result.get();
    const showThin = ui.insightsShowThin.get();
    const wanted = ui.countersEnemy.get();
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
    const enemies = (data.enemies || []).filter((e) => e.n > 0);
    if (!enemies.length) {
      replace(p.body, empty("No boards for these filters."));
      p.setState("empty");
      return;
    }
    const enemy = enemies.find((e) => e.enemyUnitId === wanted) || enemies[0];
    const select = h(
      "select",
      { class: "text-input enemy-select", "aria-label": "Enemy unit", onchange: (e) => ui.countersEnemy.set(Number(e.target.value)) },
      [...enemies]
        .sort((a, b) => a.enemyName.localeCompare(b.enemyName))
        .map((e) => h("option", { value: e.enemyUnitId, selected: e.enemyUnitId === enemy.enemyUnitId }, `${e.enemyName} (n=${num(e.n)})`)),
    );
    const rows = enemy.rows.filter((r) => showThin || !r.thin);
    const hidden = enemy.rows.length - rows.length;
    const intro = h(
      "div",
      { class: "counter-pick" },
      h("span", { class: "filter-label" }, "They field"),
      select,
      h("span", { class: "small muted" }, `my win rate ${pct(enemy.baselineWinRate, 1)} over n=${num(enemy.n)}`),
    );
    const note = h("p", { class: "insight-summary small muted" }, `${ASSOCIATION_LABEL} Minimum sample n=${data.minSample}${hidden ? `; ${hidden} thinner entries hidden` : ""}.`);
    if (!rows.length) {
      replace(p.body, intro, note, empty("No unit reaches the minimum sample against this one."));
      p.setState("empty");
      return;
    }
    const head = h("tr", null, h("th", null, "My unit"), h("th", { class: "num" }, "n"), h("th", null, "Win rate (95%)"), h("th", { class: "num" }, "vs baseline"));
    const body = rows.map((r) =>
      h(
        "tr",
        { class: r.thin ? "dim thin" : "", "data-unit-id": r.unitId, "data-n": r.n },
        h("td", null, h("span", { class: `role-dot role-${unitInfo(r.unitId).primary}` }), r.name),
        h("td", { class: "num" }, num(r.n)),
        h("td", null, intervalBar(r.winRate, r.interval, enemy.baselineWinRate)),
        h("td", { class: "num" }, liftCell(r.delta)),
      ),
    );
    replace(p.body, intro, note, h("table", { class: "data-table insight-table" }, h("thead", null, head), h("tbody", null, body)));
    p.setState("ready");
  });
}
