/* Only used by the static front end on Vercel (deploy/build_static.py sets window.FOOTIQ_STATIC).

   The Flask app behind it sleeps when idle and takes 20+ seconds to wake, so everything that
   can be answered without the data engine is answered here, from small JSON files served by
   the CDN: player search, the home-page cards, the coverage table and the competition list.
   Every other /api/ call falls through to the real server (a Vercel rewrite forwards it), and
   one background call to /api/health is sent at once so a sleeping server starts waking while
   the visitor is still reading the page and typing a name.

   The search mirrors core/advanced/lookup.py exactly: names are folded the same way, a name
   containing the query is ranked whole word, then prefix, then word start, then inside, with
   the busiest player first within a rank; at most 15 results. */
(() => {
  if (!window.FOOTIQ_STATIC) return;
  const native = window.fetch.bind(window);
  const files = {};
  const load = name => (files[name] ||= native(`/data/${name}.json`).then(r => {
    if (!r.ok) throw new Error(name);
    return r.json();
  }));
  const reply = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

  // Wake the real server now, without waiting for a call that needs it.
  native("/api/health", { cache: "no-store" }).catch(() => {});

  // Fetch the search index while the visitor is still reading the page, so the first search is instant.
  window.addEventListener("load", () => setTimeout(() => { searchIndex().catch(() => {}); }, 800));

  // ── search ────────────────────────────────────────────────────────────────
  let index = null;
  async function searchIndex() {
    if (index) return index;
    const raw = await load("search-index");
    const byLeagueSeason = new Map(), bySeason = new Map();
    for (const r of raw.rows) {
      const lsKey = raw.league[r[4]] + "\u0000" + raw.season[r[5]];
      (byLeagueSeason.get(lsKey) || byLeagueSeason.set(lsKey, []).get(lsKey)).push(r);
      (bySeason.get(r[5]) || bySeason.set(r[5], []).get(r[5])).push(r);
    }
    const seasonIdx = new Map(raw.season.map((s, i) => [s, i]));
    index = { raw, byLeagueSeason, bySeason, seasonIdx };
    return index;
  }

  function fold(s, translate) {
    let out = "";
    for (const c of s || "") out += translate[c] ?? c;
    return out.normalize("NFD").replace(/[^\x00-\x7f]/g, "").toLowerCase();
  }

  function rank(norm, q, i) {
    if (norm.split(/[ -]/).includes(q)) return 0;
    if (i === 0) return 1;
    return " -".includes(norm[i - 1]) ? 2 : 3;
  }

  function ranked(pool, q, raw) {
    const hits = [];
    for (const r of pool) {
      const i = r[0].indexOf(q);
      if (i < 0) continue;
      hits.push([rank(r[0], q, i), -(r[7] || 0), r[0], r]);
    }
    hits.sort((a, b) => a[0] - b[0] || a[1] - b[1] || (a[2] < b[2] ? -1 : a[2] > b[2] ? 1 : 0));
    return hits.slice(0, 15).map(h => {
      const r = h[3];
      return { id: r[1], name: r[2], team: raw.team[r[3]], league: raw.league[r[4]], season: raw.season[r[5]],
               position: raw.position[r[6]], minutes: r[7], age: r[8] };
    });
  }

  async function search(params) {
    const name = params.get("name") || "";
    if (name.length < 2) return [];
    const league = params.get("league") || "Premier League";
    const season = params.get("season") || "2024-25";
    const ix = await searchIndex();
    const q = fold(name, ix.raw.translate);
    if (!q) return [];
    const global = () => ranked(ix.bySeason.get(ix.seasonIdx.get(season)) || [], q, ix.raw);
    if (params.get("all_leagues") === "1") return global();
    const local = ranked(ix.byLeagueSeason.get(league + "\u0000" + season) || [], q, ix.raw);
    return local.length ? local : global();
  }

  // ── fetch ─────────────────────────────────────────────────────────────────
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const method = ((init && init.method) || (input && input.method) || "GET").toUpperCase();
    if (method === "GET" && url.startsWith("/api/")) {
      const u = new URL(url, location.origin);
      try {
        if (u.pathname === "/api/search") return reply(await search(u.searchParams));
        if (u.pathname === "/api/hub") return reply((await load("hub")).facts);
        if (u.pathname === "/api/hub-player") {
          const players = (await load("hub")).players;
          const i = parseInt(u.searchParams.get("i") || "0", 10);
          return players[i] ? reply(players[i]) : reply({ error: "no such player" }, 404);
        }
        if (u.pathname === "/api/coverage") return reply(await load("coverage"));
        if (u.pathname === "/api/leagues") return reply(await load("leagues"));
      } catch (e) {
        /* the CDN file could not be read: fall through to the real server */
      }
    }
    return native(input, init);
  };
})();
