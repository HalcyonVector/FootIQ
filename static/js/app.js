/**
 * FootIQ — Event-level football analytics
 *
 * Flow: search → player header → Advanced Metrics tabs + Combination Play.
 * Everything is built from parsed match-event data (core/advanced/).
 */

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let primaryPlayer = null;   // {id, name, team, league, season, position, minutes}
let primaryLeague = "Premier League";
let primarySeason = (window.SEASONS && window.SEASONS[0]) || "2024-25";

// ─────────────────────────────────────────────────────────────────────────────
// DOM refs
// ─────────────────────────────────────────────────────────────────────────────
const toast           = document.getElementById("toast");
const profileSection  = document.getElementById("profile-section");
const chartsLoading   = document.getElementById("charts-loading");
const advancedSection = document.getElementById("advanced-section");
const advTabs         = document.getElementById("adv-tabs");
const advPanels       = document.getElementById("adv-panels");

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 4500);
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function percentileColor(pct) {
  const stops = [[0,[239,68,68]],[25,[249,115,22]],[50,[234,179,8]],[75,[34,197,94]],[100,[59,130,246]]];
  pct = Math.max(0, Math.min(100, pct));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0,c0] = stops[i], [t1,c1] = stops[i+1];
    if (pct >= t0 && pct <= t1) {
      const a = (pct-t0)/(t1-t0);
      const r = Math.round(c0[0]+a*(c1[0]-c0[0]));
      const g = Math.round(c0[1]+a*(c1[1]-c0[1]));
      const b = Math.round(c0[2]+a*(c1[2]-c0[2]));
      return `rgb(${r},${g},${b})`;
    }
  }
  return "#3b82f6";
}

