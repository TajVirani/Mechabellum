// Current Match 7. Recommended purchases: the server's `recommendations` event, ranked by `mecha recommend`'s logic
// (inference/actions.py) on each new deploying or fight_over frame. For the Local Player, or both players when
// spectating: buys, unlocks, upgrades, technologies and offered cards, each with its supply cost and the change in
// win probability. At a fight's end the budget is an estimate (supply left plus this round's income).
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { unitInfo } from "../roles.js";
import { h, panelShell, replace, empty, pct, num, sides, PHASE_LABELS } from "../ui.js";
import { pts } from "../insights.js";

const KIND_LABELS = { buy: "Buy", unlock: "Unlock", upgrade: "Upgrade", technology: "Tech", card: "Card" };

// The payload for the current frame's battle, or null.
export function currentRecommendations() {
  const rec = store.recommendations.get();
  const frame = store.frame.get();
  const battleId = frame?.snapshot?.match?.battleId ?? null;
  if (!rec || !frame || (battleId && rec.battleId && rec.battleId !== battleId)) return null;
  return rec;
}

// Payload players in left/right order.
export function orderedPlayers(rec, frame) {
  const order = sides(frame).map((s) => s.index);
  return [...(rec.players || [])].sort((a, b) => order.indexOf(a.index) - order.indexOf(b.index));
}

function sideOf(frame, index) {
  return sides(frame).find((s) => s.index === index)?.side || "left";
}

function rowView(row, maxGain) {
  const info = row.unitId == null ? null : unitInfo(row.unitId);
  const width = maxGain > 0 ? Math.max(0, row.gain / maxGain) * 100 : 0;
  return h(
    "li",
    { class: `rec-row kind-${row.kind}`, "data-kind": row.kind, title: row.description || "" },
    h("span", { class: "rec-kind" }, KIND_LABELS[row.kind] || row.kind),
    h("span", { class: "rec-name" }, info ? h("span", { class: `role-dot role-${info.primary}` }) : null, row.label),
    h("span", { class: "rec-cost num" }, row.cost == null ? "—" : num(row.cost)),
    h("span", { class: `rec-gain num ${row.gain > 0 ? "up" : row.gain < 0 ? "down" : ""}` }, pts(row.gain), h("span", { class: "rec-gain-bar", style: { width: `${width}%` } })),
  );
}

export function mount(container) {
  const p = panelShell(container, "recommendations", "Recommended purchases", { className: "recommend-panel" });

  observe(() => {
    const frame = store.frame.get();
    const hello = store.hello.get();
    const rec = currentRecommendations();
    if (!frame) {
      replace(p.body, empty("No match yet."));
      p.setState("empty");
      return;
    }
    if ((hello && hello.modelAvailable === false) || rec?.modelAvailable === false) {
      p.root.dataset.model = "unavailable";
      replace(p.body, h("p", { class: "empty-note model-unavailable" }, "Model unavailable"), h("p", { class: "muted small" }, "Recommendations rank actions with the win model; install the ml extra and train artifacts/win_model.joblib."));
      p.setState("ready");
      return;
    }
    p.root.dataset.model = "available";
    if (!rec) {
      replace(p.body, empty("Recommendations come with the next deployment or fight end."));
      p.setState("empty");
      return;
    }
    const columns = orderedPlayers(rec, frame).map((player) => {
      const maxGain = Math.max(0, ...player.rows.map((r) => r.gain));
      return h(
        "div",
        { class: `rec-col side-${sideOf(frame, player.index)}`, "data-player-index": player.index },
        h(
          "div",
          { class: "rec-head" },
          h("span", { class: "rec-player" }, player.name || `Player ${player.index + 1}`),
          h("span", { class: "small muted" }, `${rec.budgetEstimated ? "Est. budget" : "Budget"} ${num(player.budget)}`),
          h("span", { class: "small muted", title: "The model's win probability for this position with the budget unspent; each row's Δ is against it." }, `baseline ${pct(player.baselineWinProbability, 1)}`),
        ),
        player.rows.length
          ? h(
              "ol",
              { class: "rec-list" },
              h("li", { class: "rec-row rec-labels small muted" }, h("span", null, ""), h("span", null, "Action"), h("span", { class: "num" }, "Supply"), h("span", { class: "num" }, "Δ win")),
              player.rows.map((row) => rowView(row, maxGain)),
            )
          : empty(player.candidates ? "Nothing ranked." : "Nothing affordable."),
      );
    });
    replace(
      p.body,
      h("div", { class: "rec-cols" }, columns),
      h("p", { class: "small muted rec-note" }, `Round ${rec.round}, ${PHASE_LABELS[rec.phase] || rec.phase}. ${rec.note || ""}`),
    );
    p.root.dataset.rows = String(rec.players.reduce((n, pl) => n + pl.rows.length, 0));
    p.setState("ready");
  });
}
