"""
FootIQ — Flask Application
REST API routes + Jinja2 page rendering.

Stats-first: search a player, see their event-derived Advanced Metrics
(12 tabs) and Combination Play. Everything is built from the scraped
WhoScored/Opta match data (core/advanced/) — the old FBref-CSV-backed
simple-stats/Compare/Scout system has been retired.
"""
import traceback
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from core.advanced.lookup import search_players, search_players_global, get_player_stats
from core.media import get_wikimedia_image

app = Flask(__name__)
CORS(app)

# In-memory chart cache: key = whatever the caller builds it as.
# Stores pre-rendered base64 chart PNGs so repeat lookups are instant.
_chart_cache: dict = {}
_CACHE_MAX = 200   # evict oldest when this is exceeded

LEAGUES = [
    {"id": "Premier League", "name": "Premier League", "country": "England", "logo": "https://media.api-sports.io/football/leagues/39.png"},
    {"id": "La Liga",        "name": "La Liga",         "country": "Spain",   "logo": "https://media.api-sports.io/football/leagues/140.png"},
    {"id": "Serie A",        "name": "Serie A",         "country": "Italy",   "logo": "https://media.api-sports.io/football/leagues/135.png"},
    {"id": "Bundesliga",     "name": "Bundesliga",      "country": "Germany", "logo": "https://media.api-sports.io/football/leagues/78.png"},
    {"id": "Ligue 1",        "name": "Ligue 1",         "country": "France",  "logo": "https://static.wikia.nocookie.net/logopedia/images/3/31/Ligue_1_2024.png"},
    # Newly-scraped leagues (core/advanced/config.py's LEAGUE_DIR_MAP has the
    # matching WhoScored cache-folder keys) — these ids MUST match that map
    # exactly, since the frontend just forwards whatever `id` is picked here
    # straight through as the `league` query/body param on every API call.
    {"id": "Championship",              "name": "Championship (England)",  "country": "England",       "logo": "https://media.api-sports.io/football/leagues/40.png"},
    {"id": "Eredivisie",                "name": "Eredivisie",               "country": "Netherlands",   "logo": "https://media.api-sports.io/football/leagues/88.png"},
    {"id": "Primeira Liga",             "name": "Primeira Liga",            "country": "Portugal",      "logo": "https://media.api-sports.io/football/leagues/94.png"},
    {"id": "Belgian Pro League",        "name": "Belgian Pro League",       "country": "Belgium",       "logo": "https://media.api-sports.io/football/leagues/144.png"},
    {"id": "Süper Lig",                 "name": "Süper Lig",                "country": "Turkey",        "logo": "https://media.api-sports.io/football/leagues/203.png"},
    {"id": "Scottish Premiership",      "name": "Scottish Premiership",     "country": "Scotland",      "logo": "https://media.api-sports.io/football/leagues/179.png"},
    {"id": "Champions League",          "name": "Champions League",        "country": "Europe",        "logo": "https://media.api-sports.io/football/leagues/2.png"},
    {"id": "Europa League",             "name": "Europa League",           "country": "Europe",        "logo": "https://media.api-sports.io/football/leagues/3.png"},
    # Europa Conference League was scraped in full (447 matches, 3 seasons)
    # but WhoScored never returned usable match-event data for a single one
    # of them (confirmed via a full no-cache retry) — Champions/Europa League,
    # scraped in the same session, came back 100% clean, ruling out a
    # blocking/parallelism issue. This looks like a genuine coverage-tier gap
    # on WhoScored's side, not something scraping harder fixes, so it's
    # excluded here rather than shown as a league that always returns nothing.
    {"id": "World Cup",                 "name": "World Cup",               "country": "International", "logo": "https://media.api-sports.io/football/leagues/1.png"},
    {"id": "European Championship",     "name": "European Championship",   "country": "International", "logo": "https://media.api-sports.io/football/leagues/4.png"},
]

