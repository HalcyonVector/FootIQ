/**
 * FootIQ — Player-first analytics
 *
 * Primary flow: search → auto-show stats
 * Secondary:    + Add Player to Compare → comparison mode
 */

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let primaryPlayer  = null;   // {id, name, photo, position, team, team_logo, age, nationality, appearances}
let primaryLeague  = "Premier League";
let primarySeason  = "2024-25";
let leagueAdjusted = true;   // league difficulty adjustment toggle state

let compareSlots   = [];     // [{slotEl, leagueId, seasonVal, player}]

const MAX_COMPARE  = 3;      // max extra players (so 4 total incl. primary)
const COLORS       = ["#3b82f6","#f43f5e","#10b981","#f59e0b"];
const SLOT_LABELS  = ["Player A","Player B","Player C","Player D"];

// ─────────────────────────────────────────────────────────────────────────────
// DOM refs
// ─────────────────────────────────────────────────────────────────────────────
const loadingOverlay  = document.getElementById("loading-overlay");
const toast           = document.getElementById("toast");
const profileSection  = document.getElementById("profile-section");
const chartsLoading   = document.getElementById("charts-loading");
const pctWrapper      = document.getElementById("pct-wrapper");
const chartsRow       = document.getElementById("charts-row");
const compareStrip    = document.getElementById("compare-strip");
const compareSection  = document.getElementById("compare-section");
const comparePRow     = document.getElementById("compare-players-row");
const addMoreBtn      = document.getElementById("add-more-btn");
const addMoreHint     = document.getElementById("add-more-hint");
const compareGoBtn    = document.getElementById("compare-go-btn");
const comparisonResults= document.getElementById("comparison-results");
const similarStrip    = document.getElementById("similar-strip");      // injected later

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 4500);
}
function showLoading(v) { loadingOverlay.style.display = v ? "flex" : "none"; }

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
    document.querySelectorAll(".custom-dd.open, .slot-dd.open").forEach(x => x !== dd && x.classList.remove("open"));
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
    if (q.length < 3) { resultsEl.innerHTML = ""; resultsEl.classList.remove("active"); return; }
    try {
      const url = `/api/search?name=${encodeURIComponent(q)}&league=${primaryLeague}&season=${primarySeason}${isGlobal === true ? '&all_leagues=1' : ''}`;
      const res  = await fetch(url);
      const data = await res.json();
      if (data.error) { showToast(data.error); return; }
      if (!data.length && !isGlobal) {
        // If not found in current league, retry globally
        return doSearch(true);
      } else if (!data.length) {
        resultsEl.innerHTML = `<div class="result-item" style="color:var(--muted);justify-content:center">No players found</div>`;
        resultsEl.classList.add("active"); return;
      }
      resultsEl.innerHTML = data.map(p => `
        <div class="result-item" data-id="${p.id}" data-player='${JSON.stringify(p).replace(/'/g,"&#39;")}'>
          <div class="result-item-icon">⚽</div>
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

// ─────────────────────────────────────────────────────────────────────────────
// Select primary player → auto-fetch stats
// ─────────────────────────────────────────────────────────────────────────────
async function selectPrimaryPlayer(player) {
  primaryPlayer = player;

  // Show profile section with header immediately
  profileSection.style.display = "block";
  renderProfileHeader(player);

  // Hide charts, show loading
  chartsLoading.style.display = "flex";
  pctWrapper.style.display    = "none";
  chartsRow.style.display     = "none";
  compareStrip.style.display  = "none";

  // Fetch stats (with branding support)
  try {
    const c1 = document.getElementById("export-color-1")?.value || "#3b82f6";
    const res  = await fetch("/api/player-stats", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ 
        player_id: player.id, 
        league: primaryLeague, 
        season: primarySeason,
        adjusted: leagueAdjusted,
        c1: c1
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      showToast(data.error || "Could not load stats.");
      chartsLoading.style.display = "none";
      return;
    }
    renderSoloStats(data);
  } catch { showToast("Network error."); chartsLoading.style.display = "none"; }

  // Fetch similar players (non-blocking)
  fetchSimilar(player);

  // Scroll to profile with navbar offset
  setTimeout(() => {
    const navH = document.querySelector(".navbar")?.offsetHeight || 70;
    const top = profileSection.getBoundingClientRect().top + window.scrollY - navH - 16;
    window.scrollTo({ top, behavior: "smooth" });
  }, 100);
}

function resetPrimaryPlayer() {
  primaryPlayer = null;
  profileSection.style.display = "none";
  const strip = document.getElementById("similar-strip");
  if (strip) strip.classList.remove("visible");
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
      <div class="profile-sub">${player.position} &middot; ${player.nationality} &middot; Age ${player.age}</div>
      <div class="profile-team">
        ${player.team_logo ? `<img src="${player.team_logo}" onerror="this.style.display='none'" />` : ""}
        <span>${player.team}</span>
        ${player.league ? `<span style="color:var(--muted)">&middot; ${player.league}</span>` : ""}
      </div>
      <div class="profile-season-stats" id="season-stats-row">
        <span class="profile-stat-chip apps-chip">📅 ${player.appearances || "–"} apps &middot; ${player.minutes || "–"} min</span>
      </div>
    </div>
    <div id="primary-score-chip">
      <div class="score-placeholder-pulse"></div>
    </div>
    <div id="similar-strip" class="similar-strip">
      <span class="similar-lbl">Similar:</span>
      <div id="similar-chips" class="similar-chips-inner" style="display:flex;gap:7px;flex-wrap:wrap"></div>
    </div>
  `;
}

function updateProfileSeasonStats(player) {
  const row = document.getElementById("season-stats-row");
  if (!row) return;
  // assists from older seasons may be stored as per-90 rate — convert to total
  const assistsVal = player.assists < 2 && player.minutes > 0
    ? Math.round(player.assists * player.minutes / 90)
    : Math.round(player.assists);
  const goalsVal = Math.round(player.goals);
  const gA = (player.goals !== undefined)
    ? `<span class="profile-stat-chip goal-chip">⚽ ${goalsVal} Goals</span><span class="profile-stat-chip assist-chip">🎯 ${assistsVal} Assists</span>`
    : '';
  const cards = (player.yellow_cards > 0 || player.red_cards > 0)
    ? `${player.yellow_cards > 0 ? `<span class="profile-stat-chip card-y-chip">🟨 ${player.yellow_cards} Yellow</span>` : ''}${player.red_cards > 0 ? `<span class="profile-stat-chip card-r-chip">🟥 ${player.red_cards} Red</span>` : ''}`
    : '';
  row.innerHTML = `
    <span class="profile-stat-chip apps-chip">📅 ${player.appearances} apps &middot; ${player.minutes} min</span>
    ${gA}
    ${cards}
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

function renderSoloStats(data) {
  const { player, stat_rows, charts } = data;

  // Fetch and apply profile photo client-side
  const profilePhoto = document.querySelector(".profile-photo");
  if (profilePhoto) applyWikiImage(player.name, player.team, profilePhoto);

  // Update score chip — include archetype badge
  const archetypeHtml = data.archetype
    ? `<div class="archetype-badge" style="margin-top:6px;font-size:12px;color:var(--muted);text-align:center;">${data.archetype}</div>`
    : "";
  document.getElementById("primary-score-chip").outerHTML = `
    <div class="profile-score" id="primary-score-chip">
      <div class="score-num">${player.score}</div>
      <div class="score-lbl">Composite Score</div>
      ${archetypeHtml}
    </div>
  `;

  // Show/hide adj-badge
  const adjBadge = document.getElementById("adj-badge");
  if (adjBadge) adjBadge.style.display = leagueAdjusted ? "block" : "none";

  // Update season stats chips (goals, assists, cards)
  updateProfileSeasonStats(player);

  chartsLoading.style.display = "none";

  // Inject limited-data warning for 2023-24
  const limitedBadgeId = "season-limited-warning";
  const existingBadge = document.getElementById(limitedBadgeId);
  if (existingBadge) existingBadge.remove();
  if (data.season_metric_set === "2023-24") {
    const badge = document.createElement("div");
    badge.id = limitedBadgeId;
    badge.style.cssText = "margin-bottom:10px;padding:8px 14px;background:rgba(234,179,8,0.12);border:1px solid rgba(234,179,8,0.35);border-radius:8px;color:#eab308;font-size:13px;";
    badge.textContent = "⚠️ Limited data available for this season";
    pctWrapper.insertAdjacentElement("beforebegin", badge);
  }

  // Percentile table
  renderPctTable([{
    player_name: player.name, team: player.team,
    photo: player.photo, stats: stat_rows,
  }], "pct-solo-table");
  pctWrapper.style.display = "block";

  // Render insight chips
  const insightsEl = document.getElementById("insights-section");
  if (insightsEl) {
    const insights = data.insights || [];
    if (insights.length) {
      insightsEl.style.display = "block";
      insightsEl.innerHTML = `
        <div class="glass-card" style="padding:16px 20px">
          <div class="pct-title-row" style="margin-bottom:12px">
            <span class="section-label">💡 Smart Insights</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:8px">
            ${insights.map(ins => {
              const isNeg = ins.startsWith("Below average");
              const bg    = isNeg ? "rgba(234,179,8,0.10)" : "rgba(16,185,129,0.10)";
              const border= isNeg ? "rgba(234,179,8,0.35)"  : "rgba(16,185,129,0.35)";
              const color = isNeg ? "#eab308"                : "#10b981";
              return `<div style="padding:8px 14px;background:${bg};border:1px solid ${border};border-radius:20px;color:${color};font-size:13px;">${ins}</div>`;
            }).join("")}
          </div>
        </div>`;
    } else {
      insightsEl.style.display = "none";
    }
  }

  // Solo Visual Duo (Pizza + Archetype)
  const pizza = document.getElementById("solo-pizza");
  const arche = document.getElementById("solo-archetype");
  if (pizza) pizza.src = `data:image/png;base64,${charts.pizza}`;
  if (arche) arche.src = `data:image/png;base64,${charts.archetype}`;

  // Efficiency chart (3rd, full-width)
  const effImg = document.getElementById("solo-efficiency");
  const effRow = document.getElementById("charts-row-eff");
  if (effImg && charts.efficiency) {
    effImg.src = `data:image/png;base64,${charts.efficiency}`;
    if (effRow) effRow.style.display = "flex";
  }

  chartsRow.style.display = "flex";
  compareStrip.style.display = "flex";
}


// ─────────────────────────────────────────────────────────────────────────────
// Similar players
// ─────────────────────────────────────────────────────────────────────────────
async function fetchSimilar(player) {
  try {
    const url  = `/api/similar?player_id=${player.id}&league=${primaryLeague}&season=${primarySeason}&position=${encodeURIComponent(player.position||"")}`;
    const res  = await fetch(url);
    const data = await res.json();
    if (!data.length) return;

    const chips = document.getElementById("similar-chips");
    const strip = document.getElementById("similar-strip");
    if (!chips || !strip) return;

    chips.innerHTML = data.map(p => `
      <div class="sim-chip" data-player='${JSON.stringify(p).replace(/'/g,"&#39;")}' data-name="${p.name}">
        <img class="sim-chip-img" src="" />
        <span>${p.name}</span>
      </div>
    `).join("");

    strip.classList.add("visible");

    chips.querySelectorAll(".sim-chip").forEach(chip => {
      chip.addEventListener("click", () => selectPrimaryPlayer(JSON.parse(chip.dataset.player)));
      // fetch image client-side
      const img = chip.querySelector(".sim-chip-img");
      const p = JSON.parse(chip.dataset.player);
      applyWikiImage(p.name, p.team, img);
    });
  } catch { /* non-critical */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// Compare mode
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById("add-compare-btn").addEventListener("click", () => {
  compareSection.style.display = "block";
  // Populate primary slot
  renderPrimarySlot();
  // Add first comparison slot
  if (compareSlots.length === 0) addCompareSlot();
  updateCompareUI();
  setTimeout(() => {
    const navH = document.querySelector(".navbar")?.offsetHeight || 70;
    const top = compareSection.getBoundingClientRect().top + window.scrollY - navH - 16;
    window.scrollTo({ top, behavior: "smooth" });
  }, 120);
});

document.getElementById("close-compare-btn").addEventListener("click", () => {
  compareSection.style.display = "none";
  compareSlots = [];
  comparisonResults.style.display = "none";
  comparePRow.querySelectorAll(".compare-slot:not(.primary-slot), .vs-badge").forEach(el => el.remove());
});

function renderPrimarySlot() {
  if (!primaryPlayer) return;
  const el = document.getElementById("compare-slot-primary");
  el.innerHTML = `
    <div class="slot-label">Player A · Primary</div>
    <div class="slot-player-inner" style="display:flex;align-items:center;gap:10px;padding:8px 0">
      <img class="slot-photo primary-slot-img" data-name="${primaryPlayer.name}" src="" style="border-color:var(--c0)" />
      <div class="slot-info">
        <div class="slot-name">${primaryPlayer.name}</div>
        <div class="slot-detail">${primaryPlayer.team} · ${primaryPlayer.position}</div>
      </div>
    </div>
    <div style="font-size:11px;color:var(--muted);margin-top:4px">League set in main search</div>
  `;
  applyWikiImage(primaryPlayer.name, primaryPlayer.team, el.querySelector(".primary-slot-img"));
}

function addCompareSlot() {
  if (compareSlots.length >= MAX_COMPARE) return;

  const slotIdx  = compareSlots.length + 1;
  const defaultLg = slotIdx === 1 ? "La Liga" : "Premier League";
  const defaultLgData = window.LEAGUES.find(l => l.id === defaultLg);

  const slot = document.createElement("div");
  slot.className = `compare-slot slot-${slotIdx}`;

  const seasonOpts = window.SEASONS.map(s => `<option value="${s}" ${String(s)===primarySeason?"selected":""}>${s}</option>`).join("");
  const ddItems    = window.LEAGUES.map(lg => `
    <div class="slot-dd-item ${lg.id===defaultLg?"active":""}" data-value="${lg.id}" data-logo="${lg.logo}" data-name="${lg.name}">
      <img src="${lg.logo}" class="dd-mini-logo" alt="" /><span>${lg.name}</span>
    </div>
  `).join("");

  slot.innerHTML = `
    <div class="slot-label">${SLOT_LABELS[slotIdx]}</div>
    <div class="slot-filters">
      <div class="slot-dd" id="slot-dd-${slotIdx}">
        <div class="slot-dd-sel" id="slot-dd-sel-${slotIdx}">
          <img src="${defaultLgData.logo}" class="dd-mini-logo" alt="" />
          <span style="flex:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${defaultLgData.name}</span>
          <span class="slot-dd-arrow">▾</span>
        </div>
        <div class="slot-dd-menu" id="slot-dd-menu-${slotIdx}">${ddItems}</div>
      </div>
      <select class="slot-season-sel" id="slot-season-${slotIdx}">${seasonOpts}</select>
      <input type="hidden" id="slot-league-${slotIdx}" value="${defaultLg}" />
    </div>
    <div class="slot-search-wrap">
      <span class="slot-search-icon">🔍</span>
      <input type="text" class="slot-search" id="slot-search-${slotIdx}" placeholder="Search player…" autocomplete="off" />
      <div class="search-results" id="slot-results-${slotIdx}"></div>
    </div>
    <div class="slot-player-card" id="slot-card-${slotIdx}">
      <span class="slot-placeholder">No player selected</span>
    </div>
    <button class="slot-remove" data-slot="${slotIdx}">✕ Remove this slot</button>
  `;

  const slotData = { slotIdx, leagueId: String(defaultLg), seasonVal: primarySeason, player: null };
  compareSlots.push(slotData);

  // Always add a VS badge before each new comparison slot
  const vsBadge = document.createElement("div");
  vsBadge.className = "vs-badge";
  vsBadge.textContent = "VS";
  comparePRow.appendChild(vsBadge);
  comparePRow.appendChild(slot);

  // Wire dropdown
  const dd    = document.getElementById(`slot-dd-${slotIdx}`);
  const ddSel = document.getElementById(`slot-dd-sel-${slotIdx}`);
  const ddMen = document.getElementById(`slot-dd-menu-${slotIdx}`);
  const lgInp = document.getElementById(`slot-league-${slotIdx}`);

  ddSel.addEventListener("click", e => {
    e.stopPropagation();
    document.querySelectorAll(".custom-dd.open,.slot-dd.open").forEach(x => x !== dd && x.classList.remove("open"));
    dd.classList.toggle("open");
  });
  ddMen.querySelectorAll(".slot-dd-item").forEach(item => {
    item.addEventListener("click", () => {
      slotData.leagueId = item.dataset.value;
      lgInp.value = item.dataset.value;
      ddSel.innerHTML = `<img src="${item.dataset.logo}" class="dd-mini-logo" alt="" /><span style="flex:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${item.dataset.name}</span><span class="slot-dd-arrow">▾</span>`;
      dd.classList.remove("open");
      ddMen.querySelectorAll(".slot-dd-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      if (slotData.player) clearSlotPlayer(slotIdx);
    });
  });

  document.getElementById(`slot-season-${slotIdx}`)?.addEventListener("change", e => {
    slotData.seasonVal = e.target.value;
    if (slotData.player) clearSlotPlayer(slotIdx);
  });

  // Wire search
  const srch = document.getElementById(`slot-search-${slotIdx}`);
  const resl = document.getElementById(`slot-results-${slotIdx}`);
  const doSearch = debounce(async () => {
    const q = srch.value.trim();
    if (q.length < 3) { resl.innerHTML = ""; resl.classList.remove("active"); return; }
    try {
      const res  = await fetch(`/api/search?name=${encodeURIComponent(q)}&league=${slotData.leagueId}&season=${slotData.seasonVal}`);
      const data = await res.json();
      if (!data.length) {
        resl.innerHTML = `<div class="result-item" style="color:var(--muted);justify-content:center">No players found</div>`;
        resl.classList.add("active"); return;
      }
      resl.innerHTML = data.map(p => `
        <div class="result-item" data-id="${p.id}" data-player='${JSON.stringify(p).replace(/'/g,"&#39;")}'>
          <div class="result-item-icon">⚽</div>
          <div>
            <div class="result-name">${p.name}</div>
            <div class="result-meta">${p.team} · ${p.position}</div>
          </div>
        </div>
      `).join("");
      resl.classList.add("active");
    } catch {}
  }, 380);
  srch.addEventListener("input", doSearch);
  resl.addEventListener("click", e => {
    const item = e.target.closest(".result-item[data-id]");
    if (!item) return;
    selectSlotPlayer(JSON.parse(item.dataset.player), slotIdx);
    resl.classList.remove("active");
    srch.value = "";
  });

  // Remove button
  slot.querySelector(".slot-remove").addEventListener("click", () => {
    compareSlots = compareSlots.filter(s => s.slotIdx !== slotIdx);
    vsBadge.remove(); slot.remove();
    updateCompareUI();
  });

  updateCompareUI();
}

