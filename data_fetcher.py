"""
FootIQ -- data_fetcher.py
=========================
Unified data pipeline: Big 5 leagues + optional extra leagues, 2017-18 onward.

Strategy
--------
soccerdata's FBref wrapper natively supports 5 stat types:
    standard, shooting, playing_time, keeper, misc

For the remaining 6 types (passing, passing_types, gca, defense,
possession, keepersadv) we call fbref.get(url, filepath) directly --
the same HTTP transport (Selenium headless Chrome) that soccerdata uses
internally, so Cloudflare is bypassed and rate-limiting (7s) is built in.

Data availability
-----------------
FBref has Big5 advanced stats (xG, GCA, progressive passing, etc.) from
the 2017-18 season. Earlier seasons have only basic stats (Gls, Ast, MP).
We start from 2018 (= season ending 2017-18).

URL format difference: Big5 vs individual leagues
--------------------------------------------------
Big5 combined:   .../Big5/2024-2025/passing/players/2024-2025-Big-5-...-Stats
Individual:      .../10/2024-2025/passing/2024-2025-Championship-Stats
                                          ^^^^^^^^^
                 No /players/ segment for individual leagues.

Rate-limiting
-------------
soccerdata enforces 7s between requests automatically.
Scraping 9 seasons × 11 stat types × 1 Big5 page = 99 requests  ≈  12 min (first run)
Extra leagues add ~77 requests per league (11 types × 7 seasons assumed) -- cached after.

Usage
-----
    from data_fetcher import FootIQFetcher, BIG5_SEASONS, EXTRA_LEAGUES
    fetcher = FootIQFetcher(cache_dir="data/cache")
    df = fetcher.build_big5_dataset(seasons=BIG5_SEASONS, extra_leagues=EXTRA_LEAGUES)

Run
---
    cd "D:\\Projects\\Football Project"
    python data_fetcher.py

Requirements
------------
    pip install soccerdata pandas lxml
"""

import hashlib
import logging
import pickle
import sys
import io
import time
from pathlib import Path

import pandas as pd

try:
    import soccerdata as sd
    SOCCERDATA_AVAILABLE = True
except ImportError:
    SOCCERDATA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Logging -- force UTF-8 on Windows
# ---------------------------------------------------------------------------

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("FootIQ.fetcher")

if not SOCCERDATA_AVAILABLE:
    log.error("soccerdata not installed. Run: pip install soccerdata")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# soccerdata treats the season integer as the START year:
