/**
 * FootIQ — Compare page. Up to 4 independent (league, season, player) slots,
 * POSTed together to /api/compare-stats, rendered as a radar + a full
 * per-category stat-table breakdown (one column per player).
 */

const CATEGORY_ORDER = [
  "passing", "shooting", "carrying", "half_spaces", "tempo", "decision_making",
  "final_third", "aerial", "defending", "holdup", "post_recovery", "goalkeeping",
];
const CATEGORY_LABELS = {
  passing: "Passing Profile", shooting: "Shooting & Footedness", carrying: "Carrying Profile",
  half_spaces: "Half-Spaces", tempo: "Tempo Control", decision_making: "Decision Making",
  final_third: "Final Third", aerial: "Aerial Duels", defending: "Defending Profile",
  holdup: "Hold-Up Play", post_recovery: "Post-Recovery", goalkeeping: "Goalkeeping",
};
const SLOT_COLORS = ["#3b82f6", "#f43f5e", "#10b981", "#f59e0b"];

let slots = [
  { league: "Premier League", season: (window.SEASONS && window.SEASONS[0]) || "2024-25", player: null },
  { league: "Premier League", season: (window.SEASONS && window.SEASONS[0]) || "2024-25", player: null },
];
let lastResult = null;

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

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function _initialsAvatar(name, size = 38) {
  const initials = (name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${size}' height='${size}' viewBox='0 0 ${size} ${size}'><circle cx='${size/2}' cy='${size/2}' r='${size/2}' fill='#3b82f622'/><text x='${size/2}' y='${size/2+size*0.15}' text-anchor='middle' font-family='system-ui,sans-serif' font-size='${size*0.34}' font-weight='700' fill='#3b82f6'>${initials}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// Cards render immediately with the initials placeholder above — the real
// Wikipedia photo is fetched in the background and swapped in once ready,
// same lazy pattern as player.html/scout.html (never block the card itself
// on a network round-trip to Wikipedia).
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

// ─────────────────────────────────────────────────────────────────────────────
// Slot rendering
// ─────────────────────────────────────────────────────────────────────────────
function renderSlots() {
  const container = document.getElementById("compare-slots");
  const leagues = window.LEAGUES || [];
  const seasons = window.SEASONS || [];

  container.innerHTML = slots.map((slot, idx) => {
    const removable = idx > 1;  // slots 0/1 are the required minimum and can only be cleared, not deleted
    return `
    <div class="compare-slot${idx === 0 ? " primary-slot" : ""}" data-idx="${idx}">
      ${removable ? `<button class="slot-remove-btn" data-remove="${idx}" type="button" title="Remove this player slot">✕</button>` : ""}
      <div class="slot-label">Player ${idx + 1}</div>
      ${slot.player ? `
        <div class="slot-player-card filled">
          <div class="slot-player-inner">
            <img class="slot-photo" src="${slot.player.photo || _initialsAvatar(slot.player.name)}"
                 onerror="this.src='${_initialsAvatar(slot.player.name)}'" />
            <div class="slot-info">
              <div class="slot-name">${slot.player.name}</div>
              <div class="slot-detail">${slot.player.team} · ${slot.league} · ${slot.season}</div>
            </div>
            ${!removable ? `<button class="slot-clear" data-clear="${idx}" type="button" title="Clear this player">✕</button>` : ""}
          </div>
        </div>
      ` : `
        <div class="slot-filters">
          <select class="slot-season-sel" data-league-idx="${idx}">
            ${leagues.map(lg => `<option value="${lg.id}" ${lg.id === slot.league ? "selected" : ""}>${lg.name}</option>`).join("")}
          </select>
          <select class="slot-season-sel" data-season-idx="${idx}">
            ${seasons.map(s => `<option value="${s}" ${s === slot.season ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </div>
        <div class="slot-search-wrap">
          <span class="slot-search-icon">🔍</span>
          <input class="slot-search" data-search-idx="${idx}" placeholder="Search player…" autocomplete="off" />
          <div class="search-results" data-results-idx="${idx}"></div>
        </div>
        <div class="slot-player-card"><span class="slot-placeholder">No player selected</span></div>
      `}
    </div>
  `;
  }).join("");

  container.querySelectorAll("[data-league-idx]").forEach(sel =>
    sel.addEventListener("change", e => { slots[+e.target.dataset.leagueIdx].league = e.target.value; }));
  container.querySelectorAll("[data-season-idx]").forEach(sel =>
    sel.addEventListener("change", e => { slots[+e.target.dataset.seasonIdx].season = e.target.value; }));
  container.querySelectorAll("[data-clear]").forEach(btn =>
    btn.addEventListener("click", () => { slots[+btn.dataset.clear].player = null; renderSlots(); updateGoButton(); }));
  container.querySelectorAll("[data-remove]").forEach(btn =>
    btn.addEventListener("click", () => { slots.splice(+btn.dataset.remove, 1); renderSlots(); updateGoButton(); updateAddButton(); }));

  slots.forEach((slot, idx) => {
    if (!slot.player || slot.player.photo) return;  // already has a real photo (e.g. deep-linked from Scout)
    const img = container.querySelector(`.compare-slot[data-idx="${idx}"] .slot-photo`);
    applyWikiImage(slot.player.name, slot.player.team, img).then(() => {
      // cache the resolved URL onto slot state so future re-renders (adding
      // another slot, changing a different slot's league) don't re-fetch it
      if (img && img.src && img.src.startsWith("http")) slot.player.photo = img.src;
    });
  });

  container.querySelectorAll("[data-search-idx]").forEach(input => {
    const idx = +input.dataset.searchIdx;
    const resultsEl = container.querySelector(`[data-results-idx="${idx}"]`);
    const doSearch = debounce(async () => {
      const q = input.value.trim();
      if (q.length < 2) { resultsEl.innerHTML = ""; resultsEl.classList.remove("active"); return; }
      try {
        const url = `/api/search?name=${encodeURIComponent(q)}&league=${slots[idx].league}&season=${slots[idx].season}`;
        const res = await fetch(url);
        const data = await res.json();
        if (!Array.isArray(data) || !data.length) {
          resultsEl.innerHTML = `<div class="result-item" style="color:var(--muted);justify-content:center">No players found</div>`;
          resultsEl.classList.add("active");
          return;
        }
        resultsEl.innerHTML = data.map(p => `
          <div class="result-item" data-player='${JSON.stringify(p).replace(/'/g, "&#39;")}'>
            <div class="result-item-icon">${p.name.charAt(0).toUpperCase()}</div>
            <div><div class="result-name">${p.name}</div><div class="result-meta">${p.team} · ${p.position}</div></div>
          </div>
        `).join("");
        resultsEl.classList.add("active");
      } catch { /* silent */ }
    }, 380);
    input.addEventListener("input", doSearch);
    resultsEl.addEventListener("click", e => {
      const item = e.target.closest(".result-item[data-player]");
      if (!item) return;
      const p = JSON.parse(item.dataset.player);
      slots[idx].player = p;
      slots[idx].league = slots[idx].league; // league/season already match the search scope
      renderSlots();
      updateGoButton();
    });
  });
}

function updateGoButton() {
  const goBtn = document.getElementById("compare-go-btn");
  const filled = slots.filter(s => s.player).length;
  goBtn.disabled = filled < 2;
}

function updateAddButton() {
  const btn = document.getElementById("add-slot-btn");
  const hint = document.getElementById("add-slot-hint");
  btn.disabled = slots.length >= 4;
  hint.textContent = slots.length >= 4 ? "Maximum 4 players" : `${slots.length}/4 players`;
}

document.getElementById("add-slot-btn").addEventListener("click", () => {
  if (slots.length >= 4) return;
  const seasons = window.SEASONS || [];
  slots.push({ league: "Premier League", season: seasons[0] || "2024-25", player: null });
  renderSlots();
  updateGoButton();
  updateAddButton();
});

document.addEventListener("click", e => {
  if (!e.target.closest(".slot-search-wrap")) {
    document.querySelectorAll(".compare-slot .search-results.active").forEach(r => r.classList.remove("active"));
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Run comparison
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById("compare-go-btn").addEventListener("click", runCompare);

async function runCompare() {
  const filled = slots.filter(s => s.player);
  if (filled.length < 2) return;
  const goBtn = document.getElementById("compare-go-btn");
  goBtn.disabled = true;
  goBtn.textContent = "Comparing…";
  try {
    const res = await fetch("/api/compare-stats", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ players: filled.map(s => ({ player_id: s.player.id, league: s.league, season: s.season })) }),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      document.getElementById("toast").textContent = data.error || "Comparison failed.";
      document.getElementById("toast").classList.add("show");
      setTimeout(() => document.getElementById("toast").classList.remove("show"), 4000);
      return;
    }
    lastResult = data;
    renderResults(data);
    document.getElementById("compare-results").style.display = "block";
    document.getElementById("compare-results").scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    goBtn.disabled = false;
    goBtn.textContent = "Compare";
  }
}

function renderResults(data) {
  const players = data.players;

  document.getElementById("compare-players-header").innerHTML = players.map((p, i) => {
    const score = p.composite && p.composite.score !== null ? p.composite.score : "—";
    return `
      <div class="cph-card" data-idx="${i % 4}">
        <img class="cph-photo" data-name="${p.name}" data-team="${p.team}" src="${_initialsAvatar(p.name, 46)}"
             onerror="this.src='${_initialsAvatar(p.name, 46)}'" alt="${p.name}" />
        <div class="cph-info">
          <div class="cph-name">${p.name}</div>
          <div class="cph-meta">${p.team} · ${p.position} · ${p.league} ${p.season}</div>
        </div>
        <div class="cph-score">
          <div class="cph-score-val">${score}</div>
          <div class="cph-score-lbl">Rating</div>
        </div>
      </div>
    `;
  }).join("");
  document.querySelectorAll("#compare-players-header .cph-photo[data-name]").forEach(img => {
    applyWikiImage(img.dataset.name, img.dataset.team, img);
  });

  const chartGrid = document.getElementById("compare-chart-grid");
  chartGrid.innerHTML = (data.charts || []).map(c => `
    <div class="adv-chart-tile">
      <div class="adv-chart-tile-title">${c.title}</div>
      <div class="adv-chart-tile-body"><img class="chart-img" src="data:image/png;base64,${c.image}" alt="${c.title}" /></div>
    </div>
  `).join("");

  const presentCats = CATEGORY_ORDER.filter(key => players.some(p => p.cats.some(c => c.key === key)));

  document.getElementById("compare-tabs").innerHTML = presentCats.map((key, i) =>
    `<button class="adv-tab-btn${i === 0 ? " active" : ""}" data-cat="${key}">${CATEGORY_LABELS[key]}</button>`
  ).join("");

  document.getElementById("compare-panels").innerHTML = presentCats.map((key, i) => `
    <div class="adv-panel" data-cat="${key}" style="display:${i === 0 ? "block" : "none"}">
      ${renderCategoryTable(key, players)}
    </div>
  `).join("");

  document.querySelectorAll("#compare-tabs .adv-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#compare-tabs .adv-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      btn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      document.querySelectorAll("#compare-panels .adv-panel").forEach(p =>
        p.style.display = p.dataset.cat === btn.dataset.cat ? "block" : "none");
    });
  });
}

function renderCategoryTable(catKey, players) {
  // Row label order: the first player who actually has this category.
  const source = players.find(p => p.cats.some(c => c.key === catKey));
  const cat = source.cats.find(c => c.key === catKey);
  const labels = (cat.rows[0].stats || []).map(s => s.label);

  const perPlayerStats = players.map(p => {
    const c = p.cats.find(c => c.key === catKey);
    const stats = c ? (c.rows[0].stats || []) : [];
    const byLabel = {};
    stats.forEach(s => { byLabel[s.label] = s; });
    return byLabel;
  });

  const rowsHtml = labels.map(label => {
    const cells = perPlayerStats.map(byLabel => byLabel[label]);
    const validPct = cells.map(c => (c && !c.no_data) ? c.percentile : null);
    const maxPct = Math.max(...validPct.filter(v => v !== null), -1);
    const cellsHtml = cells.map((s, i) => {
      if (!s || s.no_data) return `<td class="stat-lbl">—</td>`;
      const isWinner = s.percentile === maxPct && maxPct >= 0;
      return `<td class="w-${i % 4}${isWinner ? " winner-cell" : ""}">${s.value}${s.unit || ""}</td>`;
    }).join("");
    return `<tr><td class="stat-lbl">${label}</td>${cellsHtml}</tr>`;
  }).join("");

  const headerCells = players.map((p, i) => `<th class="th-name" data-idx="${i % 4}">${p.name}</th>`).join("");

  return `
    <div class="stat-table-wrapper">
      <div class="table-scroll">
        <table class="stat-table">
          <thead><tr><th></th>${headerCells}</tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// Deep-link pre-fill (from Scout's "Compare →" links: ?p1_id=&p1_league=&
// p1_season=&p2_id=&p2_league=&p2_season=)
// ─────────────────────────────────────────────────────────────────────────────
async function hydratePlayer(id, league, season) {
  try {
    const res = await fetch("/api/advanced-stats", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: id, league, season }),
    });
    const data = await res.json();
    return data.player || null;
  } catch { return null; }
}

async function initFromQuery() {
  const params = new URLSearchParams(location.search);
  const p1id = params.get("p1_id"), p2id = params.get("p2_id");
  if (!p1id || !p2id) return;
  const p1league = params.get("p1_league") || "Premier League", p1season = params.get("p1_season") || slots[0].season;
  const p2league = params.get("p2_league") || "Premier League", p2season = params.get("p2_season") || slots[1].season;
  const [p1, p2] = await Promise.all([
    hydratePlayer(p1id, p1league, p1season),
    hydratePlayer(p2id, p2league, p2season),
  ]);
  if (p1) slots[0] = { league: p1league, season: p1season, player: p1 };
  if (p2) slots[1] = { league: p2league, season: p2season, player: p2 };
  renderSlots();
  updateGoButton();
  if (p1 && p2) runCompare();
}

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
renderSlots();
updateGoButton();
updateAddButton();
initFromQuery();
