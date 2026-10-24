// Current Match 4. Army value and HP: per-round lines for both players, from the frames at each fight's end.
// Army value is the board's total sellSupply; HP is reactorCore.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { h, panelShell, replace, empty, makeChart, baseChartOptions, axis, cssVar, FONT, sides } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "army-hp", "Army value and HP", { className: "chart-panel" });
  const chartEl = h("div", { class: "chart" });
  const message = h("div", { class: "chart-message" });
  const note = h("p", { class: "chart-note" }, "Solid: army value (total sell supply, left axis). Dashed: HP (right axis).");
  p.body.append(chartEl, note, message);
  let chart = null;

  observe(() => {
    const frame = store.frame.get();
    const match = store.match.get();
    const rounds = Object.keys(match?.rounds || {})
      .map(Number)
      .filter((r) => r >= 1)
      .sort((a, b) => a - b);
    if (!frame?.snapshot || !rounds.length) {
      chartEl.hidden = true;
      note.hidden = true;
      replace(message, empty(frame ? "Fills in at the end of each fight." : "No match yet."));
      p.setState("empty");
      return;
    }
    chartEl.hidden = false;
    note.hidden = false;
    replace(message);
    chart ||= makeChart(chartEl);
    const [left, right] = sides(frame);
    const self = cssVar("--team-self-hi");
    const enemy = cssVar("--team-enemy-hi");
    const at = (r, key, i) => {
      const value = match.rounds[r]?.[key]?.[i] ?? null;
      // The killing blow can take the core below 0; chart it as 0 rather than off the axis.
      return value == null ? null : Math.max(0, value);
    };
    const line = (name, data, color, yAxisIndex, dashed) => ({
      name,
      type: "line",
      yAxisIndex,
      data,
      connectNulls: true,
      symbolSize: 5,
      lineStyle: { color, width: 2, type: dashed ? "dashed" : "solid" },
      itemStyle: { color },
    });
    const ln = left.player?.name || "Left";
    const rn = right.player?.name || "Right";
    const base = baseChartOptions();
    chart.setOption(
      {
        ...base,
        grid: { left: 48, right: 52, top: 54, bottom: 26 },
        legend: { top: 0, left: 0, textStyle: { color: cssVar("--text-secondary"), fontFamily: FONT, fontSize: 11 }, itemHeight: 8, itemWidth: 18, formatter: (name) => (name.length > 22 ? `${name.slice(0, 12)}… ${name.split(" ").pop()}` : name) },
        xAxis: axis("category", { data: rounds.map(String), boundaryGap: false, name: "round", nameGap: 6, splitLine: { show: false } }),
        yAxis: [axis("value", { min: 0 }), axis("value", { min: 0, splitLine: { show: false } })],
        series: [
          line(`${ln} army`, rounds.map((r) => at(r, "army", left.index)), self, 0, false),
          line(`${rn} army`, rounds.map((r) => at(r, "army", right.index)), enemy, 0, false),
          line(`${ln} HP`, rounds.map((r) => at(r, "hp", left.index)), self, 1, true),
          line(`${rn} HP`, rounds.map((r) => at(r, "hp", right.index)), enemy, 1, true),
        ],
      },
      { notMerge: true },
    );
    p.root.dataset.points = String(rounds.length);
    p.setState("ready");
  });
}
