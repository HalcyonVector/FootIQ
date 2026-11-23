"""
Quadrant plots: two football questions on one chart, so the four corners are four player types
(for example "ball winning" against "carrying": who does both, who does one, who does neither).

Each axis is an INDEX from 0 to 100: the average percentile rank, within the players being
plotted, of a few related per-90 metrics (an axis can also be a single metric). Averaging
several metrics keeps one noisy number from deciding where a player lands, and the 50 line is
the median player on that axis, which is where the quadrant lines are drawn. A metric where
lower is better (fouls, conceding, release time) is flipped first, so up and right always mean better.

Adding a plot is adding one line to PRESETS below: two axes built from columns of the advanced
table (tests/test_quadrants.py checks that they exist and that each plot has enough players),
and the four corner names.
"""

import pandas as pd

from core.advanced import stabilize
from core.advanced import config
from core.advanced.lookup import _clean_minutes
from core.advanced.metrics_master import INVERTED_METRICS

# Which players a plot shows by default. A position group, or a role matched on the position code.
# (Wingers and wing-backs sit in the "midfielder" group in this app, so roles are matched on the code.)
ROLES = {
    "attacking": (r"^(AM|FW|ML|MR)", "forwards, wingers and attacking midfielders"),
    "wide": (r"^(AML|AMR|ML|MR|DL|DR|DML|DMR)$", "wingers, wide midfielders, full-backs and wing-backs"),
    "fullback": (r"^(DL|DR|DML|DMR)$", "full-backs and wing-backs"),
    "winger": (r"^(AML|AMR|ML|MR)$", "wingers and wide midfielders"),
    "centreback": (r"^DC$", "centre-backs"),
    "forward": (r"^FW", "forwards"),
}
GROUP_WHO = {"attacker": "forwards", "midfielder": "midfielders and wingers", "defender": "defenders",
             "goalkeeper": "goalkeepers", "outfield": "outfield players"}

# Columns a plot uses that the Explore metric picker does not list (so they have no label there).
EXTRA_LABELS = {
    "carry_distance_sum_m_p90": {"label": "Carry distance", "unit": "m"},
    "ft_touches_p90": {"label": "Final-third touches", "unit": ""},
    "ft_goals_p90": {"label": "Final-third goals", "unit": ""},
    "ft_assists_p90": {"label": "Final-third assists", "unit": ""},
    "ft_key_passes_p90": {"label": "Final-third key passes", "unit": ""},
    "ft_shots_p90": {"label": "Final-third shots", "unit": ""},
    "ft_def_actions_high_p90": {"label": "High defensive actions", "unit": ""},
}


def _axis(label, *cols, lower=()):
    """An axis: its name, the columns averaged into it, and which of them are better when lower."""
    return {"label": label, "cols": list(cols), "lower": list(lower)}


def _plot(id, group, title, positions, question, x, y, quad):
    tr, tl, br, bl = quad
    return {"id": id, "group": group, "title": title, "positions": positions, "question": question,
            "x": x, "y": y, "quad": {"tr": tr, "tl": tl, "br": br, "bl": bl}}


ATT, CRE, CAR, MID, DEF, AIR, HOLD, GK, ROLE = ("Attacking", "Creation and passing", "Carrying and dribbling",
                                                "Midfield and tempo", "Defending", "Aerial play", "Hold-up play",
                                                "Goalkeepers", "Role profiles")

