"""Unit tests for core/advanced/config.py's season_key() — the multi-year vs
single-year season-folder-naming conversion."""
import pytest

from core.advanced.config import season_key, LEAGUE_DIR_MAP, match_dir


@pytest.mark.parametrize("season,expected", [
    ("2023-24", "2324"),
    ("2024-25", "2425"),
    ("2025-26", "2526"),
])
def test_multi_year_season_converts_to_soccerdata_key(season, expected):
    assert season_key(season) == expected


@pytest.mark.parametrize("season", ["2022", "2024"])
def test_single_year_season_passes_through_unchanged(season):
    # World Cup 2022 / Euro 2024 are cached under the plain year, not a
    # "23-24"-style range — this is the exact distinction the through-the-
    # aggregator bug (missing "2022"/"2024" from build_advanced_metrics.py's
    # SEASONS list) depended on getting right.
    assert season_key(season) == season


def test_every_frontend_league_has_a_dir_map_entry():
    # app.py's LEAGUES ids must all resolve here, or match_dir() throws a
    # bare KeyError deep inside the aggregator instead of a clear error.
    from app import LEAGUES
    for league in LEAGUES:
        assert league["id"] in LEAGUE_DIR_MAP, f"{league['id']!r} missing from LEAGUE_DIR_MAP"


def test_match_dir_builds_expected_path_shape():
    path = match_dir("Premier League", "2024-25")
    assert path.endswith("ENG-Premier League_2425")


def test_match_dir_single_year_competition_path_shape():
    path = match_dir("World Cup", "2022")
    assert path.endswith("INT-World Cup_2022")