// ─────────────────────────────────────────────────────────────────────────────
// Build & wire the main league dropdown
// ─────────────────────────────────────────────────────────────────────────────
function initMainDropdown() {
  const dd     = document.getElementById("dd-main");
  const ddSel  = document.getElementById("dd-sel-main");
  const ddMenu = document.getElementById("dd-menu-main");
  const lgInput= document.getElementById("main-league");

  ddMenu.innerHTML = window.LEAGUES.map(lg => `
    <div class="dd-item ${lg.id === "Premier League" ? "active" : ""}"
         data-value="${lg.id}" data-logo="${lg.logo}" data-name="${lg.name}">
      <img src="${lg.logo}" style="width:20px;height:20px;object-fit:contain;margin-right:8px;" />
      <span>${lg.name}</span>
    </div>
  `).join("");

  ddSel.addEventListener("click", e => {
    e.stopPropagation();
    dd.classList.toggle("open");
  });

  ddMenu.querySelectorAll(".dd-item").forEach(item => {
    item.addEventListener("click", () => {
      primaryLeague = item.dataset.value;
      ddSel.innerHTML = `<img src="${item.dataset.logo}" style="width:20px;height:20px;object-fit:contain;margin-right:8px;" /><span class="dd-name">${item.dataset.name}</span><span class="dd-arrow">▾</span>`;
      dd.classList.remove("open");
      ddMenu.querySelectorAll(".dd-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      lgInput.value = primaryLeague;
      if (primaryPlayer) resetPrimaryPlayer();
    });
  });

  document.getElementById("main-season")?.addEventListener("change", e => {
    primarySeason = e.target.value;
    if (primaryPlayer) resetPrimaryPlayer();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Main search
// ─────────────────────────────────────────────────────────────────────────────
function initMainSearch() {
  const searchEl  = document.getElementById("main-search");
  const resultsEl = document.getElementById("main-results");

  const doSearch = debounce(async (isGlobal = false) => {
    const q = searchEl.value.trim();
    if (q.length < 2) { resultsEl.innerHTML = ""; resultsEl.classList.remove("active"); return; }
    try {
      const url = `/api/search?name=${encodeURIComponent(q)}&league=${primaryLeague}&season=${primarySeason}${isGlobal === true ? '&all_leagues=1' : ''}`;
      const res  = await fetch(url);
      const data = await res.json();
      if (data.error) { showToast(data.error); return; }
      if (!data.length && !isGlobal) {
        return doSearch(true);
      } else if (!data.length) {
        resultsEl.innerHTML = `<div class="result-item" style="color:var(--muted);justify-content:center">No players found</div>`;
        resultsEl.classList.add("active"); return;
      }
      resultsEl.innerHTML = data.map(p => `
        <div class="result-item" data-id="${p.id}" data-player='${JSON.stringify(p).replace(/'/g,"&#39;")}'>
          <div class="result-item-icon">${p.name.charAt(0).toUpperCase()}</div>
          <div>
            <div class="result-name">${p.name}</div>
            <div class="result-meta">${p.league ? p.league + ' · ' : ''}${p.team} · ${p.position}</div>
          </div>
        </div>
      `).join("");
      resultsEl.classList.add("active");
    } catch { showToast("Search failed."); }
  }, 380);

  searchEl.addEventListener("input", doSearch);

  resultsEl.addEventListener("click", e => {
    const item = e.target.closest(".result-item[data-id]");
    if (!item) return;
    selectPrimaryPlayer(JSON.parse(item.dataset.player));
    resultsEl.classList.remove("active");
    searchEl.value = "";
  });
}

// A cross-league search (the "no results in the selected league, fall back
// to searching every league" path in doSearch above) can return a player
// whose real league/season differs from whatever the dropdowns still show —
// e.g. searching "Bellingham" while the League dropdown is stuck on
// "Premier League" finds him via the global fallback with league="La Liga".
// Every downstream fetch (advanced-stats, category-chart, linkup) queries
// using the primaryLeague/primarySeason globals, NOT the found player's own
// league/season, so leaving them stale meant those requests silently looked
// up the WRONG league and came back empty ("No advanced stats found") even
// though the player genuinely has data. Sync the globals AND the visible
// dropdowns to match whichever player was actually selected.
function _syncPrimaryFilters(player) {
  if (player.league && player.league !== primaryLeague) {
    primaryLeague = player.league;
    const lgItem = [...document.querySelectorAll("#dd-menu-main .dd-item")]
      .find(i => i.dataset.value === player.league);
    if (lgItem) {
      document.getElementById("dd-sel-main").innerHTML =
        `<img src="${lgItem.dataset.logo}" style="width:20px;height:20px;object-fit:contain;margin-right:8px;" /><span class="dd-name">${lgItem.dataset.name}</span><span class="dd-arrow">▾</span>`;
      document.querySelectorAll("#dd-menu-main .dd-item").forEach(i => i.classList.remove("active"));
      lgItem.classList.add("active");
    }
    const lgInput = document.getElementById("main-league");
    if (lgInput) lgInput.value = primaryLeague;
  }
  if (player.season && player.season !== primarySeason) {
    primarySeason = player.season;
    const seasonSel = document.getElementById("main-season");
    if (seasonSel) seasonSel.value = primarySeason;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Select primary player → fetch Advanced Metrics + Combination Play
// ─────────────────────────────────────────────────────────────────────────────
async function selectPrimaryPlayer(player) {
  primaryPlayer = player;
  _syncPrimaryFilters(player);
  resetLinkupState();

  profileSection.style.display = "block";
  renderProfileHeader(player);

  chartsLoading.style.display = "flex";
  advancedSection.style.display = "none";

  // Stats are precomputed (fast parquet lookup) — reveal them immediately.
  // Charts (Combination Play now, per-category charts later) load lazily
  // per-tab from activateTab(), so a slow chart never blocks the page.
  await fetchAdvancedStats(player);
  chartsLoading.style.display = "none";

  setTimeout(() => {
    const navH = document.querySelector(".navbar")?.offsetHeight || 70;
    const top = profileSection.getBoundingClientRect().top + window.scrollY - navH - 16;
    window.scrollTo({ top, behavior: "smooth" });
  }, 100);
}

function resetPrimaryPlayer() {
  primaryPlayer = null;
  profileSection.style.display = "none";
}

function _initialsAvatar(name, size=80) {
  const initials = name.split(" ").map(w => w[0]).slice(0,2).join("").toUpperCase();
  const colors = ["#3b82f6","#8b5cf6","#10b981","#f59e0b","#ef4444","#06b6d4"];
  const color = colors[name.charCodeAt(0) % colors.length];
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}' viewBox='0 0 ${size} ${size}'><circle cx='${size/2}' cy='${size/2}' r='${size/2}' fill='${color}22'/><circle cx='${size/2}' cy='${size/2}' r='${size/2-1}' fill='none' stroke='${color}' stroke-width='1.5'/><text x='${size/2}' y='${size/2+size*0.15}' text-anchor='middle' font-family='system-ui,sans-serif' font-size='${size*0.3}' font-weight='700' fill='${color}'>${initials}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function renderProfileHeader(player) {
  const initialSrc = player.photo || _initialsAvatar(player.name);
  document.getElementById("profile-header").innerHTML = `
    <img class="profile-photo"
         src="${initialSrc}"
         onerror="this.src='${_initialsAvatar(player.name)}'"
         alt="${player.name}" />
    <div class="profile-info">
      <div class="profile-name">${player.name}</div>
      <div class="profile-sub">${player.position}</div>
      <div class="profile-team">
        <span>${player.team || ""}</span>
        ${player.league ? `<span style="color:var(--muted)">&middot; ${player.league}</span>` : ""}
      </div>
      <div class="profile-season-stats" id="season-stats-row">
        <span class="profile-stat-chip apps-chip">${player.minutes || "–"} min &middot; ${primarySeason}</span>
      </div>
    </div>
    <div class="score-placeholder-pulse" id="profile-score-slot"></div>
  `;
  applyWikiImage(player.name, player.team, document.querySelector(".profile-photo"));
}

// Composite Rating box on the right of the header (same number Compare
// shows) — arrives with /api/advanced-stats, so it replaces the pulsing
// placeholder renderProfileHeader() put there rather than blocking the
// header on it.
function renderProfileScore(composite) {
  const slot = document.getElementById("profile-score-slot");
  if (!slot) return;
  const score = composite && composite.score !== null && composite.score !== undefined ? composite.score : null;
  if (score === null) { slot.remove(); return; }
  slot.outerHTML = `
    <div class="profile-score" id="profile-score-slot">
      <div class="score-num">${score}</div>
      <div class="score-lbl">Rating</div>
    </div>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// Client-side Wikipedia image fetcher (async, non-blocking)
// ─────────────────────────────────────────────────────────────────────────────
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

async function applyWikiImage(name, team, ...imgEls) {
  const url = await fetchWikiImage(name, team);
  if (url) {
    imgEls.forEach(el => { if (el) el.src = url; });
  } else {
    const dataUrl = _initialsAvatar(name, 80);
    imgEls.forEach(el => { if (el) el.src = dataUrl; });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Stat card renderer — one compact vertical list of metric rows (label left,
// value+bar+percentile right), shared by every Advanced Metrics tab. Sits in
// the left column of .adv-panel-body next to that tab's chart card.
// ─────────────────────────────────────────────────────────────────────────────
const LEGEND_STOPS = [["Elite 80+", 90], ["Above 60+", 70], ["Average 40+", 50], ["Below 20+", 30], ["Poor", 10]];

function renderStatCard(cat, containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const stats = (cat.rows && cat.rows[0] && cat.rows[0].stats) || [];
  el.innerHTML = `
    <div class="adv-stat-card-title">${cat.label}</div>
    ${cat.desc ? `<div class="adv-stat-card-desc">${cat.desc}</div>` : ""}
    <div class="stat-card-rows">
      ${stats.map(s => {
        const color = percentileColor(s.percentile);
        const noData = s.no_data || s.value === null;
        return `
          <div class="stat-card-row">
            <span class="scr-label">${s.label}</span>
            <div class="scr-right">
              <span class="scr-val" style="color:${noData ? 'var(--muted)' : color}">${noData ? '-' : s.value + (s.unit || '')}</span>
              <div class="scr-bar-bg"><div class="scr-bar-fill" style="width:${noData ? 0 : Math.min(s.percentile, 100)}%; background:${color}; box-shadow: 0 0 10px ${color}44;"></div></div>
            </div>
          </div>`;
      }).join("")}
    </div>
    <div class="stat-card-legend">
      ${LEGEND_STOPS.map(([lbl, pct]) => `<span><i class="scl-dot" style="background:${percentileColor(pct)}"></i>${lbl}</span>`).join("")}
    </div>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// Advanced (Opta/WhoScored event-derived) stats
// ─────────────────────────────────────────────────────────────────────────────
async function fetchAdvancedStats(player) {
  if (!advancedSection) return;
  try {
    const res = await fetch("/api/advanced-stats", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: player.id, league: primaryLeague, season: primarySeason }),
    });
    const data = await res.json();
    if (!res.ok || !data.categories || !data.categories.length) {
      showToast("No advanced stats found for this player/season.");
      renderProfileScore(null);
      return;
    }
    renderAdvancedStats(data.categories);
    renderProfileScore(data.composite);
    advancedSection.style.display = "block";
  } catch {
    showToast("Could not load advanced stats.");
    renderProfileScore(null);
  }
}

// Categories whose chart grid is wired up and ready to lazy-load on tab
// activation via /api/category-chart. "linkup" has its own endpoints/flow,
// handled separately.
const CHART_CATEGORIES = new Set([
  "passing", "shooting", "carrying", "aerial", "holdup", "half_spaces",
  "tempo", "defending", "post_recovery", "goalkeeping", "decision_making", "final_third",
]);

// category -> filter control config (radio = pick one, checkbox = pick many).
// Omitted from this map = no filter row for that category.
const CHART_FILTERS = {
  passing: { type: "radio", default: "progressive", options: [
    ["progressive", "Progressive & into box"], ["all", "All passes"],
  ]},
  aerial: { type: "checkbox", default: ["open_play", "set_piece"], options: [
    ["open_play", "Open play"], ["set_piece", "Set piece"],
  ]},
  half_spaces: { type: "radio", default: "offensive", options: [
    ["offensive", "Offensive"], ["defensive", "Defensive"], ["both", "Both"],
  ]},
  carrying: { type: "checkbox", default: ["prog_pass", "takeon_won", "takeon_lost"], options: [
    ["prog_pass", "Prog. pass after"], ["takeon_won", "Take-on won after"], ["takeon_lost", "Take-on lost after"],
  ]},
  holdup: { type: "radio", default: "final", options: [
    ["final", "Final third"], ["middle", "Middle third"], ["whole", "Whole pitch"],
  ]},
};

const _chartCache = {};        // "${catKey}:${filterStr}" -> {charts:[base64,...]}
const _chartFilterState = {};  // catKey -> current filter value (string for radio, array for checkbox)

// Tab-order prefetch: chart generation is real server-side work (matplotlib
// rendering, especially slow on Render's free-tier CPU), so switching to a
// tab you haven't opened yet always pays full cost once. After a tab has
// been sitting open for a couple seconds (a proxy for "the user is reading
// this one, not about to immediately click through"), quietly fetch the
// NEXT tab in order in the background so a click that follows a normal
// reading pause lands on a warm cache instead of waiting again. Only ever
// one prefetch in flight and only ever the very next tab — the backend here
// is a single worker (see render.yaml), so firing several requests at once
// would just queue behind each other and could make a real click wait
// BEHIND a prefetch instead of ahead of it.
let _categoryOrder = [];
let _prefetchTimer = null;
const PREFETCH_DELAY_MS = 2500;

function _cancelPrefetch() {
  if (_prefetchTimer) { clearTimeout(_prefetchTimer); _prefetchTimer = null; }
}

function _scheduleNextTabPrefetch(catKey) {
  _cancelPrefetch();
  const idx = _categoryOrder.indexOf(catKey);
  if (idx === -1) return;
  const next = _categoryOrder.slice(idx + 1).find(k => k !== "linkup" && CHART_CATEGORIES.has(k));
  if (!next) return;
  _prefetchTimer = setTimeout(() => _prefetchCategoryChart(next), PREFETCH_DELAY_MS);
}

async function _prefetchCategoryChart(catKey) {
  if (!primaryPlayer) return;
  const cfg = CHART_FILTERS[catKey];
  const filterVal = _chartFilterState[catKey] !== undefined ? _chartFilterState[catKey] : (cfg ? cfg.default : null);
  const filterStr = Array.isArray(filterVal) ? filterVal.join(",") : (filterVal || "");
  const cacheKey = `${catKey}:${filterStr}`;
  if (_chartCache[cacheKey]) return;
  try {
    const res = await fetch("/api/category-chart", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: primaryPlayer.id, league: primaryLeague, season: primarySeason,
        category: catKey, filter: filterStr,
      }),
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data.charts) _chartCache[cacheKey] = data;
  } catch { /* silent — this is a background optimization, not a user-facing load */ }
}

function renderAdvancedStats(categories) {
  _categoryOrder = categories.map(c => c.key);
  advTabs.innerHTML = categories.map((cat, i) =>
    `<button class="adv-tab-btn${i === 0 ? " active" : ""}" data-cat="${cat.key}">${cat.label}</button>`
  ).join("");

  advPanels.innerHTML = categories.map((cat, i) => `
    <div class="adv-panel" data-cat="${cat.key}" id="adv-panel-${cat.key}" style="display:${i === 0 ? "block" : "none"}">
      <div class="adv-panel-body">
        <div class="adv-stat-card" id="adv-stat-${cat.key}"></div>
        <div class="adv-chart-card" id="adv-chart-${cat.key}"></div>
      </div>
    </div>
  `).join("");

  categories.forEach(cat => {
    if (cat.key === "linkup") {
      renderLinkupStatCard(cat, `adv-stat-${cat.key}`);
      document.getElementById(`adv-chart-${cat.key}`).innerHTML = `
        <div id="linkup-stats-row" class="profile-season-stats" style="margin-bottom:10px"></div>
        <div class="linkup-chart-wrap">
          <div class="mini-spinner" id="linkup-chart-spinner" style="display:none"></div>
          <img id="linkup-chart-img" class="chart-img" alt="Combination play chart" />
        </div>
      `;
    } else {
      renderStatCard(cat, `adv-stat-${cat.key}`);
      const chartEl = document.getElementById(`adv-chart-${cat.key}`);
      if (chartEl && CHART_CATEGORIES.has(cat.key)) {
        chartEl.innerHTML = renderChartCardShell(cat.key);
      }
    }
  });

  advTabs.querySelectorAll(".adv-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      _cancelPrefetch();  // a real click always wins over a queued background prefetch
      advTabs.querySelectorAll(".adv-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      // The strip scrolls horizontally instead of wrapping now, so a tab
      // near either edge can be half-cut-off when clicked — bring it fully
      // into view within the strip itself (not the whole page).
      btn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      advPanels.querySelectorAll(".adv-panel").forEach(p => {
        p.style.display = p.dataset.cat === btn.dataset.cat ? "block" : "none";
      });
      activateTab(btn.dataset.cat);
    });
  });

  if (categories.length) activateTab(categories[0].key);
}

