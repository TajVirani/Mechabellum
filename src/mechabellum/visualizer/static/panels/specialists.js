// Stats 3. Specialists: games, W–L, win rate per specialist.
import { observe } from "../vendor/legend-state.mjs";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { groupRecord } from "../stats.js";
import { panelShell, replace, empty, recordTable } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "specialists", "Specialists", { className: "scroll-panel" });
  observe(() => {
    const matches = filteredMatches();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const rows = groupRecord(
      matches,
      (m) => m.me.specialistId ?? "none",
      (m) => m.me.specialistName || "No specialist",
    );
    replace(p.body, recordTable("Specialist", rows));
    p.setState("ready");
  });
}
