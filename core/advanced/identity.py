"""
Direct player_id lookup against the advanced parquet. Used to be a
name-based bridge between two separate ID namespaces (FBref's synthetic
hash vs WhoScored's numeric id) — now that the FBref dataset is retired,
whoscored_player_id IS the id everywhere, so this is just a row lookup.
"""


def match_to_advanced_row(player_id: int, league: str, season: str, adv_df) -> dict | None:
    match = adv_df[
        (adv_df["whoscored_player_id"] == int(player_id))
        & (adv_df["league"] == league)
        & (adv_df["season"] == season)
    ]
    if match.empty:
        return None
    return match.iloc[0].to_dict()
