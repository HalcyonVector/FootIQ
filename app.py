"""
FootIQ — Flask Application
REST API routes + Jinja2 page rendering.

Stats-first: search a player, see their event-derived Advanced Metrics
(12 tabs) and Combination Play. Everything is built from the scraped
WhoScored/Opta match data (core/advanced/) — the old FBref-CSV-backed
simple-stats/Compare/Scout system has been retired.
"""
import os
import threading
import time
import traceback
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_compress import Compress

from core.advanced import config as advanced_config
from core.advanced.lookup import search_players, search_players_global, search_players_any, get_player_stats, build_search_index
from core.media import get_wikimedia_image

app = Flask(__name__)
CORS(app)
# gzip/brotli for HTML, JSON, CSS and JS: the page shell is ~250 KB of text and
# the stats/overview JSON 15-40 KB each, all of which shrink 4-8x. Matters most
# on a slow free-tier link and a throttled CPU.
Compress(app)
app.config["COMPRESS_MIN_SIZE"] = 500
# Static files revalidate via ETag after 5 minutes rather than on every page
# view (Flask's default is "no-cache"). Short on purpose: the JS and the API
# shape change together on a deploy.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300

_GZIP_STATIC: dict = {}   # (ETag) -> gzipped body; the static files are small and change only on deploy


@app.after_request
def _gzip_static(resp):
    """flask-compress skips streamed responses, which is what static files are,
    so the 90 KB stylesheet and the JS went out raw. gzip them here, cached by
    ETag so each file is compressed once per deploy."""
    if request.endpoint != "static" or resp.status_code != 200 or resp.headers.get("Content-Encoding"):
        return resp
    if "gzip" not in request.headers.get("Accept-Encoding", "") or resp.mimetype not in (
            "text/css", "text/javascript", "application/javascript", "image/svg+xml"):
        return resp
    etag = resp.headers.get("ETag")
    body = _GZIP_STATIC.get(etag) if etag else None
    if body is None:
        import gzip
        resp.direct_passthrough = False
        body = gzip.compress(resp.get_data(), compresslevel=6)
        if etag:
            _GZIP_STATIC[etag] = body
    resp.set_data(body)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Vary"] = "Accept-Encoding"
    return resp


# In-memory chart cache: key = whatever the caller builds it as.
# Stores chart specs (small JSON, drawn client-side by static/js/charts.js).
_chart_cache: dict = {}
_CACHE_MAX = 200   # evict oldest when this is exceeded

# Loads the parquet caches and builds all 12 chart Dataset objects once, so no
# visitor's request pays for it (measured live before this existed: a
# category-chart request on a cold worker took 40s). It runs in a BACKGROUND
# thread so gunicorn starts accepting connections immediately: the HTML pages,
# CSS and JS (which need no data) load at once on a cold start, and only the
# /api/ calls that read data wait here until the warm-up is done. Before this,
# the whole site was a blank screen for the entire warm-up on Render's 0.1 CPU.
# If warm-up itself fails the flag is still set, and requests fall back to
# the normal lazy-load path rather than hanging.
_WARM = threading.Event()
_WARM_STATE = {"step": "starting", "since": time.time()}
_NO_DATA_API = ("/api/leagues", "/api/player-image", "/api/health")   # never touch the parquet caches


# Import everything the warm-up touches HERE, in the importing (main) thread, before
# the thread starts. Importing the same modules from two threads at once can
# deadlock on Python's per-module import locks -- on Render this left the warm-up
# frozen on its first import forever.
from core.advanced import store as _store_mod            # noqa: E402
from core.advanced import aggregator as _aggregator_mod  # noqa: E402,F401
import core.media, core.position                         # noqa: E402,F401


def _warm_up_in_background() -> None:
    done = _WARM
    try:
        _warm_up_store = _store_mod.warm_up

        def progress(name):
            _WARM_STATE["step"] = name
            print(f"[warm-up] {time.time() - _WARM_STATE['since']:6.1f}s  {name}", flush=True)
        _warm_up_store(progress)
        progress("search index")
        build_search_index()
        progress("done")
    except Exception:
        _WARM_STATE["step"] = "failed: " + traceback.format_exc().splitlines()[-1]
        traceback.print_exc()
    finally:
        done.set()


