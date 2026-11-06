/* ─────────────────────────────────────────────────────────────────────────────
   "Similar players" row on the profile: the same percentile-vector search the
   Scout page runs, limited to the closest few. Each card links to that
   player's profile (season included) and to a Compare pre-filled with both.

     FootIQSimilar.load(player, league, season)
     FootIQSimilar.reset()
   ───────────────────────────────────────────────────────────────────────────── */
const FootIQSimilar = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COUNT = 6;
  let token = 0;

  function profileUrl(m) {
    return `/player?${new URLSearchParams({ player_id: m.player_id, league: m.league, season: m.season })}`;
  }

  function compareUrl(player, league, season, m) {
    return "/compare?" + new URLSearchParams({
      p1_id: player.id, p1_league: league, p1_season: season,
      p2_id: m.player_id, p2_league: m.league, p2_season: m.season,
    });
  }

  function card(player, league, season, m) {
    const age = m.age ? ` · ${m.age}y` : "";
    return `<div class="sim-card">
      <div class="sim-score" title="Cosine similarity of percentile profiles">${Math.round(m.similarity)}<small>%</small></div>
      <a class="sim-name" href="${profileUrl(m)}">${esc(m.name)}</a>
      <div class="sim-meta">${esc(m.team)}</div>
      <div class="sim-meta">${esc(m.position || "")}${age}</div>
      <div class="sim-meta sim-dim">${esc(m.league)} · ${esc(m.season)}</div>
      <a class="sim-compare" href="${compareUrl(player, league, season, m)}">Compare →</a>
    </div>`;
  }

  let observer = null;

  function reset() {
    token++;
    if (observer) { observer.disconnect(); observer = null; }
    const s = $("similar-section");
    if (s) s.style.display = "none";
  }

  async function fetchAndRender(player, league, season, mine) {
    const section = $("similar-section");
    let data;
    try {
      const res = await fetch("/api/scout-similar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: player.id, league, season, limit: COUNT, max_age: null, league_pool: "all" }),
      });
      data = await res.json();
    } catch { return; }
    if (mine !== token || !data || !data.matches || !data.matches.length) return;   // stale, or not enough data to compare
    $("sim-row").innerHTML = data.matches.map(m => card(player, league, season, m)).join("");
    section.style.display = "block";
  }

  // The similarity search scans the whole position cohort, so it only runs
  // once the visitor scrolls down to the Advanced Metrics block -- not on
  // every profile view.
  function load(player, league, season) {
    reset();
    const mine = token;
    const anchor = $("advanced-section");
    if (!anchor || !("IntersectionObserver" in window)) { fetchAndRender(player, league, season, mine); return; }
    observer = new IntersectionObserver((entries) => {
      if (!entries.some(e => e.isIntersecting)) return;
      observer.disconnect();
      observer = null;
      fetchAndRender(player, league, season, mine);
    }, { rootMargin: "200px" });
    observer.observe(anchor);
  }

  return { load, reset };
})();
