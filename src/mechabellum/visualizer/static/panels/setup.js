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

// The form is built once; observe() only updates the suggestion and visibility, so typed text and focus survive
// every summaries/hello event.
export function mount(container) {
  const p = panelShell(container, "setup", "Who are you?", { className: "setup-card" });
  const input = h("input", { type: "text", class: "text-input", placeholder: "Player id, e.g. 281474976710769865", "aria-label": "Player id", spellcheck: "false" });
  const status = h("p", { class: "form-error" });
  const suggestion = h("div", { class: "suggestion-slot" });
  const cancel = h("button", { type: "button", class: "btn ghost", onclick: () => ui.showSetup.set(false) }, "Cancel");
  const save = async (playerId) => {
    const value = String(playerId || "").trim();
    if (!/^\d+$/.test(value)) {
      status.textContent = "A player id is a number.";
      return;
    }
    try {
      await setLocalPlayer(value);
      status.textContent = "";
      ui.showSetup.set(false);
    } catch (e) {
      status.textContent = `Couldn't save: ${e.message}`;
    }
  };
  const form = h(
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
    cancel,
  );
  replace(p.body, h("p", null, "The Stats view counts the matches you played. Pick your player id; it stays the same when you rename."), suggestion, form, status);

  let wasShown = false;
  observe(() => {
    const hello = store.hello.get();
    const id = store.localPlayerId.get();
    const forced = ui.showSetup.get();
    const summaries = store.summaries.get();
    if (!hello || (id && !forced)) {
      p.root.hidden = true;
      wasShown = false;
      p.setState("empty");
      return;
    }
    p.root.hidden = false;
    // Prefill the current id only when the card opens, never over what the user is typing.
    if (!wasShown) {
      input.value = id || "";
      status.textContent = "";
    }
    wasShown = true;
    cancel.hidden = !id;
    const suggested = hello.suggestedPlayerId;
    replace(
      suggestion,
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
    );
    p.setState("ready");
  });
}
