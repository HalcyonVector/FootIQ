import os

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
