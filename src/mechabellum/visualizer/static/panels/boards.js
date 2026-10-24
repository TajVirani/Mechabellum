// Current Match 5. Boards: each player's units grouped by type, with count, level and a role-coloured chip.
// Marked "as of last fight" when boardAsOfLastFight is true (the opponent while deploying).
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { unitInfo, ROLE_LABELS } from "../roles.js";
import { h, panelShell, replace, empty, num, sides } from "../ui.js";

function groups(units) {
  const byId = new Map();
  for (const u of units || []) {
    let g = byId.get(u.unitId);
    if (!g) {
      const info = unitInfo(u.unitId);
      byId.set(u.unitId, (g = { ...info, name: info.name.startsWith("Unknown") && u.unitName ? u.unitName : info.name, count: 0, levels: [], supply: 0 }));
    }
    g.count++;
    g.levels.push(u.displayLevel ?? 1);
    g.supply += Math.max(0, u.sellSupply || 0);
  }
  return [...byId.values()].sort((a, b) => b.supply - a.supply || a.name.localeCompare(b.name));
}

function levelText(levels) {
  const lo = Math.min(...levels);
  const hi = Math.max(...levels);
  return lo === hi ? `Lv ${lo}` : `Lv ${lo}–${hi}`;
}

export function mount(container) {
  const p = panelShell(container, "boards", "Boards", { className: "boards-panel" });
  observe(() => {
    const frame = store.frame.get();
    if (!frame?.snapshot) {
      replace(p.body, empty("No match yet."));
      p.setState("empty");
      return;
    }
    const cols = sides(frame).map((s) => {
      const list = groups(s.player?.units);
      const stale = !!frame.boardAsOfLastFight?.[s.index];
      const total = list.reduce((sum, g) => sum + g.supply, 0);
      return h(
        "div",
        { class: `board ${s.side}`, "data-side": s.side },
        h(
          "div",
          { class: "board-head" },
          h("span", { class: "player-name" }, s.player?.name || "—"),
          stale ? h("span", { class: "tag stale", "data-flag": "as-of-last-fight" }, "as of last fight") : null,
          h("span", { class: "board-total currency", title: "Total sell supply" }, num(total)),
        ),
        list.length
          ? h(
              "div",
              { class: "tiles" },
              list.map((g) =>
                h(
                  "div",
                  { class: `tile role-edge-${g.primary}`, "data-unit-id": g.id, title: `${g.name} · ${ROLE_LABELS[g.primary]}${g.secondary ? ` / ${ROLE_LABELS[g.secondary]}` : ""}${g.air ? " · air" : ""}${g.hitsAir ? " · hits air" : ""}` },
                  h("div", { class: "tile-name" }, g.name),
                  h(
                    "div",
                    { class: "tile-meta" },
                    h("span", { class: "tile-count" }, `×${g.count}`),
                    h("span", { class: "tile-level" }, levelText(g.levels)),
                    h("span", { class: `role-chip role-${g.primary}` }, ROLE_LABELS[g.primary]),
                  ),
                ),
              ),
            )
          : empty("Empty board"),
      );
    });
    replace(p.body, cols);
    p.setState("ready");
  });
}
