/* ─────────────────────────────────────────────────────────────────────────────
   League table page (/league) and team page (/team). Both are drawn client-side
   from /api/league-table and /api/team (built from the per-match rows).
   ───────────────────────────────────────────────────────────────────────────── */
(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const RES_COL = { W: "#22c55e", D: "#94a3b8", L: "#ef4444" };
  const q = new URLSearchParams(location.search);

  const teamUrl = (league, season, team) => `/team?${new URLSearchParams({ league, season, team })}`;
  const playerUrl = (id, league, season) => `/player?${new URLSearchParams({ player_id: id, league, season })}`;
  const formDots = form => `<span class="lg-form">${form.map(r => `<i style="background:${RES_COL[r]}" title="${r}"></i>`).join("")}</span>`;
  const ordinal = n => { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const signed = n => (n > 0 ? "+" : "") + n;

  // ── League table ──────────────────────────────────────────────────────────
  async function loadTable() {
    const league = $("lg-league").value, season = $("lg-season").value;
    try { history.replaceState(null, "", `/league?${new URLSearchParams({ league, season })}`); } catch { /* non-fatal */ }
    const section = $("lg-section");
    let data;
    try { data = await (await fetch(`/api/league-table?${new URLSearchParams({ league, season })}`)).json(); }
    catch { return; }
    section.style.display = "block";
    const name = (window.LEAGUES.find(l => l.id === league) || {}).name || league;
    $("lg-title").textContent = `${name} · ${season}`;
    if (!data.table || !data.table.length) {
      $("lg-table").innerHTML = '<div class="ov-empty">No matches for this competition and season yet.</div>';
      $("lg-note").textContent = "";
      return;
    }
    $("lg-note").textContent = data.cup
      ? "Cup competition: this adds up every match each team played, so it is not the official group or knockout standing."
      : `Built from ${data.table.reduce((a, r) => a + r.played, 0) / 2} matches with event data; a match missing from the source is missing here too.`;
    const rows = data.table.map(r => `<tr>
      <td class="lg-pos">${r.pos}</td>
      <td class="lg-team"><a href="${teamUrl(league, season, r.team)}">${esc(r.team)}</a></td>
      <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
      <td>${r.gf}</td><td>${r.ga}</td><td class="${r.gd > 0 ? "lg-pos-gd" : r.gd < 0 ? "lg-neg-gd" : ""}">${signed(r.gd)}</td>
      <td class="lg-pts">${r.points}</td>
      <td>${r.xgf.toFixed(1)}</td><td>${r.xga.toFixed(1)}</td>
      <td class="lg-form-cell">${formDots(r.form)}</td></tr>`).join("");
    $("lg-table").innerHTML = `<table class="ov-table lg-table"><thead><tr>
      <th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th>
      <th>xG</th><th>xGA</th><th>Form</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  function initLeague() {
    const lg = $("lg-league"), se = $("lg-season");
    if (q.get("league") && [...lg.options].some(o => o.value === q.get("league"))) lg.value = q.get("league");
    if (q.get("season") && [...se.options].some(o => o.value === q.get("season"))) se.value = q.get("season");
    lg.addEventListener("change", loadTable);
    se.addEventListener("change", loadTable);
    if (typeof upgradeSelects === "function") upgradeSelects();
    loadTable();
  }

  // ── Team page ─────────────────────────────────────────────────────────────
  function tile(label, value, sub) {
    return `<div class="ov-tile"><div class="ov-tile-val">${value}</div><div class="ov-tile-lbl">${label}</div>${sub ? `<div class="ov-tile-sub">${sub}</div>` : ""}</div>`;
  }

  function renderForm(results) {
    const W = 760, H = 150, padB = 24, mid = (H - padB) / 2, slot = W / results.length;
    const bw = Math.min(slot * 0.68, 22);
    const maxGd = Math.max(3, ...results.map(r => Math.abs(r.gf - r.ga)));
    let g = `<line x1="0" x2="${W}" y1="${mid}" y2="${mid}" class="ov-grid"/>`;
    results.forEach((r, i) => {
      const cx = slot * i + slot / 2, gd = r.gf - r.ga;
      const h = Math.max(3, (Math.abs(gd) / maxGd) * (mid - 6));
      const y = gd >= 0 ? mid - h : mid;
      const tip = `${r.date} · ${r.home ? "H" : "A"} vs ${r.opp} ${r.gf}–${r.ga}${r.xga === null ? "" : ` · xG ${r.xgf.toFixed(1)}–${r.xga.toFixed(1)}`}`;
      g += `<rect x="${cx - bw / 2}" y="${y}" width="${bw}" height="${h}" rx="3" fill="${RES_COL[r.result]}" class="ov-bar"><title>${esc(tip)}</title></rect>`;
      g += `<text x="${cx}" y="${H - 8}" text-anchor="middle" class="ov-axis">${r.home ? "H" : "A"}</text>`;
    });
    $("tm-form").innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="ov-svg" role="img" aria-label="Goal difference by match">${g}</svg>`;
  }

  function renderSquad(squad, league, season) {
    const cols = [
      ["Player", "name", false], ["Pos", "position", false], ["Apps", "apps", true], ["Starts", "starts", true], ["Mins", "minutes", true],
      ["G", "goals", true], ["A", "assists", true], ["xG", "xg", true], ["xA", "xa", true], ["Rating", "rating", true], ["Y/R", "yellow", true],
    ];
    let sortKey = "minutes", sortDir = -1;
    const draw = () => {
      const sorted = [...squad].sort((a, b) => {
        const x = a[sortKey], y = b[sortKey];
        if (x === null || x === undefined) return 1;
        if (y === null || y === undefined) return -1;
        return (typeof x === "string" ? x.localeCompare(y) : x - y) * sortDir;
      });
      const head = cols.map(([l, k]) => `<th data-k="${k}" class="lg-sort${k === sortKey ? " active" : ""}">${l}${k === sortKey ? (sortDir < 0 ? " ▾" : " ▴") : ""}</th>`).join("");
      const body = sorted.map(p => `<tr>
        <td><a href="${playerUrl(p.player_id, league, season)}">${esc(p.name)}</a></td><td>${esc(p.position || "–")}</td>
        <td>${p.apps}</td><td>${p.starts}</td><td>${p.minutes.toLocaleString()}</td><td>${p.goals}</td><td>${p.assists}</td>
        <td>${p.xg.toFixed(1)}</td><td>${p.xa.toFixed(1)}</td>
        <td style="color:${FootIQOverview.draw.ratingColor(p.rating)}">${p.rating === null ? "–" : p.rating.toFixed(2)}</td>
        <td>${p.yellow}/${p.red}</td></tr>`).join("");
      $("tm-squad").innerHTML = `<table class="ov-table squad-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
      $("tm-squad").querySelectorAll("th[data-k]").forEach(th => th.onclick = () => {
        const k = th.dataset.k;
        sortDir = k === sortKey ? -sortDir : (k === "name" || k === "position" ? 1 : -1);
        sortKey = k;
        draw();
      });
    };
    draw();
  }

  function renderResults(results, league, season) {
    const rows = [...results].reverse().map(r => `<tr>
      <td>${esc(r.date)}</td><td>${r.home ? "H" : "A"}</td>
      <td><a href="${teamUrl(league, season, r.opp)}">${esc(r.opp)}</a></td>
      <td><b style="color:${RES_COL[r.result]}">${r.result}</b></td><td>${r.gf}–${r.ga}</td>
      <td>${r.xgf.toFixed(2)}</td><td>${r.xga === null ? "–" : r.xga.toFixed(2)}</td></tr>`).join("");
    $("tm-results").innerHTML = `<table class="ov-table lg-results"><thead><tr><th>Date</th><th>Venue</th><th>Opponent</th><th>Res</th><th>Score</th><th>xG</th><th>xGA</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }

  async function initTeam() {
    const league = q.get("league") || "Premier League", season = q.get("season") || window.SEASONS[0], team = q.get("team") || "";
    const fail = msg => { $("tm-error-msg").textContent = msg; $("tm-error").style.display = "block"; };
    if (!team) return fail("No team selected.");
    let res, data;
    try { res = await fetch(`/api/team?${new URLSearchParams({ league, season, team })}`); data = await res.json(); }
    catch { return fail("Could not load this team."); }
    if (!res.ok || data.error) return fail(data.error === "team not found" ? `No matches found for ${team} in ${season}.` : "Could not load this team.");

    const name = (window.LEAGUES.find(l => l.id === league) || {}).name || league;
    document.title = `${team} · ${season} · FootIQ`;
    $("tm-title").textContent = team;
    $("tm-eyebrow").textContent = `${name} · ${season}`;
    const r = data.record;
    $("tm-sub").innerHTML = `${data.cup ? "" : `${ordinal(data.pos)} of ${data.teams} · `}${r.points} pts from ${r.played} matches · `
      + `<a href="/league?${new URLSearchParams({ league, season })}">full table →</a>`;
    $("tm-tiles").innerHTML = [
      tile("Record", `${r.won}-${r.drawn}-${r.lost}`, "W-D-L"),
      tile("Goals", `${r.gf}:${r.ga}`, `${signed(r.gd)} difference`),
      tile("Points", r.points, `${(r.points / r.played).toFixed(2)} per match`),
      tile("xG for", r.xgf.toFixed(1), `${signed(Math.round((r.gf - r.xgf) * 10) / 10)} vs goals`),
      tile("xG against", r.xga.toFixed(1), `${signed(Math.round((r.xga - r.ga) * 10) / 10)} vs conceded`),
      tile("Form", formDots(r.form), "last 5"),
    ].join("");
    renderForm(data.results);
    renderSquad(data.squad, league, season);
    renderResults(data.results, league, season);
    $("tm-body").style.display = "block";
  }

  if ($("lg-section")) initLeague();
  else if ($("tm-body")) initTeam();
})();
