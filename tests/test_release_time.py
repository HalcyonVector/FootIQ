"""Release time runs from when the passer got the ball (the feed has no reception event) to the pass."""
from core.advanced.timing import release_times_by_player, reception_seconds


def _ev(i, typ, sec, player, team, outcome="Successful", x=50.0, y=50.0, ex=None, ey=None, quals=(), period=1):
    return {"event_id": i, "type": typ, "minute": 0, "second": sec, "expanded_minute": 0, "period": period,
            "player_id": player, "team_id": team, "outcome_type": outcome, "x": x, "y": y, "end_x": ex, "end_y": ey,
            "qualifiers": [{"type": {"displayName": q}} for q in quals]}


def test_from_a_teammates_pass_the_ball_travel_time_is_taken_off():
    # a 13 m pass (x 40 -> 52.4 is 13 m on a 105 m pitch) arrives about 1 s after it is played
    ev = [_ev(1, "Pass", 10, 7, 1, x=40, y=50, ex=52.38, ey=50), _ev(2, "Pass", 13, 8, 1, x=52, y=50, ex=70, ey=50)]
    assert release_times_by_player(ev)[2] == 2.0


def test_from_the_passers_own_recovery_with_a_dribble_in_between():
    ev = [_ev(1, "Pass", 5, 3, 2, outcome="Unsuccessful", x=60, ex=40), _ev(2, "BallRecovery", 6, 8, 1),
          _ev(3, "TakeOn", 8, 8, 1), _ev(4, "Pass", 9, 8, 1, ex=70, ey=50)]
    assert release_times_by_player(ev)[4] == 3.0


def test_the_opponents_record_of_a_lost_duel_is_skipped():
    ev = [_ev(1, "Pass", 20, 7, 1, ex=50, ey=50), _ev(2, "Challenge", 21, 4, 2, outcome="Unsuccessful"),
          _ev(3, "Pass", 22, 8, 1, ex=70, ey=50)]
    assert reception_seconds(ev, 2) == 20.0


def test_untimed_when_the_feed_cannot_say_when_they_got_it():
    own_earlier_pass = [_ev(1, "Pass", 10, 8, 1, ex=60, ey=50), _ev(2, "Pass", 14, 8, 1, ex=70, ey=50)]
    assert 2 not in release_times_by_player(own_earlier_pass)
    across_half_time = [_ev(1, "Pass", 10, 7, 1, ex=50, ey=50), _ev(2, "Pass", 12, 8, 1, ex=70, ey=50, period=2)]
    assert 2 not in release_times_by_player(across_half_time)
    too_long = [_ev(1, "Pass", 10, 7, 1, ex=50, ey=50), _ev(2, "Pass", 40, 8, 1, ex=70, ey=50)]
    assert 2 not in release_times_by_player(too_long)


def test_set_piece_passes_are_not_timed():
    ev = [_ev(1, "Pass", 10, 7, 1, ex=50, ey=50), _ev(2, "Pass", 13, 8, 1, ex=70, ey=50, quals=("FreekickTaken",))]
    assert 2 not in release_times_by_player(ev)
