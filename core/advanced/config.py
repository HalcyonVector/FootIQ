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
}

ADVANCED_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "advanced")
PLAYER_SEASON_PARQUET = os.path.join(ADVANCED_DATA_DIR, "player_season_advanced.parquet")
LINKUP_PAIRS_PARQUET = os.path.join(ADVANCED_DATA_DIR, "linkup_pairs.parquet")

# Minimum minutes for a player-season to be included in percentile cohorts.
# Mirrors config.MIN_MINUTES used by the existing FBref-based system.
ADV_MIN_MINUTES = 450


def season_key(season: str) -> str:
    """'2023-24' -> '2324' (soccerdata's folder-naming convention)."""
    start, end = season.split("-")
    return f"{start[-2:]}{end}"


def match_dir(league: str, season: str) -> str:
    league_prefix = LEAGUE_DIR_MAP[league]
    return os.path.join(WHOSCORED_CACHE_DIR, f"{league_prefix}_{season_key(season)}")