def _start_warm_up() -> None:
    """(Re)start the warm-up in THIS process. Threads do not survive fork(): on Render the
    app is imported before gunicorn forks its worker, so the thread started at import
    time only ever existed in the parent -- the worker inherited an unset flag and no
    thread, and every data request waited forever. So it also restarts itself in each
    forked child. The Event is replaced too, since a copied one can carry a lock that
    was held by a thread that no longer exists."""
    global _WARM
    _WARM = threading.Event()
    _WARM_STATE.update(step="starting", since=time.time(), pid=os.getpid())
    threading.Thread(target=_warm_up_in_background, name="warm-up", daemon=True).start()


_start_warm_up()
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_start_warm_up)


@app.before_request
def _wait_for_warm_up():
    if not _WARM.is_set() and request.path.startswith("/api/") and request.path not in _NO_DATA_API:
        if not _WARM.wait(timeout=90):
            # Don't fall through into the lazy loaders while the warm-up thread is
            # mid-load: that would build a second copy of the data in 512MB of RAM.
            return jsonify({"error": "The server is still loading its data, try again in a moment.",
                            "step": _WARM_STATE["step"]}), 503


@app.route("/api/health")
def api_health():
    out = {"warm": _WARM.is_set(), "step": _WARM_STATE["step"], "seconds": round(time.time() - _WARM_STATE["since"], 1),
           "pid": os.getpid(), "warm_started_in_pid": _WARM_STATE.get("pid")}
    if request.args.get("stack"):   # where is each thread right now? (for diagnosing a slow boot)
        import sys
        frames = sys._current_frames()
        out["threads"] = {f"{t.name}#{t.ident}": traceback.format_stack(frames[t.ident])[-5:]
                          for t in threading.enumerate() if t.ident in frames and t.name != threading.current_thread().name}
    return jsonify(out)


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

# Domestic seasons computed from today's date (see core/advanced/config.py's
# all_domestic_seasons() docstring for why this used to be a hardcoded list
# and why that was a real bug), plus the two single-year competitions we
# have scraped data for (World Cup 2022, Euro 2024) — picking one of the
# top-3 rows with, say, "Champions League" just yields an honest "no data"
# until that season/league combo exists. World Cup 2026 already happened as
# of this writing but hasn't been scraped yet, so it's deliberately not
# listed here — an entry with no backing data is worse UX than no entry.
SEASONS = advanced_config.all_domestic_seasons() + ["2022", "2024"]

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


@app.route("/league")
def league_page():
    return render_template("league.html", leagues=LEAGUES, seasons=SEASONS)


@app.route("/team")
def team_page():
    return render_template("team.html", leagues=LEAGUES, seasons=SEASONS)


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


@app.route("/api/player")
def api_player():
    """One player for a given league/season (same shape the search results
    use) plus every season they appear in. Backs shareable /player?id=...
    links and the profile's season switcher. Falls back to another season
    in the same league if the requested one has no row (see
    get_player_stats), so the caller should read `player.season`."""
    try:
        player_id = int(request.args["id"])
    except (KeyError, ValueError):
        return jsonify({"error": "id required"}), 400
    league = request.args.get("league", "Premier League")
    season = request.args.get("season", "")
    from core.advanced.lookup import get_player_seasons
    seasons = get_player_seasons(player_id)
    player = get_player_stats(player_id, league, season)
    if not player and seasons:
        # unknown league/season combo: land on the player's newest season instead
        player = get_player_stats(player_id, seasons[0]["league"], seasons[0]["season"])
    if not player:
        return jsonify({"player": None, "seasons": []}), 404

    from core.advanced import store
    from core.advanced.summary import sample_info
    from core.advanced.lookup import get_season_progress
    from core.advanced.config import minutes_floor_for
    progress = get_season_progress(player["league"], player["season"])
    floor = minutes_floor_for(progress)
    played_for = {r["team"] for r in store.get_player_matches(player["id"], player["league"], player["season"])}
    counts = store.get_team_match_counts(player["league"], player["season"])
    team_matches = max((counts.get(t, 0) for t in played_for), default=0)
    return jsonify({"player": player, "seasons": seasons,
                    "sample": sample_info(player["minutes"], team_matches, floor=floor, progress=progress)})


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
        if request.args.get("any_season") == "1":
            return jsonify(search_players_any(name))
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
# API — home page facts and featured players (all real, computed from the dataset)
# ─────────────────────────────────────────────────────────────────────────────
_HUB: dict = {}
_FEATURED_NAMES = ["Erling Haaland", "Mohamed Salah", "Bukayo Saka", "Virgil van Dijk"]


