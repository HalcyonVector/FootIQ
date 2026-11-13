/* ─────────────────────────────────────────────────────────────────────────────
   FootIQCharts — one SVG renderer for every chart on the Advanced Metrics tabs,
   Combination Play and Compare. The server (visuals/specs.py) sends small JSON
   specs; this file draws them in a single consistent, theme-aware style.

     FootIQCharts.render(hostElement, spec)

   Spec types: pitch, bars, hist, trend, rose, bloom, scatter, radar, grouped
   (shapes are documented at the top of visuals/specs.py).
   Pitch legends are clickable (toggle a layer), hovering a layer dims the rest,
   and every mark carries a tooltip.
   ───────────────────────────────────────────────────────────────────────────── */
const FootIQCharts = (() => {
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const r1 = v => Math.round(v * 10) / 10;
  const r2 = v => Math.round(v * 100) / 100;
  let seq = 0;

  // Same red → orange → yellow → green → blue ramp as app.js's percentileColor().
  const PCT = [[0, [239, 68, 68]], [25, [249, 115, 22]], [50, [234, 179, 8]], [75, [34, 197, 94]], [100, [59, 130, 246]]];
  function pctColor(p) {
    p = Math.max(0, Math.min(100, p));
    for (let i = 0; i < PCT.length - 1; i++) {
      const [t0, c0] = PCT[i], [t1, c1] = PCT[i + 1];
      if (p >= t0 && p <= t1) {
        const a = (p - t0) / (t1 - t0);
        return "#" + [0, 1, 2].map(k => Math.round(c0[k] + a * (c1[k] - c0[k])).toString(16).padStart(2, "0")).join("");
      }
    }
    return "#3b82f6";
  }

  // ── Tooltip (one shared element, driven by data-tip attributes) ───────────
  let tipEl = null;
  document.addEventListener("mousemove", e => {
    const t = e.target.closest ? e.target.closest(".fc-host [data-tip]") : null;
    if (!t) { if (tipEl) tipEl.style.display = "none"; return; }
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "fc-tip"; document.body.appendChild(tipEl); }
    tipEl.textContent = t.getAttribute("data-tip");
    tipEl.style.display = "block";
    const pad = 14, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + w > innerWidth - 8) x = e.clientX - w - pad;
    if (y + h > innerHeight - 8) y = e.clientY - h - pad;
    tipEl.style.left = x + "px";
    tipEl.style.top = y + "px";
  });

  // ── Small shared bits ─────────────────────────────────────────────────────
  const empty = msg => `<div class="fc-empty">${esc(msg)}</div>`;

  function head(spec) {
    let h = "";
    if (spec.sub) h += `<div class="fc-sub">${esc(spec.sub)}</div>`;
    if (spec.stats && spec.stats.length) {
      h += `<div class="fc-stats">${spec.stats.map(([l, v]) => `<span><b>${esc(v)}</b> ${esc(l)}</span>`).join("")}</div>`;
    }
    return h;
  }

  function niceStep(range, n) {
    const raw = range / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }
  function ticks(lo, hi, n) {
    const st = niceStep(hi - lo || 1, n), out = [];
    for (let v = Math.ceil(lo / st - 1e-9) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(10));
    return out;
  }
  const fmtNum = v => (Math.abs(v) >= 100 ? v.toFixed(0) : String(r1(v)));

  function polyPts(cx, cy, ro, ri, n, rot = -Math.PI / 2) {
    const pts = [];
    for (let i = 0; i < n * (ri ? 2 : 1); i++) {
      const r = ri ? (i % 2 ? ri : ro) : ro, a = rot + (i * Math.PI) / (ri ? n : n / 2);
      pts.push(`${r1(cx + r * Math.cos(a))},${r1(cy + r * Math.sin(a))}`);
    }
    return pts.join(" ");
  }

  // One mark. `shape` ∈ dot | ring | star | x | pent
  function mark(shape, cx, cy, r, color, extra = "") {
    switch (shape) {
      case "ring": return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${r1(Math.max(1.6, r * 0.3))}" ${extra}/>`;
      case "star": return `<polygon points="${polyPts(cx, cy, r * 1.6, r * 0.68, 5)}" fill="${color}" stroke="rgba(255,255,255,.85)" stroke-width="1" stroke-linejoin="round" ${extra}/>`;
      case "pent": return `<polygon points="${polyPts(cx, cy, r * 1.25, 0, 5)}" fill="${color}" stroke="rgba(255,255,255,.85)" stroke-width="1" ${extra}/>`;
      case "x": {
        const d = r * 0.85;
        return `<path d="M${r1(cx - d)} ${r1(cy - d)}L${r1(cx + d)} ${r1(cy + d)}M${r1(cx - d)} ${r1(cy + d)}L${r1(cx + d)} ${r1(cy - d)}" stroke="${color}" stroke-width="${r1(Math.max(2, r * 0.42))}" stroke-linecap="round" fill="none" ${extra}/>`;
      }
      default: return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" stroke="rgba(255,255,255,.75)" stroke-width="1" ${extra}/>`;
    }
  }

  function swatch(L) {
    const c = L.color;
    if (L.shape === "line" || L.shape === "dash") {
      return `<svg width="22" height="12" viewBox="0 0 22 12"><line x1="1" y1="6" x2="21" y2="6" stroke="${c}" stroke-width="2.6" stroke-linecap="round"${L.shape === "dash" ? ' stroke-dasharray="5 3.5"' : ""}/></svg>`;
    }
    return `<svg width="16" height="14" viewBox="0 0 16 14">${mark(L.shape, 8, 7, 4.4, c)}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Pitch
  // ═════════════════════════════════════════════════════════════════════════
  // Opta coordinates: x 0-100 own goal → opponent goal, y 0-100 with y=0 on the
  // attacker's right-hand touchline. Full pitch is drawn attacking left → right
  // (y=0 at the bottom); the half pitch is drawn attacking up, like the shot map
  // on the Overview tab.
  const FULL = { W: 1050, H: 680, vb: "-24 -22 1098 724", s: 1.3, X: (x, y) => x * 10.5, Y: (x, y) => (100 - y) * 6.8 };
  // Cropped to x >= 58 (nearly every shot is inside that); anything further out is pinned to the bottom edge.
  const HALF = { W: 680, H: 441, vb: "-20 -34 720 508", s: 1.05, X: (x, y) => (100 - y) * 6.8, Y: (x, y) => Math.min((100 - x) * 10.5, 433) };

  function fullMarks() {
    const { W, H } = FULL, cy = H / 2, L = "ov-line";
    const arc = Math.sqrt(91.5 * 91.5 - 49.5 * 49.5);
    return `<g class="${L}" fill="none">
      <rect x="0" y="0" width="${W}" height="${H}"/><line x1="${W / 2}" y1="0" x2="${W / 2}" y2="${H}"/>
      <circle cx="${W / 2}" cy="${cy}" r="91.5"/>
      <rect x="0" y="${cy - 201.6}" width="165" height="403.2"/><rect x="${W - 165}" y="${cy - 201.6}" width="165" height="403.2"/>
      <rect x="0" y="${cy - 91.6}" width="55" height="183.2"/><rect x="${W - 55}" y="${cy - 91.6}" width="55" height="183.2"/>
      <path d="M165 ${cy - arc} A91.5 91.5 0 0 1 165 ${cy + arc}"/><path d="M${W - 165} ${cy - arc} A91.5 91.5 0 0 0 ${W - 165} ${cy + arc}"/>
      <rect x="-12" y="${cy - 36.6}" width="12" height="73.2"/><rect x="${W}" y="${cy - 36.6}" width="12" height="73.2"/>
    </g>
    <circle cx="${W / 2}" cy="${cy}" r="3" class="ov-spot"/><circle cx="115.5" cy="${cy}" r="3" class="ov-spot"/><circle cx="${W - 115.5}" cy="${cy}" r="3" class="ov-spot"/>
    <path d="M44 ${H - 28} H150 M133 ${H - 40} L150 ${H - 28} L133 ${H - 16}" class="ov-arrow" fill="none"/>`;
  }

  function halfMarks() {
    const { W, H } = HALF, L = "ov-line";
    return `<g class="${L}" fill="none">
      <path d="M0 ${H}V0H${W}V${H}"/>
      <rect x="138.4" y="0" width="403.2" height="165"/><rect x="248.4" y="0" width="183.2" height="55"/>
      <rect x="303.4" y="-14" width="73.2" height="14"/>
      <path d="M266.9 165 A91.5 91.5 0 0 0 413.1 165"/>
    </g><circle cx="340" cy="110" r="2.5" class="ov-spot"/>`;
  }

  function guideSVG(gd, G) {
    const op = gd.opacity ?? 0.5;
    if (gd.kind === "rect") {
      const xs = [G.X(gd.x0, gd.y0), G.X(gd.x1, gd.y1)], ys = [G.Y(gd.x0, gd.y0), G.Y(gd.x1, gd.y1)];
      const attrs = gd.fill ? `fill="${gd.fill}" fill-opacity="${op}"` : `fill="none" stroke="${gd.stroke}" stroke-opacity="${op}" stroke-width="2.4"`;
      return `<rect x="${r1(Math.min(...xs))}" y="${r1(Math.min(...ys))}" width="${r1(Math.abs(xs[1] - xs[0]))}" height="${r1(Math.abs(ys[1] - ys[0]))}" ${attrs}/>`;
    }
    if (gd.kind === "vline") {
      return `<line x1="${G.X(gd.x, 0)}" y1="${G.Y(gd.x, 0)}" x2="${G.X(gd.x, 100)}" y2="${G.Y(gd.x, 100)}" stroke="${gd.stroke}" stroke-opacity="${op}" stroke-width="2.2"${gd.dash ? ' stroke-dasharray="3 9"' : ""} stroke-linecap="round"/>`;
    }
    return "";
  }

  function layerSVG(L, G, uid) {
    const pts = L.pts || [];
    const tip = `${L.label}: ${L.count}`;
    if (!pts.length) return `<g data-layer="${esc(L.id)}"></g>`;
    const s = G.s;
    let inner = "";

    if (L.shape === "line" || L.shape === "dash") {
      const w = r1((L.width || 2.4) * s), op = L.opacity ?? 0.8;
      const dash = L.shape === "dash" ? ` stroke-dasharray="${r1(9 * s)} ${r1(6 * s)}"` : "";
      if (pts.length <= 300) {
        const mid = `fcm${uid}-${L.id}`;
        inner += `<defs><marker id="${mid}" viewBox="0 0 10 10" refX="7.5" refY="5" markerWidth="${r1(3.6 + (L.width || 2.4) * 0.15)}" markerHeight="${r1(3.6 + (L.width || 2.4) * 0.15)}" orient="auto"><path d="M0 0L10 5L0 10z" fill="${L.color}"/></marker></defs>`;
        inner += `<g stroke="${L.color}" stroke-width="${w}" stroke-opacity="${op}" stroke-linecap="round"${dash}>` +
          pts.map(p => `<line x1="${r1(G.X(p[0], p[1]))}" y1="${r1(G.Y(p[0], p[1]))}" x2="${r1(G.X(p[2], p[3]))}" y2="${r1(G.Y(p[2], p[3]))}" marker-end="url(#${mid})"/>`).join("") + `</g>`;
      } else {
        // dense layers: one path for every line + one for the origin dots (keeps the DOM small)
        const d = pts.map(p => `M${r1(G.X(p[0], p[1]))} ${r1(G.Y(p[0], p[1]))}L${r1(G.X(p[2], p[3]))} ${r1(G.Y(p[2], p[3]))}`).join("");
        const o = pts.map(p => `M${r1(G.X(p[0], p[1]))} ${r1(G.Y(p[0], p[1]))}h0`).join("");
        inner += `<path d="${d}" fill="none" stroke="${L.color}" stroke-width="${w}" stroke-opacity="${op}" stroke-linecap="round"${dash}/>` +
          `<path d="${o}" fill="none" stroke="${L.color}" stroke-opacity="${r2(Math.min(1, op + 0.1))}" stroke-width="${r1(w * 2.2)}" stroke-linecap="round"/>`;
      }
    } else {
      const r = r1((L.r || 7) * s), op = L.opacity ?? 0.92;
      inner += `<g opacity="${op}">` + pts.map(p => mark(L.shape, r1(G.X(p[0], p[1])), r1(G.Y(p[0], p[1])), r, L.color)).join("") + `</g>`;
    }
    return `<g class="fc-layer" data-layer="${esc(L.id)}" data-tip="${esc(tip)}">${inner}</g>`;
  }

  function pitchChart(host, spec) {
    const uid = ++seq, G = spec.view === "half" ? HALF : FULL;
    const layers = (spec.layers || []).slice();
    const drawn = layers.map((L, i) => ({ L, z: L.z ?? i })).sort((a, b) => a.z - b.z).map(o => o.L);
    const svg = `<svg viewBox="${G.vb}" class="ov-svg ov-pitch fc-pitch" role="img" aria-label="Pitch chart">
      <rect x="${G.vb.split(" ")[0]}" y="${G.vb.split(" ")[1]}" width="${G.vb.split(" ")[2]}" height="${G.vb.split(" ")[3]}" class="ov-grass"/>
      ${G === FULL ? fullMarks() : halfMarks()}
      ${(spec.guides || []).map(g => guideSVG(g, G)).join("")}
      ${drawn.map(L => layerSVG(L, G, uid)).join("")}
    </svg>`;
    const legend = `<div class="fc-legend">${layers.map(L =>
      `<button type="button" class="fc-leg${L.count ? "" : " zero"}" data-layer="${esc(L.id)}" title="Click to show/hide">${swatch(L)}<span>${esc(L.label)}</span><b>${L.count}</b></button>`).join("")}</div>`;
    host.innerHTML = head(spec) + svg + legend;
    host.querySelectorAll(".fc-leg").forEach(b => b.addEventListener("click", () => {
      const off = b.classList.toggle("off");
      host.querySelectorAll("g[data-layer]").forEach(g => { if (g.dataset.layer === b.dataset.layer) g.style.display = off ? "none" : ""; });
    }));
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Bars (HTML — crisp text at any width)
  // ═════════════════════════════════════════════════════════════════════════
  function barsChart(host, spec) {
    if (!spec.items || !spec.items.length) { host.innerHTML = empty("No data"); return; }
    host.innerHTML = head(spec) + `<div class="fc-bars">${spec.items.map(it => `
      <div class="fc-bar-row"><span class="fc-bar-lbl" title="${esc(it.label)}">${esc(it.label)}</span>
        <span class="fc-bar-track"><i style="background:${it.color}" data-w="${it.value}"></i></span>
        <span class="fc-bar-val">${esc(it.text)}</span></div>`).join("")}</div>`;
    requestAnimationFrame(() => requestAnimationFrame(() =>
      host.querySelectorAll(".fc-bar-track i").forEach(i => { i.style.width = i.dataset.w + "%"; })));
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Histogram
  // ═════════════════════════════════════════════════════════════════════════
  function histChart(host, spec) {
    if (!spec.counts || !spec.counts.length) { host.innerHTML = head(spec) + empty("No data"); return; }
    const W = 520, H = 290, L = 42, R = 14, T = 24, B = 46;
    const e = spec.edges, mk = spec.marker;
    let lo = e[0], hi = e[e.length - 1];
    if (mk) { lo = Math.min(lo, mk.value); hi = Math.max(hi, mk.value); }
    const span = hi - lo || 1; lo -= span * 0.02; hi += span * 0.02;
    const x = v => L + ((v - lo) / (hi - lo)) * (W - L - R);
    const yMaxT = ticks(0, Math.max(...spec.counts), 4), yMax = yMaxT[yMaxT.length - 1] || 1;
    const y = c => T + (1 - c / Math.max(yMax, Math.max(...spec.counts))) * (H - T - B);
    const unit = spec.unit || "";
    let g = "";
    yMaxT.forEach(v => { g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="fc-grid"/><text x="${L - 7}" y="${y(v) + 4}" class="fc-t" text-anchor="end">${v}</text>`; });
    ticks(lo, hi, 6).forEach(v => { g += `<text x="${x(v)}" y="${H - B + 17}" class="fc-t" text-anchor="middle">${fmtNum(v)}</text>`; });
    spec.counts.forEach((c, i) => {
      if (!c) return;
      const x0 = x(e[i]) + 1, x1 = x(e[i + 1]) - 1;
      g += `<rect x="${r1(x0)}" y="${r1(y(c))}" width="${r1(Math.max(1, x1 - x0))}" height="${r1(H - B - y(c))}" rx="3" fill="${spec.color}" fill-opacity=".85" class="fc-hbar" data-tip="${esc(`${fmtNum(e[i])}–${fmtNum(e[i + 1])}${unit}\n${c} ${c === 1 ? "event" : "events"}`)}"/>`;
    });
    g += `<line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" class="fc-axisline"/>`;
    const lbl = (v, text, row, cls) => {
      const right = x(v) > W - 150;
      return `<text x="${r1(x(v) + (right ? -6 : 6))}" y="${T + 4 + row * 15}" class="fc-t ${cls}" text-anchor="${right ? "end" : "start"}">${esc(text)}</text>`;
    };
    if (spec.median !== undefined) g += `<line x1="${x(spec.median)}" x2="${x(spec.median)}" y1="${T - 6}" y2="${H - B}" class="fc-median"/>` + lbl(spec.median, `median ${fmtNum(spec.median)}${unit}`, 0, "fc-t-strong");
    if (mk) g += `<line x1="${x(mk.value)}" x2="${x(mk.value)}" y1="${T - 6}" y2="${H - B}" class="fc-marker"/>` + lbl(mk.value, mk.label, 1, "fc-t-accent");
    const axisName = unit === "s" ? "seconds" : unit === "m" ? "metres" : "";
    if (axisName) g += `<text x="${(L + W - R) / 2}" y="${H - 6}" class="fc-t" text-anchor="middle">${axisName}</text>`;
    g += `<text transform="translate(12 ${(T + H - B) / 2}) rotate(-90)" class="fc-t" text-anchor="middle">Count</text>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg" role="img" aria-label="Distribution">${g}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Season trend (percentile by season)
  // ═════════════════════════════════════════════════════════════════════════
  function trendChart(host, spec) {
    const vals = spec.values || [], have = vals.filter(v => v !== null && v !== undefined);
    if (have.length < 2) { host.innerHTML = empty("Not enough season history yet"); return; }
    const W = 520, H = 290, L = 42, R = 22, T = 26, B = 44, n = vals.length;
    const x = i => L + (n === 1 ? 0.5 : i / (n - 1)) * (W - L - R);
    const y = v => T + (1 - v / 100) * (H - T - B);
    let g = "";
    [0, 25, 50, 75, 100].forEach(v => { g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="fc-grid"${v === 50 ? ' style="stroke-dasharray:4 4"' : ""}/><text x="${L - 7}" y="${y(v) + 4}" class="fc-t" text-anchor="end">${v}</text>`; });
    let seg = [];
    const flush = () => { if (seg.length >= 2) g += `<polyline points="${seg.join(" ")}" fill="none" class="fc-trendline"/>`; seg = []; };
    vals.forEach((v, i) => { if (v === null || v === undefined) flush(); else seg.push(`${r1(x(i))},${r1(y(v))}`); });
    flush();
    vals.forEach((v, i) => {
      g += `<text x="${x(i)}" y="${H - B + 18}" class="fc-t" text-anchor="middle">${esc(spec.seasons[i])}</text>`;
      if (v === null || v === undefined) return;
      g += `<circle cx="${r1(x(i))}" cy="${r1(y(v))}" r="7.5" fill="${pctColor(v)}" stroke="var(--bg)" stroke-width="2" data-tip="${esc(`${spec.seasons[i]}\n${Math.round(v)}th percentile`)}"/>
            <text x="${r1(x(i))}" y="${r1(y(v) - 13)}" class="fc-t fc-t-strong" text-anchor="middle">${Math.round(v)}</text>`;
    });
    g += `<text transform="translate(12 ${(T + H - B) / 2}) rotate(-90)" class="fc-t" text-anchor="middle">Percentile vs. cohort</text>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg" role="img" aria-label="Season trend">${g}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Compass rose (carry direction)
  // ═════════════════════════════════════════════════════════════════════════
  function roseChart(host, spec) {
    const S = 400, c = S / 2, R = 138;
    const P = (r, a) => [r1(c + r * Math.cos(a)), r1(c - r * Math.sin(a))];
    let g = [0.34, 0.67, 1].map(f => `<circle cx="${c}" cy="${c}" r="${r1(R * f)}" class="fc-grid" fill="none"/>`).join("");
    g += `<line x1="${c - R}" x2="${c + R}" y1="${c}" y2="${c}" class="fc-grid"/><line x1="${c}" x2="${c}" y1="${c - R}" y2="${c + R}" class="fc-grid"/>`;
    if (spec.angle !== null && spec.angle !== undefined) {
      const a0 = spec.angle - spec.spread, a1 = spec.angle + spec.spread, p0 = P(R, a0), p1 = P(R, a1), tip = P(R * 0.96, spec.angle);
      g += `<defs><marker id="rose-arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M0 0L10 5L0 10z" fill="#22c55e"/></marker></defs>
        <path d="M${c} ${c}L${p0[0]} ${p0[1]}A${R} ${R} 0 0 0 ${p1[0]} ${p1[1]}Z" fill="#22c55e" fill-opacity=".28" stroke="#22c55e" stroke-opacity=".6" stroke-width="1.5" data-tip="Typical carry direction (±1 SD)"/>
        <line x1="${c}" y1="${c}" x2="${tip[0]}" y2="${tip[1]}" stroke="#22c55e" stroke-width="4" stroke-linecap="round" marker-end="url(#rose-arrow)"/>`;
    }
    g += `<text x="${c + R + 12}" y="${c + 5}" class="fc-t fc-t-lg">Forward</text>
      <text x="${c}" y="${c - R - 12}" class="fc-t fc-t-lg" text-anchor="middle">Infield</text>
      <text x="${c - R - 12}" y="${c + 5}" class="fc-t fc-t-lg" text-anchor="end">Back</text>
      <text x="${c}" y="${c + R + 24}" class="fc-t fc-t-lg" text-anchor="middle">Outfield</text>`;
    host.innerHTML = head(spec) + `<svg viewBox="-26 4 452 ${S - 4}" class="ov-svg fc-svg fc-round" role="img" aria-label="Carry angle rose">${g}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Bloom (radial percentile bars)
  // ═════════════════════════════════════════════════════════════════════════
  function bloomChart(host, spec) {
    const items = spec.items || [];
    if (!items.length) { host.innerHTML = empty("No data"); return; }
    const W = 560, H = 470, cx = W / 2, cy = H / 2, r0 = 44, r1_ = 140, n = items.length, slice = (2 * Math.PI) / n;
    const P = (r, a) => [r1(cx + r * Math.sin(a)), r1(cy - r * Math.cos(a))];
    let g = [0.25, 0.5, 0.75, 1].map(f => `<circle cx="${cx}" cy="${cy}" r="${r1(r0 + (r1_ - r0) * f)}" class="fc-grid" fill="none"/>`).join("");
    items.forEach((it, i) => {
      const mid = i * slice, a0 = mid - slice * 0.39, a1 = mid + slice * 0.39, ro = r0 + (it.value / 100) * (r1_ - r0);
      const o0 = P(ro, a0), o1 = P(ro, a1), i0 = P(r0, a0), i1 = P(r0, a1);
      g += `<path d="M${o0[0]} ${o0[1]}A${r1(ro)} ${r1(ro)} 0 0 1 ${o1[0]} ${o1[1]}L${i1[0]} ${i1[1]}A${r0} ${r0} 0 0 0 ${i0[0]} ${i0[1]}Z" fill="${it.color}" fill-opacity=".92" stroke="var(--bg)" stroke-width="2" data-tip="${esc(`${it.label}\n${Math.round(it.value)}th percentile`)}"/>`;
      if (it.value >= 12) {   // too-short bars would put their number on top of the centre score
        const vp = P(Math.max(ro - 13, r0 + 12), mid);
        g += `<text x="${vp[0]}" y="${vp[1] + 4}" class="fc-bloom-v" text-anchor="middle">${Math.round(it.value)}</text>`;
      }
      const lp = P(r1_ + 18, mid), s = Math.sin(mid);
      const anchor = s > 0.3 ? "start" : s < -0.3 ? "end" : "middle";
      const words = it.label.toUpperCase().split(" "); let l1 = words[0], l2 = "";
      for (const w of words.slice(1)) { if ((l1 + " " + w).length <= 14 && !l2) l1 += " " + w; else l2 += (l2 ? " " : "") + w; }
      g += `<text x="${lp[0]}" y="${lp[1] + (l2 ? -2 : 4)}" class="fc-t fc-t-cap" text-anchor="${anchor}">${esc(l1)}${l2 ? `<tspan x="${lp[0]}" dy="12">${esc(l2)}</tspan>` : ""}</text>`;
    });
    g += `<text x="${cx}" y="${cy + 6}" class="fc-bloom-c" text-anchor="middle">${spec.center}</text>
          <text x="${cx}" y="${cy + 24}" class="fc-t fc-t-cap" text-anchor="middle">${esc(spec.center_label || "")}</text>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg fc-round" role="img" aria-label="Percentile bloom">${g}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Scatter (cohort cloud with the target highlighted)
  // ═════════════════════════════════════════════════════════════════════════
  function scatterChart(host, spec) {
    const W = 520, H = 470, L = 46, R = 14, T = 14, B = 50;
    const x = v => L + (v / 100) * (W - L - R), y = v => T + (1 - v / 100) * (H - T - B);
    let g = "";
    [0, 25, 50, 75, 100].forEach(v => {
      g += `<line x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - B}" class="fc-grid"${v === 50 ? ' style="stroke-dasharray:5 4;stroke:var(--dim)"' : ""}/>
            <line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="fc-grid"${v === 50 ? ' style="stroke-dasharray:5 4;stroke:var(--dim)"' : ""}/>
            <text x="${x(v)}" y="${H - B + 16}" class="fc-t" text-anchor="middle">${v}</text><text x="${L - 7}" y="${y(v) + 4}" class="fc-t" text-anchor="end">${v}</text>`;
    });
    const q = spec.quads || [];
    if (q.length === 4) {
      g += `<text x="${L + 8}" y="${T + 16}" class="fc-t fc-t-cap">${esc(q[0])}</text><text x="${W - R - 8}" y="${T + 16}" class="fc-t fc-t-cap" text-anchor="end">${esc(q[1])}</text>
            <text x="${L + 8}" y="${H - B - 8}" class="fc-t fc-t-cap">${esc(q[2])}</text><text x="${W - R - 8}" y="${H - B - 8}" class="fc-t fc-t-cap" text-anchor="end">${esc(q[3])}</text>`;
    }
    g += `<g fill="#64748b" fill-opacity=".55">${(spec.points || []).map(p => `<circle cx="${r1(x(p[0]))}" cy="${r1(y(p[1]))}" r="3.4"/>`).join("")}</g>`;
    const t = spec.target;
    if (t) {
      const right = x(t.x) > W - 150;
      g += `<circle cx="${r1(x(t.x))}" cy="${r1(y(t.y))}" r="9" fill="#8b5cf6" stroke="#fff" stroke-width="2.4" data-tip="${esc(`${t.label}\nCompleteness ${t.x} · Impact ${t.y}`)}"/>
            <text x="${r1(x(t.x) + (right ? -14 : 14))}" y="${r1(y(t.y) - 12)}" class="fc-t fc-t-strong fc-halo" text-anchor="${right ? "end" : "start"}">${esc(t.label)}</text>`;
    }
    g += `<text x="${(L + W - R) / 2}" y="${H - 6}" class="fc-t" text-anchor="middle">${esc(spec.xlabel || "")}</text>
          <text transform="translate(12 ${(T + H - B) / 2}) rotate(-90)" class="fc-t" text-anchor="middle">${esc(spec.ylabel || "")}</text>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg" role="img" aria-label="Cohort scatter">${g}</svg>`;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // XY: every player on two chosen metrics (Explore)
  // ═════════════════════════════════════════════════════════════════════════
  function niceTicks(lo, hi, n = 5) {
    const span = hi - lo || 1, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
    return out;
  }
  const fmtVal = (v, unit) => `${Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 100) / 100}${unit === "%" || unit === "m" || unit === "s" ? unit : ""}`;

  function xyChart(host, spec) {
    const pts = spec.points || [];
    if (!pts.length) { host.innerHTML = empty("No players match these filters"); return; }
    const W = 720, H = 520, L = 60, R = 18, T = 14, B = 56;
    const sorted = a => [...a].sort((p, q) => p - q);
    const qnt = (s, p) => s[Math.min(s.length - 1, Math.max(0, Math.round(p * (s.length - 1))))];
    const xs = sorted(pts.map(p => p[0])), ys = sorted(pts.map(p => p[1]));
    // Scale on the 0.5-99.5 percentile range so one extreme value cannot squash everyone else.
    let x0 = qnt(xs, 0.005), x1 = qnt(xs, 0.995), y0 = qnt(ys, 0.005), y1 = qnt(ys, 0.995);
    if (x1 === x0) { x0 -= 1; x1 += 1; }
    if (y1 === y0) { y0 -= 1; y1 += 1; }
    const px = (x1 - x0) * 0.04, py = (y1 - y0) * 0.04;
    x0 -= px; x1 += px; y0 -= py; y1 += py;
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    // Axes run so that "better" is always up and to the right, even for lower-is-better metrics.
    const sx = v => { const f = (clamp(v, x0, x1) - x0) / (x1 - x0); return L + (spec.xinvert ? 1 - f : f) * (W - L - R); };
    const sy = v => { const f = (clamp(v, y0, y1) - y0) / (y1 - y0); return T + (spec.yinvert ? f : 1 - f) * (H - T - B); };
    let g = "";
    niceTicks(x0, x1).forEach(v => { g += `<line x1="${r1(sx(v))}" x2="${r1(sx(v))}" y1="${T}" y2="${H - B}" class="fc-grid"/><text x="${r1(sx(v))}" y="${H - B + 17}" class="fc-t" text-anchor="middle">${fmtVal(v, "")}</text>`; });
    niceTicks(y0, y1).forEach(v => { g += `<line x1="${L}" x2="${W - R}" y1="${r1(sy(v))}" y2="${r1(sy(v))}" class="fc-grid"/><text x="${L - 8}" y="${r1(sy(v) + 4)}" class="fc-t" text-anchor="end">${fmtVal(v, "")}</text>`; });
    const mx = qnt(xs, 0.5), my = qnt(ys, 0.5);
    g += `<line x1="${r1(sx(mx))}" x2="${r1(sx(mx))}" y1="${T}" y2="${H - B}" style="stroke:var(--dim);stroke-dasharray:5 4"/>
          <line x1="${L}" x2="${W - R}" y1="${r1(sy(my))}" y2="${r1(sy(my))}" style="stroke:var(--dim);stroke-dasharray:5 4"/>`;

    const url = p => `/player?${new URLSearchParams({ player_id: p[4], league: p[5], season: p[6] })}`;
    const tip = p => `${p[2]}\n${p[3]} · ${p[5]}\n${spec.xlabel}: ${fmtVal(p[0], spec.xunit)}\n${spec.ylabel}: ${fmtVal(p[1], spec.yunit)}\n${p[8]} min`.replace(/\\n/g, "\n");
    g += pts.map(p => {
      const out = p[0] < x0 || p[0] > x1 || p[1] < y0 || p[1] > y1, c = spec.colors[p[7]] || "#64748b";
      return `<a href="${esc(url(p))}"><circle cx="${r1(sx(p[0]))}" cy="${r1(sy(p[1]))}" r="3.6" fill="${out ? "none" : c}" fill-opacity=".62" stroke="${c}" stroke-opacity="${out ? 0.9 : 0.25}" stroke-width="1.2" class="fc-xy-dot" data-tip="${esc(tip(p))}"/></a>`;
    }).join("");

    // Name the standouts: furthest from the medians in the "better" direction on both axes.
    const iqr = (s) => (qnt(s, 0.75) - qnt(s, 0.25)) || 1;
    const ix = iqr(xs), iy = iqr(ys);
    const score = p => ((p[0] - mx) / ix) * (spec.xinvert ? -1 : 1) + ((p[1] - my) / iy) * (spec.yinvert ? -1 : 1);
    const placed = [];
    [...pts].sort((a, b) => score(b) - score(a)).slice(0, 40).forEach(p => {
      if (placed.length >= 8) return;
      const cx = sx(p[0]), cy = sy(p[1]);
      if (placed.some(q => Math.abs(q[0] - cx) < 90 && Math.abs(q[1] - cy) < 15)) return;
      placed.push([cx, cy]);
      const right = cx > W - 140;
      g += `<text x="${r1(cx + (right ? -8 : 8))}" y="${r1(cy - 7)}" class="fc-t fc-t-strong fc-halo" text-anchor="${right ? "end" : "start"}">${esc(p[2])}</text>`;
    });

    const dir = (inv, name) => inv ? `${name} (lower is better, axis flipped)` : name;
    g += `<text x="${(L + W - R) / 2}" y="${H - 8}" class="fc-t" text-anchor="middle">${esc(dir(spec.xinvert, spec.xlabel))}</text>
          <text transform="translate(14 ${(T + H - B) / 2}) rotate(-90)" class="fc-t" text-anchor="middle">${esc(dir(spec.yinvert, spec.ylabel))}</text>`;
    const groups = [...new Set(pts.map(p => p[7]))];
    const legend = `<div class="fc-legend">${groups.map(k => `<span class="fc-leg static"><i class="fc-dot" style="background:${spec.colors[k] || "#64748b"}"></i><span>${esc(k.charAt(0).toUpperCase() + k.slice(1))}s</span></span>`).join("")}</div>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg" role="img" aria-label="${esc(spec.xlabel)} against ${esc(spec.ylabel)}">${g}</svg>` + legend;
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Radar + grouped bars (Compare)
  // ═════════════════════════════════════════════════════════════════════════
  const seriesLegend = series => `<div class="fc-legend">${series.map(s => `<span class="fc-leg static"><i class="fc-dot" style="background:${s.color}"></i><span>${esc(s.name)}</span></span>`).join("")}</div>`;

  function radarChart(host, spec) {
    const W = 480, H = 420, cx = W / 2, cy = 205, R = 140, ax = spec.axes, n = ax.length;
    const P = (r, i) => { const a = (2 * Math.PI * i) / n; return [r1(cx + r * Math.sin(a)), r1(cy - r * Math.cos(a))]; };
    let g = [25, 50, 75, 100].map(v => `<polygon points="${ax.map((_, i) => P((R * v) / 100, i).join(",")).join(" ")}" class="fc-grid" fill="none"/>`).join("");
    g += [25, 50, 75, 100].map(v => `<text x="${cx + 4}" y="${cy - (R * v) / 100 + 11}" class="fc-t fc-t-dim">${v}</text>`).join("");
    ax.forEach((name, i) => {
      const e = P(R, i), l = P(R + 22, i), s = Math.sin((2 * Math.PI * i) / n);
      g += `<line x1="${cx}" y1="${cy}" x2="${e[0]}" y2="${e[1]}" class="fc-grid"/>
            <text x="${l[0]}" y="${l[1] + 4}" class="fc-t fc-t-lg" text-anchor="${s > 0.3 ? "start" : s < -0.3 ? "end" : "middle"}">${esc(name)}</text>`;
    });
    spec.series.forEach(s => {
      const pts = s.values.map((v, i) => P((R * v) / 100, i));
      g += `<polygon points="${pts.map(p => p.join(",")).join(" ")}" fill="${s.color}" fill-opacity=".16" stroke="${s.color}" stroke-width="2.4" stroke-linejoin="round"/>`;
      pts.forEach((p, i) => { g += `<circle cx="${p[0]}" cy="${p[1]}" r="4.2" fill="${s.color}" stroke="var(--bg)" stroke-width="1.5" data-tip="${esc(`${s.name}\n${ax[i]}: ${Math.round(s.values[i])}th pct`)}"/>`; });
    });
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg fc-round" role="img" aria-label="Radar comparison">${g}</svg>` + (spec.series.length > 1 ? seriesLegend(spec.series) : "");
  }

  function groupedChart(host, spec) {
    const W = 680, H = 330, L = 40, R = 8, T = 14, B = 74, nc = spec.cats.length, np = spec.series.length;
    const y = v => T + (1 - v / 100) * (H - T - B), gw = (W - L - R) / nc, bw = (gw * 0.78) / np;
    let g = [0, 25, 50, 75, 100].map(v => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="fc-grid"/><text x="${L - 7}" y="${y(v) + 4}" class="fc-t" text-anchor="end">${v}</text>`).join("");
    spec.cats.forEach((c, ci) => {
      const gx = L + ci * gw, start = gx + gw / 2 - (bw * np) / 2;
      spec.series.forEach((s, si) => {
        const v = s.values[ci] || 0, bx = start + si * bw;
        g += `<rect x="${r1(bx + 1)}" y="${r1(y(v))}" width="${r1(Math.max(1, bw - 2))}" height="${r1(H - B - y(v))}" rx="3" fill="${s.color}" class="fc-hbar" data-tip="${esc(`${s.name}\n${c}: ${Math.round(v)}th pct`)}"/>`;
      });
      g += `<text transform="translate(${r1(gx + gw / 2 + 4)} ${H - B + 14}) rotate(-32)" class="fc-t" style="font-size:12px" text-anchor="end">${esc(c)}</text>`;
    });
    g += `<line x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}" class="fc-axisline"/>`;
    host.innerHTML = head(spec) + `<svg viewBox="0 0 ${W} ${H}" class="ov-svg fc-svg" role="img" aria-label="Category comparison">${g}</svg>` + seriesLegend(spec.series);
  }

  // ═════════════════════════════════════════════════════════════════════════
  const RENDERERS = { pitch: pitchChart, bars: barsChart, hist: histChart, trend: trendChart, rose: roseChart,
                      bloom: bloomChart, scatter: scatterChart, xy: xyChart, radar: radarChart, grouped: groupedChart };

  function render(host, spec) {
    host.classList.add("fc-host");
    const fn = spec && RENDERERS[spec.type];
    if (!fn) { host.innerHTML = empty("No chart data"); return; }
    try { fn(host, spec); } catch (err) { console.error("chart failed", spec && spec.type, err); host.innerHTML = empty("This chart could not be drawn"); }
  }

  // Grid tiles that deserve the whole row (full pitches, the category comparison).
  const isWide = spec => !!spec && ((spec.type === "pitch" && spec.view !== "half") || spec.type === "grouped");

  // Renders [{key,title,spec}] into a tile grid (used by the Player and Compare pages).
  function renderTiles(grid, charts) {
    grid.innerHTML = (charts || []).map(c => `
      <div class="adv-chart-tile${isWide(c.spec) ? " adv-chart-tile-wide" : ""}">
        <div class="adv-chart-tile-title">${esc(c.title)}</div>
        <div class="adv-chart-tile-body"><div class="fc-host"></div></div>
      </div>`).join("");
    const hosts = grid.querySelectorAll(".fc-host");
    (charts || []).forEach((c, i) => render(hosts[i], c.spec));
  }

  return { render, renderTiles, pctColor };
})();