# Corner order in each tuple: top-right, top-left, bottom-right, bottom-left.
PRESETS = [
    # ── Attacking ───────────────────────────────────────────────────────────────────────────
    _plot("creation_threat", ATT, "Chance creation vs shot threat", "attacking",
          "Who makes chances for others and who takes them, and who does both?",
          _axis("Shot threat", "shoot_xg_p90", "shoot_in_box_count_p90"),
          _axis("Chance creation", "pass_xa_p90", "pass_key_passes_count_p90", "dm_shot_creator_p90"),
          ("Complete attackers", "Creators", "Shooters", "Limited output")),
    _plot("shot_volume_quality", ATT, "Shot volume vs shot quality", "attacking",
          "Who shoots a lot, and who shoots from good positions?",
          _axis("Shot volume", "shoot_shots_count_p90"), _axis("Shot quality (xG per shot)", "shoot_xg_per_shot"),
          ("Volume and quality", "Selective, good chances", "Volume, low quality", "Quiet")),
    _plot("finishing", ATT, "Chances vs goals", "attacking",
          "Who gets the chances, and who scores more than those chances suggest?",
          _axis("Chances (open-play xG)", "shoot_xg_p90"), _axis("Goals", "shoot_goals_count_p90"),
          ("Elite scorers", "Clinical finishers", "Chances, few goals", "Quiet")),
    _plot("shot_location", ATT, "Shot location: how many, from where", "attacking",
          "Who is a box poacher and who shoots from range?",
          _axis("Share of shots in the box", "shoot_in_box_share_pct"), _axis("Shot volume", "shoot_shots_count_p90"),
          ("Box predators", "Shoot from range", "Selective poachers", "Few, long shots")),
    _plot("shot_accuracy", ATT, "Shot volume vs accuracy", "attacking",
          "Who shoots often, and who keeps it on target?",
          _axis("Shot volume", "shoot_shots_count_p90"), _axis("Shot accuracy", "shoot_accuracy_pct"),
          ("Many, on target", "Few but accurate", "Many, wasteful", "Rare, inaccurate")),
    _plot("big_chances", ATT, "Big chances vs goals", "attacking",
          "Who gets the clearest chances, and who actually scores?",
          _axis("Big-chance shots", "shoot_big_chance_count_p90"), _axis("Goals", "shoot_goals_count_p90"),
          ("Big-chance scorers", "Score from less", "Big-chance wasters", "Quiet")),
    _plot("box_presence", ATT, "In the box: shooting vs carrying", "attacking",
          "Who gets into the box with the ball, and who gets shots away there?",
          _axis("Shots in the box", "shoot_in_box_count_p90"), _axis("Carries into the box", "carry_into_box_count_p90"),
          ("Box invaders", "Carry in, rarely shoot", "Poachers", "Stay outside")),
    _plot("aerial_finisher", ATT, "Headed shots vs aerial duels in the final third", "attacking",
          "Who wins the ball in the air up front, and who turns it into headed shots?",
          _axis("Headed shots", "shoot_headed_count_p90"), _axis("Final-third aerial duels", "aer_duels_att_third_p90"),
          ("Aerial threats", "Target men", "Headed poachers", "Not aerial")),
    _plot("dribble_creation", ATT, "Dribble threat vs shot creation", "attacking",
          "Who beats a man, who sets up shots, and who does both?",
          _axis("Dribble threat", "dm_dribble_threat_p90"), _axis("Shot creation", "dm_shot_creator_p90"),
          ("Dribble and create", "Pure creators", "Dribblers", "Limited")),
    _plot("direct_threat", ATT, "Direct threat vs goals", "attacking",
          "Who is involved in dangerous actions, and who finishes them?",
          _axis("Direct threat actions", "dm_direct_threat_actions_p90"), _axis("Goals", "shoot_goals_count_p90"),
          ("Decisive", "Efficient scorers", "Involved, few goals", "Peripheral")),
    _plot("final_third_output", ATT, "Final-third involvement vs end product", "attacking",
          "Who gets on the ball in the final third, and who produces goals and chances from it?",
          _axis("Final-third touches", "ft_touches_p90"),
          _axis("End product", "ft_goals_p90", "ft_assists_p90", "ft_key_passes_p90"),
          ("Busy and productive", "Efficient", "Busy, little end product", "Peripheral")),
    _plot("final_third_shoot_create", ATT, "Final third: shooting vs creating", "attacking",
          "In the final third, who shoots and who passes to a shooter?",
          _axis("Final-third shots", "ft_shots_p90"), _axis("Final-third key passes", "ft_key_passes_p90"),
          ("Shoot and create", "Creators", "Shooters", "Quiet")),
    _plot("press_and_score", ATT, "Pressing high vs goal threat", "attacking",
          "Who defends from the front and still threatens?",
          _axis("High defensive actions", "ft_def_actions_high_p90"), _axis("Goal threat", "shoot_xg_p90"),
          ("Press and score", "Goal threats, no press", "Pressers", "Neither")),
    _plot("half_space_threat", ATT, "Half-space: receiving vs threat", "attacking",
          "Who is found between the lines, and what do they do there?",
          _axis("Half-space receptions", "hs_receptions_p90"),
          _axis("Half-space threat", "hs_shots_p90", "hs_key_passes_p90", "hs_into_box_p90"),
          ("Half-space playmakers", "Make it happen from little", "Receive, rarely hurt", "Rarely used")),
    _plot("half_space_carry_pass", ATT, "Half-space: carrying vs passing forward", "attacking",
          "From the half-spaces, who drives forward and who passes forward?",
          _axis("Progressive carries", "hs_prog_carries_p90"), _axis("Progressive passes", "hs_prog_passes_p90"),
          ("Progress both ways", "Pass forward", "Carry forward", "Rarely progress")),
    # ── Creation and passing ────────────────────────────────────────────────────────────────
    _plot("passing_carrying", CRE, "Progress by passing vs by carrying", "midfielder",
          "Does a player move the team forward with the ball at his feet or with his passing?",
          _axis("Carrying progression", "carry_prog_count_p90", "carry_penetration_gain_m_p90"),
          _axis("Passing progression", "pass_prog_count_p90", "pass_penetration_gain_m_p90", "pass_progression_rate_pct"),
          ("Progress both ways", "Progress by passing", "Progress by carrying", "Recyclers")),
    _plot("security_ambition", CRE, "Ball security vs ambition", "midfielder",
          "Who keeps the ball and who tries to break lines, and who does both?",
          _axis("Ball security (pass accuracy)", "pass_accuracy_pct"),
          _axis("Ambition (progression rate)", "pass_progression_rate_pct"),
          ("Safe and ambitious", "Ambitious, riskier", "Safe recyclers", "Neither")),
    _plot("prog_volume_accuracy", CRE, "Progressive passing: volume vs accuracy", "midfielder",
          "Who plays many forward passes, and who completes them?",
          _axis("Progressive passes", "pass_prog_count_p90"), _axis("Progressive pass accuracy", "pass_prog_accuracy_pct"),
          ("Many, accurate", "Few, accurate", "Many, wasteful", "Rare, inaccurate")),
    _plot("penetration_accuracy", CRE, "Penetration vs accuracy", "midfielder",
          "Who gains the most ground with passes, and at what cost to accuracy?",
          _axis("Pitch gained per 90 (passing)", "pass_penetration_gain_m_p90"), _axis("Pass accuracy", "pass_accuracy_pct"),
          ("Penetrate and keep it", "Safe, short", "Penetrate, risky", "Neither")),
    _plot("pass_vs_carry_into_box", CRE, "Into the box: by pass vs by carry", "attacking",
          "Who gets the ball into the box by passing, and who by carrying?",
          _axis("Passes into the box", "pass_into_box_count_p90"), _axis("Carries into the box", "carry_into_box_count_p90"),
          ("Either way", "Carry in", "Pass in", "Rarely")),
    _plot("through_balls_xa", CRE, "Through balls vs expected assists", "attacking",
          "Who plays the killer ball, and who creates chances in other ways?",
          _axis("Through balls attempted", "pass_through_balls_attempted_count_p90"), _axis("Expected assists (xA)", "pass_xa_p90"),
          ("Killer-pass creators", "Create other ways", "Through-ball hopefuls", "Limited")),
    _plot("crossing_creation", CRE, "Crossing vs chance creation", "wide",
          "Who creates from wide areas by crossing, and who creates by other passes?",
          _axis("Crosses completed", "pass_crosses_count_p90"), _axis("Chance creation", "pass_xa_p90", "pass_key_passes_count_p90"),
          ("Wide creators", "Create by other passes", "Crossers", "Low delivery")),
    _plot("key_passes_assists", CRE, "Key passes vs assists", "attacking",
          "Who creates chances, and whose chances get finished?",
          _axis("Key passes", "pass_key_passes_count_p90"), _axis("Assists", "pass_assists_count_p90"),
          ("Productive creators", "Efficient assisters", "Unlucky creators", "Few chances")),
    _plot("quick_forward", CRE, "Quick release vs ambition", "midfielder",
          "Who plays quickly and forward?",
          _axis("Quick passes (<2s)", "pass_quick_pct"), _axis("Progression rate", "pass_progression_rate_pct"),
          ("Quick and forward", "Forward, takes time", "Quick, sideways", "Slow and safe")),
    _plot("quick_accurate", CRE, "Quick release vs accuracy", "midfielder",
          "Who plays quickly without losing the ball?",
          _axis("Quick passes (<2s)", "pass_quick_pct"), _axis("Pass accuracy", "pass_accuracy_pct"),
          ("Quick and accurate", "Slow, accurate", "Quick, loses it", "Slow, loses it")),
    _plot("one_touch_progress", CRE, "One-touch play vs progression", "midfielder",
          "Who combines in one touch, and who moves it forward?",
          _axis("One-touch passes", "pass_one_touch_pct"), _axis("Progressive passes", "pass_prog_count_p90"),
          ("Combine and progress", "Progress with more touches", "One-touch recyclers", "Neither")),
    _plot("release_speed_ambition", CRE, "Release speed vs ambition", "midfielder",
          "Who gets rid of the ball fast and still goes forward? (faster release scores higher)",
          _axis("Release speed", "pass_median_release_s"), _axis("Progression rate", "pass_progression_rate_pct"),
          ("Fast and forward", "Forward, slower", "Fast, sideways", "Slow and safe")),
    # ── Carrying and dribbling ──────────────────────────────────────────────────────────────
    _plot("dribble_volume_success", CAR, "Dribbling: volume vs success", "attacking",
          "Who takes defenders on often, and who actually beats them?",
          _axis("Take-ons attempted", "carry_takeons_attempted_p90"), _axis("Take-on success", "carry_takeon_success_pct"),
          ("Elite dribblers", "Selective, efficient", "Volume, wasteful", "Rarely dribble")),
    _plot("carry_style", CAR, "Carry style: length vs directness", "outfield",
          "Who makes long carries, and who carries straight at goal?",
          _axis("Mean carry length", "carry_mean_distance_m"), _axis("Directness", "carry_directness"),
          ("Long, direct runners", "Short, direct", "Long, patient", "Short, patient")),
    _plot("carry_volume_progress", CAR, "Carrying: volume vs progression", "midfielder",
          "Who carries a lot, and how much of it moves the team forward?",
          _axis("Carry distance", "carry_distance_sum_m_p90"), _axis("Progressive carries", "carry_prog_count_p90"),
          ("Carry far and forward", "Carry little, forward", "Carry far, sideways", "Rarely carry")),
    _plot("dribble_threat_success", CAR, "Dribble threat vs take-on success", "attacking",
          "Who is a dribbling threat, and who wins their duels?",
          _axis("Dribble threat", "dm_dribble_threat_p90"), _axis("Take-on success", "carry_takeon_success_pct"),
          ("Threat and winner", "Picks moments", "Threat, loses a lot", "Rarely dribbles")),
    _plot("carry_box_penetration", CAR, "Carry penetration vs entries into the box", "attacking",
          "Who gains ground with the ball, and who gets it into the box?",
          _axis("Carry penetration", "carry_penetration_gain_m_p90"), _axis("Carries into the box", "carry_into_box_count_p90"),
          ("Drive and arrive", "Short, into the box", "Long, stop short", "Rarely carry")),
    _plot("takeons_creation", CAR, "Take-ons vs chance creation", "attacking",
          "Who dribbles, and who turns it into chances?",
          _axis("Take-ons attempted", "carry_takeons_attempted_p90"), _axis("Chance creation", "pass_key_passes_count_p90", "pass_xa_p90"),
          ("Dribble and create", "Create without dribbling", "Dribble, no chances", "Quiet")),
    # ── Midfield and tempo ──────────────────────────────────────────────────────────────────
    _plot("winning_carrying", MID, "Ball winning vs carrying", "midfielder",
          "Who wins the ball back, who drives it forward, and who does both?",
          _axis("Carrying", "carry_prog_count_p90", "carry_penetration_gain_m_p90", "carry_into_box_count_p90",
                "carry_distance_sum_m_p90"),
          _axis("Ball winning", "def_tackles_total_p90", "def_interceptions_total_p90", "def_recoveries_total_p90"),
          ("Win it and drive it", "Ball winners", "Ball carriers", "Low involvement")),
    _plot("destroyer_creator", MID, "Destroyers vs creators", "midfielder",
          "Is a midfielder there to stop attacks or to start them?",
          _axis("Creating", "pass_key_passes_count_p90", "pass_xa_p90", "pass_prog_count_p90"),
          _axis("Destroying", "def_tackles_total_p90", "def_interceptions_total_p90", "def_recoveries_total_p90"),
          ("Complete midfielders", "Destroyers", "Creators", "Low involvement")),
    _plot("after_winning", MID, "After winning the ball", "midfielder",
          "Who wins the ball back, and who turns it into progress straight away?",
          _axis("Recoveries", "pr_recoveries_p90"),
          _axis("Progress off recovery", "pr_prog_passes_off_recovery_p90", "pr_prog_carries_off_recovery_p90"),
          ("Win it and attack", "Opportunistic", "Win it, recycle it", "Quiet in transition")),
    _plot("recover_and_keep", MID, "Recoveries vs keeping the ball afterwards", "midfielder",
          "Who wins the ball and then keeps it?",
          _axis("Recoveries", "pr_recoveries_p90"), _axis("Retention after recovery", "pr_retention_pct"),
          ("Win it and keep it", "Few, but kept", "Win it, give it away", "Quiet")),
    _plot("recovery_pass_carry", MID, "After a recovery: pass forward vs carry forward", "midfielder",
          "Once the ball is won, does the player go forward by pass or by carry?",
          _axis("Carries forward (share)", "pr_prog_carry_pct"), _axis("Passes forward (share)", "pr_prog_pass_pct"),
          ("Forward every way", "Pass forward", "Carry forward", "Recycle")),
    _plot("recover_go_forward", MID, "Recoveries vs releasing backwards", "midfielder",
          "Who wins the ball and plays forward instead of back? (fewer backward releases scores higher)",
          _axis("Recoveries", "pr_recoveries_p90"), _axis("Forward release", "pr_backward_release_pct"),
          ("Win it, play forward", "Few, but forward", "Win it, go back", "Quiet and safe")),
    _plot("press_resist_carry_iq", MID, "Press resistance vs carry intelligence", "midfielder",
          "Who stays calm under pressure, and who carries into the right space?",
          _axis("Press resistance", "dm_press_resist_pct"), _axis("Carry IQ", "dm_carry_iq_pct"),
          ("Calm and clever", "Clever carriers", "Press-resistant", "Struggle under pressure")),
    _plot("space_time", MID, "Finding space vs buying time", "midfielder",
          "Who finds space, and who gives teammates time?",
          _axis("Space finding", "dm_space_finder_pct"), _axis("Time bought for teammates", "dm_time_bought_s"),
          ("Find space, buy time", "Buy time", "Find space", "Neither")),
    _plot("tempo", MID, "Tempo: accelerate vs settle", "midfielder",
          "Who speeds the game up and who calms it down?",
          _axis("Settling (resets)", "tempo_resets_p90"), _axis("Accelerating (injectors)", "tempo_injectors_p90"),
          ("Two-way controllers", "Accelerators", "Settlers", "Low tempo influence")),
    _plot("tempo_success", MID, "Accelerating: how often vs how well", "midfielder",
          "Who injects pace often, and does it come off?",
          _axis("Injectors", "tempo_injectors_p90"), _axis("Injector success", "tempo_injector_success_pct"),
          ("Frequent and effective", "Selective, effective", "Frequent, wasteful", "Rarely accelerates")),
    _plot("aggression_into_box", MID, "Aggression vs getting into the box", "midfielder",
          "Who plays aggressively, and who delivers it into the box?",
          _axis("Aggression ratio", "tempo_aggression_ratio"), _axis("Injectors into the box", "tempo_injectors_into_box_p90"),
          ("Aggressive and incisive", "Incisive, patient", "Aggressive, blunt", "Patient")),
    _plot("half_space_defending", MID, "Half-space defending: tackles vs interceptions", "midfielder",
          "Between the lines, who tackles and who reads the pass?",
          _axis("Tackles", "hs_tackles_p90"), _axis("Interceptions", "hs_interceptions_p90"),
          ("Do both", "Readers", "Tacklers", "Passive")),
    # ── Defending ───────────────────────────────────────────────────────────────────────────
    _plot("tackle_volume_success", DEF, "Tackling: volume vs success", "defender",
          "Who gets stuck in, and who wins the duels they take on?",
          _axis("Tackles attempted", "def_tackles_total_p90"), _axis("Tackle success", "def_tackle_success_pct"),
          ("Dominant tacklers", "Selective, precise", "Busy, beaten", "Passive")),
    _plot("tackles_interceptions", DEF, "Tackles vs interceptions", "defender",
          "Does a defender win the ball by tackling or by reading the pass?",
          _axis("Tackles", "def_tackles_total_p90"), _axis("Interceptions", "def_interceptions_total_p90"),
          ("Complete ball winners", "Readers of the game", "Tacklers", "Passive")),
    _plot("clearances_blocks", DEF, "Clearances vs blocks", "defender",
          "Who deals with danger by clearing it, and who by getting in the way?",
          _axis("Clearances", "def_clearances_total_p90"), _axis("Blocks", "def_blocks_total_p90"),
          ("Last-ditch defenders", "Shot blockers", "Clearers", "Rarely tested")),
    _plot("box_defending", DEF, "Defending the box: actions vs aerial wins", "defender",
          "Who is busiest in their own box, and who wins the high ball there?",
          _axis("Box actions", "def_box_actions_p90"), _axis("Box aerials won", "def_box_aerials_won_count_p90"),
          ("Box dominators", "Aerial specialists", "Ground defenders", "Rarely tested")),
    _plot("flank_channel", DEF, "Flank vs channel defending", "defender",
          "Does a defender cover the wide areas or the channels?",
          _axis("Flank actions", "def_flank_actions_p90"), _axis("Channel actions", "def_channel_actions_p90"),
          ("Cover everywhere", "Channel defenders", "Flank defenders", "Little cover")),
    _plot("tackles_fouls", DEF, "Tackling vs fouling in the box", "defender",
          "Who wins the ball cleanly? (fewer fouls in the box scores higher)",
          _axis("Tackles", "def_tackles_total_p90"), _axis("Discipline in the box", "def_fouls_box_count_p90"),
          ("Win it cleanly", "Clean but passive", "Win it, foul it", "Passive and fouling")),
    # ── Aerial play ─────────────────────────────────────────────────────────────────────────
    _plot("aerial", AIR, "Aerial duels: volume vs quality", "defender",
          "Who is involved in the air, and who wins it cleanly?",
          _axis("Aerial duels", "aer_duels_count_p90"), _axis("Duel quality", "aer_duel_quality_pct"),
          ("Aerial dominators", "Selective winners", "Contest, lose", "Stay on the ground")),
    _plot("aerial_win_retain", AIR, "Aerial win rate vs keeping the ball", "defender",
          "Who wins headers, and whose headers go to a teammate?",
          _axis("Win rate in open play", "aer_win_rate_op_pct"), _axis("Retains and plays", "aer_retains_plays_pct"),
          ("Win it and keep it", "Keep it, win less", "Win it, lose the ball", "Lose both")),
    _plot("aerial_attack", AIR, "Attacking aerial duels vs shots from them", "attacking",
          "Who wins it in the air up front and gets a shot away?",
          _axis("Attacking-third duels", "aer_duels_att_third_p90"), _axis("Shots off a duel", "aer_shots_off_duel_p90"),
          ("Aerial threats", "Efficient", "Win it, no shots", "Not aerial")),
    _plot("aerial_use", AIR, "After an aerial duel: passing vs progressing", "outfield",
          "Who uses the ball after a header, and who moves it forward?",
          _axis("Passes off a duel", "aer_passes_off_duel_p90"), _axis("Progressive passes off a duel", "aer_prog_passes_off_duel_p90"),
          ("Use it well", "Few but forward", "Use it safely", "Rarely")),
    # ── Hold-up play ────────────────────────────────────────────────────────────────────────
    _plot("holdup_retention", HOLD, "Hold-up play: volume vs retention", "attacker",
          "Who holds the ball up often, and who keeps it?",
          _axis("Hold-up episodes", "hu_final_episodes_p90"), _axis("Retention", "hu_final_retention_pct"),
          ("Reliable target men", "Safe, selective", "Lose it often", "Rarely hold up")),
    _plot("holdup_progress", HOLD, "Hold-up play: carry on vs release", "attacker",
          "After holding it, does he turn and carry or release forward?",
          _axis("Progressive carry", "hu_final_prog_carry_pct"), _axis("Progressive release", "hu_final_prog_release_pct"),
          ("Do both", "Release forward", "Turn and carry", "Lay it off")),
    _plot("holdup_shoot_foul", HOLD, "Hold-up play: shoot vs win fouls", "attacker",
          "Does holding the ball up lead to a shot or a free kick?",
          _axis("Shots from holds", "hu_final_shot_from_hold_pct"), _axis("Fouls won per hold", "hu_final_fouls_won_per_hold"),
          ("Shoot and draw fouls", "Draw fouls", "Shoot", "Neither")),
    _plot("holdup_danger", HOLD, "Hold-up play: retention vs dangerous losses", "attacker",
          "Who keeps it, and who gives it away in dangerous places? (fewer dangerous losses scores higher)",
          _axis("Retention", "hu_final_retention_pct"), _axis("Safe from dangerous losses", "hu_final_dangerous_loss_pct"),
          ("Secure", "Careful, loses some", "Keeps it, risky losses", "Careless")),
    _plot("holdup_tackles_avoided", HOLD, "Hold-up play: volume vs riding tackles", "attacker",
          "Who holds it up a lot and rides challenges?",
          _axis("Hold-up episodes", "hu_final_episodes_p90"), _axis("Tackles avoided per hold", "hu_final_tackles_avoided_per_hold"),
          ("Strong target men", "Hard to dispossess", "Busy, easy to tackle", "Rarely hold up")),
    # ── Goalkeepers ─────────────────────────────────────────────────────────────────────────
    _plot("gk_style", GK, "Shot stopping vs distribution", "goalkeeper",
          "Who stops the shots, and who starts the attacks?",
          _axis("Distribution accuracy", "gk_distribution_accuracy_pct"), _axis("Save rate", "gk_save_rate_pct"),
          ("Complete keepers", "Shot stoppers", "Distributors", "Below average on both")),
    _plot("gk_busy_effective", GK, "Workload vs save rate", "goalkeeper",
          "Who faces a lot of shots, and who saves them?",
          _axis("Saves per 90", "gk_saves_count_p90"), _axis("Save rate", "gk_save_rate_pct"),
          ("Busy and brilliant", "Quiet but sharp", "Busy, beaten", "Quiet, beaten")),
    _plot("gk_sweeper", GK, "Sweeping: how often vs how far", "goalkeeper",
          "Who acts as a sweeper, and how far off the line?",
          _axis("Sweeps", "gk_sweeps_count_p90"), _axis("Sweep distance", "gk_sweep_distance"),
          ("Aggressive sweepers", "Rare, far", "Frequent, short", "Stay on the line")),
    _plot("gk_command", GK, "Command of the box vs shots faced", "goalkeeper",
          "Who claims crosses, and who is busy with shots?",
          _axis("Claims", "gk_claims_count_p90"), _axis("Saves per 90", "gk_saves_count_p90"),
          ("Commanding and busy", "Shot-stopping focus", "Commanding, protected", "Neither")),
    _plot("gk_build_up", GK, "Build-up: short vs accurate", "goalkeeper",
          "Who plays out from the back, and who keeps the ball when doing it?",
          _axis("Plays short", "gk_plays_short_pct"), _axis("Distribution accuracy", "gk_distribution_accuracy_pct"),
          ("Build-up keepers", "Accurate, direct", "Short but loose", "Long and loose")),
    _plot("gk_workload_conceded", GK, "Workload vs goals conceded", "goalkeeper",
          "Who faces a lot and still keeps goals out? (fewer goals conceded scores higher)",
          _axis("Saves per 90", "gk_saves_count_p90"),
          _axis("Goals not conceded", "gk_goals_conceded_count_p90", lower=("gk_goals_conceded_count_p90",)),
          ("Busy and solid", "Quiet and solid", "Busy, leaking", "Quiet, leaking")),
    # ── Role profiles ───────────────────────────────────────────────────────────────────────
    _plot("fullback_two_way", ROLE, "Full-backs: attacking vs defending", "fullback",
          "Which full-backs attack, which defend, and which do both?",
          _axis("Attacking output", "pass_crosses_count_p90", "pass_key_passes_count_p90", "carry_prog_count_p90"),
          _axis("Defending", "def_tackles_total_p90", "def_interceptions_total_p90", "def_clearances_total_p90"),
          ("Two-way full-backs", "Defensive full-backs", "Attacking full-backs", "Quiet")),
    _plot("winger_style", ROLE, "Wingers: dribbler vs crosser", "winger",
          "Does a winger beat his man or deliver from wide?",
          _axis("Take-ons attempted", "carry_takeons_attempted_p90"), _axis("Crosses completed", "pass_crosses_count_p90"),
          ("Complete wingers", "Crossers", "Dribblers", "Low volume")),
    _plot("winger_threat", ROLE, "Wingers: goal threat vs chance creation", "winger",
          "Does a winger score, create, or both?",
          _axis("Goal threat (xG)", "shoot_xg_p90"), _axis("Chance creation (xA)", "pass_xa_p90"),
          ("Scorers and creators", "Creators", "Scorers", "Limited output")),
    _plot("centre_back_style", ROLE, "Centre-backs: ball-playing vs defending", "centreback",
          "Which centre-backs defend, which build play, and which do both?",
          _axis("Ball progression", "pass_prog_count_p90", "pass_penetration_gain_m_p90", "carry_prog_count_p90"),
          _axis("Defensive actions", "def_tackles_total_p90", "def_interceptions_total_p90", "def_clearances_total_p90",
                "def_blocks_total_p90"),
          ("Complete defenders", "Stoppers", "Ball-playing defenders", "Limited involvement")),
    _plot("striker_style", ROLE, "Strikers: goal threat vs link-up", "forward",
          "Is a forward a poacher, a link player, or both?",
          _axis("Goal threat", "shoot_xg_p90", "shoot_in_box_count_p90"),
          _axis("Link-up play", "hu_final_episodes_p90", "pass_key_passes_count_p90", "hu_final_retention_pct"),
          ("Complete forwards", "Link-up forwards", "Poachers", "Limited")),
]
BY_ID = {p["id"]: p for p in PRESETS}
GROUPS = list(dict.fromkeys(p["group"] for p in PRESETS))


