// Status banner: waiting, no game, retrying, layout mismatch, playback done, and a lost server connection.
// data-state is "ready" while a banner shows and "empty" when there's nothing to report (live, off, or no status
// yet); data-status always carries the live source's state.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { h, panelShell, replace } from "../ui.js";

const MESSAGES = {
  waiting: ["Waiting for a match", "The game is running; the view fills in when a match starts."],
  no_game: ["Mechabellum isn't running", "Start the game and this view connects on its own."],
  retrying: ["Reading the game…", "The live reader hit a read error and is retrying."],
  layout_mismatch: ["Game build not supported", "The game's memory layout doesn't match this build of the reader."],
  playback_done: ["Playback finished", "Showing the recording's final state."],
};

export function mount(container) {
  const p = panelShell(container, "status", null, { className: "status-banner" });
  observe(() => {
    const connection = store.connection.get();
    const status = store.status.get();
    const state = status?.state ?? "none";
    p.root.dataset.status = connection === "lost" ? "disconnected" : state;
    let title = null;
    let detail = null;
    let tone = "info";
    if (connection === "lost") {
      [title, detail, tone] = ["Lost the Visualizer server", "Reconnecting…", "warn"];
    } else if (MESSAGES[state]) {
      [title, detail] = MESSAGES[state];
      if (status.detail) detail = status.detail;
      if (state === "layout_mismatch" && status.gameVersion) detail = `${detail} (game ${status.gameVersion})`;
      tone = state === "layout_mismatch" || state === "no_game" ? "warn" : state === "playback_done" ? "done" : "info";
    }
    if (!title) {
      p.root.hidden = true;
      replace(p.body);
      p.setState("empty");
      return;
    }
    p.root.hidden = false;
    p.root.dataset.tone = tone;
    replace(p.body, h("span", { class: "status-icon", "aria-hidden": "true" }), h("strong", null, title), detail ? h("span", { class: "status-detail" }, detail) : null);
    p.setState("ready");
  });
}
