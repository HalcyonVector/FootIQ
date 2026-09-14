import os
from datetime import date

# First domestic season this app has data for — the fixed end of the rolling
# window all_domestic_seasons() computes below.
DOMESTIC_SEASON_START_YEAR = 2023


def current_season() -> str:
    """The domestic season currently in progress, e.g. '2026-27' — computed
    from today's date rather than hardcoded. A hardcoded season string is
    exactly what caused the app to silently keep re-scraping "2025-26" for
    weeks after the 2026-27 season had already started: scraping/auto_update.py
    had CURRENT_SEASON = "2025-26" as a literal, the weekly job kept
    "succeeding" against that same wrong season indefinitely, and nothing
    ever caught it since a successful-but-stale scrape looks identical to a
    successful up-to-date one. Seasons start ~August; before that (Jan-Jul)
    we're still in the second half of the PREVIOUS season."""
    today = date.today()
    start_year = today.year if today.month >= 8 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def all_domestic_seasons() -> list[str]:
    """Every domestic season from DOMESTIC_SEASON_START_YEAR through the
    current one, newest first — e.g. ['2026-27','2025-26','2024-25','2023-24'].
    Grows by one entry each year as the season rolls over instead of a fixed
    list someone has to remember to update (and nothing then depends on
    remembering — this is the single source of truth for that window)."""
    today = date.today()
    current_start_year = today.year if today.month >= 8 else today.year - 1
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(current_start_year, DOMESTIC_SEASON_START_YEAR - 1, -1)]


def season_sort_key(season: str) -> int:
    """Chronological sort key spanning both domestic seasons ('2023-24') and
    single-year tournament seasons ('2022', '2024', WC/Euros) — a plain
    `sorted()` or `reversed()` on a dropdown-ordered list doesn't produce a
    real timeline since tournaments sit strictly *between* two domestic
    seasons, not adjacent to either by string comparison. Domestic 'YYYY-YY'
    keys on its start year (Aug); a tournament 'YYYY' (played the following
    summer) keys 5 units after the season that started the PRIOR August, so
    it always sorts after that season and before the one starting that same
    calendar year."""
    if "-" in season:
        return int(season.split("-")[0]) * 10
    return (int(season) - 1) * 10 + 5


# Where the raw WhoScored match-event JSON cache lives (soccerdata's default
# layout: {WHOSCORED_CACHE_DIR}/{League-Key}_{SeasonKey}/{match_id}.json).
# This directory is NOT part of the repo — override via env var on other machines.
WHOSCORED_CACHE_DIR = os.getenv(
    "FOOTIQ_WHOSCORED_DIR",
    r"C:\Users\basus\soccerdata\data\WhoScored\events",
)

# FootIQ league name -> soccerdata folder prefix
LEAGUE_DIR_MAP = {
    "Premier League": "ENG-Premier League",
    "La Liga": "ESP-La Liga",
    "Serie A": "ITA-Serie A",
    "Bundesliga": "GER-Bundesliga",
    "Ligue 1": "FRA-Ligue 1",
    "Championship": "ENG-Championship",
    "Eredivisie": "NED-Eredivisie",
    "Primeira Liga": "POR-Liga Portugal",
    "Belgian Pro League": "BEL-Pro League",
    "Süper Lig": "TUR-Super Lig",
    "Scottish Premiership": "SCO-Premiership",
    "Champions League": "EUR-Champions League",
    "Europa League": "EUR-Europa League",
    "World Cup": "INT-World Cup",
    "European Championship": "INT-European Championship",
}

ADVANCED_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "advanced")
PLAYER_SEASON_PARQUET = os.path.join(ADVANCED_DATA_DIR, "player_season_advanced.parquet")

# Combination Play: a small summary table (one row per passer/receiver pair,
# no list columns — safe to load fully into memory like PLAYER_SEASON_PARQUET)
# plus the actual per-reception events, partitioned by league/season so a
# single pair's chart only ever reads one partition off disk, never all
# ~8.4M reception events across every league/season/pair at once.
LINKUP_SUMMARY_PARQUET = os.path.join(ADVANCED_DATA_DIR, "linkup_summary.parquet")
LINKUP_RECEPTIONS_DIR = os.path.join(ADVANCED_DATA_DIR, "linkup_receptions")

# Wave 5: per-category raw chart-event coordinates, ONE ROW PER EVENT (not one
# row per player-season holding list-columns of every event — that shape
# forced loading every player's every event into memory just to draw one
# player's chart, which alone needed >1GB RSS and OOM-crashed on a 512MB
# hosting tier). Each category gets its own directory, partitioned by
# league/season, so a single chart request reads one small partition of one
# category instead of the whole dataset.
CHART_EVENTS_DIR = os.path.join(ADVANCED_DATA_DIR, "chart_events")

# Minimum minutes for a player-season to be included in percentile cohorts.
# Mirrors config.MIN_MINUTES used by the existing FBref-based system.
ADV_MIN_MINUTES = 450


def season_key(season: str) -> str:
    """'2023-24' -> '2324' (soccerdata's multi-year folder-naming convention).

    Single-year competitions (World Cup, Euros, etc.) are cached under the
    plain year instead (e.g. '2022'), so pass those straight through.
    """
    if "-" not in season:
        return season
    start, end = season.split("-")
    return f"{start[-2:]}{end}"


def match_dir(league: str, season: str) -> str:
    league_prefix = LEAGUE_DIR_MAP[league]
    return os.path.join(WHOSCORED_CACHE_DIR, f"{league_prefix}_{season_key(season)}")
