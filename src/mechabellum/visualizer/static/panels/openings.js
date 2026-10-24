// Stats 4. Openings: grouped by openingLead by default, with a toggle to the exact openingName.
import { observe } from "../vendor/legend-state.mjs";
import { ui } from "../store.js";
import { filteredMatches, statsEmptyReason } from "../selectors.js";
import { groupRecord } from "../stats.js";
import { h, panelShell, replace, empty, recordTable } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "openings", "Openings", { className: "scroll-panel" });
  const toggle = h("div", { class: "seg", role: "group", "aria-label": "Group openings by" });
  p.tools.append(toggle);
  observe(() => {
    const group = ui.openingsGroup.get();
    replace(
      toggle,
      [
        ["lead", "Lead unit"],
        ["name", "Exact"],
      ].map(([key, label]) =>
        h("button", { type: "button", class: key === group ? "on" : "", "data-group": key, onclick: () => ui.openingsGroup.set(key) }, label),
      ),
    );
    const matches = filteredMatches();
    const reason = statsEmptyReason(matches);
    if (reason) {
      replace(p.body, empty(reason));
      p.setState("empty");
      return;
    }
    const rows =
      group === "lead"
        ? groupRecord(matches, (m) => m.me.openingLead || m.me.openingName || "none", (m) => m.me.openingLead || m.me.openingName || "No opening")
        : groupRecord(matches, (m) => m.me.openingId ?? m.me.openingName ?? "none", (m) => m.me.openingName || "No opening");
    replace(p.body, recordTable(group === "lead" ? "Lead unit" : "Opening", rows));
    p.setState("ready");
  });
}
