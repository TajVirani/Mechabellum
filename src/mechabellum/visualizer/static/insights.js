// Shared by the insight panels: the server computes "what winning boards have" and counters from the Match
// Summaries (GET /api/winning-boards, /api/counters; cached until the summaries change). The SSE stream doesn't
// carry these tables, so each panel keeps its latest response in a panel-local observable, never in the store.
import { observable, observe } from "./vendor/legend-state.mjs";
import { store, ui, isIndexing } from "./store.js";
import { h, pct } from "./ui.js";

// The Stats filters as query parameters. Modes never mix (AsyncBattle's unit ids differ), so "All" means Normal.
export function filterParams(extra = {}) {
  const f = ui.filters.get();
  const params = new URLSearchParams();
  params.set("mode", f.mode === "async" ? "AsyncBattle" : "Normal");
  if (f.versions && f.versions.length) params.set("versions", f.versions.join(","));
  if (f.from) params.set("from", f.from);
  if (f.to) params.set("to", f.to);
  if (ui.insightsScope.get() === "me" && store.localPlayerId.get()) params.set("player", store.localPlayerId.get());
  for (const [k, v] of Object.entries(extra)) if (v != null && v !== "") params.set(k, String(v));
  return params;
}

// An observable {status: "idle" | "loading" | "ready" | "error", data, error} that refetches `url()` whenever
// its tracked inputs or the summaries change. Debounced, longer while the replay folder is still being indexed.
export function fetched(url) {
  const state = observable({ status: "idle", data: null, error: null });
  let timer = null;
  let seq = 0;
  observe(() => {
    const target = url();
    store.summaries.get(); // refetch when the summaries change
    if (!store.hello.get() || !target) return;
    const delay = isIndexing(store.status.peek()) ? 2000 : 250;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++seq;
      if (!state.data.peek()) state.status.set("loading");
      try {
        const response = await fetch(target);
        const body = await response.json();
        if (!response.ok) throw new Error(body?.error || `HTTP ${response.status}`);
        if (mine === seq) state.set({ status: "ready", data: body, error: null });
      } catch (err) {
        if (mine === seq) state.set({ status: "error", data: null, error: String(err.message || err) });
      }
    }, delay);
  });
  return state;
}

export const pts = (x, digits = 1) => (x == null ? "—" : `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(x * 100).toFixed(digits)} pts`);

// Win rate with its Wilson 95% interval as a small range bar; `baseline` draws a tick for comparison.
export function intervalBar(rate, interval, baseline) {
  const [lo, hi] = interval || [rate ?? 0, rate ?? 0];
  const bar = h(
    "span",
    { class: "ci-bar", title: interval ? `95% interval ${pct(lo, 1)}–${pct(hi, 1)}` : "" },
    h("span", { class: "ci-range", style: { left: `${lo * 100}%`, width: `${Math.max(0, hi - lo) * 100}%` } }),
    baseline == null ? null : h("span", { class: "ci-base", style: { left: `${baseline * 100}%` } }),
    rate == null ? null : h("span", { class: "ci-point", style: { left: `${rate * 100}%` } }),
  );
  return h("span", { class: "ci" }, h("span", { class: "wr-value" }, pct(rate, 1)), bar);
}

export function liftCell(lift) {
  return h("span", { class: `lift ${lift > 0 ? "up" : lift < 0 ? "down" : ""}` }, pts(lift));
}

// A segmented toggle bound to a `ui` field: [[key, label], ...].
export function segToggle(label, field, options) {
  const el = h("div", { class: "seg", role: "group", "aria-label": label });
  observe(() => {
    const value = field.get();
    el.replaceChildren(...options.map(([key, text]) => h("button", { type: "button", class: key === value ? "on" : "", "data-value": key, onclick: () => field.set(key) }, text)));
  });
  return el;
}

export function thinToggle() {
  const input = h("input", { type: "checkbox", onchange: (e) => ui.insightsShowThin.set(e.target.checked) });
  observe(() => {
    input.checked = !!ui.insightsShowThin.get();
  });
  return h("label", { class: "thin-toggle small muted" }, input, " Show thin");
}

export const ASSOCIATION_LABEL = "Observed association, not causal.";
