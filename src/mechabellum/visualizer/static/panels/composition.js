// Current Match 3. Board composition by role: a stacked supply-share bar per player with Air / Hits-air / bodies,
// the winning-board baseline beside them ("thin" when n < 5), a This round / Whole match toggle, and a per-round
// line chart of the left player's role shares against the baseline (dashed).
import { observe } from "../vendor/legend-state.mjs";
import { store, ui } from "../store.js";
import { ROLES, ROLE_LABELS } from "../roles.js";
import { h, panelShell, replace, empty, pct, makeChart, baseChartOptions, axis, roleColor, cssVar, FONT, sides } from "../ui.js";

function meanComposition(list) {
  const items = list.filter((c) => c && (c.supply ?? 1) > 0);
  if (!items.length) return null;
  const roles = Object.fromEntries(ROLES.map((r) => [r, 0]));
  let air = 0;
  let hitsAir = 0;
  let bodies = 0;
  let supply = 0;
  for (const c of items) {
    for (const r of ROLES) roles[r] += c.roles?.[r] || 0;
    air += c.air || 0;
    hitsAir += c.hitsAir || 0;
    bodies += c.bodies || 0;
    supply += c.supply || 0;
  }
  const n = items.length;
  for (const r of ROLES) roles[r] /= n;
  return { roles, air: air / n, hitsAir: hitsAir / n, bodies: bodies / n, supply: supply / n };
}

function bar(kind, label, comp, { side, tag } = {}) {
  const shares = ROLES.map((r) => [r, comp?.roles?.[r] || 0]);
  const total = shares.reduce((s, [, v]) => s + v, 0);
  return h(
    "div",
    { class: `comp-row ${kind}`, "data-bar": side || kind, "data-total": total.toFixed(4) },
    h("div", { class: "comp-label" }, h("span", { class: "comp-name", title: label }, label), tag ? h("span", { class: "tag thin" }, tag) : null),
    h(
      "div",
      { class: "comp-bar" },
      total > 0
        ? shares
            .filter(([, v]) => v > 0)
            .map(([r, v]) =>
              h(
                "div",
                { class: `seg-fill role-${r}`, style: { width: `${(v / total) * 100}%` }, "data-role": r, "data-share": v.toFixed(4), title: `${ROLE_LABELS[r]} ${pct(v, 1)}` },
                v >= 0.08 ? h("span", null, pct(v)) : null,
              ),
            )
        : h("div", { class: "seg-empty" }, "Empty board"),
    ),
    h(
      "div",
      { class: "comp-flags" },
      h("span", { title: "Supply share of air units" }, h("b", null, "Air "), pct(comp?.air)),
      h("span", { title: "Supply share of units that hit air" }, h("b", null, "AA "), pct(comp?.hitsAir)),
      h("span", { title: "Member count" }, h("b", null, "Bodies "), comp?.bodies != null ? Math.round(comp.bodies) : "—"),
    ),
  );
}