// Fires when a tab becomes active — lazily loads that category's chart
// (never blocks the stat card, which is already rendered by this point).
function activateTab(catKey) {
  if (catKey === "linkup") {
    loadLinkupTab();
  } else if (CHART_CATEGORIES.has(catKey)) {
    wireChartFilterControls(catKey);
    loadCategoryChart(catKey);
  }
  _scheduleNextTabPrefetch(catKey);
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-category charts (/api/category-chart) — lazy per-tab, spinner while
// pending, client-side cached per (category, filter) so revisits are instant.
// Each tab renders a GRID of 2-4 titled chart cards (an arbitrary-length
// [{key,title,image}] list from the backend), not a fixed 1-or-2 slot layout.
// ─────────────────────────────────────────────────────────────────────────────

// Categories whose /api/category-chart response includes a `stats` dict —
// rendered as an HTML chip row (stays legible at any width, unlike counts
// baked into a chart image that gets squeezed into a half-width slot).
const CHART_STATS_CATEGORIES = new Set(["carrying"]);

function _chartGridSpinner() {
  return `<div class="adv-chart-tile" style="grid-column:1/-1"><div class="adv-chart-tile-body"><div class="mini-spinner"></div></div></div>`;
}

function renderChartCardShell(catKey) {
  const cfg = CHART_FILTERS[catKey];
  const filterHtml = cfg ? `
    <div class="adv-chart-filter" id="adv-chart-filter-${catKey}">
      ${cfg.options.map(([val, label]) => {
        const active = cfg.type === "radio" ? val === cfg.default : cfg.default.includes(val);
        return `<button type="button" class="adv-chart-filter-btn${active ? " active" : ""}" data-val="${val}">${label}</button>`;
      }).join("")}
    </div>` : "";
  const statsRowHtml = CHART_STATS_CATEGORIES.has(catKey)
    ? `<div class="profile-season-stats" id="adv-chart-stats-${catKey}" style="margin-bottom:10px"></div>` : "";
  return `${filterHtml}${statsRowHtml}<div class="adv-chart-grid" id="adv-chart-grid-${catKey}">${_chartGridSpinner()}</div>`;
}

function wireChartFilterControls(catKey) {
  const el = document.getElementById(`adv-chart-filter-${catKey}`);
  if (!el || el.dataset.wired) return;
  el.dataset.wired = "1";
  const cfg = CHART_FILTERS[catKey];
  el.querySelectorAll(".adv-chart-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      if (cfg.type === "radio") {
        el.querySelectorAll(".adv-chart-filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        _chartFilterState[catKey] = btn.dataset.val;
      } else {
        btn.classList.toggle("active");
        _chartFilterState[catKey] = [...el.querySelectorAll(".adv-chart-filter-btn.active")].map(b => b.dataset.val);
      }
      loadCategoryChart(catKey, true);
    });
  });
}

