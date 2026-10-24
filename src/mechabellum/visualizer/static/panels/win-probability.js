// Current Match 2. Win probability: the left player's probability per round, a 50% midline and swing markers
// sized by |swing|. Shows "model unavailable" when the server has no model.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { h, panelShell, replace, empty, makeChart, baseChartOptions, axis, cssVar, FONT, sides } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "win-probability", "Win probability", { className: "chart-panel" });
  const chartEl = h("div", { class: "chart" });
  const message = h("div", { class: "chart-message" });
  p.body.append(chartEl, message);
  let chart = null;

  observe(() => {
    const hello = store.hello.get();
    const predictions = store.predictions.get();
    const frame = store.frame.get();
    const battleId = frame?.snapshot?.match?.battleId ?? null;
    if (hello && hello.modelAvailable === false) {
      chartEl.hidden = true;
      replace(message, h("p", { class: "empty-note model-unavailable" }, "Model unavailable"), h("p", { class: "muted small" }, "Install the ml extra and train artifacts/win_model.joblib to see win probability."));
      p.root.dataset.model = "unavailable";
      p.root.dataset.points = "0";
      p.setState("ready");
      return;
    }
    p.root.dataset.model = "available";
    const rows = predictions.battleId && (!battleId || predictions.battleId === battleId) ? predictions.rows : [];
    p.root.dataset.points = String(rows.length);
    if (!rows.length) {
      chartEl.hidden = true;
      replace(message, empty(frame ? "The first prediction comes at the end of round 1's fight." : "No match yet."));
      p.setState("empty");
      return;
    }
    chartEl.hidden = false;
    replace(message);
    chart ||= makeChart(chartEl);
    const [left] = sides(frame);
    const self = cssVar("--team-self-hi");
    const enemy = cssVar("--team-enemy-hi");
    const maxRound = Math.max(...rows.map((r) => r.round), 1);
    const base = baseChartOptions();
    chart.setOption(
      {
        ...base,
        grid: { left: 44, right: 16, top: 16, bottom: 28 },
        tooltip: {
          ...base.tooltip,
          formatter: (items) => {
            const it = items.find((x) => x.seriesIndex === 0) || items[0];
            const row = rows[it.dataIndex];
            return `Round ${row.round}<br>${left.player?.name ?? "Left"}: ${(row.leftWinProbability * 100).toFixed(1)}%<br>Swing: ${row.swing >= 0 ? "+" : ""}${(row.swing * 100).toFixed(1)} pts`;
          },
        },
        xAxis: axis("value", { min: 1, max: Math.max(maxRound, 2), interval: 1, name: "round", nameGap: 6, splitLine: { show: false } }),
        yAxis: axis("value", { min: 0, max: 100, interval: 25, axisLabel: { ...axis("value").axisLabel, formatter: "{value}%" } }),
        series: [
          {
            name: "Win probability",
            type: "line",
            data: rows.map((r) => [r.round, Math.round(r.leftWinProbability * 1000) / 10]),
            lineStyle: { width: 2.5, color: cssVar("--icon-line") },
            areaStyle: { color: cssVar("--icon-line"), opacity: 0.06 },
            symbol: "circle",
            clip: false,
            symbolSize: (value, params) => 6 + Math.min(22, Math.abs(rows[params.dataIndex].swing) * 80),
            itemStyle: { borderColor: cssVar("--bg-panel"), borderWidth: 1.5, color: (params) => (params.value[1] >= 50 ? self : enemy) },
            markLine: {
              symbol: "none",
              silent: true,
              lineStyle: { color: cssVar("--text-dim"), type: "dashed" },
              label: { formatter: "50%", color: cssVar("--text-secondary"), fontFamily: FONT, fontSize: 10, position: "insideEndTop" },
              data: [{ yAxis: 50 }],
            },
          },
        ],
      },
      { notMerge: true },
    );
    p.setState("ready");
  });
}
