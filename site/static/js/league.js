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
  const fmtStyle = (m, v) => v === null || v === undefined ? "–" : `${Number(v).toFixed(m.decimals)}${m.unit === "%" ? "%" : m.unit === "m" ? " m" : ""}`;
  const rankWord = (m, rank, n) => `${ordinal(rank)} of ${n}${rank === 1 ? (m.order === "low" ? " (lowest)" : " (highest)") : ""}`;

  // How every team in the competition plays, ranked on one chosen measure at a time.
  let styleData = null;
  async function loadStyles(league, season) {
    styleData = null;
    $("lg-style").innerHTML = '<div class="ov-empty">Loading…</div>';
    try {
      const d = await (await fetch(`/api/team-styles?${new URLSearchParams({ league, season })}`)).json();
      if (d.error || !d.teams) throw new Error(d.error || "no data");
      styleData = d;
    } catch {
      if (typeof FootIQUI !== "undefined") FootIQUI.error($("lg-style"), "Could not load the team styles.", () => loadStyles(league, season));
      return;
    }
    const sel = $("lg-metric");
    if (!sel.options.length) {
      sel.innerHTML = styleData.metrics.map(m => `<option value="${m.key}">${esc(m.label)}</option>`).join("");
      sel.onchange = () => drawStyles(league, season);
    }
    drawStyles(league, season);
  }

  function drawStyles(league, season) {
    if (!styleData) return;
    const m = styleData.metrics.find(x => x.key === $("lg-metric").value) || styleData.metrics[0];
    $("lg-metric-desc").textContent = m.desc;
    const rows = styleData.teams.filter(t => t.values[m.key] !== null && t.values[m.key] !== undefined)
      .sort((a, b) => a.ranks[m.key] - b.ranks[m.key]);
    if (!rows.length) { $("lg-style").innerHTML = '<div class="ov-empty">No data for this measure.</div>'; return; }
    const vals = rows.map(r => r.values[m.key]), lo = Math.min(...vals), hi = Math.max(...vals);
    const width = v => hi === lo ? 100 : 8 + 92 * (m.order === "low" ? (hi - v) / (hi - lo) : (v - lo) / (hi - lo));
    $("lg-style").innerHTML = `<div class="lg-style-list">${rows.map(r => `
      <div class="lg-style-row">
        <span class="lg-style-rank">${r.ranks[m.key]}</span>
        <a class="lg-style-team" href="${teamUrl(league, season, r.team)}">${esc(r.team)}</a>
        <span class="lg-style-bar"><i style="width:${width(r.values[m.key]).toFixed(1)}%"></i></span>
        <span class="lg-style-val">${fmtStyle(m, r.values[m.key])}</span>
      </div>`).join("")}</div>`;
  }

  function showTab(tab) {
    document.querySelectorAll(".lg-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
    $("lg-style-panel").style.display = tab === "style" ? "block" : "none";
    $("lg-table-panel").style.display = tab === "style" ? "none" : "block";
    try { const u = new URL(location.href); u.searchParams.set("tab", tab); history.replaceState(null, "", u); } catch { /* non-fatal */ }
    if (tab === "style" && !styleData) loadStyles($("lg-league").value, $("lg-season").value);
  }

  // ── League table ──────────────────────────────────────────────────────────
  async function loadTable() {
    const league = $("lg-league").value, season = $("lg-season").value;
    try {
      const tab = new URLSearchParams(location.search).get("tab");
      history.replaceState(null, "", `/league?${new URLSearchParams({ league, season, ...(tab ? { tab } : {}) })}`);
    } catch { /* non-fatal */ }
    const section = $("lg-section");
    styleData = null;
    if ($("lg-style-panel") && $("lg-style-panel").style.display === "block") loadStyles(league, season);
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
    document.querySelectorAll(".lg-tab").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
    if (typeof upgradeSelects === "function") upgradeSelects();
    loadTable();
    if (q.get("tab") === "style") showTab("style");
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

  async function renderTeamStyle(league, season, team) {
    let d;
    try { d = await (await fetch(`/api/team-styles?${new URLSearchParams({ league, season })}`)).json(); } catch { return; }
    const me = d && d.teams && d.teams.find(t => t.team === team);
    if (!me) return;
    const n = d.teams.length;
    $("tm-style-sub").textContent = `ranked among the ${n} teams in this competition`;
    $("tm-style").innerHTML = d.metrics.filter(m => me.values[m.key] !== null && me.values[m.key] !== undefined).map(m => {
      const rank = me.ranks[m.key], share = n > 1 ? (n - rank) / (n - 1) : 1;
      return `<div class="tm-style-tile" title="${esc(m.desc)}">
        <div class="tm-style-label">${esc(m.label)}</div>
        <div class="tm-style-val">${fmtStyle(m, me.values[m.key])}</div>
        <div class="tm-style-bar"><i style="width:${(8 + 92 * share).toFixed(1)}%"></i></div>
        <div class="tm-style-rank">${rankWord(m, rank, n)}</div>
        <a class="tm-style-more" href="/league?${new URLSearchParams({ league, season, tab: "style" })}">compare →</a>
      </div>`;
    }).join("");
    $("tm-style-card").style.display = "block";
  }

  async function initTeam() {
    const league = q.get("league") || "Premier League", season = q.get("season") || window.DEFAULT_SEASON || window.SEASONS[0], team = q.get("team") || "";
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
    renderTeamStyle(league, season, team);
    renderSquad(data.squad, league, season);
    renderResults(data.results, league, season);
    $("tm-body").style.display = "block";
  }

  if ($("lg-section")) initLeague();
  else if ($("tm-body")) initTeam();
})();