def who(positions: str) -> str:
    return ROLES[positions][1] if positions in ROLES else GROUP_WHO.get(positions, positions)


def public_presets() -> list[dict]:
    """What the page needs to build its picker (no columns)."""
    return [{"id": p["id"], "group": p["group"], "title": p["title"], "question": p["question"],
             "positions": p["positions"], "who": who(p["positions"]),
             "x": p["x"]["label"], "y": p["y"]["label"], "quad": p["quad"]} for p in PRESETS]


def _index(subset: pd.DataFrame, axis: dict) -> pd.Series:
    """Mean percentile rank (0-100, higher is better) of the axis's metrics over the given players,
    each ranked on minutes-adjusted values (stabilize.py) so a short spell cannot sit in a corner on
    a lucky rate. Dot size still shows the real minutes."""
    ranks = []
    for col in axis["cols"]:
        lower_is_better = col in INVERTED_METRICS or col in axis["lower"]
        vals, centre = subset[col], subset[col].median()
        if centre == centre:
            vals = stabilize.adjusted(vals, subset["total_minutes"], centre, stabilize.minutes_for_half_signal(col))
        ranks.append(vals.rank(pct=True, ascending=not lower_is_better) * 100)
    return sum(ranks) / len(ranks)


def _select(subset: pd.DataFrame, group: str) -> pd.DataFrame:
    """Players in a position group (goalkeeper, defender, ...), 'outfield', or a role matched on the code."""
    if group in ROLES:
        return subset[subset["position"].astype(str).str.match(ROLES[group][0])]
    if group == "outfield":
        return subset[subset["_pos_group"] != "goalkeeper"]
    return subset[subset["_pos_group"] == group]


