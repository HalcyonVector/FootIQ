/* Retries /api/ calls that fail while the server is starting or being redeployed
   (network error, or a 502/503/504 from Render's proxy or from the app itself while
   it is still loading its data). Free-tier hosting sleeps and restarts, so a first
   request can miss; a quiet retry beats an error toast. All API calls here are
   reads, so repeating one is safe.

   While any API call has been waiting more than a few seconds, a small note explains
   why, so a cold start reads as "starting up" and not as a broken page. */
(() => {
  const orig = window.fetch.bind(window);
  const RETRY_STATUS = new Set([502, 503, 504]);
  const DELAYS = [3000, 7000, 12000];   // waits before retry 1, 2, 3
  const NOTE_AFTER_MS = 4000;

  let pending = 0, timer = null, note = null;
  function showNote() {
    if (note || !document.body) return;
    note = document.createElement("div");
    note.setAttribute("role", "status");
    note.style.cssText = "position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:9999;" +
      "max-width:min(92vw,460px);padding:10px 16px;border-radius:12px;font:500 13px/1.4 'Outfit',sans-serif;" +
      "color:#e5e7eb;background:rgba(17,24,39,.94);border:1px solid rgba(99,102,241,.45);" +
      "box-shadow:0 10px 30px rgba(0,0,0,.4);text-align:center";
    note.textContent = "Starting up and loading the player data. The first visit after a quiet spell takes a little while.";
    document.body.appendChild(note);
  }
  function begin() {
    if (pending++ === 0) timer = setTimeout(showNote, NOTE_AFTER_MS);
  }
  function end() {
    if (--pending === 0) {
      clearTimeout(timer);
      if (note) { note.remove(); note = null; }
    }
  }

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (!url.startsWith("/api/")) return orig(input, init);
    begin();
    try {
      for (let i = 0; ; i++) {
        try {
          const res = await orig(input, init);
          if (!RETRY_STATUS.has(res.status) || i >= DELAYS.length) return res;
        } catch (err) {
          if (i >= DELAYS.length || (init && init.signal && init.signal.aborted)) throw err;
        }
        await new Promise(r => setTimeout(r, DELAYS[i]));
      }
    } finally {
      end();
    }
  };
})();