def _hub_facts() -> dict:
    if "facts" in _HUB:
        return _HUB["facts"]
    import json as _json
    from core.advanced import config as _cfg, store as _store
    from core.advanced.metrics_master import CATEGORIES
    from datetime import date
    df = _store.get_advanced_df()
    counts = df["season"].value_counts()
    full_season = max((s for s, c in counts.items() if c >= 0.9 * counts.max()), key=_cfg.season_sort_key)
    matches = 0
    try:
        import pyarrow.dataset as pa_ds
        ds = _store._overview_dataset("matches", _cfg.PLAYER_MATCHES_DIR)
        matches = len(set(ds.to_table(columns=["match_key"]).column("match_key").to_pylist()))
    except Exception:
        traceback.print_exc()
    updated = ""
    try:
        built = _json.load(open(os.path.join(os.path.dirname(_cfg.PLAYER_SEASON_PARQUET), "..", "DATA_VERSION")))["built"]
        d = date.fromisoformat(built)
        updated = f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        pass
    featured = []
    for nm in _FEATURED_NAMES:
        hit = search_players_global(nm, full_season)
        if hit:
            featured.append({k: hit[0][k] for k in ("id", "name", "team", "league", "season")})
    _HUB["facts"] = {
        "updated": updated, "matches": matches, "players": int(df["whoscored_player_id"].nunique()),
        "metrics": sum(len(c["metrics"]) for c in CATEGORIES.values()), "season": full_season, "featured": featured,
    }
    return _HUB["facts"]


