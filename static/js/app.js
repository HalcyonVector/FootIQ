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
const linkupSection   = document.getElementById("linkup-section");
const linkupChips     = document.getElementById("linkup-chips");
const linkupStatsRow  = document.getElementById("linkup-stats-row");
const linkupChartImg  = document.getElementById("linkup-chart-img");

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
    if (q.length < 3) { resultsEl.innerHTML = ""; resultsEl.classList.remove("active"); return; }
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
// Select primary player → fetch Advanced Metrics + Combination Play
// ─────────────────────────────────────────────────────────────────────────────
async function selectPrimaryPlayer(player) {
  primaryPlayer = player;

  profileSection.style.display = "block";
  renderProfileHeader(player);

  chartsLoading.style.display = "flex";
  advancedSection.style.display = "none";
  linkupSection.style.display = "none";

  await Promise.allSettled([
    fetchAdvancedStats(player),
    fetchLinkupTeammates(player),
  ]);
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
        <span class="profile-stat-chip apps-chip">📅 ${player.minutes || "–"} min &middot; ${primarySeason}</span>
      </div>
    </div>
  `;
  applyWikiImage(player.name, player.team, document.querySelector(".profile-photo"));
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
// Generic percentile-table renderer (shared by every Advanced Metrics tab)
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
      return;
    }
    renderAdvancedStats(data.categories);
    advancedSection.style.display = "block";
  } catch { showToast("Could not load advanced stats."); }
}

function renderAdvancedStats(categories) {
  advTabs.innerHTML = categories.map((cat, i) =>
    `<button class="adv-tab-btn${i === 0 ? " active" : ""}" data-cat="${cat.key}">${cat.icon} ${cat.label}</button>`
  ).join("");

  advPanels.innerHTML = categories.map((cat, i) =>
    `<div class="adv-panel" data-cat="${cat.key}" id="adv-panel-${cat.key}" style="display:${i === 0 ? "block" : "none"}"></div>`
  ).join("");

  categories.forEach(cat => renderPctTable(cat.rows, `adv-panel-${cat.key}`));

  advTabs.querySelectorAll(".adv-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      advTabs.querySelectorAll(".adv-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      advPanels.querySelectorAll(".adv-panel").forEach(p => {
        p.style.display = p.dataset.cat === btn.dataset.cat ? "block" : "none";
      });
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Combination Play (pairwise pass network)
// ─────────────────────────────────────────────────────────────────────────────
let linkupPasserId = null;

async function fetchLinkupTeammates(player) {
  if (!linkupSection) return;
  try {
    const res = await fetch("/api/linkup-teammates", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_id: player.id, league: primaryLeague, season: primarySeason }),
    });
    const data = await res.json();
    if (!res.ok || !data.teammates || !data.teammates.length) return;  // some players (e.g. rarely-used subs) have too little data — hide gracefully

    linkupPasserId = data.player_whoscored_id;
    linkupChips.innerHTML = data.teammates.map((t, i) =>
      `<div class="linkup-chip${i === 0 ? " active" : ""}" data-teammate-id="${t.teammate_id}" data-name="${t.name}">
         <span>${t.name}</span><span class="lc-count">${t.pass_count}</span>
       </div>`
    ).join("");

    linkupChips.querySelectorAll(".linkup-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        linkupChips.querySelectorAll(".linkup-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        fetchLinkupDetail(chip.dataset.teammateId);
      });
    });

    linkupSection.style.display = "block";
    await fetchLinkupDetail(data.teammates[0].teammate_id);
  } catch { /* silent — bonus section, not core flow */ }
}

async function fetchLinkupDetail(teammateId) {
  if (linkupPasserId == null) return;
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

    const s = data.stats;
    linkupStatsRow.innerHTML = `
      <span class="profile-stat-chip goal-chip">Prog. Passes: ${s.prog_passes}</span>
      <span class="profile-stat-chip card-y-chip">Prog. Carries: ${s.prog_carries}</span>
      <span class="profile-stat-chip assist-chip">Take-Ons: ${s.take_ons_won}</span>
      <span class="profile-stat-chip apps-chip">Shots: ${s.shots}</span>
    `;
    linkupChartImg.src = `data:image/png;base64,${data.chart}`;
  } catch { /* silent */ }
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
// Init
// ─────────────────────────────────────────────────────────────────────────────
initMainDropdown();
initMainSearch();

// Theme Toggle
const themeBtn = document.getElementById("theme-toggle");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const isLight = document.body.getAttribute("data-theme") === "light";
    document.body.setAttribute("data-theme", isLight ? "dark" : "light");
    themeBtn.textContent = isLight ? "🌙" : "☀️";
  });
}

// Scroll-reveal is handled once, in base.html's initScrollAnimations().