#   season=2017 → 2017-18, season=2025 → 2025-26
# 2017-18 is the first season with all FBref advanced stats (xG, GCA, etc.)
# 2025-26 is the most recent completed season.
BIG5_SEASONS = [2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

BIG5_LEAGUE_ID = "Big 5 European Leagues Combined"
FBREF_API      = "https://fbref.com"

# Additional leagues beyond the Big 5 to include when requested.
# These are all domestic leagues with full FBref coverage and consistent
# URL formats that our direct scraper handles correctly.
EXTRA_LEAGUES = [
    "ENG-Championship",       # England 2nd division
    "NED-Eredivisie",         # Netherlands
    "POR-Primeira Liga",      # Portugal
    "BEL-First Division A",   # Belgium
    "TUR-Süper Lig",          # Turkey
    "SCO-Scottish Premiership",
]

# Stat types that soccerdata.FBref.read_player_season_stats() supports natively
SD_NATIVE_TYPES = {"standard", "shooting", "playing_time", "keeper", "misc"}

# Stat types we fetch via fbref.get() (same transport, no 403)
# Maps FootIQ name -> FBref URL path segment
DIRECT_TYPES: dict[str, str] = {
    "passing":       "passing",
    "passing_types": "passing_types",
    "gca":           "gca",
    "defense":       "defense",
    "possession":    "possession",
    "keepersadv":    "keepersadv",
}

ALL_STAT_TYPES = [
    "standard", "shooting", "playing_time", "keeper", "misc",
    "passing", "passing_types", "gca", "defense", "possession", "keepersadv",
]

MERGE_KEYS = ["player", "squad", "league", "season"]

META_COLS = frozenset({
    "player", "squad", "league", "season",
    "nation", "pos", "age", "born",
    "mp", "starts", "min", "90s",
})

FBREF_COMP_MAP = {
    "Premier League":       "ENG-Premier League",
    "La Liga":              "ESP-La Liga",
    "Bundesliga":           "GER-Bundesliga",
    "Fußball-Bundesliga":   "GER-Bundesliga",   # exact string FBref uses in HTML
    "Serie A":              "ITA-Serie A",
    "Ligue 1":              "FRA-Ligue 1",
    "Championship":         "ENG-Championship",
    "Eredivisie":           "NED-Eredivisie",
    "Primeira Liga":        "POR-Primeira Liga",
    "First Division A":     "BEL-First Division A",
    "Süper Lig":            "TUR-Süper Lig",
    "Scottish Prem":        "SCO-Scottish Premiership",
    "Scottish Premiership": "SCO-Scottish Premiership",
}

def _map_comp(value) -> str:
    """Robust league name mapper — exact match first, then substring fallback."""
    if not isinstance(value, str):
        return value
    if value in FBREF_COMP_MAP:
        return FBREF_COMP_MAP[value]
    vl = value.lower()
    if "premier league" in vl and "championship" not in vl:
        return "ENG-Premier League"
    if "la liga" in vl:
        return "ESP-La Liga"
    if "bundesliga" in vl:
        return "GER-Bundesliga"
    if "serie a" in vl:
        return "ITA-Serie A"
    if "ligue 1" in vl:
        return "FRA-Ligue 1"
    if "championship" in vl:
        return "ENG-Championship"
    if "eredivisie" in vl:
        return "NED-Eredivisie"
    if "primeira" in vl:
        return "POR-Primeira Liga"
    if "first division a" in vl or "jupiler" in vl:
        return "BEL-First Division A"
    if "süper lig" in vl or "super lig" in vl:
        return "TUR-Süper Lig"
    if "scottish" in vl:
        return "SCO-Scottish Premiership"
    return value


# Extra league configs for leagues NOT supported by soccerdata natively.
# We bypass sd.FBref() entirely for these and build URLs from scratch.
EXTRA_LEAGUE_CONFIGS: dict[str, dict] = {
    "ENG-Championship":     {"comp_id": 10, "slug": "Championship"},
    "NED-Eredivisie":       {"comp_id": 23, "slug": "Eredivisie"},
    "POR-Primeira Liga":    {"comp_id": 32, "slug": "Primeira-Liga"},
    "BEL-First Division A": {"comp_id": 37, "slug": "Belgian-First-Division-A"},
    "TUR-Süper Lig":        {"comp_id": 26, "slug": "Super-Lig"},
    "SCO-Scottish Premiership": {"comp_id": 40, "slug": "Scottish-Premiership"},
}

# Maps our internal stat type name → FBref URL path segment.
# Note: standard="stats", keeper="keepers", playing_time="playingtime" (no underscore).
FBREF_STAT_SLUGS: dict[str, str] = {
    "standard":      "stats",
    "shooting":      "shooting",
    "playing_time":  "playingtime",
    "keeper":        "keepers",
    "misc":          "misc",
    "passing":       "passing",
    "passing_types": "passing_types",
    "gca":           "gca",
    "defense":       "defense",
    "possession":    "possession",
    "keepersadv":    "keepersadv",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _season_str(season: int) -> str:
    """season is the START year: 2025 → '2025-2026'."""
    return f"{season}-{season + 1}"


def _make_fbref(league_id: str, season: int, cache_root: Path):
    """Create a soccerdata FBref object for a given league + season."""
    return sd.FBref(
        leagues  = league_id,
        seasons  = season,
        data_dir = cache_root / "soccerdata",
    )


# ---------------------------------------------------------------------------
# Main fetcher
# ---------------------------------------------------------------------------

class FootIQFetcher:
    """
    FootIQ unified data fetcher.

    Fetches all 11 stat types for:
      - Big 5 European Leagues Combined (efficient -- one page per stat per season)
      - Optional extra leagues scraped individually

    Everything is cached; FBref is hit once per URL, ever.
    """

    def __init__(self, cache_dir: str = "data/cache"):
        self._root = Path(cache_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._master_dir = self._root / "master"
        self._master_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_big5_dataset(
        self,
        seasons: list = None,
        stat_types: list = None,
        extra_leagues: list = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch and merge all stat types for all Big 5 leagues + optional extras.

        Parameters
        ----------
        seasons : list[int]
            Season START years (soccerdata convention): 2025 = 2025-26.
            Defaults to BIG5_SEASONS (2017-18 through 2025-26).
        stat_types : list[str]
            Subset of ALL_STAT_TYPES. Defaults to all 11.
        extra_leagues : list[str]
            Additional league IDs beyond Big 5. Must be keys in EXTRA_LEAGUE_CONFIGS.
        force_refresh : bool
            Bust master cache and re-fetch from FBref.

        Returns
        -------
        pd.DataFrame -- one row per player per season per league
        """
        seasons       = seasons       or BIG5_SEASONS
        stat_types    = stat_types    or ALL_STAT_TYPES
        extra_leagues = extra_leagues or []

        frames = []

        # --- Big 5 combined ---
        for i, s in enumerate(seasons):
            log.info(f"\n{'='*60}")
            log.info(f"[Big5] Season: {_season_str(s)}")
            log.info(f"{'='*60}")
            try:
                df = self._get_season(BIG5_LEAGUE_ID, s, stat_types, force_refresh)
                if df is not None and not df.empty:
                    frames.append(df)
            except BaseException as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                log.error(f"[Big5] Season {_season_str(s)} failed: {e}")
            # Cool-down between seasons so FBref doesn't flag the session.
            # Skip on last season and when data was served from cache (instant).
            if i < len(seasons) - 1:
                log.info("  [inter-season cooldown 45s]")
                time.sleep(45)

        # --- Extra leagues ---
        # soccerdata only supports the Big5 leagues natively; extra leagues must be
        # fetched by building FBref URLs directly and using a shared Selenium transport.
        if extra_leagues:
            transport = self._make_transport_fbref(seasons[0] if seasons else 2025)
            for league in extra_leagues:
                if league not in EXTRA_LEAGUE_CONFIGS:
                    log.warning(f"  Unknown extra league '{league}' -- skipping")
                    continue
                for i, s in enumerate(seasons):
                    log.info(f"\n{'='*60}")
                    log.info(f"[{league}] Season: {_season_str(s)}")
                    log.info(f"{'='*60}")
                    try:
                        df = self._get_extra_season(transport, league, s, stat_types, force_refresh)
                        if df is not None and not df.empty:
                            frames.append(df)
                    except BaseException as e:
                        if isinstance(e, (KeyboardInterrupt, SystemExit)):
                            raise
                        log.error(f"[{league}] Season {_season_str(s)} failed: {e}")
                    if i < len(seasons) - 1:
                        log.info("  [inter-season cooldown 45s]")
                        time.sleep(45)

        if not frames:
            log.warning("No data retrieved.")
            return pd.DataFrame()

        out = pd.concat(frames, ignore_index=True)
        log.info(f"\nDone -- {out.shape[0]:,} rows x {out.shape[1]} cols")
        log.info(f"  Leagues : {sorted(out['league'].dropna().unique())}")
        log.info(f"  Seasons : {sorted(out['season'].dropna().unique())}")
        return out

    # ------------------------------------------------------------------
    # Per-league, per-season
    # ------------------------------------------------------------------

    # Bump this string whenever the merge logic or column schema changes,
    # to automatically invalidate all old master cache files.
    CACHE_VERSION = "v6"

    def _master_cache_key(self, league: str, season: int, stat_types: list) -> Path:
        slug = league.replace(" ", "_").replace("-", "_")
        key  = hashlib.md5(
            f"{self.CACHE_VERSION}-{slug}-{season}-{sorted(stat_types)}".encode()
        ).hexdigest()
        return self._master_dir / f"{key}.pkl"

    def _get_season(
        self,
        league: str,
        season: int,
        stat_types: list,
        force_refresh: bool,
    ) -> pd.DataFrame:
        path = self._master_cache_key(league, season, stat_types)

        if not force_refresh and path.exists():
            log.info(f"Master cache hit -- {league} {_season_str(season)}")
            with open(path, "rb") as f:
                return pickle.load(f)

        is_big5 = (league == BIG5_LEAGUE_ID)
        frames  = self._fetch_all_stats(league, season, stat_types, is_big5)

        if not frames:
            log.warning(f"No frames for {league} {_season_str(season)}")
            return pd.DataFrame()

        master = _merge_frames(frames, season)

        with open(path, "wb") as f:
            pickle.dump(master, f)
        log.info(f"Saved master cache: {path.name}")
        return master

    # ------------------------------------------------------------------
    # Extra league support (soccerdata doesn't support these natively)
    # ------------------------------------------------------------------

    def _make_transport_fbref(self, season: int):
        """
        Create a soccerdata FBref object using a valid (Big5) league purely for
        its Selenium transport.  We reuse it to fetch any FBref URL, including
        unsupported leagues.
        """
        return _make_fbref(BIG5_LEAGUE_ID, season, self._root)

    def _get_extra_season(
        self,
        transport,
        league: str,
        season: int,
        stat_types: list,
        force_refresh: bool,
    ) -> pd.DataFrame:
        """Master-cache wrapper for a single extra-league season."""
        path = self._master_cache_key(league, season, stat_types)

        if not force_refresh and path.exists():
            log.info(f"Master cache hit -- {league} {_season_str(season)}")
            with open(path, "rb") as f:
                return pickle.load(f)

        frames = self._fetch_extra_all_stats(transport, league, season, stat_types)

        if not frames:
            log.warning(f"No frames for {league} {_season_str(season)}")
            return pd.DataFrame()

        master = _merge_frames(frames, season)

        with open(path, "wb") as f:
            pickle.dump(master, f)
        log.info(f"Saved master cache: {path.name}")
        return master

    def _fetch_extra_all_stats(
        self,
        transport,
        league: str,
        season: int,
        stat_types: list,
    ) -> dict:
        """
        Fetch all stat types for an extra league by building FBref URLs directly.

        URL pattern (individual league, no /players/ segment):
          https://fbref.com/en/comps/{comp_id}/{season_str}/{stat_slug}/{season_str}-{slug}-Stats

        Advanced stat types (passing, gca, etc.) are JS-rendered on FBref.
        We use the Selenium driver directly with a JS-wait for those.
        Basic stat types (standard, shooting, etc.) are server-rendered and
        can be fetched with the plain transport.get() (no wait needed).
        """
        config     = EXTRA_LEAGUE_CONFIGS[league]
        season_str = _season_str(season)
        driver     = _get_driver(transport)   # shared Selenium session
        results    = {}

        for stat_type in stat_types:
            url_slug = FBREF_STAT_SLUGS.get(stat_type)
            if not url_slug:
                log.warning(f"     No URL slug for '{stat_type}' -- skipping")
                continue

            url = (
                f"{FBREF_API}/en/comps/{config['comp_id']}"
                f"/{season_str}/{url_slug}"
                f"/{season_str}-{config['slug']}-Stats"
            )
            safe_league = league.replace(" ", "_").replace("-", "_")
            filepath    = transport.data_dir / f"extra_{safe_league}_{season}_{stat_type}.html"
            log.info(f"     [get] {url}")

            try:
                html_str = None
                needs_js_wait = stat_type in DIRECT_TYPES

                # --- check existing cache ---
                if filepath.is_file():
                    try:
                        cached = filepath.read_text(encoding="utf-8", errors="replace")
                        if _html_has_real_stats(cached):
                            html_str = cached
                            log.info("     (cache hit – valid)")
                        elif needs_js_wait:
                            log.info("     (cache stale – iz-only, re-fetching)")
                            # Don't unlink — _fetch_with_js_wait overwrites
                        elif cached.strip():
                            # server-rendered page (standard etc.) — use as-is
                            html_str = cached
                    except Exception:
                        pass  # will re-fetch below

                # --- fetch fresh ---
                if html_str is None:
                    if needs_js_wait and driver is not None:
                        html_str = _fetch_with_js_wait(driver, url, filepath)
                    else:
                        if needs_js_wait:
                            log.warning("     Selenium driver not accessible; using transport.get()")
                            try:
                                filepath.unlink(missing_ok=True)
                            except OSError:
                                pass
                        reader   = transport.get(url, filepath)
                        html_str = reader.read().decode("utf-8", errors="replace")

                df = self._parse_html(html_str, stat_type, season, league)
                if df is not None and not df.empty:
                    df["league"] = league   # override with canonical ID
                    results[stat_type] = df
                    log.info(f"     {len(df):,} rows")
                else:
                    log.warning(f"     Empty result for '{stat_type}'")
            except BaseException as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                log.error(f"     Failed '{stat_type}': {type(e).__name__}: {e}")

        return results

    # ------------------------------------------------------------------
    # Fetch all stat types for one (league, season)
    # ------------------------------------------------------------------

    def _fetch_all_stats(
        self,
        league: str,
        season: int,
        stat_types: list,
        is_big5: bool,
    ) -> dict:
        if not SOCCERDATA_AVAILABLE:
            log.error("soccerdata not installed.")
            return {}

        try:
            fbref = _make_fbref(league, season, self._root)
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            log.error(f"FBref init failed for {league}: {e}")
            return {}

        # Pre-fetch seasons (warms up the Selenium session / Cloudflare cookies)
        try:
            seasons_df = fbref.read_seasons()
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            log.error(f"read_seasons() failed for {league}: {e}")
            seasons_df = None

        results = {}

        for st in stat_types:
            log.info(f"  -> {st}")
            try:
                if st in SD_NATIVE_TYPES:
                    if is_big5:
                        # soccerdata silently drops Bundesliga rows because it
                        # cannot map "de Bundesliga" → "GER-Bundesliga" internally.
                        # Workaround: let soccerdata download the HTML (if needed),
                        # then parse it ourselves with _parse_html which routes
                        # through _map_comp and handles all 5 league names.
                        skey = f"{season % 100:02d}{(season + 1) % 100:02d}"
                        filepath = fbref.data_dir / f"players_{league}_{skey}_{st}.html"
                        if not filepath.exists():
                            log.info(f"     Warming up soccerdata cache for {st} ...")
                            try:
                                fbref.read_player_season_stats(stat_type=st)
                            except Exception as _e:
                                log.warning(f"     soccerdata warmup failed: {_e}")
                        if filepath.exists():
                            html = filepath.read_text(encoding="utf-8", errors="replace")
                            df = self._parse_html(html, st, season, league)
                            log.info(f"     (parsed from soccerdata HTML cache)")
                        else:
                            log.warning(f"     HTML cache missing; falling back to soccerdata parse")
                            raw = fbref.read_player_season_stats(stat_type=st)
                            df  = self._normalise_sd(raw, st, season, league, is_big5)
                    else:
                        raw = fbref.read_player_season_stats(stat_type=st)
                        df  = self._normalise_sd(raw, st, season, league, is_big5)
                elif st in DIRECT_TYPES and seasons_df is not None:
                    df = self._fetch_direct(fbref, seasons_df, st, season, is_big5)
                else:
                    log.warning(f"     Skipping '{st}'")
                    continue

                if df is not None and not df.empty:
                    results[st] = df
                    log.info(f"     {len(df):,} rows")
                else:
                    log.warning(f"     Empty result for '{st}'")

            except BaseException as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                log.error(f"     Failed '{st}': {type(e).__name__}: {e}")

        return results

    # ------------------------------------------------------------------
    # soccerdata native -- normalise
    # ------------------------------------------------------------------

    def _normalise_sd(
        self,
        df: pd.DataFrame,
        stat_type: str,
        season: int,
        league: str,
        is_big5: bool,
    ) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()

        if isinstance(df.columns, pd.MultiIndex):
            flat = []
            for a, b in df.columns:
                a_s = str(a).strip()
                b_s = str(b).strip()
                if a_s == "" or a_s.startswith("Unnamed"):
                    flat.append(b_s.lower().replace(" ", "_").replace("%", "_pct"))
                else:
                    flat.append(
                        f"{a_s}__{b_s}".lower()
                        .replace(" ", "_")
                        .replace("%", "_pct")
                    )
            df.columns = flat
        else:
            df.columns = [c.lower().replace(" ", "_").replace("%", "_pct") for c in df.columns]

        df.columns = [
            c[:-2] if c.endswith("__") and c.count("__") == 1 else c
            for c in df.columns
        ]

        if "team" in df.columns and "squad" not in df.columns:
            df = df.rename(columns={"team": "squad"})

        df["season"] = season

        if "league" not in df.columns:
            if "comp" in df.columns:
                df["league"] = df["comp"].map(_map_comp)
            elif not is_big5:
                df["league"] = league
            else:
                df["league"] = BIG5_LEAGUE_ID

        return self._finish(df, stat_type)

    # ------------------------------------------------------------------
    # Direct fetch via fbref.get() -- same Selenium transport, no 403
    # ------------------------------------------------------------------

    def _fetch_direct(
        self,
        fbref,
        seasons_df: pd.DataFrame,
        stat_type: str,
        season: int,
        is_big5: bool,
    ) -> pd.DataFrame:
        """
        Fetch an advanced stat page (passing, GCA, defense …) for Big5.

        FBref renders these pages' stat values via JavaScript *after* the
        initial HTML load, so plain fbref.get() captures empty iz-cells.
        We use the underlying Selenium driver directly and poll the DOM
        until cells are populated (up to 45 s), then cache the live HTML.

        URL structure:
          Big5 combined:  .../Big5/{season}/passing/players/{season}-Big-5-...-Stats
          Individual:     .../10/{season}/passing/{season}-Championship-Stats
        The /players/ suffix is required for Big5 combined to get the
        player-level table (without it you get squad-level stats only).
        Advanced stat cells on the player page are JS-rendered — we use
        _fetch_with_js_wait so Selenium waits until cells populate.
        """
        url_slug = DIRECT_TYPES[stat_type]
        driver   = _get_driver(fbref)   # None if soccerdata hides it
        dfs      = []

        for (lkey, skey), season_row in seasons_df.iterrows():
            base = "/".join(season_row.url.split("/")[:-1])
            last = season_row.url.split("/")[-1]

            # Big5 combined player stat pages need the /players/ segment.
            # Individual league pages do NOT use /players/ for advanced stats.
            if is_big5:
                url = f"{FBREF_API}{base}/{url_slug}/players/{last}"
            else:
                url = f"{FBREF_API}{base}/{url_slug}/{last}"

            filepath = fbref.data_dir / f"players_{lkey}_{skey}_{stat_type}.html"
            log.info(f"     [get] {url}")

            try:
                # --- try cache first (only if it actually has stat data) ---
                html_str = None
                if filepath.is_file():
                    try:
                        cached = filepath.read_text(encoding="utf-8", errors="replace")
                        if _html_has_real_stats(cached):
                            html_str = cached
                            log.info("     (cache hit – valid)")
                        else:
                            log.info("     (cache stale – iz-only, re-fetching)")
                            # Don't unlink — _fetch_with_js_wait overwrites the file
                    except Exception:
                        pass  # will re-fetch below

                # --- fetch fresh if needed ---
                if html_str is None:
                    if driver is not None:
                        html_str = _fetch_with_js_wait(driver, url, filepath)
                    else:
                        # Fallback: plain fbref.get() (may still get iz-cells)
                        log.warning("     Selenium driver not accessible; using fbref.get()")
                        # Remove stale cache so fbref.get() actually re-fetches
                        try:
                            filepath.unlink(missing_ok=True)
                        except OSError:
                            pass
                        reader   = fbref.get(url, filepath)
                        html_str = reader.read().decode("utf-8", errors="replace")

                df = self._parse_html(html_str, stat_type, season, lkey)
                if not df.empty:
                    dfs.append(df)
            except BaseException as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                log.error(f"     fetch failed: {e}")

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def _parse_html(
        self,
        html: str,
        stat_type: str,
        season: int,
        league_key: str,
    ) -> pd.DataFrame:
        # Strip HTML comments (FBref wraps some tables in comments on non-Big5 pages)
        clean = html.replace("<!--", "").replace("-->", "")
        try:
            tables = pd.read_html(io.StringIO(clean), header=[0, 1])
        except ValueError:
            log.warning("     No parseable tables in page")
            return pd.DataFrame()

        if not tables:
            return pd.DataFrame()

        df = max(tables, key=len)
        df = _flatten_direct_cols(df)

        if "player" in df.columns:
            df = df[df["player"] != "Player"].copy()
            df = df[df["player"].notna()].copy()

        df["season"] = season

        if "comp" in df.columns:
            df["league"] = df["comp"].map(_map_comp)
        else:
            df["league"] = _map_comp(league_key)

        return self._finish(df, stat_type)

    # ------------------------------------------------------------------
    # Shared finalisation
    # ------------------------------------------------------------------

    def _finish(self, df: pd.DataFrame, stat_type: str) -> pd.DataFrame:
        if "team" in df.columns and "squad" not in df.columns:
            df = df.rename(columns={"team": "squad"})

        if "player" not in df.columns:
            log.error(f"  [{stat_type}] 'player' column not found -- skipping")
            return pd.DataFrame()

        prefix = f"{stat_type}__"
        rename = {
            col: f"{prefix}{col}"
            for col in df.columns
            if col not in META_COLS
            and col != "comp"
            and not col.startswith(prefix)
        }
        df = df.rename(columns=rename)

        for col in df.columns:
            if col.startswith(prefix):
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["player"])

        key_cols = [k for k in MERGE_KEYS if k in df.columns]
        if key_cols and df.duplicated(subset=key_cols).any():
            n_before = len(df)
            df = df.drop_duplicates(subset=key_cols, keep="first")
            log.warning(f"  [{stat_type}] dropped {n_before - len(df)} duplicate rows")

        return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Column flattener for pd.read_html(header=[0,1]) output
# ---------------------------------------------------------------------------

def _flatten_direct_cols(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.columns, pd.MultiIndex):
        df.columns = [c.lower().replace(" ", "_").replace("%", "_pct") for c in df.columns]
        return df

    PASS_PREFIXES = {0: "total", 1: "short", 2: "medium", 3: "long"}
    PASS_REPEATED = {"Cmp", "Att", "Cmp%"}
    pass_occ: dict = {}
    seen:     dict = {}
    result         = []

    for top, sub in df.columns:
        unnamed = str(top).startswith("Unnamed")

        if sub in PASS_REPEATED:
            occ    = pass_occ.get(sub, 0)
            prefix = PASS_PREFIXES.get(occ, str(occ))
            name   = f"{prefix}_{sub.lower().replace('%', '_pct')}"
            pass_occ[sub] = occ + 1
        elif unnamed:
            name = sub.lower().replace(" ", "_").replace("%", "_pct")
        else:
            g    = top.lower().replace(" ", "_").replace("%", "_pct")
            s    = sub.lower().replace(" ", "_").replace("%", "_pct")
            name = f"{g}__{s}" if g != s else s

        count      = seen.get(name, 0)
        seen[name] = count + 1
        result.append(f"{name}_{count}" if count else name)

    df.columns = result
    return df


# ---------------------------------------------------------------------------
# Selenium / JS-wait helpers
# ---------------------------------------------------------------------------

# Stat columns that FBref includes on EVERY advanced stat page as context
# (always present even without actual stat data — not useful for validation).
_ALWAYS_PRESENT_STATS = frozenset({
    # Identity / rank columns — always server-rendered on every FBref table.
    # These start with digits (rk) or are non-stat context, so they cause
    # false-positives in both _html_has_real_stats and the JS poll check.
    "rk", "ranker", "players_used",
    "age", "birth_year",
    "nation", "pos", "squad", "comp", "matches",
    "minutes_90s", "90s",
})


def _get_driver(fbref):
    """
    Extract the raw Selenium WebDriver from a soccerdata FBref object.

    soccerdata uses BaseSeleniumReader which stores the driver under one of
    several attribute names depending on version.  We try them all.
    Returns None if no driver can be found.
    """
    for attr in ("driver", "_driver", "_webdriver", "webdriver"):
        d = getattr(fbref, attr, None)
        if d is not None and hasattr(d, "get") and hasattr(d, "page_source"):
            return d
    return None


def _html_has_real_stats(html: str, threshold: int = 200) -> bool:
    """
    Return True if the HTML contains real player-level stat data.

    Counts non-identity numeric cells that appear IN THE SAME TABLE ROW as a
    player cell.  This excludes squad-table rows (which have no player cell but
    DO have numeric data) so we don't get a false positive when:
      - The Big5 combined /players/ page has a squad summary table at the top
        with server-rendered numbers, AND
      - The actual player stats table is still empty (JS hasn't fired yet).

    threshold=200 means we need ≥200 non-identity stat values in player rows,
    i.e. roughly 1 real stat column across ~2000 players.
    """
    import re as _re
    row_re  = _re.compile(r'<tr\b[^>]*>(.*?)</tr>', _re.DOTALL | _re.IGNORECASE)
    cell_re = _re.compile(r'data-stat="(\w+)"[^>]*>([\d.]+)</td>')
    has_player_row = False
    count = 0
    for m in row_re.finditer(html):
        row = m.group(1)
        if 'data-stat="player"' not in row:
            continue
        has_player_row = True
        for stat, _ in cell_re.findall(row):
            if stat not in _ALWAYS_PRESENT_STATS:
                count += 1
    return has_player_row and count >= threshold


def _fetch_with_js_wait(
    driver,
    url: str,
    filepath,
    rate_limit: float = 7.0,
    max_wait: int = 120,
) -> str:
    """
    Navigate to *url* via an existing Selenium driver, wait until JavaScript
    has populated the stat cells, then save and return the page HTML.

    FBref loads standard stats synchronously (server-rendered), but advanced
    stat pages (passing, GCA, defense, possession …) render the stat values
    asynchronously via JS after the initial HTML is delivered.  A plain
    driver.get() + immediate page_source captures the shell with empty cells.

    We poll the DOM until we see ≥ 50 non-iz td[data-stat] cells with
    numeric content, or until max_wait seconds elapse.
    """
    # Respect FBref's rate limit (same as soccerdata's default).
    time.sleep(rate_limit)

    driver.get(url)
    # Scroll to bottom so any lazy-loaded rows are triggered
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    except Exception:
        pass

    # Exclude identity/rank columns (rk, age, etc.) that are server-rendered
    # and would trigger a false "JS ready" signal before actual stats load.
    JS_CHECK = (
        "var skip={'rk':1,'ranker':1,'age':1,'birth_year':1,'nation':1,"
        "  'pos':1,'squad':1,'comp':1,'matches':1,'minutes_90s':1,'90s':1};"
        "return Array.from(document.querySelectorAll('td[data-stat]'))"
        ".filter(function(td){"
        "  var stat=td.getAttribute('data-stat');"
        "  if(skip[stat]) return false;"
        "  var v=(td.textContent||td.innerText||'').trim();"
        "  return !td.classList.contains('iz') && v!=='' && /^[\\d]/.test(v);"
        "}).length;"
    )

    for elapsed in range(max_wait):
        time.sleep(1)
        try:
            count = driver.execute_script(JS_CHECK)
            log.debug(f"     JS poll {elapsed + 1}s: {count} real stat cells")
            if isinstance(count, (int, float)) and count >= 500:
                log.info(f"     JS rendered in {elapsed + 1}s ({int(count)} real stat cells)")
                break
        except Exception:
            pass  # driver not ready yet or execute_script not supported
    else:
        log.warning("     JS render timeout — cells may still be empty")

    html = driver.page_source
    try:
        filepath = filepath if hasattr(filepath, "write_text") else __import__("pathlib").Path(filepath)
        filepath.write_text(html, encoding="utf-8", errors="replace")
    except Exception as e:
        log.warning(f"     Could not cache to {filepath}: {e}")

    return html


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge_frames(frames: dict, season: int) -> pd.DataFrame:
    base_key = "standard" if "standard" in frames else next(iter(frames))
    base     = frames[base_key].copy()
    log.info(f"\n[merge] base='{base_key}' ({len(base):,} rows)")

    # Merge on player+squad+season only — NOT league.
    # The base (standard) frame already has canonical league names from soccerdata.
    # Including league in the join risks NaN when FBref HTML uses a slightly
    # different string (e.g. "Fußball-Bundesliga" vs "GER-Bundesliga").
    SAFE_KEYS = ["player", "squad", "season"]

    for key, df in frames.items():
        if key == base_key:
            continue

        on = [c for c in SAFE_KEYS if c in base.columns and c in df.columns]
        if not on or not {"player", "squad"}.intersection(on):
            log.warning(f"  Skipping '{key}' -- insufficient merge keys {on}")
            continue

        drop     = [c for c in df.columns if c in base.columns and c not in on]
        df_right = df.drop(columns=drop, errors="ignore")

        if df_right.duplicated(subset=on).any():
            df_right = df_right.drop_duplicates(subset=on, keep="first")

        log.info(f"  + '{key}' on {on} (+{len(df_right.columns) - len(on)} cols)")
        base = base.merge(df_right, on=on, how="left")

    base["season"] = season
    log.info(f"  Final: {base.shape[0]:,} rows x {base.shape[1]} cols")
    return base.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Page helpers
# ---------------------------------------------------------------------------

def filter_min_minutes(df: pd.DataFrame, min_90s: float = 5.0) -> pd.DataFrame:
    col = next((c for c in ("90s", "standard__playing_time__90s") if c in df.columns), None)
    if col:
        return df[pd.to_numeric(df[col], errors="coerce") >= min_90s].copy()
    return df


def filter_by_position(df: pd.DataFrame, pos: str) -> pd.DataFrame:
    if "pos" not in df.columns:
        return df
    return df[df["pos"].str.contains(pos, na=False)].copy()


def filter_by_league(df: pd.DataFrame, league: str) -> pd.DataFrame:
    return df[df["league"] == league].copy()


def filter_by_season(df: pd.DataFrame, season: int) -> pd.DataFrame:
    return df[df["season"] == season].copy()


def player_career_slice(df: pd.DataFrame, player_name: str) -> pd.DataFrame:
    return (
        df[df["player"].str.lower() == player_name.lower()]
        .sort_values("season")
        .copy()
    )


def get_stat_columns(df: pd.DataFrame, stat_type: str) -> list:
    return [c for c in df.columns if c.startswith(f"{stat_type}__")]


def available_leagues(df: pd.DataFrame) -> list:
    return sorted(df["league"].dropna().unique().tolist()) if "league" in df.columns else []


def available_seasons(df: pd.DataFrame) -> list:
    return sorted(df["season"].dropna().unique().tolist()) if "season" in df.columns else []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Clean up leftover v3 PKL caches (now on v4 -- they will never be hit but
    # remove them to avoid confusion and save disk space).
    import glob as _glob
    _old_pkls = _glob.glob("data/cache/master/*.pkl")
    if _old_pkls:
        log.info(f"Removing {len(_old_pkls)} stale master PKL(s) from previous run")
        for _p in _old_pkls:
            try:
                Path(_p).unlink()
            except OSError:
                pass

    fetcher = FootIQFetcher(cache_dir="data/cache")

    df = fetcher.build_big5_dataset(seasons=BIG5_SEASONS, extra_leagues=EXTRA_LEAGUES)

    print(f"\nShape  : {df.shape}")
    print(f"Leagues: {available_leagues(df)}")
    print(f"Seasons: {available_seasons(df)}")

    print(f"\nColumns by stat type:")
    for st in ALL_STAT_TYPES:
        cols = get_stat_columns(df, st)
        print(f"  {st:16s} -> {len(cols):3d} cols")

    mids = filter_by_position(filter_min_minutes(df), "MF")
    print(f"\nScout page (all leagues, MF, >=5x90min): {len(mids):,} players")
    print(mids["league"].value_counts().to_string())

    test_player = "Mohamed Salah"
    career = player_career_slice(df, test_player)
    if not career.empty:
        cols = [c for c in [
            "player", "squad", "league", "season",
            "standard__performance__gls",
            "standard__expected__xg",
            "gca__sca__sca90",
            "passing__total_cmp_pct",
            "defense__tackles__tkl",
        ] if c in career.columns]
        print(f"\n{test_player} career slice:")
        print(career[cols].to_string(index=False))
    else:
        print(f"\n{test_player} not found")
