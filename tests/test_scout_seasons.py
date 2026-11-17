"""Scout's season window: candidates come from the chosen seasons, one result per player."""
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data" / "advanced" / "player_season_advanced.parquet"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data release not downloaded")


@pytest.fixture(scope="module")
def setup():
    from core.advanced.store import get_advanced_df
    df = get_advanced_df()
    seasons = sorted(df["season"].unique(), reverse=True)
    recent = [s for s in seasons if "-" in s][:2]
    # a regular from the older recent season, in a domestic league
    pick = df[(df["season"] == recent[1]) & (df["total_minutes"] > 2500) & (df["league"] == "Premier League")].iloc[0]
    return df, recent, pick


def test_recent_window_only_returns_recent_seasons(setup):
    from core.advanced.scout import find_similar
    df, recent, pick = setup
    matches, widened = find_similar(df, int(pick["whoscored_player_id"]), pick["league"], pick["season"], limit=20, seasons=recent)
    assert matches and not widened
    assert {m["season"] for m in matches} <= set(recent)
    assert len({m["player_id"] for m in matches}) == len(matches)        # one row per player


def test_no_window_can_reach_older_seasons(setup):
    from core.advanced.scout import find_similar
    df, recent, pick = setup
    matches, _ = find_similar(df, int(pick["whoscored_player_id"]), pick["league"], pick["season"], limit=20)
    assert matches


def test_impossible_filters_loosen_age_before_seasons(setup):
    from core.advanced.scout import find_similar
    df, recent, pick = setup
    matches, widened = find_similar(df, int(pick["whoscored_player_id"]), pick["league"], pick["season"], limit=10,
                                    max_age=10, seasons=recent)
    assert widened and matches
    assert {m["season"] for m in matches} <= set(recent)                 # the age limit went, the season window stayed
