/* Retries /api/ calls that fail while the server is starting or being redeployed
   (network error, or a 502/503/504 from Render's proxy or from the app itself while
   it is still loading its data). Free-tier hosting sleeps and restarts, so a first
   request can miss; a quiet retry beats an error toast. All API calls here are
   reads, so repeating one is safe. */
(() => {
  const orig = window.fetch.bind(window);
  const RETRY_STATUS = new Set([502, 503, 504]);
  const DELAYS = [3000, 7000, 12000];   // waits before retry 1, 2, 3
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    if (!url.startsWith("/api/")) return orig(input, init);
    for (let i = 0; ; i++) {
      try {
        const res = await orig(input, init);
        if (!RETRY_STATUS.has(res.status) || i >= DELAYS.length) return res;
      } catch (err) {
        if (i >= DELAYS.length || (init && init.signal && init.signal.aborted)) throw err;
      }
      await new Promise(r => setTimeout(r, DELAYS[i]));
    }
  };
})();
