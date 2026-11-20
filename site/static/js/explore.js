/**
 * FootIQ — Explore page. Rank every player-season by a single chosen metric
 * (category + metric + league/season/position/age filters), via /api/explore.
 * The discovery counterpart to Scout: no reference player required.
 */

function _initialsAvatar(name, size = 64) {
  const initials = (name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const colors = ["#ec4899","#f472b6","#db2777","#ec4899","#f472b6","#db2777"];
  const color = colors[(name || "?").charCodeAt(0) % colors.length];
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}' viewBox='0 0 ${size} ${size}'><circle cx='${size/2}' cy='${size/2}' r='${size/2}' fill='${color}22'/><circle cx='${size/2}' cy='${size/2}' r='${size/2-1}' fill='none' stroke='${color}' stroke-width='1.5'/><text x='${size/2}' y='${size/2+size*0.15}' text-anchor='middle' font-family='system-ui,sans-serif' font-size='${size*0.3}' font-weight='700' fill='${color}'>${initials}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

const _wikiImgCache = {};
async function fetchWikiImage(name, team = "") {
  const cacheKey = `${name}_${team}`;
  if (_wikiImgCache[cacheKey] !== undefined) return _wikiImgCache[cacheKey];
  try {
    const url = `/api/player-image?name=${encodeURIComponent(name)}${team ? `&team=${encodeURIComponent(team)}` : ""}`;
    const r = await fetch(url);
    if (r.ok) {
      const d = await r.json();
      _wikiImgCache[cacheKey] = d.url || "";
      return _wikiImgCache[cacheKey];
    }
  } catch {}
  _wikiImgCache[cacheKey] = "";
  return "";
}
async function applyWikiImage(name, team, imgEl) {
  if (!imgEl) return;
  const url = await fetchWikiImage(name, team);
  if (url) imgEl.src = url;
}

function percentileColor(pct) {
  const stops = [[0,[239,68,68]],[25,[249,115,22]],[50,[234,179,8]],[75,[34,197,94]],[100,[59,130,246]]];
  pct = Math.max(0, Math.min(100, pct));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0,c0] = stops[i], [t1,c1] = stops[i+1];
    if (pct >= t0 && pct <= t1) {
      const a = (pct-t0)/(t1-t0);
      return `rgb(${Math.round(c0[0]+a*(c1[0]-c0[0]))},${Math.round(c0[1]+a*(c1[1]-c0[1]))},${Math.round(c0[2]+a*(c1[2]-c0[2]))})`;
    }
  }
  return "#3b82f6";
}

const CATEGORIES = window.EXPLORE_CATEGORIES || [];

function currentMetricUnit() {
  const cat = CATEGORIES.find(c => c.category === document.getElementById("explore-category").value);
  const metric = cat && cat.metrics.find(m => m.col === document.getElementById("explore-metric").value);
  return (metric && metric.unit) || "";
}

function populateCategorySelect() {
  const catSel = document.getElementById("explore-category");
  catSel.innerHTML = `<option value="" selected disabled>Choose a category</option>` +
    CATEGORIES.map(c => `<option value="${c.category}">${c.category_label}</option>`).join("");
  populateMetricSelect();
  if (typeof upgradeSelects === "function") upgradeSelects();
}

function populateMetricSelect() {
  const catSel = document.getElementById("explore-category");
  const metricSel = document.getElementById("explore-metric");
  const cat = CATEGORIES.find(c => c.category === catSel.value);
  metricSel.innerHTML = `<option value="" selected disabled>Choose a metric</option>` +
    (cat ? cat.metrics.map(m => `<option value="${m.col}">${m.label}</option>`).join("") : "");
  if (typeof upgradeSelects === "function") upgradeSelects();
}

function populateYSelects() {
  const catSel = document.getElementById("explore-category-y");
  catSel.innerHTML = `<option value="" selected disabled>Choose a category</option>` +
    CATEGORIES.map(c => `<option value="${c.category}">${c.category_label}</option>`).join("");
  populateYMetricSelect();
}

function populateYMetricSelect() {
  const cat = CATEGORIES.find(c => c.category === document.getElementById("explore-category-y").value);
  document.getElementById("explore-metric-y").innerHTML = `<option value="" selected disabled>Choose a metric</option>` +
    (cat ? cat.metrics.map(m => `<option value="${m.col}">${m.label}</option>`).join("") : "");
  if (typeof upgradeSelects === "function") upgradeSelects();
}

function isScatterView() { return document.getElementById("explore-view").value === "scatter"; }
function isQuadrantView() { return document.getElementById("explore-view").value === "quadrant"; }
const QUADRANTS = window.EXPLORE_QUADRANTS || [];
let _plotToken = 0;   // a slow earlier request must not draw over a newer choice

