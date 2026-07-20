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
    "Europa Conference League": "EUR-Conference League",
    "World Cup": "INT-World Cup",
    "European Championship": "INT-European Championship",
}

ADVANCED_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "advanced")
PLAYER_SEASON_PARQUET = os.path.join(ADVANCED_DATA_DIR, "player_season_advanced.parquet")
LINKUP_PAIRS_PARQUET = os.path.join(ADVANCED_DATA_DIR, "linkup_pairs.parquet")
# Wave 5: per-category raw chart-event coordinates (evt_<category>_<field> list
# columns) — kept separate from PLAYER_SEASON_PARQUET so /api/advanced-stats
# (read on every player load) never pays for this heavier file.
CHART_EVENTS_PARQUET = os.path.join(ADVANCED_DATA_DIR, "player_chart_events.parquet")

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