async function loadCategoryChart(catKey, forceReload = false) {
  if (!primaryPlayer) return;
  const cfg = CHART_FILTERS[catKey];
  if (_chartFilterState[catKey] === undefined) {
    _chartFilterState[catKey] = cfg ? cfg.default : null;
  }
  const filterVal = _chartFilterState[catKey];
  const filterStr = Array.isArray(filterVal) ? filterVal.join(",") : (filterVal || "");
  const cacheKey = `${catKey}:${filterStr}`;

  if (!forceReload && _chartCache[cacheKey]) {
    renderChartImages(catKey, _chartCache[cacheKey]);
    return;
  }

  const grid = document.getElementById(`adv-chart-grid-${catKey}`);
  if (grid) grid.innerHTML = _chartGridSpinner();

  try {
    const res = await fetch("/api/category-chart", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: primaryPlayer.id, league: primaryLeague, season: primarySeason,
        category: catKey, filter: filterStr,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.charts) { renderChartError(catKey); return; }
    _chartCache[cacheKey] = data;
    renderChartImages(catKey, data);
  } catch {
    renderChartError(catKey);
  }
}

function renderChartImages(catKey, data) {
  const grid = document.getElementById(`adv-chart-grid-${catKey}`);
  if (grid) {
    grid.innerHTML = (data.charts || []).map(c => `
      <div class="adv-chart-tile">
        <div class="adv-chart-tile-title">${c.title}</div>
        <div class="adv-chart-tile-body"><img class="chart-img" src="data:image/png;base64,${c.image}" alt="${c.title}" /></div>
      </div>
    `).join("");
  }
  if (data.stats && catKey === "carrying") {
    const s = data.stats;
    const statsRow = document.getElementById(`adv-chart-stats-${catKey}`);
    if (statsRow) statsRow.innerHTML = `
      <span class="profile-stat-chip goal-chip">Prog. Carries: ${s.prog_carries}</span>
      <span class="profile-stat-chip card-y-chip">Prog. pass after: ${s.prog_pass_after}</span>
      <span class="profile-stat-chip assist-chip">Take-on won after: ${s.takeon_won_after}</span>
      <span class="profile-stat-chip apps-chip">Take-on lost after: ${s.takeon_lost_after}</span>
      <span class="profile-stat-chip">Angle Bias: ${s.abi >= 0 ? "+" : ""}${s.abi} (${s.abi_label})</span>
    `;
  }
}

