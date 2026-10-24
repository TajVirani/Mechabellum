// Current Match 6. This round's offer: the reinforcementOffer cards by name, while playing only (localIndex set).
// Names come from the frame's `offerNames` when the server sends them; otherwise the card id is shown.
import { observe } from "../vendor/legend-state.mjs";
import { store } from "../store.js";
import { h, panelShell, replace, empty } from "../ui.js";

export function mount(container) {
  const p = panelShell(container, "offer", "This round's offer", { className: "offer-panel" });
  observe(() => {
    const frame = store.frame.get();
    const offer = frame?.snapshot?.match?.reinforcementOffer || [];
    const playing = frame && frame.localIndex != null;
    if (!frame) {
      replace(p.body, empty("No match yet."));
      p.setState("empty");
      return;
    }
    if (!playing) {
      replace(p.body, empty("Shown only while you're playing."));
      p.setState("empty");
      return;
    }
    if (!offer.length) {
      replace(p.body, empty("No offer this round."));
      p.setState("empty");
      return;
    }
    const names = frame.offerNames || [];
    replace(
      p.body,
      h(
        "div",
        { class: "offer-cards" },
        offer.map((id, i) =>
          h("div", { class: "offer-card", "data-card-id": id }, h("div", { class: "card-name" }, names[i] || `Card #${id}`), names[i] ? h("div", { class: "card-id" }, `#${id}`) : null),
        ),
      ),
    );
    p.setState("ready");
  });
}
