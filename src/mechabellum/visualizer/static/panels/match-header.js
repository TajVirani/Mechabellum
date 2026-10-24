// Current Match 1. Header: names, ratings, round, phase, HP (reactorCore), supply and income for both sides.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { h, panelShell, replace, empty, num, sides, PHASE_LABELS } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "match-header", null, { className: "match-header" });
  observe(() => {
    const frame = store.frame.get();
    const snapshot = frame?.snapshot;
    if (!snapshot) {
      replace(p.body, empty(store.hello.get()?.liveSource === "none" ? "No live source: started with --no-live." : "No match yet."));
      p.setState("empty");
      return;
    }
    const match = snapshot.match || {};
    const [left, right] = sides(frame);
    const outcome = snapshot.outcome;
    const plate = (s) => {
      const pl = s.player || {};
      // The core can go below 0 on the killing blow; never show negative HP.
      const hp = pl.reactorCore == null ? null : Math.max(0, pl.reactorCore);
      const maxHp = pl.maxReactorCore || null;
      const won = outcome ? outcome.winnerIndex === s.index : null;
      return h(
        "div",
        { class: `plate ${s.side}`, "data-side": s.side },
        h(
          "div",
          { class: "plate-top" },
          s.label ? h("span", { class: "side-label" }, s.label) : null,
          h("span", { class: "player-name", "data-field": "name", title: pl.playerId || "" }, pl.name || "—"),
          pl.rating != null ? h("span", { class: "rating", "data-field": "rating" }, pl.rating) : null,
          won != null ? h("span", { class: `result ${won ? "win" : "loss"}` }, won ? "Winner" : "Defeated") : null,
        ),
        h(
          "div",
          { class: "hp-bar", title: `HP ${num(hp)}${maxHp ? ` / ${num(maxHp)}` : ""}` },
          h("div", { class: "hp-fill", style: { width: `${maxHp && hp != null ? Math.max(0, Math.min(100, (hp / maxHp) * 100)) : 0}%` } }),
        ),
        h(
          "div",
          { class: "plate-stats" },
          stat("HP", hp != null ? `${num(hp)}${maxHp ? ` / ${num(maxHp)}` : ""}` : "—", "hp"),
          stat("Supply", num(pl.supply), "supply", "currency"),
          stat("Income", pl.roundSupplyIncome != null ? `+${num(pl.roundSupplyIncome)}` : "—", "income", "currency"),
        ),
      );
    };
    replace(
      p.body,
      plate(left),
      h(
        "div",
        { class: "round-pill" },
        h("div", { class: "round-label" }, "Round"),
        h("div", { class: "round-value", "data-field": "round" }, match.round ?? "—"),
        h("div", { class: "phase", "data-field": "phase" }, PHASE_LABELS[match.phase] || match.phase || "—"),
      ),
      plate(right),
    );
    p.setState("ready");
  });
}

function stat(label, value, key, cls = "") {
  return h("div", { class: `pstat ${cls}`, "data-field": key }, h("span", { class: "pstat-label" }, label), h("span", { class: "pstat-value" }, value));
}
