// Small DOM, formatting and chart helpers shared by the panels.

import * as echarts from "./vendor/echarts.esm.min.js";

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children) {
    if (c == null || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

// A panel shell: root carries the data-panel/data-state test hooks. Returns {root, body, tools, setState}.
export function panelShell(container, name, title, { className = "" } = {}) {
  const tools = h("div", { class: "panel-tools" });
  const body = h("div", { class: "panel-body" });
  const root = h(
    "section",
    { class: `panel ${className}`.trim(), "data-panel": name, "data-state": "empty" },
    title ? h("header", { class: "panel-head" }, h("h2", null, title), tools) : null,
    body,
  );
  container.append(root);
  return {
    root,
    body,
    tools,
    setState(state) {
      root.dataset.state = state;
    },
  };
}

export function replace(el, ...children) {
  el.replaceChildren();
  append(el, children);
}

export function empty(message) {
  return h("p", { class: "empty-note" }, message);
}

export const pct = (x, digits = 0) => (x == null || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(digits)}%`);
export const num = (x) => (x == null ? "—" : Number(x).toLocaleString("en-US"));
export const signed = (x) => (x == null ? "—" : x > 0 ? `+${x}` : x < 0 ? `−${Math.abs(x)}` : "±0");

// "62% n=13", dimmed below n=5 by the caller via `smallSample`.
export function winRate(wins, games) {
  return h("span", { class: "winrate" }, h("span", { class: "wr-value" }, games ? pct(wins / games) : "—"), h("span", { class: "wr-n" }, `n=${games}`));
}
export const smallSample = (n) => n < 5;

export function wl(wins, losses) {
  return h("span", { class: "wl" }, h("span", { class: "w" }, wins), "–", h("span", { class: "l" }, losses));
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export const FONT = `"Xolonium", "Akrobat", "Rajdhani", "Segoe UI", sans-serif`;

export function roleColor(role) {
  return cssVar(`--role-${role}`);
}

// An ECharts instance that follows its element's size. Charts render on canvas with no animation delay.
export function makeChart(el) {
  const chart = echarts.init(el, null, { renderer: "canvas" });
  const ro = new ResizeObserver(() => chart.resize());
  ro.observe(el);
  return chart;
}

export function baseChartOptions() {
  const text = cssVar("--text-secondary");
  const grid = cssVar("--chart-grid");
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: FONT, color: text },
    animationDuration: 200,
    tooltip: {
      trigger: "axis",
      backgroundColor: cssVar("--bg-nav"),
      borderColor: cssVar("--edge"),
      textStyle: { color: cssVar("--text-primary"), fontFamily: FONT, fontSize: 12 },
    },
  };
}

export function axis(type, extra = {}) {
  const text = cssVar("--text-secondary");
  const grid = cssVar("--chart-grid");
  return {
    type,
    axisLine: { lineStyle: { color: grid } },
    axisTick: { lineStyle: { color: grid } },
    axisLabel: { color: text, fontFamily: FONT, fontSize: 11 },
    splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
    nameTextStyle: { color: text, fontFamily: FONT, fontSize: 11 },
    ...extra,
  };
}

export const PHASE_LABELS = {
  opening: "Opening",
  deploying: "Deploying",
  deploy_over: "Deploy over",
  battle_start: "Battle start",
  fighting: "Fighting",
  fight_over: "Fight over",
  unknown: "Unknown",
};

// Left/right sides of the current frame: left is the Local Player, or player 0 when spectating.
export function sides(frame) {
  const players = frame?.snapshot?.players || [];
  const local = frame?.localIndex;
  const leftIndex = local === 1 ? 1 : 0;
  const rightIndex = 1 - leftIndex;
  const spectating = local == null;
  return [
    { side: "left", index: leftIndex, player: players[leftIndex], label: spectating ? null : "You", spectating },
    { side: "right", index: rightIndex, player: players[rightIndex], label: spectating ? null : "Opponent", spectating },
  ];
}

// A games / W–L / win-rate table, used by the Specialists and Openings panels. Rows: {label, games, wins, losses}.
export function recordTable(label, rows) {
  return h(
    "table",
    { class: "data-table" },
    h("thead", null, h("tr", null, h("th", null, label), h("th", { class: "num" }, "Games"), h("th", { class: "num" }, "W–L"), h("th", { class: "num" }, "Win rate"))),
    h(
      "tbody",
      null,
      rows.map((r) =>
        h(
          "tr",
          { class: smallSample(r.games) ? "dim" : "" },
          h("td", null, r.label),
          h("td", { class: "num" }, r.games),
          h("td", { class: "num" }, wl(r.wins, r.losses)),
          h("td", { class: "num" }, winRate(r.wins, r.games)),
        ),
      ),
    ),
  );
}