function renderChartError(catKey) {
  const grid = document.getElementById(`adv-chart-grid-${catKey}`);
  if (grid) grid.innerHTML = `<div class="adv-chart-tile" style="grid-column:1/-1"><div class="adv-chart-tile-body" style="color:var(--muted);font-size:12px">No chart data for this player/season.</div></div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Combination Play (pairwise pass network) — now a normal tab. Left side is
// a "most-found teammates" table + dropdown selector; right side is the
// chart for whichever teammate is selected, loaded lazily per selection.
// ─────────────────────────────────────────────────────────────────────────────
let linkupTeammates = null;    // null = not fetched yet; [] = fetched, no data
let linkupLoading = false;
let linkupPasserId = null;
let linkupActiveTeammateId = null;
let _linkupDetailCache = {};   // teammateId -> {stats, chart}

function resetLinkupState() {
  linkupTeammates = null;
  linkupLoading = false;
  linkupPasserId = null;
  linkupActiveTeammateId = null;
  _linkupDetailCache = {};
}

function renderLinkupStatCard(cat, containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <div class="adv-stat-card-title">${cat.label}</div>
    <div class="adv-stat-card-desc">${cat.desc || "Pick a teammate to see what they do with the ball after receiving it from this player."}</div>
    <div class="linkup-select-label" style="font-weight:700;color:var(--text);font-size:12px;margin-top:2px">Most-found teammates</div>
    <table class="linkup-table"><thead><tr><th>Receiver</th><th>Passes</th></tr></thead><tbody id="linkup-table-body"><tr><td colspan="2" style="color:var(--muted)">Loading…</td></tr></tbody></table>
    <div class="linkup-select-label">Show what a teammate does after receiving</div>
    <select class="linkup-select" id="linkup-select"></select>
  `;
  document.getElementById("linkup-select").addEventListener("change", e => selectLinkupTeammate(e.target.value));
}

