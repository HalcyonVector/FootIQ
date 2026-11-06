/* ─────────────────────────────────────────────────────────────────────────────
   Player Overview: season stat line, strengths, form chart, shot map (+ goal
   placement), heatmaps and career table. Everything is drawn client-side as
   SVG from /api/player-overview JSON (no server-rendered images).

   Public API (called from app.js):
     FootIQOverview.load(player, league, season)  fetch + render
     FootIQOverview.renderInsights(insights)       strengths / weaknesses chips
     FootIQOverview.reset()
     FootIQOverview.draw.{shotMap, heat, ratingColor}   pure SVG builders, reused by Compare
   ───────────────────────────────────────────────────────────────────────────── */
const FootIQOverview = (() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, d = 0) => (v === null || v === undefined) ? "–" : Number(v).toFixed(d);

  let state = { data: null, pass: null, isGK: false, shotFilter: "all", heatMode: "touches", passMode: "chances", token: 0 };

  // ── Rating colours (same bands the big stat sites use) ──
  function ratingColor(r) {
    if (r === null || r === undefined) return "#475569";
    if (r >= 8.0) return "#22d3ee";
    if (r >= 7.0) return "#22c55e";
    if (r >= 6.0) return "#f59e0b";
    return "#ef4444";
  }

  // ── Stat tiles ────────────────────────────────────────────────────────────
  function tile(label, value, sub, accent) {
    return `<div class="ov-tile"><div class="ov-tile-val"${accent ? ` style="color:${accent}"` : ""}>${value}</div>
      <div class="ov-tile-lbl">${label}</div>${sub ? `<div class="ov-tile-sub">${sub}</div>` : ""}</div>`;
  }

  function renderTiles(line, isGK) {
    const p90 = line.per90 || {};
    const rating = line.avg_rating;
    const tiles = [
      tile("Appearances", line.apps, `${line.starts} starts`),
      tile("Minutes", line.minutes.toLocaleString()),
      tile("Avg rating", fmt(rating, 2), line.motm ? `${line.motm}× man of the match` : "", ratingColor(rating)),
    ];
    if (isGK) {
      tiles.push(
        tile("Clean sheets", line.clean_sheets),
        tile("Goals conceded", line.goals_conceded),
        tile("Saves", line.saves),
      );
    } else {
      tiles.push(
        tile("Goals", line.goals, line.pens_scored ? `${line.npg} non-pen` : (p90.goals !== undefined ? `${fmt(p90.goals, 2)} / 90` : "")),
        tile("Assists", line.assists, p90.assists !== undefined ? `${fmt(p90.assists, 2)} / 90` : ""),
        tile("xG", fmt(line.xg, 1), `${fmt(line.npxg, 1)} non-pen · ${line.goals - line.xg >= 0 ? "+" : ""}${fmt(line.goals - line.xg, 1)} vs goals`),
        tile("xA", fmt(line.xa, 1), p90.xa !== undefined ? `${fmt(p90.xa, 2)} / 90` : ""),
        tile("Shots", line.shots, `${line.sot} on target`),
        tile("Key passes", line.key_passes, p90.key_passes !== undefined ? `${fmt(p90.key_passes, 2)} / 90` : ""),
      );
    }
    tiles.push(
      tile("Pass accuracy", line.pass_pct === null ? "–" : `${fmt(line.pass_pct, 1)}%`, `${line.passes.toLocaleString()} passes`),
      tile("Tackles won", line.tackles_won, line.tackle_pct === null ? "" : `${fmt(line.tackle_pct, 0)}% success`),
      tile("Aerials won", line.aerials_won, line.aerial_pct === null ? "" : `${fmt(line.aerial_pct, 0)}% success`),
      tile("Cards", `${line.yellow}<span class="ov-tile-sep">/</span>${line.red}`, "yellow / red"),
    );
    $("ov-tiles").innerHTML = tiles.join("");
  }

  // ── Strengths / weaknesses ───────────────────────────────────────────────
  function renderInsights(insights) {
    const el = $("ov-insights");
    if (!el) return;
    if (!insights || (!insights.strengths.length && !insights.weaknesses.length)) { el.innerHTML = ""; return; }
    const chip = (s, cls) => `<span class="ov-chip ${cls}" title="${esc(s.category)} · ${fmt(s.value, 2)}${esc(s.unit)}">
      ${esc(s.label)}<b>${Math.round(s.percentile)}</b></span>`;
    el.innerHTML = `
      ${insights.strengths.length ? `<div class="ov-ins-col"><div class="ov-ins-title ov-good">Strengths</div>
        <div class="ov-chips">${insights.strengths.map(s => chip(s, "ov-chip-good")).join("")}</div></div>` : ""}
      ${insights.weaknesses.length ? `<div class="ov-ins-col"><div class="ov-ins-title ov-bad">Areas to improve</div>
        <div class="ov-chips">${insights.weaknesses.map(s => chip(s, "ov-chip-bad")).join("")}</div></div>` : ""}
      <div class="ov-ins-note">Number = percentile vs same-position players this season.</div>`;
  }

  // ── Form chart ────────────────────────────────────────────────────────────
  function renderForm(form) {
    const el = $("ov-form");
    const W = 760, H = 190, padL = 28, padB = 30, padT = 14;
    const n = form.length;
    if (!n) { el.innerHTML = '<div class="ov-empty">No matches.</div>'; return; }
    const slot = (W - padL) / n;
    const bw = Math.min(slot * 0.68, 22);
    const lo = 5, hi = 10, plotH = H - padT - padB;
    const yOf = r => padT + plotH * (1 - (Math.min(Math.max(r, lo), hi) - lo) / (hi - lo));
    const rated = form.filter(m => m.rating !== null);
    const avg = rated.length ? rated.reduce((a, m) => a + m.rating, 0) / rated.length : null;

    let g = "";
    for (const v of [6, 7, 8, 9]) {
      g += `<line x1="${padL}" x2="${W}" y1="${yOf(v)}" y2="${yOf(v)}" class="ov-grid"/>
            <text x="${padL - 6}" y="${yOf(v) + 3}" class="ov-axis" text-anchor="end">${v}</text>`;
    }
    form.forEach((m, i) => {
      const cx = padL + slot * i + slot / 2;
      const where = m.home ? "H" : "A";
      const score = m.gf === null ? "" : `${m.gf}–${m.ga}`;
      const tip = `${m.date || ""} · ${where} vs ${m.opp || "?"} ${score} ${m.result || ""}\n`
        + `Rating ${m.rating === null ? "–" : m.rating.toFixed(1)} · ${m.minutes}'${m.started ? "" : " (sub)"}`
        + `${m.goals ? ` · ${m.goals} goal${m.goals > 1 ? "s" : ""}` : ""}${m.assists ? ` · ${m.assists} assist${m.assists > 1 ? "s" : ""}` : ""}`
        + `${m.xg ? ` · ${m.xg} xG` : ""}`;
      if (m.rating !== null) {
        const y = yOf(m.rating);
        g += `<rect x="${cx - bw / 2}" y="${y}" width="${bw}" height="${padT + plotH - y}" rx="3" fill="${ratingColor(m.rating)}" class="ov-bar"><title>${esc(tip)}</title></rect>`;
        // goals = solid dot, assists = ring, above the bar
        let dotY = y - 7;
        for (let k = 0; k < Math.min(m.goals, 3); k++, dotY -= 8) g += `<circle cx="${cx}" cy="${dotY}" r="3.2" class="ov-dot-goal"/>`;
        for (let k = 0; k < Math.min(m.assists, 3); k++, dotY -= 8) g += `<circle cx="${cx}" cy="${dotY}" r="3" class="ov-dot-assist"/>`;
      } else {
        g += `<rect x="${cx - bw / 2}" y="${padT + plotH - 3}" width="${bw}" height="3" rx="1.5" fill="#475569"><title>${esc(tip)}</title></rect>`;
      }
      const rc = { W: "#22c55e", D: "#94a3b8", L: "#ef4444" }[m.result] || "transparent";
      g += `<circle cx="${cx}" cy="${H - 12}" r="${Math.min(bw / 2, 5)}" fill="${rc}"><title>${esc(tip)}</title></circle>`;
    });
    if (avg !== null) {
      g += `<line x1="${padL}" x2="${W}" y1="${yOf(avg)}" y2="${yOf(avg)}" class="ov-avg"/>
            <text x="${W}" y="${yOf(avg) - 4}" class="ov-avg-lbl" text-anchor="end">avg ${avg.toFixed(2)}</text>`;
    }
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="ov-svg" role="img" aria-label="Match rating by game">${g}</svg>
      <div class="ov-legend">
        <span><i class="ov-sw" style="background:#22d3ee"></i>8+</span><span><i class="ov-sw" style="background:#22c55e"></i>7–8</span>
        <span><i class="ov-sw" style="background:#f59e0b"></i>6–7</span><span><i class="ov-sw" style="background:#ef4444"></i>&lt;6</span>
        <span><i class="ov-dot-goal-sw"></i>Goal</span><span><i class="ov-dot-assist-sw"></i>Assist</span>
        <span class="ov-legend-note">Bottom dots: W / D / L · oldest → newest</span>
      </div>`;
  }

  // ── Pitch drawing ─────────────────────────────────────────────────────────
  // Half pitch, attacking up. 10px per metre. Opta coords: x 0-100 (own goal →
  // opponent goal), y 0-100 with y=0 on the attacker's right-hand touchline,
  // so screen X = (100 - y) puts the attacker's right on the right.
  const HP = { W: 680, H: 580, ux: 6.8, uy: 10.5, top: -20 };
  const sx = y => (100 - y) * HP.ux;
  const sy = x => (100 - x) * HP.uy;

  function halfPitchSVG(inner) {
    const L = "ov-line";
    return `<svg viewBox="0 ${HP.top} ${HP.W} ${HP.H - HP.top}" class="ov-svg ov-pitch" role="img" aria-label="Shot map">
      <rect x="0" y="${HP.top}" width="${HP.W}" height="${HP.H - HP.top}" class="ov-grass"/>
      <rect x="1" y="0" width="${HP.W - 2}" height="${HP.H - 1}" class="${L}" fill="none"/>
      <rect x="138.4" y="0" width="403.2" height="165" class="${L}" fill="none"/>
      <rect x="248.4" y="0" width="183.2" height="55" class="${L}" fill="none"/>
      <rect x="303.4" y="-14" width="73.2" height="14" class="${L}" fill="none"/>
      <circle cx="340" cy="110" r="2.5" class="ov-spot"/>
      <path d="M 266.9 165 A 91.5 91.5 0 0 0 413.1 165" class="${L}" fill="none"/>
      ${inner}</svg>`;
  }

  const SHOT_COL = { goal: "#22c55e", saved: "#3b82f6", blocked: "#94a3b8", post: "#f59e0b", off_target: "#ef4444" };
  const SHOT_LBL = { goal: "Goal", saved: "Saved", blocked: "Blocked", post: "Hit post", off_target: "Off target" };
  const SIT_LBL = { open_play: "Open play", penalty: "Penalty", free_kick: "Free kick", corner: "Corner", set_piece: "Set piece" };
  const BODY_LBL = { foot: "Foot", head: "Header", other: "Other" };

  function shotPasses(s, f) {
    if (f === "goals") return s.outcome === "goal";
    if (f === "open") return s.situation === "open_play";
    if (f === "setpiece") return s.situation !== "open_play";
    return true;
  }

  // Pure builders (no DOM access) so Compare can draw the same charts per player.
  function shotMarks(shots, scale = 1) {
    let marks = "";
    // biggest chances last so small circles stay clickable on top
    [...shots].sort((a, b) => b.xg - a.xg).forEach(s => {
      const r = (5 + Math.sqrt(s.xg) * 24) * scale;
      const tip = `${s.minute}' · ${SHOT_LBL[s.outcome]} · ${s.xg.toFixed(2)} xG\n${SIT_LBL[s.situation]} · ${BODY_LBL[s.body]}${s.big_chance ? " · big chance" : ""}`;
      const col = SHOT_COL[s.outcome];
      marks += `<circle cx="${sx(s.y).toFixed(1)}" cy="${Math.min(sy(s.x), HP.H - 8).toFixed(1)}" r="${r.toFixed(1)}" fill="${col}"
                 fill-opacity="${s.outcome === "goal" ? 0.85 : 0.45}" stroke="${col}" stroke-width="${s.outcome === "goal" ? 2.5 : 1.5}" class="ov-shot"><title>${esc(tip)}</title></circle>`;
    });
    return marks;
  }

  function shotMap(shots, filter = "all", scale = 1) {
    return halfPitchSVG(shotMarks(shots.filter(s => shotPasses(s, filter)), scale));
  }

  function renderShots() {
    const { data, shotFilter } = state;
    const shots = (data.shots || []).filter(s => shotPasses(s, shotFilter));
    const host = $("ov-shots");
    if (!(data.shots || []).length) { host.innerHTML = '<div class="ov-empty">No shots recorded.</div>'; $("ov-goal").innerHTML = ""; return; }

    host.innerHTML = halfPitchSVG(shotMarks(shots));

    const n = shots.length, xg = shots.reduce((a, s) => a + s.xg, 0), g = shots.filter(s => s.outcome === "goal").length;
    $("ov-shot-sum").innerHTML = `<b>${n}</b> shots · <b>${g}</b> goals · <b>${xg.toFixed(1)}</b> xG · <b>${n ? (xg / n).toFixed(2) : "–"}</b> xG/shot`;

    // Goal-mouth placement: only shots that reached the frame.
    const placed = shots.filter(s => s.gm_y !== null && s.gm_z !== null && ["goal", "saved"].includes(s.outcome));
    const GW = 360, GH = 150, y0 = 45.2, y1 = 54.8, zMax = 36;
    let pm = "";
    placed.forEach(s => {
      // viewed from the front: attacker's left (larger y) is on screen-left
      const cx = ((y1 - Math.min(Math.max(s.gm_y, y0 - 1.5), y1 + 1.5)) / (y1 - y0)) * (GW - 40) + 20;
      const cy = (GH - 12) - (Math.min(s.gm_z, zMax + 4) / zMax) * (GH - 40);
      pm += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${(5 + Math.sqrt(s.xg) * 10).toFixed(1)}" fill="${SHOT_COL[s.outcome]}"
              fill-opacity="${s.outcome === "goal" ? 0.85 : 0.4}" stroke="${SHOT_COL[s.outcome]}"><title>${esc(`${s.minute}' · ${SHOT_LBL[s.outcome]} · ${s.xg.toFixed(2)} xG`)}</title></circle>`;
    });
    $("ov-goal").innerHTML = placed.length ? `
      <div class="ov-sub-title">Shot placement <span>(on target, keeper's view)</span></div>
      <svg viewBox="0 0 ${GW} ${GH}" class="ov-svg">
        <rect x="20" y="${GH - 12 - (GH - 40)}" width="${GW - 40}" height="${GH - 40}" class="ov-goalframe" fill="none"/>
        <line x1="0" x2="${GW}" y1="${GH - 12}" y2="${GH - 12}" class="ov-line"/>${pm}</svg>` : "";
  }

  // ── Heatmap ───────────────────────────────────────────────────────────────
  const FP = { W: 1050, H: 680 };
  const fx = x => (x / 100) * FP.W;
  const fy = y => (1 - y / 100) * FP.H;      // y=0 is the attacker's right touchline = bottom of the screen

  // Full pitch, attacking left → right. `uid` namespaces the SVG ids so several
  // pitches (Compare shows one per player) can share a page.
  function fullPitchSVG(inner, uid, defs = "", label = "Pitch") {
    const { W, H } = FP;
    return `<svg viewBox="0 0 ${W} ${H}" class="ov-svg ov-pitch" role="img" aria-label="${label}">
      <defs>${defs}<clipPath id="${uid}-clip"><rect width="${W}" height="${H}"/></clipPath></defs>
      <rect width="${W}" height="${H}" class="ov-grass"/>
      ${inner}
      <g class="ov-line" fill="none">
        <rect x="2" y="2" width="${W - 4}" height="${H - 4}"/><line x1="${W / 2}" x2="${W / 2}" y1="2" y2="${H - 2}"/>
        <circle cx="${W / 2}" cy="${H / 2}" r="91.5"/>
        <rect x="2" y="${(H - 403.2) / 2}" width="165" height="403.2"/><rect x="${W - 167}" y="${(H - 403.2) / 2}" width="165" height="403.2"/>
        <rect x="2" y="${(H - 183.2) / 2}" width="55" height="183.2"/><rect x="${W - 57}" y="${(H - 183.2) / 2}" width="55" height="183.2"/>
      </g>
      <path d="M 40 ${H - 26} H 150 M 134 ${H - 38} L 150 ${H - 26} L 134 ${H - 14}" class="ov-arrow" fill="none"/>
    </svg>`;
  }

  function heatSVG(cells, gx, gy, hue, uid = "ov-heat") {
    const { W, H } = FP, cw = W / gx, ch = H / gy;
    const max = Math.max(1, ...cells);
    let rects = "";
    for (let ix = 0; ix < gx; ix++) {
      for (let iy = 0; iy < gy; iy++) {
        const v = cells[ix * gy + iy];
        if (!v) continue;
        const a = Math.sqrt(v / max);
        // iy=0 is the attacker's right touchline = bottom of the screen
        rects += `<rect x="${(ix * cw).toFixed(1)}" y="${((gy - 1 - iy) * ch).toFixed(1)}" width="${cw + 0.5}" height="${ch + 0.5}" fill="${hue}" fill-opacity="${(a * 0.92).toFixed(3)}"/>`;
      }
    }
    return fullPitchSVG(`<g clip-path="url(#${uid}-clip)"><g filter="url(#${uid}-blur)">${rects}</g></g>`, uid,
      `<filter id="${uid}-blur" x="-5%" y="-5%" width="110%" height="110%"><feGaussianBlur stdDeviation="16"/></filter>`, "Heatmap");
  }

  // ── Pass map: chances created / progressive / into the box / incomplete ───
  const PASS_MODES = {
    chances: { label: "Chances created" },
    progressive: { pick: f => f & 2 },
    box: { pick: f => f & 4 },
    failed: { pick: f => !(f & 1) },
  };
  const PASS_COL = { ok: "#38bdf8", fail: "#f87171", goal: "#22c55e", chance: "#fbbf24" };

  function arrow(x1, y1, x2, y2, col, w, op, tip) {
    return `<line x1="${fx(x1).toFixed(1)}" y1="${fy(y1).toFixed(1)}" x2="${fx(x2).toFixed(1)}" y2="${fy(y2).toFixed(1)}"
      stroke="${col}" stroke-width="${w}" stroke-opacity="${op}" stroke-linecap="round" marker-end="url(#pm-${col.slice(1)})"><title>${esc(tip)}</title></line>`;
  }

  function passMapSVG(pm, mode) {
    let g = "";
    if (mode === "chances") {
      [...pm.chances].sort((a, b) => a.xg - b.xg).forEach(c => {
        const col = c.outcome === "goal" ? PASS_COL.goal : PASS_COL.chance;
        g += arrow(c.ax, c.ay, c.aex, c.aey, col, c.outcome === "goal" ? 4 : 2.6, 0.9,
          `${c.minute}' · led to a ${c.outcome.replace("_", " ")} · ${c.xg.toFixed(2)} xG`);
        g += `<circle cx="${fx(c.aex).toFixed(1)}" cy="${fy(c.aey).toFixed(1)}" r="${(3 + Math.sqrt(c.xg) * 9).toFixed(1)}" fill="${col}" fill-opacity=".35" stroke="${col}"/>`;
      });
    } else {
      const pick = PASS_MODES[mode].pick;
      pm.passes.filter(p => pick(p[4])).forEach(p => {
        const ok = p[4] & 1;
        g += arrow(p[0], p[1], p[2], p[3], ok ? PASS_COL.ok : PASS_COL.fail, 2, ok ? 0.55 : 0.6,
          `${ok ? "Completed" : "Incomplete"}${p[4] & 2 ? " · progressive" : ""}${p[4] & 4 ? " · into the box" : ""}`);
      });
    }
    const marker = col => `<marker id="pm-${col.slice(1)}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${col}"/></marker>`;
    return fullPitchSVG(g, "pm", Object.values(PASS_COL).map(marker).join(""), "Pass map");
  }

  function renderPassMap() {
    const host = $("ov-pass"), pm = state.pass;
    if (!host || !pm) return;
    const mode = state.passMode, sum = $("ov-pass-sum");
    if (mode === "chances") {
      const n = pm.chances.length, goals = pm.chances.filter(c => c.outcome === "goal").length;
      if (!n) { host.innerHTML = '<div class="ov-empty">No chances created recorded.</div>'; sum.innerHTML = ""; return; }
      const xa = pm.chances.reduce((a, c) => a + c.xg, 0);
      sum.innerHTML = `<b>${n}</b> chances created · <b>${goals}</b> assists · <b>${xa.toFixed(1)}</b> xA`;
    } else {
      const shown = pm.passes.filter(p => PASS_MODES[mode].pick(p[4]));
      if (!shown.length) { host.innerHTML = '<div class="ov-empty">None recorded.</div>'; sum.innerHTML = ""; return; }
      const done = shown.filter(p => p[4] & 1).length;
      sum.innerHTML = `<b>${shown.length}</b> passes · <b>${Math.round(100 * done / shown.length)}%</b> completed`;
    }
    host.innerHTML = passMapSVG(pm, mode);
  }

  function renderHeat() {
    const { data, heatMode } = state;
    const host = $("ov-heat");
    if (!data.heat) { host.innerHTML = '<div class="ov-empty">No heatmap data.</div>'; return; }
    const cells = heatMode === "touches" ? data.heat.touches : data.heat.defs;
    const total = cells.reduce((a, b) => a + b, 0);
    if (!total) { host.innerHTML = '<div class="ov-empty">No actions recorded.</div>'; return; }
    host.innerHTML = heatSVG(cells, data.grid.x, data.grid.y, heatMode === "touches" ? "#3b82f6" : "#f43f5e", "ov-heat")
      + `<div class="ov-legend"><span>${total.toLocaleString()} ${heatMode === "touches" ? "touches" : "defensive actions (tackles, interceptions, clearances, recoveries, blocks)"}</span>
         <span class="ov-legend-note">Attacking direction →</span></div>`;
  }

  // ── Career table ──────────────────────────────────────────────────────────
  function renderCareer(career) {
    const rows = career.map(c => `<tr>
      <td>${esc(c.season)}</td><td>${esc(c.league)}</td><td>${esc(c.team)}</td>
      <td>${c.apps}</td><td>${c.minutes.toLocaleString()}</td><td>${c.goals}</td><td>${c.assists}</td>
      <td>${fmt(c.xg, 1)}</td><td>${fmt(c.xa, 1)}</td>
      <td style="color:${ratingColor(c.avg_rating)}">${fmt(c.avg_rating, 2)}</td><td>${c.yellow}/${c.red}</td></tr>`).join("");
    $("ov-career").innerHTML = `<table class="ov-table"><thead><tr><th>Season</th><th>Competition</th><th>Team</th>
      <th>Apps</th><th>Mins</th><th>G</th><th>A</th><th>xG</th><th>xA</th><th>Rating</th><th>Y/R</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ── Wiring ────────────────────────────────────────────────────────────────
  function wireToggles() {
    document.querySelectorAll("#ov-shot-filters [data-f]").forEach(b => b.onclick = () => {
      state.shotFilter = b.dataset.f;
      document.querySelectorAll("#ov-shot-filters [data-f]").forEach(x => x.classList.toggle("active", x === b));
      renderShots();
    });
    document.querySelectorAll("#ov-pass-modes [data-p]").forEach(b => b.onclick = () => {
      state.passMode = b.dataset.p;
      document.querySelectorAll("#ov-pass-modes [data-p]").forEach(x => x.classList.toggle("active", x === b));
      renderPassMap();
    });
    document.querySelectorAll("#ov-heat-modes [data-m]").forEach(b => b.onclick = () => {
      state.heatMode = b.dataset.m;
      document.querySelectorAll("#ov-heat-modes [data-m]").forEach(x => x.classList.toggle("active", x === b));
      renderHeat();
    });
  }

  function reset() {
    state.token++;
    state.data = null;
    state.pass = null;
    const s = $("overview-section");
    if (s) s.style.display = "none";
  }

  async function load(player, league, season) {
    const section = $("overview-section");
    if (!section) return;
    const token = ++state.token;
    section.style.display = "none";
    $("ov-insights").innerHTML = "";   // previous player's chips; the new ones arrive with /api/advanced-stats
    let data;
    try {
      const res = await fetch("/api/player-overview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: player.id, league, season }),
      });
      data = await res.json();
    } catch { return; }
    if (token !== state.token || !data || !data.available) return;   // stale response or no data built yet

    state.data = data;
    state.isGK = /^GK/i.test(player.position || "");
    state.shotFilter = "all";
    state.heatMode = "touches";
    document.querySelectorAll("#ov-shot-filters [data-f]").forEach(x => x.classList.toggle("active", x.dataset.f === "all"));
    document.querySelectorAll("#ov-heat-modes [data-m]").forEach(x => x.classList.toggle("active", x.dataset.m === "touches"));

    $("ov-sub").textContent = `${data.season} · ${league}`;
    renderTiles(data.line, state.isGK);
    renderForm(data.form);
    $("ov-shot-card").style.display = state.isGK ? "none" : "";
    if (!state.isGK) renderShots();
    renderHeat();
    renderCareer(data.career);
    wireToggles();
    section.style.display = "block";
    loadPassMap(player, league, data.season, token);
  }

  async function loadPassMap(player, league, season, token) {
    const card = $("ov-pass-card");
    if (!card) return;
    card.style.display = "none";
    state.pass = null;
    let pm;
    try {
      const res = await fetch("/api/pass-map", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_id: player.id, league, season }),
      });
      pm = await res.json();
    } catch { return; }
    if (token !== state.token || !pm || !pm.available) return;
    state.pass = pm;
    // open on the most interesting layer this player actually has
    state.passMode = pm.chances.length ? "chances" : "progressive";
    document.querySelectorAll("#ov-pass-modes [data-p]").forEach(x => x.classList.toggle("active", x.dataset.p === state.passMode));
    renderPassMap();
    card.style.display = "";
  }

  return { load, reset, renderInsights, draw: { shotMap, heat: heatSVG, ratingColor } };
})();