function selectSlotPlayer(player, slotIdx) {
  const slotData = compareSlots.find(s => s.slotIdx === slotIdx);
  if (!slotData) return;
  slotData.player = player;

  const card = document.getElementById(`slot-card-${slotIdx}`);
  card.innerHTML = `
    <div class="slot-player-inner">
      <img class="slot-photo slot-wiki-img" data-name="${player.name}" src="" />
      <div class="slot-info">
        <div class="slot-name">${player.name}</div>
        <div class="slot-detail">${player.team} · ${player.position}</div>
      </div>
      <button class="slot-clear" data-slot="${slotIdx}">✕</button>
    </div>
  `;
  card.classList.add("filled");
  document.getElementById(`slot-card-${slotIdx}`).parentElement.classList.add("filled-slot");
  card.querySelector(".slot-clear").addEventListener("click", () => clearSlotPlayer(slotIdx));
  // fetch photo async
  applyWikiImage(player.name, player.team, card.querySelector(".slot-wiki-img"));
  updateCompareUI();
}

function clearSlotPlayer(slotIdx) {
  const slotData = compareSlots.find(s => s.slotIdx === slotIdx);
  if (slotData) slotData.player = null;
  const card = document.getElementById(`slot-card-${slotIdx}`);
  if (card) { 
    card.innerHTML = `<span class="slot-placeholder">No player selected</span>`; 
    card.classList.remove("filled"); 
    card.parentElement.classList.remove("filled-slot");
  }
  updateCompareUI();
}

