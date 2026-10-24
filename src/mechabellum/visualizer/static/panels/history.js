// Stats 5. History graph: rolling win rate over the last 20 matches, the Local Player's captured rating on a
// second axis, and a vertical mark line where the game version changes.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { rollingWinRate, myRating, versionKey } from "../stats.js";
import { h, panelShell, replace, empty, makeChart, baseChartOptions, axis, cssVar, FONT } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "history", "History", { className: "chart-panel" });
  const chartEl = h("div", { class: "chart" });
  const note = h("p", { class: "chart-note" });
  const message = h("div", { class: "chart-message" });
  p.body.append(chartEl, note, message);
  let chart = null;

  observe(() => {
    const matches = filteredMatches();
    const ratings = store.ratings.get();
    const playerId = store.localPlayerId.get();
    const reason = statsEmptyReason(matches);
    if (reason) {
      chartEl.hidden = true;
      note.textContent = "";
      replace(message, empty(reason));
      p.setState("empty");
      return;
    }
    chartEl.hidden = false;
    replace(message);
    chart ||= makeChart(chartEl);

    const x = matches.map((m, i) => String(i + 1));
    const rolling = rollingWinRate(matches, 20).map((v) => Math.round(v * 1000) / 10);
    const rating = matches.map((m) => myRating(ratings, m.s.battleId, playerId));
    const ratingPoints = rating.filter((r) => r != null).length;

    const marks = [];
    matches.forEach((m, i) => {
      if (i > 0 && versionKey(m.s) !== versionKey(matches[i - 1].s)) marks.push({ xAxis: i, label: { formatter: versionKey(m.s) } });
    });

    const base = baseChartOptions();
    const accent = cssVar("--accent");
    const self = cssVar("--team-self-hi");
    const text = cssVar("--text-secondary");
    chart.setOption(
      {
        ...base,
        grid: { left: 44, right: 54, top: 30, bottom: 28 },
        legend: { top: 0, left: 0, textStyle: { color: text, fontFamily: FONT, fontSize: 11 }, itemHeight: 8 },
        tooltip: {
          ...base.tooltip,
          formatter: (items) => {
            const i = items[0].dataIndex;
            const m = matches[i];
            const lines = [`${m.s.date} vs ${m.opp?.name ?? "?"} — ${m.won ? "Win" : "Loss"}`];
            for (const it of items) if (it.value != null) lines.push(`${it.marker}${it.seriesName}: ${it.value}${it.seriesIndex === 0 ? "%" : ""}`);
            return lines.join("<br>");
          },
        },
        xAxis: axis("category", { data: x, splitLine: { show: false }, boundaryGap: false }),
        yAxis: [
          axis("value", { min: 0, max: 100, interval: 25, axisLabel: { ...axis("value").axisLabel, formatter: "{value}%" } }),
          axis("value", { scale: true, splitLine: { show: false } }),
        ],
        series: [
          {
            name: "Win rate (last 20)",
            type: "line",
            data: rolling,
            showSymbol: matches.length < 40,
            symbolSize: 4,
            lineStyle: { color: accent, width: 2 },
            itemStyle: { color: accent },
            areaStyle: { color: accent, opacity: 0.08 },
            markLine: {
              symbol: "none",
              silent: true,
              lineStyle: { color: cssVar("--text-dim"), type: "dashed" },
              label: { color: text, fontFamily: FONT, fontSize: 10, position: "insideEndTop" },
              data: [{ yAxis: 50, label: { show: false } }, ...marks],
            },
          },
          {
            name: "Rating",
            type: "line",
            yAxisIndex: 1,
            data: rating,
            connectNulls: true,
            symbolSize: 5,
            lineStyle: { color: self, width: 2 },
            itemStyle: { color: self },
          },
        ],
      },
      { notMerge: true },
    );
    note.textContent = ratingPoints < 2 ? "Rating shows once two matches have a captured rating (ratings are captured live)." : "";
    p.root.dataset.points = String(matches.length);
    p.setState("ready");
  });
}