// The plot's own position group is the default (a goalkeeper plot should not start on outfielders);
// the Position filter still overrides it. "all" in the filter means "the plot's group" server-side.
function describeQuadrant() {
  const q = QUADRANTS.find(p => p.id === document.getElementById("explore-quad").value);
  const el = document.getElementById("explore-quad-question");
  if (q && el) el.textContent = `${q.question} Shown for ${q.who} unless you pick a position below.`;
  return q;
}

// The plots are grouped by theme, in the order they are defined.
function populateQuadrantSelect() {
  const sel = document.getElementById("explore-quad");
  const groups = [...new Set(QUADRANTS.map(q => q.group))];
  sel.innerHTML = groups.map(g => `<optgroup label="${g}">` +
    QUADRANTS.filter(q => q.group === g).map(q => `<option value="${q.id}">${q.title}</option>`).join("") + `</optgroup>`).join("");
  const label = sel.closest(".filter-group").querySelector("label");
  if (label) label.textContent = `Quadrant plot (${QUADRANTS.length})`;
}

async function runQuadrant() {
  const q = describeQuadrant();
  const token = ++_plotToken;
  const host = document.getElementById("explore-scatter");
  document.getElementById("explore-results-section").style.display = "block";
  document.getElementById("explore-list").style.display = "none";
  host.style.display = "block";
  document.getElementById("explore-results-heading").textContent = q ? q.title : "Quadrant plot";
  FootIQUI.loading(host, "Plotting players…");
  const minMinutes = document.getElementById("explore-min-minutes").value;
  try {
    const res = await fetch("/api/explore-quadrant", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset: q && q.id,
        league: document.getElementById("explore-league").value,
        season: document.getElementById("explore-season").value,
        position_group: document.getElementById("explore-position").value,
        min_minutes: minMinutes === "none" ? null : minMinutes,
      }),
    });
    const data = await res.json();
    if (token !== _plotToken) return;
    if (!res.ok || data.error) { FootIQUI.error(host, data.error || "Could not load the plot.", runExplore); return; }
    FootIQCharts.render(host, data.spec);
  } catch {
    if (token === _plotToken) FootIQUI.error(host, "Could not load the plot.", runExplore);
  }
}

async function runScatter() {
  const token = ++_plotToken;
  const xm = document.getElementById("explore-metric").value, ym = document.getElementById("explore-metric-y").value;
  const host = document.getElementById("explore-scatter");
  document.getElementById("explore-results-section").style.display = "block";
  document.getElementById("explore-list").style.display = "none";
  host.style.display = "block";
  document.getElementById("explore-results-heading").textContent = "Scatter plot";
  if (!xm || !ym) {
    host.innerHTML = `<div class="fc-empty">Choose a metric for each axis.</div>`;
    return;
  }
  host.innerHTML = `<div style="text-align:center;color:var(--muted);padding:32px"><div class="mini-spinner" style="margin:0 auto 10px"></div>Plotting players…</div>`;
  const minMinutes = document.getElementById("explore-min-minutes").value;
  try {
    const res = await fetch("/api/explore-scatter", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        x_metric: xm, y_metric: ym,
        league: document.getElementById("explore-league").value,
        season: document.getElementById("explore-season").value,
        position_group: document.getElementById("explore-position").value,
        min_minutes: minMinutes === "none" ? null : minMinutes,
      }),
    });
    const data = await res.json();
    if (token !== _plotToken) return;
    if (!res.ok || data.error) { FootIQUI.error(host, data.error || "Could not load the plot.", runExplore); return; }
    FootIQCharts.render(host, data.spec);
  } catch {
    if (token === _plotToken) FootIQUI.error(host, "Could not load the plot.", runExplore);
  }
}

function applyView() {
  const scatter = isScatterView(), quad = isQuadrantView(), plot = scatter || quad;
  document.getElementById("explore-y-row").style.display = scatter ? "flex" : "none";
  document.getElementById("explore-quad-row").style.display = quad ? "flex" : "none";
  document.getElementById("explore-metric-row").style.display = quad ? "none" : "";
  document.getElementById("explore-scatter").style.display = plot ? "block" : "none";
  document.getElementById("explore-list").style.display = plot ? "none" : "";
  runExplore();
}