@app.route("/api/hub")
def api_hub():
    try:
        return jsonify(_hub_facts())
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/hub-player")
def api_hub_player():
    """Real numbers for one featured player: the six radar percentiles, the season
    goals line and the Final Third score -- the same figures the Player page shows."""
    try:
        i = int(request.args.get("i", 0))
        facts = _hub_facts()
        if not (0 <= i < len(facts["featured"])):
            return jsonify({"error": "no such player"}), 404
        if ("player", i) in _HUB:
            return jsonify(_HUB[("player", i)])
        p = facts["featured"][i]
        from core.advanced import store as _store, summary as _summary
        from core.advanced.identity import match_to_advanced_row
        from core.advanced.percentiles import build_all_categories
        from visuals import specs as sp
        df = _store.get_advanced_df()
        row = match_to_advanced_row(p["id"], p["league"], p["season"], df)
        cats = build_all_categories(row, row.get("position", ""), p["season"], df)
        axes = [{"label": lbl, "value": round(sp._percentile_for(cats, k, l))} for (k, l), lbl in zip(sp.RADAR_METRICS, sp.RADAR_LABELS)]
        line = _summary.season_line(_store.get_player_matches(p["id"], p["league"], p["season"]))
        out = {**p, "axes": axes, "goals": line["goals"], "assists": line["assists"],
               "final_third": next((a["value"] for a in axes if a["label"] == "Final Third"), None)}
        _HUB[("player", i)] = out
        return jsonify(out)
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
        from core.advanced.summary import insights
        return jsonify({"player": raw, "categories": categories, "composite": composite,
                        "insights": insights(categories)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/player-overview", methods=["POST"])
def api_player_overview():
    """Season stat line, form, career table, shot map (with xG) and
    heatmaps for one player-season -- the "paid-site" overview. Reads only
    this player's slice of the partitioned Overview tables."""
    try:
        body      = request.get_json(force=True)
        player_id = int(body["player_id"])
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")

        # Resolve the season the stats card actually shows (lookup falls
        # back to another season if this one has no row).
        raw = get_player_stats(player_id, league, season)
        if raw:
            season = raw["season"]

        from core.advanced import store, summary

        rows = store.get_player_matches(player_id, league, season)
        if not rows:
            return jsonify({"available": False})

        return jsonify({
            "available": True,
            "season": season,
            "line": summary.season_line(rows),
            "form": summary.form(rows),
            "career": summary.career(store.get_player_matches(player_id)),
            **_overview_visuals(player_id, league, season),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _overview_visuals(player_id: int, league: str, season: str) -> dict:
    """Shot map + heatmap payload shared by the profile Overview and Compare."""
    from core.advanced import store
    from core.advanced.overview import GRID_X, GRID_Y
    return {
        "shots": store.get_player_shots(player_id, league, season),
        "heat": store.get_player_heat(player_id, league, season),
        "grid": {"x": GRID_X, "y": GRID_Y},
    }


@app.route("/api/pass-map", methods=["POST"])
def api_pass_map():
    """Passes (with progressive / into-box flags) and the chances this player
    created, for the profile's pass map. Coordinates are compact arrays; the
    client filters by mode."""
    try:
        body      = request.get_json(force=True)
        player_id = int(body["player_id"])
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")

        from core.advanced import store
        events = store.get_chart_events("passing", player_id, league, season)
        chances = store.get_chances_created(player_id, league, season)
        if not events and not chances:
            return jsonify({"available": False})

        # [x, y, end_x, end_y, flags]  flags: 1 = completed, 2 = progressive, 4 = into box
        passes = []
        for e in events:
            if e.get("x") is None or e.get("end_x") is None:
                continue
            flags = (1 if e.get("completed") else 0) | (2 if e.get("progressive") else 0) | (4 if e.get("into_box") else 0)
            passes.append([round(e["x"], 1), round(e["y"], 1), round(e["end_x"], 1), round(e["end_y"], 1), flags])
        chances = [c for c in chances if c.get("ax") is not None and c.get("aex") is not None]
        return jsonify({"available": True, "passes": passes, "chances": chances})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — league tables and team pages (built from the per-match rows)
# ─────────────────────────────────────────────────────────────────────────────

_LEAGUE_IDS = {lg["id"] for lg in LEAGUES}
_CUP_COMPETITIONS = {lg["id"] for lg in LEAGUES if lg["country"] in ("Europe", "International")}


@app.route("/api/league-table")
def api_league_table():
    league = request.args.get("league", "Premier League")
    season = request.args.get("season", "")
    if league not in _LEAGUE_IDS:
        return jsonify({"error": "unknown league"}), 400
    try:
        from core.advanced import store, tables
        table = tables.league_table(store.get_season_matches(league, season))
        return jsonify({"league": league, "season": season, "table": table, "cup": league in _CUP_COMPETITIONS})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/team")
def api_team():
    league = request.args.get("league", "Premier League")
    season = request.args.get("season", "")
    team = request.args.get("team", "").strip()
    if league not in _LEAGUE_IDS or not team:
        return jsonify({"error": "league and team required"}), 400
    try:
        from core.advanced import store, tables
        rows = store.get_season_matches(league, season)
        adv = store.get_advanced_df()
        names = {}
        if not adv.empty:
            cur = adv[(adv["league"] == league) & (adv["season"] == season)]
            names = dict(zip(cur["whoscored_player_id"].astype(int), cur["player_name"]))
        page = tables.team_page(rows, team, names)
        if page is None:
            return jsonify({"error": "team not found"}), 404
        return jsonify({"league": league, "season": season, "cup": league in _CUP_COMPETITIONS, **page})
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
            from visuals import specs as _specs
            spec = _specs.linkup_map(pair["passer_name"], receptions)
            if len(_chart_cache) >= _CACHE_MAX:
                _chart_cache.pop(next(iter(_chart_cache)))
            _chart_cache[cache_key] = spec
        else:
            spec = _chart_cache[cache_key]

        return jsonify({
            "stats": {
                "prog_passes": counts.get("prog_pass", 0),
                "prog_carries": counts.get("prog_carry", 0),
                "take_ons_won": counts.get("takeon_won", 0),
                "take_ons_lost": counts.get("takeon_lost", 0),
                "shots": counts.get("shot", 0),
                "receptions": len(receptions),
            },
            "spec": spec,
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

        from visuals import specs as sp

        chart_stats = None  # only Carrying returns this -- its counts render as HTML chips
        charts = []  # list of {key, title, spec}

        def chart(key, title, spec):
            charts.append({"key": key, "title": title, "spec": spec})

        if category == "passing":
            passes = recs("passing", ["x", "y", "end_x", "end_y", "completed", "progressive", "into_box", "release_s"])
            mode = filt or "progressive"
            # Every companion chart respects the same filter as the map --
            # "Progressive & into box" looks at just that subset, not the whole
            # season, so the tile grid never shows charts that look identical
            # regardless of which toggle is picked.
            filtered_passes = [p for p in passes if p["progressive"] or p["into_box"]] if mode == "progressive" else passes
            chart("map", "Pass Map", sp.passing_map(passes, mode))
            chart("outcome", "Outcome Breakdown", sp.pass_outcomes(filtered_passes))
            chart("release", "Release Times", sp.release_times(filtered_passes))
            chart("zone", "Pass Origin by Third", sp.pass_zones(filtered_passes))

        elif category == "shooting":
            shots = recs("shooting", ["x", "y", "outcome", "body_part"])
            chart("map", "Shot Map", sp.shot_map(shots))
            chart("distance", "Shot Distance", sp.shot_distance(shots))
            chart("body_part", "Body Part", sp.shot_body_parts(shots))
            chart("funnel", "Conversion Funnel", sp.shot_funnel(shots))

        elif category == "carrying":
            show = tuple(filt.split(",")) if filt else ("prog_pass", "takeon_won", "takeon_lost")
            carries = recs("carrying", ["start_x", "start_y", "end_x", "end_y", "progressive", "followup"])
            takeons = recs("takeons", ["x", "y", "outcome"])
            map_spec, map_stats = sp.carry_map(carries, show=show)
            rose_spec, rose_stats = sp.carry_rose(carries)
            chart_stats = {**map_stats, **rose_stats}
            chart("map", "Progressive Carries", map_spec)
            chart("rose", "Carry Angle Rose", rose_spec)
            chart("distance", "Carry Distance", sp.carry_distance(carries))
            chart("takeons", "Take-Ons", sp.takeon_map(takeons))

        elif category == "aerial":
            phases = tuple(filt.split(",")) if filt else ("open_play", "set_piece")
            duels = recs("aerial", ["x", "y", "won", "phase"])
            stats = stats_for("aerial")
            chart("map", "Duel Locations", sp.aerial_map(duels, phases))
            chart("outcome", "After Winning a Duel", sp.aerial_outcomes(stats))
            chart("phase", "Win Rate by Phase", sp.aerial_phases(stats, phases))

        elif category == "holdup":
            zone = filt or "final"
            all_episodes = recs("holdup", ["x", "y", "zone", "outcome"])
            episodes = all_episodes if zone == "whole" else [ep for ep in all_episodes if ep["zone"] == zone]
            chart("map", "Hold-Up Episodes", sp.holdup_map(episodes))
            chart("outcome", "Outcome Breakdown", sp.holdup_outcomes(episodes))
            chart("zone_volume", "Episodes by Zone", sp.holdup_zones(all_episodes))

        elif category == "half_spaces":
            hs_mode = filt or "offensive"
            offense = recs("half_space_off", ["x", "y", "end_x", "end_y", "kind"])
            defense = recs("half_space_def", ["x", "y", "kind"])
            stats = stats_for("half_spaces")
            # Side Split mixes both regardless of mode (deliberately), but
            # Percentiles switches with the map.
            chart("map", "Half-Space Play", sp.half_space_map(offense, defense, hs_mode))
            chart("side_split", "Side Split", sp.half_space_sides(offense, defense))
            chart("percentiles", "Percentiles", sp.half_space_percentiles(stats, hs_mode))

        elif category == "tempo":
            actions = recs("tempo", ["x", "y", "end_x", "end_y", "kind", "release_s"])
            chart("map", "Tempo Actions", sp.tempo_map(actions))
            chart("release", "Release Times", sp.tempo_release(actions))
            chart("balance", "Injector vs Reset", sp.tempo_balance(actions))

        elif category == "defending":
            actions = recs("defending", ["x", "y", "action", "outcome"])
            chart("map", "Defensive Actions", sp.defending_map(actions))
            chart("zone", "Actions by Zone", sp.defending_zones(actions))
            chart("type", "Action-Type Breakdown", sp.defending_types(actions))

        elif category == "post_recovery":
            recoveries = recs("post_recovery", ["x", "y", "end_x", "end_y", "outcome"])
            chart("map", "Post-Recovery Sequences", sp.post_recovery_map(recoveries))
            chart("outcome", "Outcome Breakdown", sp.post_recovery_outcomes(recoveries))
            chart("zone", "Recoveries by Third", sp.post_recovery_zones(recoveries))

        elif category == "goalkeeping":
            shots = recs("goalkeeping", ["x", "y", "outcome"])
            stats = stats_for("goalkeeping")
            chart("map", "Shots Faced", sp.gk_map(shots))
            chart("outcome", "Shot Outcome", sp.gk_outcomes(shots))
            chart("distribution", "Distribution Profile", sp.gk_distribution(stats))

        elif category == "decision_making":
            stats = stats_for("decision_making")
            chart("bloom", "Decision-Making Bloom", sp.decision_bloom(stats))
            chart("bar", "Percentile Ranking", sp.decision_bars(stats))

        elif category == "final_third":
            position = row.get("position", "")
            points = pct_mod.build_final_third_scatter(position, season, df, player_id)
            cohort = pct_mod.build_cohort(df, position, season)
            floor_pct, per_touch_pct, _, _ = pct_mod.final_third_pillar_percentiles(row, cohort, df, season)
            target = next((p for p in points if p["is_target"]), None)
            player_completeness = target["completeness"] if target else None
            chart("scatter", "Completeness vs Impact", sp.final_third_scatter(player_name, points))
            chart("pillars", "Four Pillars", sp.pillar_bars(floor_pct, per_touch_pct))
            chart("distribution", "Cohort Distribution", sp.completeness_distribution(player_name, points, player_completeness))

        else:
            return jsonify({"error": f"Unknown category '{category}'"}), 400

        # Shared across every category -- "is this player trending up or down
        # relative to their cohort", something multi-season data already
        # supports but nothing else in the app surfaces.
        from core.advanced.composite import category_percentile_trend
        from core.advanced.metrics_master import CATEGORIES

        # Chronological oldest -> newest for a left-to-right timeline. SEASONS
        # is dropdown-display order (newest domestic season first, tournament
        # one-offs tacked on the end), NOT a timeline -- sort by the real
        # calendar order instead (see season_sort_key's docstring).
        trend_seasons = sorted(SEASONS, key=advanced_config.season_sort_key)
        trend_values = category_percentile_trend(player_id, category, trend_seasons, df)
        chart("trend", "Season Trend",
              sp.trend(trend_seasons, trend_values, sub=f"{CATEGORIES[category]['label']} · percentile by season"))

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
        from visuals import specs as sp

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
            from core.advanced import store as _store, summary as _summary
            mrows = _store.get_player_matches(pid, league, season)
            players.append({
                "player_id": pid, "name": row.get("player_name"), "team": row.get("team_name"),
                "league": league, "season": season, "position": position,
                "minutes": _clean_minutes(row.get("total_minutes")),
                "cats": cats, "composite": compute_composite(cats, row.get("position", "")),
                # season stat line + shot map + heatmap (None until the overview tables are built)
                "overview": ({"line": _summary.season_line(mrows), **_overview_visuals(pid, league, season)}
                             if mrows else None),
            })

        cache_key = ("compare_charts", tuple(sorted((p["player_id"], p["league"], p["season"]) for p in players)))
        if cache_key in _chart_cache:
            charts = _chart_cache[cache_key]
        else:
            charts = [
                {"key": "composite", "title": "Composite Rating", "spec": sp.compare_composite(players)},
                {"key": "radar", "title": "Headline Comparison", "spec": sp.compare_radar(players)},
                {"key": "categories", "title": "Category Percentile Comparison", "spec": sp.compare_categories(players)},
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
        limit     = min(max(int(body.get("limit", 20)), 1), 20)
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

        matches, widened = find_similar(df, player_id, league, season, limit=limit, max_age=max_age, leagues=leagues)
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
