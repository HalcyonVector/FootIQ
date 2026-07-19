/**
 * FootIQ — Scout page. Search a target player, then rank the most
 * statistically similar player-seasons across all 5 leagues and 3 seasons
 * (same position group), via /api/scout-similar.
 */

let scoutLeague = "Premier League";
let scoutSeason = (window.SEASONS && window.SEASONS[0]) || "2024-25";
let scoutTarget = null;

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function _initialsAvatar(name, size = 64) {
  const initials = (name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const colors = ["#3b82f6","#8b5cf6","#10b981","#f59e0b","#ef4444","#06b6d4"];
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

// ─────────────────────────────────────────────────────────────────────────────
// League dropdown (same pattern as player.html)
// ─────────────────────────────────────────────────────────────────────────────
function initScoutDropdown() {
  const dd = document.getElementById("dd-scout");
  const ddSel = document.getElementById("dd-sel-scout");
  const ddMenu = document.getElementById("dd-menu-scout");
  const lgInput = document.getElementById("scout-league");
  if (!dd) return;

  ddMenu.innerHTML = (window.LEAGUES || []).map(lg => `
    <div class="dd-item ${lg.id === "Premier League" ? "active" : ""}" data-value="${lg.id}" data-logo="${lg.logo}" data-name="${lg.name}">
      <img src="${lg.logo}" style="width:20px;height:20px;object-fit:contain;margin-right:8px;" />
      <span>${lg.name}</span>
    </div>
  `).join("");

  ddSel.addEventListener("click", e => { e.stopPropagation(); dd.classList.toggle("open"); });
  ddMenu.querySelectorAll(".dd-item").forEach(item => {
    item.addEventListener("click", () => {
      scoutLeague = item.dataset.value;
      ddSel.innerHTML = `<img src="${item.dataset.logo}" style="width:20px;height:20px;object-fit:contain;margin-right:8px;" /><span class="dd-name">${item.dataset.name}</span><span class="dd-arrow">▾</span>`;
      dd.classList.remove("open");
      ddMenu.querySelectorAll(".dd-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
      lgInput.value = scoutLeague;
    });
  });
  document.getElementById("scout-season")?.addEventListener("change", e => { scoutSeason = e.target.value; });
}

document.addEventListener("click", () => {
  document.querySelectorAll(".custom-dd.open").forEach(d => d.classList.remove("open"));
  document.querySelectorAll(".search-results.active").forEach(r => r.classList.remove("active"));
});
document.querySelector(".search-card")?.addEventListener("click", e => e.stopPropagation());

// ─────────────────────────────────────────────────────────────────────────────
// Target search
// ─────────────────────────────────────────────────────────────────────────────
function initScoutSearch() {
  const searchEl = document.getElementById("scout-search");
  const resultsEl = document.getElementById("scout-results");

  const doSearch = debounce(async (isGlobal = false) => {
    const q = searchEl.value.trim();
    if (q.length < 2) { resultsEl.innerHTML = ""; resultsEl.classList.remove("active"); return; }
    try {
      const url = `/api/search?name=${encodeURIComponent(q)}&league=${scoutLeague}&season=${scoutSeason}${isGlobal ? "&all_leagues=1" : ""}`;
      const res = await fetch(url);
      const data = await res.json();
      if (!Array.isArray(data)) return;
      if (!data.length && !isGlobal) return doSearch(true);
      if (!data.length) {
        resultsEl.innerHTML = `<div class="result-item" style="color:var(--muted);justify-content:center">No players found</div>`;
        resultsEl.classList.add("active");
        return;
      }
      resultsEl.innerHTML = data.map(p => `
        <div class="result-item" data-player='${JSON.stringify(p).replace(/'/g, "&#39;")}'>
          <div class="result-item-icon">${p.name.charAt(0).toUpperCase()}</div>
          <div><div class="result-name">${p.name}</div><div class="result-meta">${p.league ? p.league + " · " : ""}${p.team} · ${p.position}${p.age ? " · Age " + p.age : ""}</div></div>
        </div>
      `).join("");
      resultsEl.classList.add("active");
    } catch { /* silent */ }
  }, 380);

  searchEl.addEventListener("input", doSearch);
  resultsEl.addEventListener("click", e => {
    const item = e.target.closest(".result-item[data-player]");
    if (!item) return;
    selectTarget(JSON.parse(item.dataset.player));
    resultsEl.classList.remove("active");
    searchEl.value = "";
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Select target -> fetch similar players
// ─────────────────────────────────────────────────────────────────────────────
async function selectTarget(player) {
  scoutTarget = { id: player.id, league: player.league || scoutLeague, season: player.season || scoutSeason };

  const header = document.getElementById("scout-target-header");
  const ageStr = player.age ? ` &middot; Age ${player.age}` : "";
  header.innerHTML = `
    <img class="profile-photo" src="${player.photo || _initialsAvatar(player.name)}"
         onerror="this.src='${_initialsAvatar(player.name)}'" alt="${player.name}" />
    <div class="profile-info">
      <div class="profile-name">${player.name}</div>
      <div class="profile-sub">${player.position}</div>
      <div class="profile-team"><span>${player.team || ""}</span> <span style="color:var(--muted)">&middot; ${scoutTarget.league} &middot; ${scoutTarget.season}${ageStr}</span></div>
    </div>
  `;
  document.getElementById("scout-target-section").style.display = "block";
  applyWikiImage(player.name, player.team, header.querySelector(".profile-photo"));

  await runScoutSearch();
}

async function runScoutSearch() {
  if (!scoutTarget) return;
  const listEl = document.getElementById("scout-matches-list");
  const widenedEl = document.getElementById("scout-widened-notice");
  widenedEl.style.display = "none";
  listEl.innerHTML = `<div class="glass-card" style="text-align:center;color:var(--muted);padding:32px"><div class="mini-spinner" style="margin:0 auto 10px"></div>Finding similar players…</div>`;
  document.getElementById("scout-results-section").style.display = "block";

  const maxAge = document.getElementById("scout-max-age").value;
  const leaguePool = document.getElementById("scout-league-pool").value;

  try {
    const res = await fetch("/api/scout-similar", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        player_id: scoutTarget.id, league: scoutTarget.league, season: scoutTarget.season,
        max_age: maxAge === "none" ? null : maxAge, league_pool: leaguePool,
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      listEl.innerHTML = `<div class="glass-card" style="color:var(--muted);padding:24px;text-align:center">${data.error || "Could not find matches."}</div>`;
      return;
    }
    widenedEl.style.display = data.widened ? "block" : "none";
    renderMatches(data.matches || []);
  } catch {
    listEl.innerHTML = `<div class="glass-card" style="color:var(--muted);padding:24px;text-align:center">Could not load matches.</div>`;
  }
}

async function applyWikiImage(name, team, imgEl) {
  if (!imgEl) return;
  const url = await fetchWikiImage(name, team);
  if (url) imgEl.src = url;
}

function renderMatches(matches) {
  const listEl = document.getElementById("scout-matches-list");
  if (!matches.length) {
    listEl.innerHTML = `<div class="glass-card" style="color:var(--muted);padding:24px;text-align:center">Not enough comparable players in this position group yet.</div>`;
    return;
  }
  listEl.innerHTML = matches.map((m, i) => {
    const color = percentileColor(m.similarity);
    const ageStr = m.age ? ` <span class="scout-match-age">(Age ${m.age})</span>` : "";
    const compareUrl = `/compare?p1_id=${scoutTarget.id}&p1_league=${encodeURIComponent(scoutTarget.league)}&p1_season=${encodeURIComponent(scoutTarget.season)}`
      + `&p2_id=${m.player_id}&p2_league=${encodeURIComponent(m.league)}&p2_season=${encodeURIComponent(m.season)}`;
    return `
      <div class="scout-match-card${i === 0 ? " top-match" : ""}">
        <div class="scout-match-rank">#${i + 1}</div>
        <img class="scout-match-photo" data-name="${m.name}" data-team="${m.team}" src="${_initialsAvatar(m.name, 52)}"
             onerror="this.src='${_initialsAvatar(m.name, 52)}'" alt="${m.name}" />
        <div class="scout-match-info">
          <div class="scout-match-name">${m.name}${ageStr}</div>
          <div class="scout-match-meta">${m.team} &middot; ${m.league} &middot; ${m.season} &middot; ${m.position} &middot; ${m.minutes} min</div>
        </div>
        <div class="scout-match-score">
          <div class="scout-match-score-val" style="color:${color}">${m.similarity}%</div>
          <div class="scout-match-score-lbl">Similarity</div>
        </div>
        <a class="scout-match-cta" href="${compareUrl}">Compare →</a>
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
initScoutDropdown();
initScoutSearch();
document.getElementById("scout-max-age")?.addEventListener("change", () => runScoutSearch());
document.getElementById("scout-league-pool")?.addEventListener("change", () => runScoutSearch());

const scoutThemeBtn = document.getElementById("theme-toggle");
if (scoutThemeBtn) {
  scoutThemeBtn.addEventListener("click", () => {
    const isLight = document.body.getAttribute("data-theme") === "light";
    document.body.setAttribute("data-theme", isLight ? "dark" : "light");
    scoutThemeBtn.textContent = isLight ? "🌙" : "☀️";
    localStorage.setItem("theme", isLight ? "dark" : "light");
  });
}