def quadrant_points(df: pd.DataFrame, preset_id: str, season: str, league: str | None = None,
                    position_group: str | None = None, min_minutes: int | None = None, limit: int = 2500) -> dict:
    """{"preset": ..., "points": [...]} for one preset under the same filters as the other Explore views.
    Position 'all' means the preset's own players, so a goalkeeper never appears among outfielders."""
    preset = BY_ID[preset_id]
    cols = preset["x"]["cols"] + preset["y"]["cols"]
    subset = df[df["season"] == season]
    subset = subset[config.league_mask(subset, league)]
    subset = _select(subset, preset["positions"] if not position_group or position_group == "all" else position_group)
    floor = min_minutes if min_minutes is not None else config.minutes_floor(subset)
    subset = subset[subset["total_minutes"] >= floor]
    if any(c not in subset.columns for c in cols):
        return {"preset": preset, "points": []}
    subset = subset[subset[cols].notna().all(axis=1)]
    if subset.empty:
        return {"preset": preset, "points": []}
    subset = subset.sort_values("total_minutes", ascending=False).head(limit).copy()
    subset["_x"] = _index(subset, preset["x"])
    subset["_y"] = _index(subset, preset["y"])
    # Column arrays zipped row by row: iterrows() built a pandas Series per player and was most of the time.
    raw = subset[cols].to_numpy(dtype=float).tolist()
    points = [{"x": float(x), "y": float(y), "name": name, "team": team, "league": lg, "season": season, "group": grp,
               "id": int(pid), "minutes": _clean_minutes(mins), "raw": r}
              for x, y, name, team, lg, grp, pid, mins, r in zip(
                  subset["_x"].to_numpy(), subset["_y"].to_numpy(), subset["player_name"].to_numpy(),
                  subset["team_name"].to_numpy(), subset["league"].to_numpy(), subset["_pos_group"].to_numpy(),
                  subset["whoscored_player_id"].to_numpy(), subset["total_minutes"].to_numpy(), raw)]
    return {"preset": preset, "points": points}