async function loadLinkupTab() {
  if (linkupTeammates !== null || linkupLoading || !primaryPlayer) return;
  linkupLoading = true;
  const body = document.getElementById("linkup-table-body");
  try {
    const res = await fetch("/api/linkup-teammates", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: primaryPlayer.id, league: primaryLeague, season: primarySeason }),
    });
    const data = await res.json();
    linkupTeammates = data.teammates || [];
    linkupPasserId = data.player_whoscored_id;

    if (!linkupTeammates.length) {
      if (body) body.innerHTML = `<tr><td colspan="2" style="color:var(--muted)">Not enough data</td></tr>`;
      return;
    }

    if (body) {
      body.innerHTML = linkupTeammates.map((t, i) =>
        `<tr data-id="${t.teammate_id}" class="${i === 0 ? "active" : ""}"><td>${t.name}</td><td>${t.pass_count}</td></tr>`
      ).join("");
      body.querySelectorAll("tr[data-id]").forEach(tr =>
        tr.addEventListener("click", () => selectLinkupTeammate(tr.dataset.id)));
    }
    const select = document.getElementById("linkup-select");
    if (select) select.innerHTML = linkupTeammates.map(t =>
      `<option value="${t.teammate_id}">${t.name} (${t.pass_count} passes)</option>`
    ).join("");

    await selectLinkupTeammate(linkupTeammates[0].teammate_id);
  } catch {
    if (body) body.innerHTML = `<tr><td colspan="2" style="color:var(--muted)">Could not load</td></tr>`;
  } finally {
    linkupLoading = false;
  }
}

