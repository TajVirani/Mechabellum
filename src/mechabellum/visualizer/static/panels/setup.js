// Setup card: until a Local Player id is set, offer the suggested id (with the name it last played under) and a
// text field. Saving POSTs to /api/local-player on localhost; the store only changes when the server's `config`
// event comes back over SSE.
import { observe } from "../vendor/legend-state.mjs";
import { store, ui } from "../store.js";
import { h, panelShell, replace } from "../ui.js";

export async function setLocalPlayer(playerId) {
  const response = await fetch("/api/local-player", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ playerId }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

function lastNameOf(summaries, playerId) {
  for (let i = summaries.length - 1; i >= 0; i--) {
    const p = (summaries[i].players || []).find((x) => x.playerId === playerId);
    if (p) return p.name;
  }
  return null;
}

function countOf(summaries, playerId) {
  return summaries.filter((s) => (s.players || []).some((p) => p.playerId === playerId)).length;
}

export function mount(container) {
  const p = panelShell(container, "setup", "Who are you?", { className: "setup-card" });
  let error = "";
  observe(() => {
    const hello = store.hello.get();
    const id = store.localPlayerId.get();
    const forced = ui.showSetup.get();
    const summaries = store.summaries.get();
    if (!hello || (id && !forced)) {
      p.root.hidden = true;
      replace(p.body);
      p.setState("empty");
      return;
    }
    p.root.hidden = false;
    const suggested = hello.suggestedPlayerId;
    const input = h("input", { type: "text", class: "text-input", placeholder: "Player id, e.g. 281474976710769865", value: id || "", "aria-label": "Player id", spellcheck: "false" });
    const status = h("p", { class: "form-error" }, error);
    const save = async (playerId) => {
      const value = String(playerId || "").trim();
      if (!/^\d+$/.test(value)) {
        error = "A player id is a number.";
        status.textContent = error;
        return;
      }
      try {
        await setLocalPlayer(value);
        error = "";
        ui.showSetup.set(false);
      } catch (e) {
        error = `Couldn't save: ${e.message}`;
        status.textContent = error;
      }
    };
    replace(
      p.body,
      h("p", null, "The Stats view counts the matches you played. Pick your player id; it stays the same when you rename."),
      suggested
        ? h(
            "div",
            { class: "suggestion" },
            h(
              "div",
              null,
              h("div", { class: "suggest-name" }, lastNameOf(summaries, suggested) || "Unknown name"),
              h("div", { class: "suggest-id" }, `${suggested} · in ${countOf(summaries, suggested)} of ${summaries.length} replays`),
            ),
            h("button", { type: "button", class: "btn primary", "data-action": "use-suggested", onclick: () => save(suggested) }, "That's me"),
          )
        : h("p", { class: "muted" }, "No player appears in most of your replays, so there's no suggestion."),
      h(
        "form",
        {
          class: "id-form",
          onsubmit: (e) => {
            e.preventDefault();
            save(input.value);
          },
        },
        input,
        h("button", { type: "submit", class: "btn" }, "Save id"),
        id ? h("button", { type: "button", class: "btn ghost", onclick: () => ui.showSetup.set(false) }, "Cancel") : null,
      ),
      status,
    );
    p.setState("ready");
  });
}