# Only seasons we actually have scraped Advanced Metrics data for. The two
# single-year competitions (World Cup 2022, Euro 2024) get their own entries
# here too — picking one of the top-3 rows with, say, "Champions League"
# just yields an honest "no data" until that season/league combo exists.
SEASONS = ["2025-26", "2024-25", "2023-24", "2022", "2024"]

# The original 5-league scope, kept around for Scout's "top 5 only" pool
# option — narrowing to these avoids a smaller domestic league (e.g.
# Scottish Premiership) surfacing as someone's "most similar" player purely
# because the position cohort there is thinner, not because the profile
# actually matches better.
TOP5_LEAGUES = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("hub.html")


@app.route("/player")
def player_page():
    return render_template("player.html", leagues=LEAGUES, seasons=SEASONS)


@app.route("/compare")
def compare_page():
    return render_template("compare.html", leagues=LEAGUES, seasons=SEASONS)


@app.route("/scout")
def scout_page():
    return render_template("scout.html", leagues=LEAGUES, seasons=SEASONS)


@app.route("/explore")
def explore_page():
    from core.advanced.explore import explorable_metrics
    return render_template("explore.html", leagues=LEAGUES, seasons=SEASONS, categories=explorable_metrics())


# ─────────────────────────────────────────────────────────────────────────────
# API — misc
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/player-image")
def api_player_image():
    name = request.args.get("name", "").strip()
    team = request.args.get("team", "").strip()
    if not name:
        return jsonify({"url": ""})
    url = get_wikimedia_image(name, team=team)
    return jsonify({"url": url})


@app.route("/api/leagues")
def api_leagues():
    return jsonify(LEAGUES)


# ─────────────────────────────────────────────────────────────────────────────
# API — search
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    name        = request.args.get("name", "").strip()
    league      = request.args.get("league", "Premier League")
    season      = request.args.get("season", "2024-25")
    all_leagues = request.args.get("all_leagues", "0") == "1"

    if len(name) < 2:
        return jsonify([])

    try:
        if all_leagues:
            results = search_players_global(name, season)
        else:
            results = search_players(name, league, season)
            if not results:
                results = search_players_global(name, season)
        return jsonify(results[:15])
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — advanced metrics (Opta/WhoScored event-derived stats)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/advanced-stats", methods=["POST"])
def api_advanced_stats():
    try:
        body      = request.get_json(force=True)
        player_id = body["player_id"]
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")

        raw = get_player_stats(player_id, league, season)
        if not raw:
            return jsonify({"player": None, "categories": []})

        from core.advanced.store import get_advanced_df
        from core.advanced.identity import match_to_advanced_row
        from core.advanced.percentiles import build_all_categories
        from core.advanced.composite import compute_composite

        df = get_advanced_df()
        if df.empty:
            return jsonify({"player": raw, "categories": []})

        row = match_to_advanced_row(player_id, league, season, df)
        if row is None:
            return jsonify({"player": raw, "categories": []})

        categories = build_all_categories(row, raw.get("position", ""), season, df)
        # Same composite Compare already shows per player — the single-player
        # header has styled-but-unused CSS for this (.profile-score/.score-num
        # in style.css) that was never wired up on this page.
        composite = compute_composite(categories, raw.get("position", ""))
        return jsonify({"player": raw, "categories": categories, "composite": composite})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/linkup-teammates", methods=["POST"])
def api_linkup_teammates():
    try:
        body      = request.get_json(force=True)
        player_id = body["player_id"]
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")

        from core.advanced.store import get_linkup_summary_df

        link_df = get_linkup_summary_df()
        if link_df.empty:
            return jsonify({"teammates": []})

        ws_id = int(player_id)
        mine = link_df[(link_df["passer_id"] == ws_id) & (link_df["league"] == league) & (link_df["season"] == season)]
        mine = mine.sort_values("count", ascending=False).head(10)

        teammates = [
            {"teammate_id": int(r["receiver_id"]), "name": r["receiver_name"], "pass_count": int(r["count"])}
            for _, r in mine.iterrows()
        ]
        return jsonify({"player_whoscored_id": ws_id, "teammates": teammates})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/linkup-detail", methods=["POST"])
