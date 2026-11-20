"""A header is a set-piece duel when it comes straight from a corner, free kick or throw-in: the
set-piece tag sits on the delivery, not on the header itself."""
from core.advanced.categories.aerial import compute_aerial, _from_set_piece


def _ev(i, typ, minute, second, player, team, quals=(), outcome="Successful", x=90.0):
    return {"event_id": i, "type": typ, "minute": minute, "second": second, "player_id": player, "team_id": team,
            "qualifiers": [{"type": {"displayName": q}} for q in quals], "outcome_type": outcome,
            "x": x, "y": 50.0, "end_x": None, "end_y": None}


def test_header_from_a_corner_is_a_set_piece_duel():
    events = [
        _ev(1, "Pass", 10, 0, 7, 1, quals=("CornerTaken", "Cross")),
        _ev(2, "Aerial", 10, 2, 9, 1),                          # attacker wins it
        _ev(3, "Aerial", 10, 2, 4, 2, outcome="Unsuccessful"),  # the defender's record of the same duel
    ]
    assert _from_set_piece(events, 1) and _from_set_piece(events, 2)
    out = compute_aerial(events)
    assert out[9]["aer_duels_sp"] == 1 and out[9]["aer_won_sp"] == 1     # both jumpers count it as set piece
    assert out[4]["aer_duels_sp"] == 1 and "aer_duels_op" not in out[4]


def test_header_from_an_open_play_cross_or_long_after_a_corner_is_not():
    open_cross = [_ev(1, "Pass", 20, 0, 7, 1, quals=("Cross",)), _ev(2, "Aerial", 20, 1, 9, 1)]
    assert not _from_set_piece(open_cross, 1)
    late = [_ev(1, "Pass", 30, 0, 7, 1, quals=("CornerTaken",)), _ev(2, "Aerial", 30, 20, 9, 1)]
    assert not _from_set_piece(late, 1)