function updateCompareUI() {
  const filled = compareSlots.filter(s => s.player !== null).length;
  compareGoBtn.disabled = filled === 0;
  addMoreBtn.disabled   = compareSlots.length >= MAX_COMPARE;
  addMoreHint.textContent = `${compareSlots.length + 1} of ${MAX_COMPARE + 1} players`;
}

addMoreBtn.addEventListener("click", () => {
  if (compareSlots.length < MAX_COMPARE) addCompareSlot();
});

// ─────────────────────────────────────────────────────────────────────────────
// Generate comparison
// ─────────────────────────────────────────────────────────────────────────────
compareGoBtn.addEventListener("click", async () => {
  const filled = compareSlots.filter(s => s.player !== null);
  if (!primaryPlayer || filled.length === 0) return;

  showLoading(true);
  comparisonResults.style.display = "none";

  const specs = [
    { id: primaryPlayer.id, league: primaryLeague, season: primarySeason },
    ...filled.map(s => ({ id: s.player.id, league: s.leagueId, season: s.seasonVal })),
  ];

  try {
    const c1 = document.getElementById("export-color-1")?.value || "#3b82f6";
    const c2 = document.getElementById("export-color-2")?.value || "#f43f5e";
    const c3 = document.getElementById("export-color-3")?.value || "#10b981";
    const c4 = document.getElementById("export-color-4")?.value || "#f59e0b";
    const res  = await fetch("/api/compare", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ players: specs, adjusted: leagueAdjusted, c1: c1, c2: c2, c3: c3, c4: c4 }),
    });
    const data = await res.json();
    if (!res.ok || data.error) { showToast(data.error || "Comparison failed."); return; }
    renderComparison(data);
  } catch { showToast("Network error."); }
  finally   { showLoading(false); }
});