async function runExplore() {
  const token = (!isQuadrantView() && !isScatterView()) ? ++_plotToken : null;
  if (isQuadrantView()) { await runQuadrant(); return; }
  if (isScatterView()) { await runScatter(); return; }
  document.getElementById("explore-list").style.display = "";
  document.getElementById("explore-scatter").style.display = "none";
  const metricSel = document.getElementById("explore-metric");
  if (!metricSel.value) return;  // nothing chosen yet — stay on the empty state, like Scout before a target is picked

  document.getElementById("explore-results-section").style.display = "block";

  const listEl = document.getElementById("explore-list");
  const headingEl = document.getElementById("explore-results-heading");
  const metricLabel = metricSel.options[metricSel.selectedIndex] ? metricSel.options[metricSel.selectedIndex].text : "";
  headingEl.textContent = metricLabel ? `Top Players: ${metricLabel}` : "Top Players";

  listEl.innerHTML = `<div class="glass-card" style="text-align:center;color:var(--muted);padding:32px"><div class="mini-spinner" style="margin:0 auto 10px"></div>Ranking players…</div>`;

  const minMinutes = document.getElementById("explore-min-minutes").value;

  try {
    const res = await fetch("/api/explore", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        metric: metricSel.value,
        league: document.getElementById("explore-league").value,
        season: document.getElementById("explore-season").value,
        position_group: document.getElementById("explore-position").value,
        min_minutes: minMinutes === "none" ? null : minMinutes,
      }),
    });
    const data = await res.json();
    if (token !== _plotToken) return;    // a newer metric or filter was chosen while this loaded
    if (!res.ok || data.error) {
      FootIQUI.error(listEl, data.error || "Could not load results.", runExplore);
      return;
    }
    renderResults(data.results || []);
  } catch {
    if (token !== _plotToken) return;
    FootIQUI.error(listEl, "Could not load results.", runExplore);
  }
}

function renderResults(results) {
  const listEl = document.getElementById("explore-list");
  if (!results.length) {
    FootIQUI.empty(listEl, "No players meet these filters", "Try another season, league or position, or lower the minimum minutes.");
    return;
  }
  const unit = currentMetricUnit();
  listEl.innerHTML = results.map((r, i) => {
    const color = percentileColor(r.percentile);
    const ageStr = r.age ? ` <span class="scout-match-age">(Age ${r.age})</span>` : "";
    const valStr = unit === "%" ? `${r.value}%` : unit === "m" ? `${r.value}m` : unit === "s" ? `${r.value}s` : r.value;
    const profileUrl = `/player?player_id=${r.player_id}&league=${encodeURIComponent(r.league)}&season=${encodeURIComponent(r.season)}`;
    return `
      <div class="scout-match-card${i === 0 ? " top-match" : ""}">
        <div class="scout-match-rank">#${r.rank}</div>
        <img class="scout-match-photo" data-name="${r.name}" data-team="${r.team}" src="${_initialsAvatar(r.name, 52)}"
             onerror="this.src='${_initialsAvatar(r.name, 52)}'" alt="${r.name}" />
        <div class="scout-match-info">
          <div class="scout-match-name">${r.name}${ageStr}</div>
          <div class="scout-match-meta">${r.team} &middot; ${r.league} &middot; ${r.season} &middot; ${r.position} &middot; ${r.minutes} min</div>
        </div>
        <div class="scout-match-score">
          <div class="scout-match-score-val" style="color:${color}">${valStr}</div>
          <div class="scout-match-score-lbl">${r.percentile}th pct</div>
        </div>
        <a class="scout-match-cta" href="${profileUrl}">View Profile &rarr;</a>
      </div>
    `;
  }).join("");

  listEl.querySelectorAll("img.scout-match-photo[data-name]").forEach(img => {
    applyWikiImage(img.dataset.name, img.dataset.team, img);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
populateCategorySelect();
populateYSelects();
populateQuadrantSelect();
if (typeof upgradeSelects === "function") upgradeSelects();
document.getElementById("explore-category").addEventListener("change", () => { populateMetricSelect(); });
document.getElementById("explore-category-y").addEventListener("change", populateYMetricSelect);
document.getElementById("explore-view").addEventListener("change", applyView);
["explore-metric", "explore-metric-y", "explore-quad", "explore-league", "explore-season", "explore-position", "explore-min-minutes"].forEach(id => {
  document.getElementById(id).addEventListener("change", runExplore);
});

const exploreThemeBtn = document.getElementById("theme-toggle");
if (exploreThemeBtn) {
  exploreThemeBtn.addEventListener("click", () => {
    const isLight = document.body.getAttribute("data-theme") === "light";
    document.body.setAttribute("data-theme", isLight ? "dark" : "light");
    exploreThemeBtn.textContent = isLight ? "🌙" : "☀️";
    localStorage.setItem("theme", isLight ? "dark" : "light");
  });
}