export function mount(container) {
  const p = panelShell(container, "composition", "Board composition by role", { className: "composition-panel" });
  const toggle = h("div", { class: "seg", role: "group", "aria-label": "Composition scope" });
  p.tools.append(toggle);
  const bars = h("div", { class: "comp-bars" });
  const legend = h("div", { class: "role-legend" }, ROLES.map((r) => h("span", null, h("i", { class: `role-dot role-${r}` }), ROLE_LABELS[r])));
  const chartEl = h("div", { class: "chart small-chart" });
  p.body.append(bars, legend, chartEl);
  let chart = null;

  observe(() => {
    const scope = ui.compositionScope.get();
    replace(
      toggle,
      [
        ["round", "This round"],
        ["match", "Whole match"],
      ].map(([key, label]) => h("button", { type: "button", class: key === scope ? "on" : "", "data-scope": key, onclick: () => ui.compositionScope.set(key) }, label)),
    );
    const frame = store.frame.get();
    const match = store.match.get();
    const baseline = store.baseline.get();
    if (!frame?.snapshot) {
      replace(bars, empty("No match yet."));
      legend.hidden = true;
      chartEl.hidden = true;
      p.setState("empty");
      return;
    }
    legend.hidden = false;
    const round = frame.snapshot.match?.round ?? 0;
    const [left, right] = sides(frame);
    const rounds = Object.keys(match?.rounds || {})
      .map(Number)
      .filter((r) => r >= 1)
      .sort((a, b) => a - b);
    const compAt = (r, i) => match?.rounds?.[r]?.composition?.[i] || null;

    let leftComp;
    let rightComp;
    let base;
    let baseLabel;
    if (scope === "match") {
      leftComp = meanComposition(rounds.map((r) => compAt(r, left.index)));
      rightComp = meanComposition(rounds.map((r) => compAt(r, right.index)));
      base = baseline?.overall || null;
      baseLabel = "Winning boards, all rounds";
    } else {
      leftComp = compAt(round, left.index) || frame.composition?.[left.index];
      rightComp = compAt(round, right.index) || frame.composition?.[right.index];
      base = baseline?.byRound?.[String(round)] || null;
      baseLabel = `Winning boards, round ${round}`;
    }
    const thin = base && (base.thin || (base.n != null && base.n < 5));
    const nameOf = (s) => s.player?.name || (s.side === "left" ? "Left" : "Right");
    replace(
      bars,
      bar("player left", nameOf(left), leftComp, { side: "left" }),
      bar("player right", nameOf(right), rightComp, { side: "right" }),
      base
        ? bar("baseline", baseLabel, base, { side: "baseline", tag: thin ? `thin · n=${base.n ?? 0}` : base.n != null ? `n=${base.n}` : null })
        : h("div", { class: "comp-row baseline missing", "data-bar": "baseline-missing" }, h("div", { class: "comp-label" }, baseLabel), h("div", { class: "muted small" }, "No winning boards for this round yet.")),
    );

    // Per-round chart of the left player's role shares, with the baseline as dashed lines.
    const chartRounds = rounds.length ? rounds : [round];
    if (chartRounds.length < 1 || chartRounds[0] < 1) {
      chartEl.hidden = true;
    } else {
      chartEl.hidden = false;
      chart ||= makeChart(chartEl);
      const series = [];
      for (const r of ROLES) {
        const color = roleColor(r);
        const own = chartRounds.map((k) => {
          const c = compAt(k, left.index);
          return c ? Math.round((c.roles?.[r] || 0) * 1000) / 10 : null;
        });
        const baseVals = chartRounds.map((k) => {
          const b = baseline?.byRound?.[String(k)];
          return b ? Math.round((b.roles?.[r] || 0) * 1000) / 10 : null;
        });
        if (own.every((v) => !v) && baseVals.every((v) => !v)) continue;
        series.push({ name: ROLE_LABELS[r], type: "line", data: own, symbolSize: 5, lineStyle: { color, width: 2 }, itemStyle: { color }, connectNulls: true });
        series.push({ name: `${ROLE_LABELS[r]} (winning boards)`, type: "line", data: baseVals, symbol: "none", lineStyle: { color, width: 1.5, type: "dashed", opacity: 0.75 }, itemStyle: { color }, connectNulls: true });
      }
      const opts = baseChartOptions();
      chart.setOption(
        {
          ...opts,
          grid: { left: 40, right: 12, top: 22, bottom: 24 },
          title: { text: `${nameOf(left)} by round · dashed = winning boards`, left: 0, top: 0, textStyle: { color: cssVar("--text-secondary"), fontFamily: FONT, fontSize: 11, fontWeight: "normal" } },
          xAxis: axis("category", { data: chartRounds.map(String), boundaryGap: false, splitLine: { show: false } }),
          yAxis: axis("value", { min: 0, max: 100, interval: 25, axisLabel: { ...axis("value").axisLabel, formatter: "{value}%" } }),
          series,
        },
        { notMerge: true },
      );
    }
    p.setState("ready");
  });
}
