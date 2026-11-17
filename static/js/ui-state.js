/**
 * FootIQ: shared loading / empty / error panels, so a failed request shows what happened and a
 * "Try again" button in the place the content would have been, instead of a toast that
 * disappears or nothing at all. The free host sleeps when idle and the first request after a
 * quiet spell can take 20 to 30 seconds (or fail while it wakes), so errors say that.
 */
const FootIQUI = (() => {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function card(host, kind, title, text, retry) {
    host.innerHTML = `<div class="state-card state-${kind}" ${kind === "error" ? 'role="alert"' : ""}>
      <div class="state-title">${esc(title)}</div>
      ${text ? `<div class="state-text">${esc(text)}</div>` : ""}
      ${retry ? '<button type="button" class="state-btn">Try again</button>' : ""}
    </div>`;
    if (retry) host.querySelector(".state-btn").addEventListener("click", retry);
  }

  return {
    /** Something failed: say so, explain the likely cause, offer a retry. */
    error(host, message, retry) {
      card(host, "error", message || "Could not load this.",
        "The server may still be waking up. The first request after a quiet spell can take 20 to 30 seconds.", retry);
    },
    /** Nothing to show: say why and what to try. */
    empty(host, title, hint) { card(host, "empty", title, hint); },
    /** Waiting: a labelled spinner. */
    loading(host, text) {
      host.innerHTML = `<div class="state-card state-loading"><div class="mini-spinner"></div><div class="state-title">${esc(text || "Loading…")}</div></div>`;
    },
  };
})();