async function selectLinkupTeammate(teammateId) {
  teammateId = String(teammateId);
  linkupActiveTeammateId = teammateId;
  document.querySelectorAll("#linkup-table-body tr[data-id]").forEach(tr =>
    tr.classList.toggle("active", tr.dataset.id === teammateId));
  const select = document.getElementById("linkup-select");
  if (select) select.value = teammateId;

  if (_linkupDetailCache[teammateId]) {
    renderLinkupDetail(_linkupDetailCache[teammateId]);
    return;
  }

  const spinner = document.getElementById("linkup-chart-spinner");
  const img = document.getElementById("linkup-chart-img");
  if (spinner) spinner.style.display = "block";
  if (img) img.style.display = "none";
  try {
    const res = await fetch("/api/linkup-detail", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        passer_id: linkupPasserId, teammate_id: teammateId,
        league: primaryLeague, season: primarySeason,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.chart) return;
    _linkupDetailCache[teammateId] = data;
    renderLinkupDetail(data);
  } catch { /* silent */ }
  finally { if (spinner) spinner.style.display = "none"; }
}

function renderLinkupDetail(data) {
  const s = data.stats;
  const statsRow = document.getElementById("linkup-stats-row");
  if (statsRow) statsRow.innerHTML = `
    <span class="profile-stat-chip goal-chip">Prog. Passes: ${s.prog_passes}</span>
    <span class="profile-stat-chip card-y-chip">Prog. Carries: ${s.prog_carries}</span>
    <span class="profile-stat-chip assist-chip">Take-Ons: ${s.take_ons_won}</span>
    <span class="profile-stat-chip apps-chip">Shots: ${s.shots}</span>
  `;
  const img = document.getElementById("linkup-chart-img");
  if (img) { img.src = `data:image/png;base64,${data.chart}`; img.style.display = "block"; }
}