function renderComparison(data) {
  const { players, scores, winner_idx, stat_table, pct_table, charts } = data;

  // Score cards — all centered, winner gets neon glow
  const colors = [
    document.getElementById("export-color-1")?.value || "#3b82f6",
    document.getElementById("export-color-2")?.value || "#f43f5e",
    document.getElementById("export-color-3")?.value || "#10b981",
    document.getElementById("export-color-4")?.value || "#f59e0b",
  ];
  document.getElementById("score-cards-row").innerHTML = players.map((pl, i) => {
    const isWinner = i === winner_idx;
    const color = colors[i] || colors[0];
    const archetypeHtml = pl.archetype
      ? `<div style="font-size:11px;color:var(--muted);margin-top:6px;">${pl.archetype}</div>`
      : "";
    const insightHtml = (pl.insights && pl.insights[0])
      ? `<div style="margin-top:8px;padding:6px 10px;background:rgba(255,255,255,0.04);border-radius:10px;font-size:11px;color:var(--muted);text-align:center;max-width:160px;">${pl.insights[0]}</div>`
      : "";
    return `
    <div class="score-card" data-idx="${i}" style="
      flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
      padding:24px 16px; border-radius:16px; position:relative;
      background:${isWinner ? `rgba(${i===0?'59,130,246':i===1?'244,63,94':i===2?'16,185,129':'245,158,11'},0.08)` : 'rgba(255,255,255,0.03)'};
      border:1.5px solid ${isWinner ? color : 'rgba(255,255,255,0.07)'};
      box-shadow:${isWinner ? `0 0 24px ${color}44, 0 0 8px ${color}22` : 'none'};
      transition:all 0.3s;
    ">
      ${isWinner ? `<div style="position:absolute;top:10px;right:12px;font-size:18px;">🏆</div>` : ''}
      <img class="sc-photo" data-name="${pl.name}" src="" style="
        width:60px;height:60px;border-radius:50%;object-fit:cover;margin-bottom:12px;
        border:2px solid ${color};
        box-shadow:${isWinner ? `0 0 12px ${color}66` : 'none'};
      " onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'60\\' height=\\'60\\'%3E%3Ccircle cx=\\'30\\' cy=\\'30\\' r=\\'30\\' fill=\\'%231e2535\\'/%3E%3C/svg%3E'" />
      <div style="font-size:15px;font-weight:700;color:var(--text);text-align:center;margin-bottom:8px;">${pl.name}</div>
      <div style="font-size:32px;font-weight:900;color:${color};line-height:1;">${scores[i]}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted);margin-top:4px;">Composite Score</div>
      ${archetypeHtml}
      ${insightHtml}
    </div>`;
  }).join("");

  // Fetch photos for score cards
  document.querySelectorAll(".sc-photo").forEach(img => {
    const idx = img.closest(".score-card").dataset.idx;
    applyWikiImage(players[idx].name, players[idx].team, img);
  });

  // Inject comparison mode label above percentile table
  const modeLabelEl = document.getElementById("comparison-mode-label");
  if (modeLabelEl) {
    const modeText = data.comparison_mode === "modern"
      ? "Full Modern Stats (2024-25)"
      : "Universal Per-90 Stats (Cross-Season)";
    modeLabelEl.innerHTML = `<div style="margin-bottom:10px;padding:7px 14px;background:rgba(59,130,246,0.10);border:1px solid rgba(59,130,246,0.30);border-radius:8px;color:#93c5fd;font-size:13px;">📊 ${modeText}</div>`;
  }

  // DataMB percentile table
  renderPctTable(pct_table, "pct-compare-table");

  // Stat table
  const thead = document.getElementById("stat-thead");
  const tbody  = document.getElementById("stat-tbody");
  thead.innerHTML = `<th class="stat-lbl">Stat</th>` +
    players.map((pl,i) => `<th class="th-name" data-idx="${i}">${pl.name}</th>`).join("");
  tbody.innerHTML = stat_table.map(row => {
    const cells = row.values.map((v,i) =>
      `<td class="${i===row.winner_idx?`w-${i}`:""}">${v.value}</td>`
    ).join("");
    return `<tr><td class="stat-lbl">${row.label}</td>${cells}</tr>`;
  }).join("");

  // Charts
  ["cmp-radar","cmp-bar","cmp-lollipop","cmp-percentile"].forEach((id, i) => {
    const keys = ["radar","bar","lollipop","percentile"];
    const el = document.getElementById(id);
    if (el && charts[keys[i]]) el.src = `data:image/png;base64,${charts[keys[i]]}`;
  });

  comparisonResults.style.display = "block";
  setTimeout(() => {
    const navH = document.querySelector(".navbar")?.offsetHeight || 70;
    const top = comparisonResults.getBoundingClientRect().top + window.scrollY - navH - 16;
    window.scrollTo({ top, behavior: "smooth" });
  }, 120);

  window._lastCharts = charts;
  window._lastNames  = players.map(p => p.name);
}

