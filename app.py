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
]

# Only seasons we actually have scraped Advanced Metrics data for.
SEASONS = ["2025-26", "2024-25", "2023-24"]


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("player.html", leagues=LEAGUES, seasons=SEASONS)


@app.route("/player")
def player_page():
    return render_template("player.html", leagues=LEAGUES, seasons=SEASONS)


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

    if len(name) < 3:
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

        df = get_advanced_df()
        if df.empty:
            return jsonify({"player": raw, "categories": []})

        row = match_to_advanced_row(player_id, league, season, df)
        if row is None:
            return jsonify({"player": raw, "categories": []})

        categories = build_all_categories(row, raw.get("position", ""), season, df)
        return jsonify({"player": raw, "categories": categories})
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

        from core.advanced.store import get_linkup_df

        link_df = get_linkup_df()
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

        from core.advanced.store import get_linkup_df

        link_df = get_linkup_df()
        if link_df.empty:
            return jsonify({"error": "No data"}), 400

        match = link_df[(link_df["passer_id"] == passer_id) & (link_df["receiver_id"] == teammate_id)
                         & (link_df["league"] == league) & (link_df["season"] == season)]
        if match.empty:
            return jsonify({"error": "No data for this pair"}), 404
        pair = match.iloc[0]

        receptions = [
            {"reception_x": pair["reception_x"][i], "reception_y": pair["reception_y"][i],
             "outcome": pair["outcome"][i], "end_x": pair["end_x"][i], "end_y": pair["end_y"][i]}
            for i in range(len(pair["reception_x"]))
        ]

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


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
