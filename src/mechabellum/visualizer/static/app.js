// The Visualizer app: builds the layout, mounts the panels, connects to /events (auto-reconnecting) and switches
// tabs. It opens on Stats and auto-switches to Current Match when a match goes live.
import { observe } from "./vendor/legend-state.mjs";
import { store, ui, applyEvent, setConnection, EVENT_TYPES } from "./store.js";
import { h } from "./ui.js";

import * as setup from "./panels/setup.js";
import * as filters from "./panels/filters.js";
import * as status from "./panels/status.js";
import * as record from "./panels/record.js";
import * as units from "./panels/units.js";
import * as specialists from "./panels/specialists.js";
import * as openings from "./panels/openings.js";
import * as history from "./panels/history.js";
import * as opponents from "./panels/opponents.js";
import * as recent from "./panels/recent.js";
import * as matchHeader from "./panels/match-header.js";
import * as winProbability from "./panels/win-probability.js";
import * as composition from "./panels/composition.js";
import * as armyHp from "./panels/army-hp.js";
import * as boards from "./panels/boards.js";
import * as offer from "./panels/offer.js";

function buildLayout(root) {
  const tab = (view, label) =>
    h("button", { type: "button", class: "tab", role: "tab", "data-view": view, onclick: () => ui.view.set(view) }, h("span", null, label), view === "current" ? h("i", { class: "live-dot", "aria-hidden": "true" }) : null);
  const tabs = h("nav", { class: "tabs", role: "tablist" }, tab("stats", "Stats"), tab("current", "Current Match"));
  const meta = h("div", { class: "topbar-meta" });
  const topbar = h("header", { class: "topbar" }, h("div", { class: "wordmark" }, h("span", { class: "wm-mark" }), h("span", null, "Visualizer")), tabs, meta);
  const statusSlot = h("div", { class: "status-slot" });

  const g = (cls) => h("div", { class: `cell ${cls}` });
  const stats = {
    setup: g("c-setup"),
    filters: g("c-filters"),
    record: g("c-record"),
    history: g("c-history"),
    units: g("c-units"),
    specialists: g("c-specialists"),
    openings: g("c-openings"),
    recent: g("c-recent"),
    opponents: g("c-opponents"),
  };
  const current = {
    header: g("c-header"),
    win: g("c-win"),
    composition: g("c-composition"),
    army: g("c-army"),
    boards: g("c-boards"),
    offer: g("c-offer"),
  };
  const statsView = h("main", { class: "view stats-view", "data-view-container": "stats" }, Object.values(stats));
  const currentView = h("main", { class: "view current-view", "data-view-container": "current" }, Object.values(current));
  root.replaceChildren(topbar, statusSlot, statsView, currentView);
  return { tabs, meta, statusSlot, stats, current, statsView, currentView };
}

function mountPanels(layout) {
  status.mount(layout.statusSlot);
  setup.mount(layout.stats.setup);
  filters.mount(layout.stats.filters);
  record.mount(layout.stats.record);
  history.mount(layout.stats.history);
  units.mount(layout.stats.units);
  specialists.mount(layout.stats.specialists);
  openings.mount(layout.stats.openings);
  recent.mount(layout.stats.recent);
  opponents.mount(layout.stats.opponents);
  matchHeader.mount(layout.current.header);
  winProbability.mount(layout.current.win);
  composition.mount(layout.current.composition);
  armyHp.mount(layout.current.army);
  boards.mount(layout.current.boards);
  offer.mount(layout.current.offer);
}

function bindViews(layout) {
  observe(() => {
    const view = ui.view.get();
    for (const btn of layout.tabs.querySelectorAll("[data-view]")) {
      const on = btn.dataset.view === view;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", String(on));
    }
    layout.statsView.dataset.active = String(view === "stats");
    layout.currentView.dataset.active = String(view === "current");
    // Charts in a hidden view measure 0×0; nudge them once the view is visible.
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
  });
  observe(() => {
    const live = store.status.get()?.state === "live";
    layout.tabs.querySelector('[data-view="current"]').classList.toggle("is-live", live);
  });
  observe(() => {
    const s = store.status.get();
    const hello = store.hello.get();
    const connection = store.connection.get();
    const bits = [];
    const version = s?.gameVersion;
    if (version) bits.push(h("span", { class: "meta-chip" }, `Game ${version}`));
    if (s?.bridge && s.bridge !== "absent") bits.push(h("span", { class: `meta-chip bridge-${s.bridge}` }, `Bridge ${s.bridge}`));
    if (hello?.liveSource === "playback") bits.push(h("span", { class: "meta-chip" }, "Playback"));
    bits.push(h("span", { class: `meta-chip conn-${connection}`, title: hello?.serverVersion ? `Server ${hello.serverVersion}` : "" }, connection === "open" ? "Connected" : connection === "lost" ? "Offline" : "Connecting"));
    layout.meta.replaceChildren(...bits);
  });
}

// Auto-switch to Current Match once per new match: when the live state turns "live", or when a frame arrives
// for a battle this page hasn't shown yet (that covers a catch-up that lands on a finished playback).
function bindAutoSwitch() {
  const seen = new Set();
  let lastState = null;
  observe(() => {
    const state = store.status.get()?.state ?? null;
    if (state === "live" && lastState !== "live") ui.view.set("current");
    lastState = state;
  });
  observe(() => {
    const battleId = store.frame.get()?.snapshot?.match?.battleId;
    if (!battleId || seen.has(battleId)) return;
    seen.add(battleId);
    ui.view.set("current");
  });
}

// SSE with auto-reconnect. EventSource retries on its own while the server is up; if it gives up (CLOSED), open a
// new one with backoff. Each reconnect's `hello` replaces state from the catch-up.
export function connect(url = "/events") {
  let delay = 1000;
  let source = null;
  const open = () => {
    setConnection("connecting");
    source = new EventSource(url);
    source.onopen = () => {
      delay = 1000;
      setConnection("open");
    };
    source.onerror = () => {
      setConnection("lost");
      if (source.readyState === EventSource.CLOSED) {
        source.close();
        setTimeout(open, delay);
        delay = Math.min(delay * 2, 15000);
      }
    };
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, (e) => {
        let data;
        try {
          data = JSON.parse(e.data);
        } catch (err) {
          console.warn(`Visualizer: bad ${type} event`, err);
          return;
        }
        applyEvent(type, data);
      });
    }
  };
  open();
  return () => source && source.close();
}

export function start({ live = true } = {}) {
  const layout = buildLayout(document.getElementById("app"));
  mountPanels(layout);
  bindViews(layout);
  bindAutoSwitch();
  window.__visualizer = { store, ui, applyEvent };
  if (live) connect();
  return layout;
}