// ─────────────────────────────────────────────────────────────────────────────
// DataMB percentile table renderer
// ─────────────────────────────────────────────────────────────────────────────
function renderPctTable(rows, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !rows.length) return;
  const labels = rows[0].stats.map(s => s.label);

  el.innerHTML = `
    <table class="pct-table">
      <thead>
        <tr>
          <th>Player Profile</th>
          ${labels.map(l=>`<th>${l}</th>`).join("")}
        </tr>
      </thead>
      <tbody>
        ${rows.map(row => `
          <tr>
            <td>
              <div class="pct-player-cell">
                <div>
                  <div class="pct-player-name">${row.player_name}</div>
                  <div class="pct-player-team">${row.team||""}</div>
                </div>
              </div>
            </td>
            ${row.stats.map(s => {
              const color = percentileColor(s.percentile);
              const noData = s.value === 0 || s.value === null;
              return `
                <td>
                  <div class="pct-dashboard-cell">
                    <div class="pct-val-row">
                      <span class="pct-cell-val" style="color:${noData ? 'var(--muted)' : color}">${noData ? '—' : s.value}</span>
                    </div>
                    <div class="pct-bar-bg">
                      <div class="pct-bar-fill" style="width:${noData ? 0 : Math.min(s.percentile,100)}%; background:${color}; box-shadow: 0 0 10px ${color}44;"></div>
                    </div>
                    <span class="pct-cell-label">${noData ? 'No data' : s.percentile + 'th Pct'}</span>
                  </div>
                </td>`;
            }).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// Close any open dropdowns on outside click
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener("click", () => {
  document.querySelectorAll(".custom-dd.open,.slot-dd.open").forEach(d => d.classList.remove("open"));
  document.querySelectorAll(".search-results.active").forEach(r => r.classList.remove("active"));
});

// Prevent search result / dropdown closing when clicking inside them
document.querySelectorAll(".search-card,.compare-players-row").forEach(el => {
  el.addEventListener("click", e => e.stopPropagation());
});

// ─────────────────────────────────────────────────────────────────────────────
// Export
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById("export-btn")?.addEventListener("click", () => {
  if (!window._lastCharts) return;
  const label = (window._lastNames || []).map(n => n.split(" ").pop()).join("_vs_");
  [["radar",`${label}_radar.png`],["bar",`${label}_bar.png`],["lollipop",`${label}_lollipop.png`],["percentile",`${label}_percentile.png`]]
    .forEach(([k,fn]) => {
      if (!window._lastCharts[k]) return;
      const a = document.createElement("a");
      a.href = `data:image/png;base64,${window._lastCharts[k]}`; a.download = fn; a.click();
    });
});

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

// Stop search card clicks from closing dropdowns
document.querySelector(".search-card")?.addEventListener("click", e => e.stopPropagation());

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
initMainDropdown();
initMainSearch();

// League adjustment toggle
document.addEventListener("change", e => {
  if (e.target.id !== "league-adj-toggle") return;
  leagueAdjusted = e.target.checked;
  if (primaryPlayer) selectPrimaryPlayer(primaryPlayer);
});

// ─────────────────────────────────────────────────────────────────────────────
// Interactive Chart Logic (Angle-based Tooltips)
// ─────────────────────────────────────────────────────────────────────────────
let currentPlayerData = null;

function initVisualInteractions() {
  const tooltip = document.getElementById("chart-tooltip");
  
  ["card-pizza", "card-archetype"].forEach(id => {
    const card = document.getElementById(id);
    if (!card) return;
    const img = card.querySelector("img");

    card.addEventListener("mousemove", (e) => {
      if (!currentPlayerData) return;
      
      const rect = img.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      
      // Distance check (only show tooltip if near the chart center)
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < 40 || dist > rect.width * 0.45) {
        tooltip.style.display = "none";
        return;
      }

      // 1. Convert mouse coordinates to Matplotlib-style degrees
      // atan2(dy, dx) gives radians from horizontal right (East). 
      // We negate dy because web Y is positive DOWN, whereas math Y is positive UP.
      let deg = Math.atan2(-dy, dx) * 180 / Math.PI;
      if (deg < 0) deg += 360; // Now deg is 0-360 CCW starting from RIGHT (East)

      let label = "", val = "", pct = "";

      if (id === "card-pizza" && currentPlayerData.stat_rows) {
        // Pizza starts at TOP (90 deg). We shift the angle so 0 is Top.
        // We use Math.floor because segments are centered ON the angles
        let pizzaDeg = (deg - 90 + 360) % 360; 
        const n = currentPlayerData.stat_rows.length;
        const sliceSize = 360 / n;
        const idx = Math.floor((pizzaDeg + sliceSize/2) / sliceSize) % n;
        const item = currentPlayerData.stat_rows[idx];
        label = item.label;
        val   = item.value;
        pct   = `${item.percentile}th Pct`;
      } else if (id === "card-archetype" && currentPlayerData.archetype_scores) {
        // Radar axes: (0=Attack, 72=Creation, 144=Progression, 216=Technical, 288=Defense)
        // Hardcoded labels to guarantee order parity with backend visuals
        const labels = ["Attack", "Creation", "Progression", "Technical", "Defense"];
        const n = labels.length;
        const sliceSize = 360 / n;
        
        // Match standard CCW indexing starting from RIGHT (0 deg)
        const idx = Math.floor((deg + sliceSize/2) / sliceSize) % n;
        label = labels[idx];
        const valRaw = currentPlayerData.archetype_scores[label] || 0;
        val   = (valRaw * 10).toFixed(1);
        pct   = `${Math.round(valRaw * 100)}th Pct`;
      }

      if (label) {
        tooltip.style.display = "block";
        tooltip.style.left = (e.clientX + 15) + "px";
        tooltip.style.top = (e.clientY + 15) + "px";
        document.getElementById("ct-label").textContent = label;
        document.getElementById("ct-val").textContent = val;
        document.getElementById("ct-pct").textContent = pct;
      }
    });

    card.addEventListener("mouseleave", () => {
      tooltip.style.display = "none";
    });
  });
}

