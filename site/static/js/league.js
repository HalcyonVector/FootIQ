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


  // Team quadrant plots: every team in the competition on two style measures, median lines splitting
  // the four corners. y "low" measures (pressing, xG against) are flipped so up always means more of the good thing.
  const TEAM_PLOTS = [
    { id: "poss_press", title: "Possession vs pressing", x: "possession", y: "ppda",
      q: "Who keeps the ball, who hunts it down, and who does both?",
      c: { tr: "Control and press", tl: "Press and counter", br: "Patient possession", bl: "Sit deep" } },
    { id: "xg_xga", title: "Chances created vs chances conceded", x: "xg", y: "xga",
      q: "Who creates the most and gives away the least?",
      c: { tr: "Dominant", tl: "Solid but blunt", br: "Open and dangerous", bl: "Struggling" } },
    { id: "height_press", title: "Ball-winning height vs pressing", x: "def_height", y: "ppda",
      q: "Who presses high, and who waits in a low block?",
      c: { tr: "High press", tl: "Aggressive mid-block", br: "High line, passive", bl: "Deep block" } },
    { id: "poss_direct", title: "Possession vs directness", x: "possession", y: "directness",
      q: "Who has the ball and goes forward with it fast, and who keeps it patiently?",
      c: { tr: "Dominant and direct", tl: "Direct, little ball", br: "Patient build-up", bl: "Low tempo, little ball" } },
    { id: "volume_quality", title: "Shot volume vs shot quality", x: "shots", y: "xg_per_shot",
      q: "Who shoots a lot, and who waits for good chances?",
      c: { tr: "Many good chances", tl: "Few, high quality", br: "Shoot from anywhere", bl: "Little threat" } },
    { id: "territory_threat", title: "Territory vs threat", x: "final_third", y: "xg",
      q: "Who plays in the opponent's third, and who turns it into chances?",
      c: { tr: "Camp in and create", tl: "Efficient counter", br: "Territory without threat", bl: "Pinned back" } },
    { id: "length_aerial", title: "Pass length vs aerial duels won", x: "pass_length", y: "aerial_win",
      q: "Who plays long and wins the ball in the air?",
      c: { tr: "Long ball, won in the air", tl: "Short but strong in the air", br: "Long, loses the duels", bl: "Short, weak in the air" } },
    { id: "accuracy_takeons", title: "Pass accuracy vs take-ons", x: "pass_accuracy", y: "takeons",
      q: "Who keeps it tidy, and who takes players on?",
      c: { tr: "Tidy and daring", tl: "Dribbling sides", br: "Tidy passers", bl: "Neither" } },
    { id: "regains_xg", title: "Winning the ball high vs creating chances", x: "high_regains", y: "xg",
      q: "Does winning the ball in the final third turn into chances?",
      c: { tr: "Press into chances", tl: "Create without pressing", br: "Press, little end product", bl: "Neither" } },
    { id: "tackles_interceptions", title: "Tackling vs intercepting", x: "tackles", y: "interceptions",
      q: "Does a team win the ball by going in, or by reading the pass?",
      c: { tr: "Active ball-winners", tl: "Read the game", br: "Tackle-heavy", bl: "Passive" } },
    { id: "setpiece_aerial", title: "Set-piece threat vs aerial duels won", x: "setpiece_xg", y: "aerial_win",
      q: "Who gets its chances from set pieces, and does it win in the air?",
      c: { tr: "Set-piece specialists", tl: "Strong in the air, open-play chances", br: "Set pieces without the height", bl: "Open play, on the ground" } },
    { id: "box_volume", title: "Box entries vs shots from the box", x: "box_passes", y: "box_shots",
      q: "Who gets the ball into the box, and who shoots from there?",
      c: { tr: "Live in the box", tl: "Few entries, shoot close", br: "Enter often, shoot from range", bl: "Outside shooters" } },
    { id: "release_prog", title: "Speed of passing vs progression", x: "release", y: "prog_passes",
      q: "Who moves it quickly, and who moves it forward?",
      c: { tr: "Quick and forward", tl: "Forward, takes its time", br: "Quick, sideways", bl: "Slow and safe" } },
    { id: "xgd_ppm", title: "Performance vs results", x: "xgd", y: "ppm",
      q: "Are the results in line with how well a team plays? Top left: more points than its xG difference suggests; bottom right: fewer.",
      c: { tr: "Good and winning", tl: "Winning above its level", br: "Unlucky", bl: "Struggling" } },
  ];

  // Options grouped by theme (the dropdown shows a heading per group).
  const groupedOptions = (items, val, label, group) => {
    const groups = [...new Set(items.map(group))];
    return groups.map(g => `<optgroup label="${esc(g)}">${items.filter(i => group(i) === g)
      .map(i => `<option value="${esc(val(i))}">${esc(label(i))}</option>`).join("")}</optgroup>`).join("");
  };
  const PLOT_GROUP = p => ({ poss_press: "Style", height_press: "Style", poss_direct: "Style", release_prog: "Style",
    length_aerial: "Style", accuracy_takeons: "Style", tackles_interceptions: "Defending", regains_xg: "Attack and pressing",
    xg_xga: "Output", volume_quality: "Output", territory_threat: "Output", box_volume: "Output", setpiece_aerial: "Output",
    xgd_ppm: "Results" })[p.id] || "Other";

  function drawTeamPlot(league, season) {
    if (!styleData) return;
    const plot = TEAM_PLOTS.find(p => p.id === $("lg-map").value) || TEAM_PLOTS[0];
    const mx = styleData.metrics.find(m => m.key === plot.x), my = styleData.metrics.find(m => m.key === plot.y);
    $("lg-map-desc").textContent = plot.q;
    const pts = styleData.teams.filter(t => t.values[plot.x] != null && t.values[plot.y] != null)
      .map(t => [t.values[plot.x], t.values[plot.y], t.team, "", 0, league, season, "team", t.matches]);
    FootIQCharts.render($("lg-map-chart"), {
      type: "xy", team: true, sub: `${pts.length} teams. Dashed lines are the medians. Click a team for its page.`,
      xlabel: mx.label, ylabel: my.label, xunit: mx.unit, yunit: my.unit, xinvert: mx.order === "low", yinvert: my.order === "low",
      colors: { team: "#ec4899" }, corners: plot.c, points: pts,
      note: `${mx.label}: ${mx.desc} ${my.label}: ${my.desc}`,
    });
  }

  // How every team in the competition plays, ranked on one chosen measure at a time.
  let styleData = null;
  let styleToken = 0, tableToken = 0;   // a slow answer for the previous competition must not draw over the new one
  async function loadStyles(league, season) {
    const mine = ++styleToken;
    styleData = null;
    $("lg-style").innerHTML = '<div class="ov-empty">Loading…</div>';
    try {
      const d = await (await fetch(`/api/team-styles?${new URLSearchParams({ league, season })}`)).json();
      if (mine !== styleToken) return;
      if (d.error || !d.teams) throw new Error(d.error || "no data");
      styleData = d;
    } catch {
      if (mine !== styleToken) return;
      if (typeof FootIQUI !== "undefined") FootIQUI.error($("lg-style"), "Could not load the team styles.", () => loadStyles(league, season));
      return;
    }
    const sel = $("lg-metric");
    if (!sel.options.length) sel.innerHTML = groupedOptions(styleData.metrics, m => m.key, m => m.label, m => m.group || "Other");
    sel.onchange = () => drawStyles(league, season);
    const mp = $("lg-map");
    if (mp && !mp.options.length) mp.innerHTML = groupedOptions(TEAM_PLOTS, p => p.id, p => p.title, PLOT_GROUP);
    if (mp) mp.onchange = () => drawTeamPlot(league, season);
    if (typeof upgradeSelects === "function") upgradeSelects();     // the site's own dropdown, with group headings
    drawStyles(league, season);
    if ($("lg-map-panel") && $("lg-map-panel").style.display === "block") drawTeamPlot(league, season);
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
    $("lg-map-panel").style.display = tab === "map" ? "block" : "none";
    $("lg-table-panel").style.display = tab === "table" ? "block" : "none";
    try { const u = new URL(location.href); u.searchParams.set("tab", tab); history.replaceState(null, "", u); } catch { /* non-fatal */ }
    const league = $("lg-league").value, season = $("lg-season").value;
    if ((tab === "style" || tab === "map") && !styleData) loadStyles(league, season);
    else if (tab === "map") drawTeamPlot(league, season);
  }

  // ── League table ──────────────────────────────────────────────────────────
  async function loadTable() {
    const mine = ++tableToken;
    const league = $("lg-league").value, season = $("lg-season").value;
    try {
      const tab = new URLSearchParams(location.search).get("tab");
      history.replaceState(null, "", `/league?${new URLSearchParams({ league, season, ...(tab ? { tab } : {}) })}`);
    } catch { /* non-fatal */ }
    const section = $("lg-section");
    styleData = null;
    styleToken++;                       // styles still loading for the previous competition are dropped
    if (($("lg-style-panel") && $("lg-style-panel").style.display === "block") ||
        ($("lg-map-panel") && $("lg-map-panel").style.display === "block")) loadStyles(league, season);
    let data;
    try { data = await (await fetch(`/api/league-table?${new URLSearchParams({ league, season })}`)).json(); }
    catch { return; }
    if (mine !== tableToken) return;
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
    showTab(["style", "map", "table"].includes(q.get("tab")) ? q.get("tab") : "style");   // opens on How they play
  }

  // ── Team page ─────────────────────────────────────────────────────────────
  function tile(label, value, sub) {
    return `<div class="ov-tile"><div class="ov-tile-val">${value}</div><div class="ov-tile-lbl">${label}</div>${sub ? `<div class="ov-tile-sub">${sub}</div>` : ""}</div>`;
  }

  function renderForm(results) {
    const narrow = ($("tm-form").clientWidth || window.innerWidth) < 480;     // phone: half-width canvas, readable text
    const W = narrow ? 380 : 760, H = narrow ? 170 : 150, padB = 24, mid = (H - padB) / 2, slot = W / results.length;
    const letters = slot >= 16;                  // H/A under each bar only when there is room (the tooltip has it too)
    const bw = Math.min(slot * 0.68, 22);
    const maxGd = Math.max(3, ...results.map(r => Math.abs(r.gf - r.ga)));
    let g = `<line x1="0" x2="${W}" y1="${mid}" y2="${mid}" class="ov-grid"/>`;
    results.forEach((r, i) => {
      const cx = slot * i + slot / 2, gd = r.gf - r.ga;
      const h = Math.max(3, (Math.abs(gd) / maxGd) * (mid - 6));
      const y = gd >= 0 ? mid - h : mid;
      const tip = `${r.date} · ${r.home ? "H" : "A"} vs ${r.opp} ${r.gf}–${r.ga}${r.xga === null ? "" : ` · xG ${r.xgf.toFixed(1)}–${r.xga.toFixed(1)}`}`;
      g += `<rect x="${cx - bw / 2}" y="${y}" width="${bw}" height="${h}" rx="3" fill="${RES_COL[r.result]}" class="ov-bar"><title>${esc(tip)}</title></rect>`;
      if (letters) g += `<text x="${cx}" y="${H - 8}" text-anchor="middle" class="ov-axis">${r.home ? "H" : "A"}</text>`;
    });
    $("tm-form").innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="ov-svg${narrow ? " ov-narrow" : ""}" role="img" aria-label="Goal difference by match">${g}</svg>`;
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
    const shown = d.metrics.filter(m => me.values[m.key] !== null && me.values[m.key] !== undefined);
    const tile = m => {
      const rank = me.ranks[m.key], share = n > 1 ? (n - rank) / (n - 1) : 1;
      return `<div class="tm-style-tile" title="${esc(m.desc)}">
        <div class="tm-style-label">${esc(m.label)}</div>
        <div class="tm-style-val">${fmtStyle(m, me.values[m.key])}</div>
        <div class="tm-style-bar"><i style="width:${(8 + 92 * share).toFixed(1)}%"></i></div>
        <div class="tm-style-rank">${rankWord(m, rank, n)}</div>
        <a class="tm-style-more" href="/league?${new URLSearchParams({ league, season, tab: "style" })}">compare →</a>
      </div>`;
    };
    const groups = [...new Set(shown.map(m => m.group || "Other"))];
    $("tm-style").innerHTML = groups.map(g => `<div class="tm-style-group"><div class="tm-style-group-title">${esc(g)}</div>
      <div class="tm-style-grid">${shown.filter(m => (m.group || "Other") === g).map(tile).join("")}</div></div>`).join("");
    $("tm-style-card").style.display = "block";
    renderAttack(me, d.teams);
  }

  // ── Full pitch (attacking left to right; Opta y=100 is the attacking team's left, drawn at the top) ──
  const PW = 1050, PH = 680;
  const px = x => (x / 100) * PW, py = y => ((100 - y) / 100) * PH;
  function pitchSVG(inner, extraClass = "") {
    const box = (x0, w, h) => `<rect x="${x0}" y="${(PH - h) / 2}" width="${w}" height="${h}" class="tm-pl"/>`;
    return `<svg viewBox="-12 -12 ${PW + 24} ${PH + 24}" class="ov-svg tm-pitch ${extraClass}">
      <rect x="0" y="0" width="${PW}" height="${PH}" class="tm-pitch-bg"/>
      <rect x="0" y="0" width="${PW}" height="${PH}" class="tm-pl"/><line x1="${PW / 2}" x2="${PW / 2}" y1="0" y2="${PH}" class="tm-pl"/>
      <circle cx="${PW / 2}" cy="${PH / 2}" r="91.5" class="tm-pl"/>
      ${box(0, 165, 403)}${box(PW - 165, 165, 403)}${box(0, 55, 183)}${box(PW - 55, 55, 183)}
      ${inner}</svg>`;
  }

  function renderAttack(me, all) {
    const a = me.attack;
    if (!a) return;
    const avg = k => { const v = all.map(t => t.attack && t.attack[k]).filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
    const lane = (y0, y1, share, label, key) => {
      const op = 0.12 + 0.6 * (share / 100);
      const diff = avg(key) == null ? "" : ` (league ${avg(key).toFixed(0)}%)`;
      return `<rect x="${px(66.7)}" y="${py(y1)}" width="${px(100) - px(66.7)}" height="${py(y0) - py(y1)}" fill="#ec4899" fill-opacity="${op.toFixed(2)}"/>
        <text x="${px(83.3)}" y="${(py(y0) + py(y1)) / 2 + 4}" class="tm-lane-t" text-anchor="middle">${share.toFixed(0)}%</text>
        <text x="${px(83.3)}" y="${(py(y0) + py(y1)) / 2 + 40}" class="tm-lane-s" text-anchor="middle">${esc(label + diff)}</text>`;
    };
    const arrow = `<line x1="${px(20)}" x2="${px(55)}" y1="${PH / 2}" y2="${PH / 2}" class="tm-arrow" marker-end="url(#tm-arr)"/>
      <defs><marker id="tm-arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#94a3b8"/></marker></defs>`;
    $("tm-attack").innerHTML = pitchSVG(lane(66.7, 100, a.left, "left", "left") + lane(33.3, 66.7, a.centre, "centre", "centre") +
      lane(0, 33.3, a.right, "right", "right") + `<line x1="${px(66.7)}" x2="${px(66.7)}" y1="0" y2="${PH}" class="tm-pl tm-pl-strong"/>` + arrow);
    $("tm-attack-note").textContent = `${a.entries_per_match} completed passes into the final third and ${a.box_per_match} into the box per match. Left and right are from the team's point of view, attacking to the right.`;
    $("tm-attack-card").style.display = "block";
  }

  function renderHomeAway(results) {
    if (!results || !results.length) return;
    const split = home => {
      const r = results.filter(m => !!m.home === home), n = r.length;
      if (!n) return null;
      const pts = r.reduce((s, m) => s + (m.result === "W" ? 3 : m.result === "D" ? 1 : 0), 0);
      const xg = r.reduce((s, m) => s + (m.xgf || 0), 0), xga = r.reduce((s, m) => s + (m.xga || 0), 0);
      const w = r.filter(m => m.result === "W").length, d = r.filter(m => m.result === "D").length;
      return { n, ppg: pts / n, rec: `${w}-${d}-${n - w - d}`, gf: r.reduce((s, m) => s + m.gf, 0), ga: r.reduce((s, m) => s + m.ga, 0),
               xg: xg / n, xga: xga / n };
    };
    const h = split(true), a = split(false);
    if (!h || !a) return;
    const row = (label, fh, fa, better) => {
      const hv = fh(h), av = fa(a);
      return `<tr><td>${label}</td><td class="${better(h, a) > 0 ? "tm-ha-best" : ""}">${hv}</td><td class="${better(h, a) < 0 ? "tm-ha-best" : ""}">${av}</td></tr>`;
    };
    $("tm-ha").innerHTML = `<table class="ov-table tm-ha-table"><thead><tr><th></th><th>Home</th><th>Away</th></tr></thead><tbody>
      ${row("Matches", s => s.n, s => s.n, () => 0)}
      ${row("Record (W-D-L)", s => s.rec, s => s.rec, () => 0)}
      ${row("Points per match", s => s.ppg.toFixed(2), s => s.ppg.toFixed(2), (x, y) => x.ppg - y.ppg)}
      ${row("Goals", s => `${s.gf}:${s.ga}`, s => `${s.gf}:${s.ga}`, (x, y) => (x.gf - x.ga) / x.n - (y.gf - y.ga) / y.n)}
      ${row("xG per match", s => s.xg.toFixed(2), s => s.xg.toFixed(2), (x, y) => x.xg - y.xg)}
      ${row("xG against per match", s => s.xga.toFixed(2), s => s.xga.toFixed(2), (x, y) => y.xga - x.xga)}
      </tbody></table>`;
    $("tm-ha-card").style.display = "block";
  }

  async function renderNetwork(league, season, team) {
    let d;
    try { d = await (await fetch(`/api/team-network?${new URLSearchParams({ league, season, team })}`)).json(); } catch { return; }
    if (!d || !d.nodes || d.nodes.length < 3) return;
    const maxN = Math.max(1, ...d.edges.map(e => e.n)), maxP = Math.max(1, ...d.nodes.map(n => n.passes || 0));
    const byId = Object.fromEntries(d.nodes.map(n => [n.id, n]));
    const last = name => { const parts = String(name).split(" "); return parts.length > 1 ? parts.slice(1).join(" ") : name; };
    const edges = d.edges.filter(e => e.n >= maxN * 0.18).slice(0, 30).map(e => {
      const a = byId[e.a], b = byId[e.b], f = e.n / maxN;
      return `<line x1="${px(a.x).toFixed(1)}" y1="${py(a.y).toFixed(1)}" x2="${px(b.x).toFixed(1)}" y2="${py(b.y).toFixed(1)}"
        stroke="#ec4899" stroke-opacity="${(0.2 + 0.65 * f).toFixed(2)}" stroke-width="${(1.5 + 11 * f).toFixed(1)}" stroke-linecap="round">
        <title>${esc(`${a.name} and ${b.name}: ${e.n} passes`)}</title></line>`;
    }).join("");
    const nodes = d.nodes.map(n => {
      const r = 14 + 16 * Math.sqrt((n.passes || 0) / maxP);
      return `<g><circle cx="${px(n.x).toFixed(1)}" cy="${py(n.y).toFixed(1)}" r="${r.toFixed(1)}" class="tm-node">
          <title>${esc(`${n.name} (${n.position || ""}), ${n.minutes} minutes, ${n.passes} passes with these teammates`)}</title></circle>
        <text x="${px(n.x).toFixed(1)}" y="${(py(n.y) + r + 24).toFixed(1)}" class="tm-node-t" text-anchor="middle">${esc(last(n.name))}</text></g>`;
    }).join("");
    $("tm-net").innerHTML = pitchSVG(edges + nodes);
    $("tm-net-card").style.display = "block";
  }

  async function renderTeamShots(league, season, team) {
    let d;
    try { d = await (await fetch(`/api/team-shots?${new URLSearchParams({ league, season, team })}`)).json(); } catch { return; }
    const shots = (d && d.shots) || [];
    if (!shots.length || typeof FootIQOverview === "undefined") return;
    $("tm-shots").innerHTML = FootIQOverview.draw.shotMap(shots, "all", 0.75);
    const n = shots.length, xg = shots.reduce((s, x) => s + (x.xg || 0), 0), g = shots.filter(x => x.outcome === "goal").length;
    const box = shots.filter(x => x.x >= 83 && x.y >= 21 && x.y <= 79).length;
    $("tm-shot-sum").innerHTML = `<b>${n}</b> shots · <b>${g}</b> goals · <b>${xg.toFixed(1)}</b> xG · <b>${(xg / n).toFixed(2)}</b> xG/shot · <b>${Math.round(100 * box / n)}%</b> from inside the box`;
    $("tm-shots-card").style.display = "block";
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
    renderHomeAway(data.results);
    renderNetwork(league, season, team);
    renderTeamShots(league, season, team);
    renderSquad(data.squad, league, season);
    renderResults(data.results, league, season);
    $("tm-body").style.display = "block";
  }

  if ($("lg-section")) initLeague();
  else if ($("tm-body")) initTeam();
})();