def api_linkup_detail():
    try:
        body        = request.get_json(force=True)
        passer_id   = int(body["passer_id"])
        teammate_id = int(body["teammate_id"])
        league      = body.get("league", "Premier League")
        season      = body.get("season", "2024-25")

        from core.advanced.store import get_linkup_summary_df, get_linkup_receptions

        link_df = get_linkup_summary_df()
        if link_df.empty:
            return jsonify({"error": "No data"}), 400

        match = link_df[(link_df["passer_id"] == passer_id) & (link_df["receiver_id"] == teammate_id)
                         & (link_df["league"] == league) & (link_df["season"] == season)]
        if match.empty:
            return jsonify({"error": "No data for this pair"}), 404
        pair = match.iloc[0]

        receptions = get_linkup_receptions(passer_id, teammate_id, league, season)
        if not receptions:
            return jsonify({"error": "No data for this pair"}), 404

        import collections
        counts = collections.Counter(r["outcome"] for r in receptions)

        cache_key = ("linkup", passer_id, teammate_id, league, season)
        if cache_key not in _chart_cache:
            from visuals.linkup import generate_linkup_chart
            chart = generate_linkup_chart(pair["passer_name"], pair["receiver_name"], receptions)
            if len(_chart_cache) >= _CACHE_MAX:
                _chart_cache.pop(next(iter(_chart_cache)))
            _chart_cache[cache_key] = chart
        else:
            chart = _chart_cache[cache_key]

        return jsonify({
            "stats": {
                "prog_passes": counts.get("prog_pass", 0),
                "prog_carries": counts.get("prog_carry", 0),
                "take_ons_won": counts.get("takeon_won", 0),
                "take_ons_lost": counts.get("takeon_lost", 0),
                "shots": counts.get("shot", 0),
                "receptions": len(receptions),
            },
            "chart": chart,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/category-chart", methods=["POST"])
def api_category_chart():
    """A titled GRID of charts (3-4 for most categories, fewer where a
    category genuinely has less raw variety to show) for a given Advanced
    Metrics tab, rendered lazily on tab activation — never bundled into
    /api/advanced-stats, which must stay fast. Each entry in the returned
    `charts` list is {key, title, image}. `filter` is an optional
    comma-separated string whose meaning depends on category (passing: mode;
    aerial: phases; half_spaces: mode; carrying: followups to show) — it
    only ever affects that category's primary pitch-map chart; the
    companion charts always reflect the full, unfiltered data."""
    try:
        body        = request.get_json(force=True)
        player_id   = int(body["player_id"])
        league      = body.get("league", "Premier League")
        season      = body.get("season", "2024-25")
        category    = body["category"]
        filt        = body.get("filter", "")

        cache_key = ("category_chart", player_id, league, season, category, filt)
        if cache_key in _chart_cache:
            return jsonify(_chart_cache[cache_key])

        from core.advanced.store import get_advanced_df, get_chart_events
        from core.advanced.identity import match_to_advanced_row
        from core.advanced import percentiles as pct_mod

        df = get_advanced_df()
        row = match_to_advanced_row(player_id, league, season, df)
        if row is None:
            return jsonify({"error": "No data for this player/season"}), 404
        player_name, team = row.get("player_name"), row.get("team_name")

        def recs(prefix, fields=None):
            # Reads only this one category's league/season partition,
            # filtered to this one player — never the whole chart-events
            # dataset (see core/advanced/store.get_chart_events docstring).
            return get_chart_events(prefix, player_id, league, season)

        _stats_cache = {}

        def stats_for(cat_key):
            """Ranks only cat_key against the cohort (build_one_category),
            not all 12 categories — every call site in this endpoint only
            ever asks for the one category whose tab is actually being
            rendered, so there's nothing to gain from computing the other 11.
            Still memoized per cat_key in case a category ever calls this
            more than once in a single request."""
            if cat_key not in _stats_cache:
                cat = pct_mod.build_one_category(row, row.get("position", ""), season, df, cat_key)
                _stats_cache[cat_key] = cat["rows"][0]["stats"] if cat else []
            return _stats_cache[cat_key]

        chart_stats = None  # only Carrying returns this — its counts render as HTML, not baked into the image
        charts = []  # list of {key, title, image}

        if category == "passing":
            from visuals.passing import generate_passing_chart, generate_pass_outcome_chart, generate_release_time_chart, generate_pass_zone_chart
            passes = recs("passing", ["x", "y", "end_x", "end_y", "completed", "progressive", "into_box", "release_s"])
            mode = filt or "progressive"
            # Every companion chart respects the same filter as the map —
            # "Progressive & into box" mode looks at just that subset, not
            # the whole season, so the tile grid never shows 3+ charts that
            # look identical regardless of which toggle is picked.
            filtered_passes = [p for p in passes if p["progressive"] or p["into_box"]] if mode == "progressive" else passes
            charts = [
                {"key": "map", "title": "Pass Map", "image": generate_passing_chart(player_name, team, season, passes, mode=mode)},
                {"key": "outcome", "title": "Outcome Breakdown", "image": generate_pass_outcome_chart(player_name, team, season, filtered_passes)},
                {"key": "release", "title": "Release Times", "image": generate_release_time_chart(player_name, team, season, filtered_passes)},
                {"key": "zone", "title": "Pass Origin by Third", "image": generate_pass_zone_chart(player_name, team, season, filtered_passes)},
            ]

        elif category == "shooting":
            from visuals.shooting import generate_shooting_chart, generate_shot_distance_chart, generate_body_part_chart, generate_shot_funnel_chart
            shots = recs("shooting", ["x", "y", "outcome", "body_part"])
            charts = [
                {"key": "map", "title": "Shot Map", "image": generate_shooting_chart(player_name, team, season, shots)},
                {"key": "distance", "title": "Shot Distance", "image": generate_shot_distance_chart(player_name, team, season, shots)},
                {"key": "body_part", "title": "Body Part", "image": generate_body_part_chart(player_name, team, season, shots)},
                {"key": "funnel", "title": "Conversion Funnel", "image": generate_shot_funnel_chart(player_name, team, season, shots)},
            ]

        elif category == "carrying":
            from visuals.carrying import generate_carrying_chart, generate_carry_angle_rose, generate_carry_distance_chart, generate_takeon_chart
            show = tuple(filt.split(",")) if filt else ("prog_pass", "takeon_won", "takeon_lost")
            carries = recs("carrying", ["start_x", "start_y", "end_x", "end_y", "progressive", "followup"])
            takeons = recs("takeons", ["x", "y", "outcome"])
            map_chart, map_stats = generate_carrying_chart(player_name, team, season, carries, show=show)
            rose_chart, rose_stats = generate_carry_angle_rose(player_name, carries)
            chart_stats = {**map_stats, **rose_stats}
            charts = [
                {"key": "map", "title": "Progressive Carries", "image": map_chart},
                {"key": "rose", "title": "Carry Angle Rose", "image": rose_chart},
                {"key": "distance", "title": "Carry Distance", "image": generate_carry_distance_chart(player_name, team, season, carries)},
                {"key": "takeons", "title": "Take-Ons", "image": generate_takeon_chart(player_name, team, season, takeons)},
            ]

        elif category == "aerial":
            from visuals.aerial import generate_aerial_chart, generate_aerial_outcome_chart, generate_aerial_phase_chart
            phases = tuple(filt.split(",")) if filt else ("open_play", "set_piece")
            duels = recs("aerial", ["x", "y", "won", "phase"])
            stats = stats_for("aerial")
            charts = [
                {"key": "map", "title": "Duel Locations", "image": generate_aerial_chart(player_name, team, season, duels, phases=phases)},
                {"key": "outcome", "title": "After Winning a Duel", "image": generate_aerial_outcome_chart(player_name, team, season, stats)},
                {"key": "phase", "title": "Win Rate by Phase", "image": generate_aerial_phase_chart(player_name, team, season, stats, phases=phases)},
            ]

        elif category == "holdup":
            from visuals.holdup import generate_holdup_chart, generate_holdup_outcome_chart, generate_holdup_zone_volume_chart
            zone = filt or "final"
            all_episodes = recs("holdup", ["x", "y", "zone", "outcome"])
            episodes = all_episodes if zone == "whole" else [ep for ep in all_episodes if ep["zone"] == zone]
            charts = [
                {"key": "map", "title": "Hold-Up Episodes", "image": generate_holdup_chart(player_name, team, season, episodes, zone=zone)},
                {"key": "outcome", "title": "Outcome Breakdown", "image": generate_holdup_outcome_chart(player_name, team, season, episodes)},
                {"key": "zone_volume", "title": "Episodes by Zone", "image": generate_holdup_zone_volume_chart(player_name, team, season, all_episodes)},
            ]

        elif category == "half_spaces":
            from visuals.half_spaces import generate_half_space_chart, generate_half_space_zone_split_chart, generate_half_space_percentile_chart
            hs_mode = filt or "offensive"
            offense = recs("half_space_off", ["x", "y", "end_x", "end_y", "kind"])
            defense = recs("half_space_def", ["x", "y", "kind"])
            stats = stats_for("half_spaces")
            # Side Split mixes both regardless of mode (deliberately — "which
            # side is this player's half-space work concentrated on" doesn't
            # depend on offense/defense), but Percentiles switches with the map.
            charts = [
                {"key": "map", "title": "Half-Space Play", "image": generate_half_space_chart(player_name, team, season, offense, defense, mode=hs_mode)},
                {"key": "side_split", "title": "Side Split", "image": generate_half_space_zone_split_chart(player_name, team, season, offense, defense)},
                {"key": "percentiles", "title": "Percentiles", "image": generate_half_space_percentile_chart(player_name, team, season, stats, mode=hs_mode)},
            ]

        elif category == "tempo":
            from visuals.tempo import generate_tempo_chart, generate_tempo_release_chart, generate_tempo_balance_chart
            actions = recs("tempo", ["x", "y", "end_x", "end_y", "kind", "release_s"])
            charts = [
                {"key": "map", "title": "Tempo Actions", "image": generate_tempo_chart(player_name, team, season, actions)},
                {"key": "release", "title": "Release Times", "image": generate_tempo_release_chart(player_name, team, season, actions)},
                {"key": "balance", "title": "Injector vs Reset", "image": generate_tempo_balance_chart(player_name, team, season, actions)},
            ]

        elif category == "defending":
            from visuals.defending import generate_defending_chart, generate_defending_zone_chart, generate_defending_type_chart
            actions = recs("defending", ["x", "y", "action", "outcome"])
            charts = [
                {"key": "map", "title": "Defensive Actions", "image": generate_defending_chart(player_name, team, season, actions)},
                {"key": "zone", "title": "Actions by Zone", "image": generate_defending_zone_chart(player_name, team, season, actions)},
                {"key": "type", "title": "Action-Type Breakdown", "image": generate_defending_type_chart(player_name, team, season, actions)},
            ]

        elif category == "post_recovery":
            from visuals.post_recovery import generate_post_recovery_chart, generate_post_recovery_outcome_chart, generate_post_recovery_zone_chart
            recoveries = recs("post_recovery", ["x", "y", "end_x", "end_y", "outcome"])
            charts = [
                {"key": "map", "title": "Post-Recovery Sequences", "image": generate_post_recovery_chart(player_name, team, season, recoveries)},
                {"key": "outcome", "title": "Outcome Breakdown", "image": generate_post_recovery_outcome_chart(player_name, team, season, recoveries)},
                {"key": "zone", "title": "Recoveries by Third", "image": generate_post_recovery_zone_chart(player_name, team, season, recoveries)},
            ]

        elif category == "goalkeeping":
            from visuals.goalkeeping import generate_goalkeeping_chart, generate_gk_outcome_chart, generate_gk_distribution_chart
            shots = recs("goalkeeping", ["x", "y", "outcome"])
            stats = stats_for("goalkeeping")
            charts = [
                {"key": "map", "title": "Shots Faced", "image": generate_goalkeeping_chart(player_name, team, season, shots)},
                {"key": "outcome", "title": "Shot Outcome", "image": generate_gk_outcome_chart(player_name, team, season, shots)},
                {"key": "distribution", "title": "Distribution Profile", "image": generate_gk_distribution_chart(player_name, team, season, stats)},
            ]

        elif category == "decision_making":
            from visuals.decision_making import generate_decision_bloom_chart, generate_decision_bar_chart
            stats = stats_for("decision_making")
            charts = [
                {"key": "bloom", "title": "Decision-Making Bloom", "image": generate_decision_bloom_chart(player_name, team, season, stats)},
                {"key": "bar", "title": "Percentile Ranking", "image": generate_decision_bar_chart(player_name, team, season, stats)},
            ]

        elif category == "final_third":
            from visuals.final_third import generate_final_third_scatter, generate_pillar_bar_chart, generate_completeness_distribution_chart
            position = row.get("position", "")
            points = pct_mod.build_final_third_scatter(position, season, df, player_id)
            cohort = pct_mod.build_cohort(df, position, season)
            floor_pct, per_touch_pct, _, _ = pct_mod.final_third_pillar_percentiles(row, cohort, df, season)
            target = next((p for p in points if p["is_target"]), None)
            player_completeness = target["completeness"] if target else None
            charts = [
                {"key": "scatter", "title": "Completeness vs Impact", "image": generate_final_third_scatter(player_name, team, season, points)},
                {"key": "pillars", "title": "Four Pillars", "image": generate_pillar_bar_chart(player_name, team, season, floor_pct, per_touch_pct)},
                {"key": "distribution", "title": "Cohort Distribution", "image": generate_completeness_distribution_chart(player_name, team, season, points, player_completeness)},
            ]

        else:
            return jsonify({"error": f"Unknown category '{category}'"}), 400

        # Shared across every category — "is this player trending up or down
        # relative to their cohort", something multi-season data already
        # supports but nothing else in the app surfaces.
        from core.advanced.composite import category_percentile_trend
        from core.advanced.metrics_master import CATEGORIES
        from visuals.chart_utils import generate_trend_chart

        trend_seasons = list(reversed(SEASONS))  # oldest -> newest for a left-to-right timeline
        trend_values = category_percentile_trend(player_id, category, trend_seasons, df)
        charts.append({
            "key": "trend",
            "title": "Season Trend",
            "image": generate_trend_chart(
                player_name, f"{CATEGORIES[category]['label']} · percentile by season",
                trend_seasons, trend_values,
            ),
        })

        result = {"charts": charts}
        if chart_stats is not None:
            result["stats"] = chart_stats
        if len(_chart_cache) >= _CACHE_MAX:
            _chart_cache.pop(next(iter(_chart_cache)))
        _chart_cache[cache_key] = result
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — Compare (2-4 players side by side, built on the same event data)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/compare-stats", methods=["POST"])
def api_compare_stats():
    try:
        body = request.get_json(force=True)
        players_in = body.get("players", [])
        if not (2 <= len(players_in) <= 4):
            return jsonify({"error": "Provide 2-4 players"}), 400

        from core.advanced.store import get_advanced_df
        from core.advanced.identity import match_to_advanced_row
        from core.advanced.lookup import _clean_position, _clean_minutes
        from core.advanced.percentiles import build_all_categories
        from core.advanced.composite import compute_composite
        from visuals.compare import generate_comparison_radar, generate_composite_bar_chart, generate_category_comparison_chart

        df = get_advanced_df()
        if df.empty:
            return jsonify({"error": "No data"}), 404

        players = []
        for p in players_in:
            pid = int(p["player_id"])
            league = p.get("league", "Premier League")
            season = p.get("season", "2024-25")
            row = match_to_advanced_row(pid, league, season, df)
            if row is None:
                return jsonify({"error": f"No data for player {pid} in {league} {season}"}), 404
            # Photo is intentionally NOT fetched here (that's a synchronous
            # network call to Wikipedia per player) — the frontend lazy-loads
            # it client-side after the card is already on screen, same as
            # the Player and Scout pages.
            position = _clean_position(row.get("position"))
            cats = build_all_categories(row, row.get("position", ""), season, df)
            players.append({
                "player_id": pid, "name": row.get("player_name"), "team": row.get("team_name"),
                "league": league, "season": season, "position": position,
                "minutes": _clean_minutes(row.get("total_minutes")),
                "cats": cats, "composite": compute_composite(cats, row.get("position", "")),
            })

        cache_key = ("compare_charts", tuple(sorted((p["player_id"], p["league"], p["season"]) for p in players)))
        if cache_key in _chart_cache:
            charts = _chart_cache[cache_key]
        else:
            charts = [
                {"key": "composite", "title": "Composite Rating", "image": generate_composite_bar_chart(players)},
                {"key": "radar", "title": "Headline Comparison", "image": generate_comparison_radar(players)},
                {"key": "categories", "title": "Category Percentile Comparison", "image": generate_category_comparison_chart(players)},
            ]
            if len(_chart_cache) >= _CACHE_MAX:
                _chart_cache.pop(next(iter(_chart_cache)))
            _chart_cache[cache_key] = charts

        return jsonify({"players": players, "charts": charts})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — Scout (whole-profile percentile-vector similarity search)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/scout-similar", methods=["POST"])
def api_scout_similar():
    try:
        body      = request.get_json(force=True)
        player_id = int(body["player_id"])
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")
        max_age   = body.get("max_age")
        max_age   = int(max_age) if max_age not in (None, "", "none") else None
        league_pool = body.get("league_pool", "all")
        if league_pool == "top5":
            leagues = TOP5_LEAGUES
        elif league_pool and league_pool != "all":
            leagues = [league_pool]
        else:
            leagues = None

        from core.advanced.store import get_advanced_df
        from core.advanced.identity import match_to_advanced_row
        from core.advanced.lookup import _clean_position, _clean_age, _clean_minutes
        from core.advanced.scout import find_similar

        df = get_advanced_df()
        if df.empty:
            return jsonify({"error": "No data"}), 404

        target_row = match_to_advanced_row(player_id, league, season, df)
        if target_row is None:
            return jsonify({"error": "No data for this player/season"}), 404
        # No photo fetch here — scout.js already rendered the target header
        # (with an initials placeholder) from the /api/search result before
        # this request even started, and lazy-loads the real photo itself.

        matches, widened = find_similar(df, player_id, league, season, limit=20, max_age=max_age, leagues=leagues)
        return jsonify({
            "target": {
                "player_id": player_id, "name": target_row.get("player_name"),
                "team": target_row.get("team_name"), "league": league, "season": season,
                "position": _clean_position(target_row.get("position")),
                "age": _clean_age(target_row.get("age")),
                "minutes": _clean_minutes(target_row.get("total_minutes")),
            },
            "matches": matches,
            "widened": widened,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — Explore (ranked stat browsing — discovery without a reference player)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/explore", methods=["POST"])
def api_explore():
    try:
        body = request.get_json(force=True)
        metric_col = body["metric"]
        season = body.get("season", "2024-25")
        league = body.get("league", "all")
        position_group = body.get("position_group", "all")
        min_minutes = body.get("min_minutes")
        min_minutes = int(min_minutes) if min_minutes not in (None, "", "none") else None

        from core.advanced.store import get_advanced_df
        from core.advanced.explore import rank_players

        df = get_advanced_df()
        if df.empty:
            return jsonify({"error": "No data"}), 404

        results = rank_players(
            df, metric_col, season, league=league, position_group=position_group,
            min_minutes=min_minutes, limit=25,
        )
        return jsonify({"results": results})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    # Render (and most hosts) set PORT and expect a bind on 0.0.0.0. Debug
    # mode stays local-only — the Werkzeug debugger it enables lets anyone
    # who can reach an unhandled-exception page execute arbitrary code,
    # which is fine on localhost but not something to expose publicly.
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False, threaded=True)