// Update renderSoloStats to store data for interactions
const originalRenderSoloStats = renderSoloStats;
renderSoloStats = function(data) {
  currentPlayerData = data;
  originalRenderSoloStats(data);
  initVisualInteractions();
};

// Theme Toggle
const themeBtn = document.getElementById("theme-toggle");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const isLight = document.body.getAttribute("data-theme") === "light";
    document.body.setAttribute("data-theme", isLight ? "dark" : "light");
    themeBtn.textContent = isLight ? "🌙" : "☀️";
  });
}

// Scroll animation observer (futuristic fade up)
const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add("scroll-animate-visible");
    }
  });
}, { threshold: 0.1 });

// Apply to elements gently
setTimeout(() => {
  document.querySelectorAll(".glass-card, .step, .league-badge, .stat-item, .section-heading").forEach((el) => {
    el.classList.add("scroll-animate");
    observer.observe(el);
  });
}, 100);

// ─────────────────────────────────────────────────────────────────────────────
// Brand Color Live Refresh
// ─────────────────────────────────────────────────────────────────────────────
["export-color-1", "export-color-2", "export-color-3", "export-color-4"].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", debounce(() => {
    // If comparison results are visible, refresh comparison
    if (comparisonResults.style.display === "block") {
      compareGoBtn.click();
    } 
    // Otherwise if a primary player is loaded, refresh solo view
    else if (primaryPlayer) {
      selectPrimaryPlayer(primaryPlayer);
    }
  }, 500));
});

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}