// ─────────────────────────────────────────────────────────────────────────────
// Close any open dropdowns on outside click
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener("click", () => {
  document.querySelectorAll(".custom-dd.open").forEach(d => d.classList.remove("open"));
  document.querySelectorAll(".search-results.active").forEach(r => r.classList.remove("active"));
});

// Prevent search result closing when clicking inside the search card
document.querySelector(".search-card")?.addEventListener("click", e => e.stopPropagation());

// ─────────────────────────────────────────────────────────────────────────────
// Hint buttons (pre-fill search)
// ─────────────────────────────────────────────────────────────────────────────
document.querySelectorAll(".hint-btn").forEach(btn => {
  btn.addEventListener("click", e => {
    e.stopPropagation();
    const searchEl = document.getElementById("main-search");
    if (!searchEl) return;
    searchEl.value = btn.dataset.name;
    searchEl.dispatchEvent(new Event("input"));
    searchEl.focus();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Deep-link pre-fill (from Explore's "View Profile" links: ?player_id=&
// league=&season=)
// ─────────────────────────────────────────────────────────────────────────────
async function initFromQuery() {
  const params = new URLSearchParams(location.search);
  const pid = params.get("player_id");
  if (!pid) return;
  const league = params.get("league") || primaryLeague;
  const season = params.get("season") || primarySeason;
  try {
    const res = await fetch("/api/advanced-stats", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: pid, league, season }),
    });
    const data = await res.json();
    if (data.player) selectPrimaryPlayer({ ...data.player, league, season });
  } catch { /* silent — deep link just won't pre-select */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
initMainDropdown();
initMainSearch();
initFromQuery();

// Theme Toggle
const themeBtn = document.getElementById("theme-toggle");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const isLight = document.body.getAttribute("data-theme") === "light";
    document.body.setAttribute("data-theme", isLight ? "dark" : "light");
    themeBtn.textContent = isLight ? "🌙" : "☀️";
    localStorage.setItem("theme", isLight ? "dark" : "light");
  });
}

// Scroll-reveal is handled once, in base.html's initScrollAnimations().
