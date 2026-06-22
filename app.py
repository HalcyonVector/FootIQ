"""
FootIQ — Flask Application
REST API routes + Jinja2 page rendering.
"""
import traceback
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from core.fetcher import (search_players, search_players_global,
                           get_player_stats, search_players_by_league,
                           get_wikimedia_image)
from core.normalizer import normalize_stats
from core.scorer import (compute_composite_score, compute_composite_score_from_cfg,
                          get_radar_data,
                          get_position_config, get_archetype_scores,
                          get_season_metric_set, get_comparison_metric_set)
from core.adjuster import adjust_norm
from core.archetype import classify
from core.insights import generate_insights
from visuals.radar import generate_radar
from visuals.bar import generate_bar
from visuals.percentile import generate_percentile
from visuals.pizza import generate_pizza
from visuals.lollipop import generate_lollipop
from visuals.solo import generate_solo_radar, generate_archetype_radar, generate_efficiency_chart

app = Flask(__name__)
CORS(app)

# In-memory chart cache: key = (player_id, league, season, adjusted, c1)
# Stores pre-rendered base64 chart PNGs so repeat searches are instant
_chart_cache: dict = {}
_CACHE_MAX = 200   # evict oldest when this is exceeded

LEAGUES = [
    {"id": "Premier League", "name": "Premier League", "country": "England", "logo": "https://media.api-sports.io/football/leagues/39.png"},
    {"id": "La Liga",        "name": "La Liga",         "country": "Spain",   "logo": "https://media.api-sports.io/football/leagues/140.png"},
    {"id": "Serie A",        "name": "Serie A",         "country": "Italy",   "logo": "https://media.api-sports.io/football/leagues/135.png"},
    {"id": "Bundesliga",     "name": "Bundesliga",      "country": "Germany", "logo": "https://media.api-sports.io/football/leagues/78.png"},
    {"id": "Ligue 1",        "name": "Ligue 1",         "country": "France",  "logo": "https://static.wikia.nocookie.net/logopedia/images/3/31/Ligue_1_2024.png"},
]

SEASONS = ["2024-25", "2023-24", "2022-23", "2021-22"]

POS_GROUPS = {
    "attacker":   ["attacker", "forward", "winger", "striker", "fw"],
    "midfielder": ["midfielder", "midfield", "mf"],
    "defender":   ["defender", "back", "defence", "defense", "df"],
    "goalkeeper": ["goalkeeper", "keeper", "gk"],
}


def _pos_group(pos_str: str) -> str:
    low = (pos_str or "").lower().strip()
    # Handle exact short codes first (CSV uses FW, MF, DF, GK)
    if low == "fw":   return "attacker"
    if low == "mf":   return "midfielder"
    if low == "df":   return "defender"
    if low == "gk":   return "goalkeeper"
    # Handle compound codes like "FW,MF" — use the first part
    if "," in low:
        low = low.split(",")[0].strip()
        if low == "fw": return "attacker"
        if low == "mf": return "midfielder"
        if low == "df": return "defender"
        if low == "gk": return "goalkeeper"
    for group, keys in POS_GROUPS.items():
        if any(k in low for k in keys):
            return group
    return "attacker"


def _filter_cfg_to_available(cfg: dict, norm: dict) -> dict:
    """Remove metrics that have no data (value is 0 or None) for this player."""
    keep = [(m, l, mx, w) for m, l, mx, w in zip(
        cfg["metrics"], cfg["labels"], cfg["max_vals"], cfg["weights"]
    ) if (norm.get(m) or 0) > 0]
    if not keep:
        return cfg  # fallback: return original if everything is 0
    metrics, labels, max_vals, weights = zip(*keep)
    return {"metrics": list(metrics), "labels": list(labels),
            "max_vals": list(max_vals), "weights": list(weights)}


def _player_summary(raw: dict, score: float) -> dict:
    return {
        "id":           raw["id"],
        "name":         raw["name"],
        "photo":        raw.get("photo", ""),
        "age":          raw.get("age", ""),
        "nationality":  raw.get("nationality", ""),
        "team":         raw.get("team", ""),
        "team_logo":    raw.get("team_logo", ""),
        "league":       raw.get("league", ""),
        "league_logo":  raw.get("league_logo", ""),
        "position":     raw.get("position", ""),
        "appearances":  raw.get("appearances", 0),
        "minutes":      raw.get("minutes", 0),
        "goals":        raw.get("goals", 0),
        "assists":      raw.get("assists", 0),
        "yellow_cards": raw.get("yellow_cards", 0),
        "red_cards":    raw.get("red_cards", 0),
        "score":        score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pages
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("hub.html", leagues=LEAGUES, seasons=SEASONS)

@app.route("/player")
def player_compare():
    return render_template("player.html", leagues=LEAGUES, seasons=SEASONS)

@app.route("/scout")
def scout_matcher():
    return render_template("scout.html", leagues=LEAGUES, seasons=SEASONS)


# ─────────────────────────────────────────────────────────────────────────────
# API — leagues
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
    name       = request.args.get("name", "").strip()
    league     = request.args.get("league", "Premier League")
    season     = request.args.get("season", "2024-25")
    all_leagues = request.args.get("all_leagues", "0") == "1"
    
    if len(name) < 3:
        return jsonify([])
    
    try:
        if all_leagues:
            results = search_players_global(name, season)
        else:
            results = search_players(name, league, season)
            # Fallback to global if local search returns nothing
            if not results:
                results = search_players_global(name, season)
                
        return jsonify(results[:15])
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — similar players
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/similar")
def api_similar():
    player_id    = request.args.get("player_id", type=int)
    season       = request.args.get("season", "2024-25")
    position     = request.args.get("position", "")
    target_group = _pos_group(position)

    try:
        from core.fetcher import _get_df
        from core.scorer import compute_similarity, get_position_config, _detect_position
        from core.normalizer import normalize_stats as _norm
        import pandas as pd

        df = _get_df()

        if "-" not in str(season):
            season = f"{season}-{str(int(season)+1)[2:]}"

        pool_df = df[df["season"] == season]

        # Build target player norm + scaled vector
        target_row = df[df["player_id"] == player_id]
        if target_row.empty:
            return jsonify([])

        def row_to_raw(row):
            def v(col):
                try: return float(row[col]) if not pd.isna(row[col]) else 0
                except: return 0
            return {
                "position": row.get("Pos", "FW"),
                "goals": v("Gls"), "assists": v("Ast"),
                "shots_total": v("Sh"), "shots_on": v("SoT"),
                "xg": v("xG"),
                "passes_key": v("KP"), "pass_accuracy": v("Cmp%"),
                "progressive_passes": v("PrgP"),
                "tackles": v("Tkl"), "interceptions": v("Int"), "blocks": v("Blocks"),
                "clearances": v("Clr"),
                "dribbles_success": v("Succ"),
                "progressive_carries": v("PrgC"),
                "aerial_win_pct": v("AerWon%") if v("AerWon%") > 0 else (
                    round(v("AerWon") / (v("AerWon") + v("AerLost")) * 100, 1)
                    if (v("AerWon") + v("AerLost")) > 0 else 0
                ),
                "fouls_drawn": v("Fld"), "fouls_committed": v("Fls"),
                "minutes": v("Min"),
            }

        t_row = target_row.iloc[0]
        t_raw = row_to_raw(t_row)
        t_norm = _norm(t_raw)
        cfg = get_position_config(t_norm.get("position", "FW"))
        from core.scorer import get_radar_data
        _, _, t_scaled = get_radar_data(t_norm, cfg)

        candidates = []
        for _, row in pool_df.iterrows():
            pid = int(row["player_id"])
            if pid == player_id:
                continue
            if _pos_group(row.get("Pos", "")) != target_group:
                continue
            try:
                mins = float(row.get("Min", 0) or 0)
            except Exception:
                mins = 0
            if mins < 900:
                continue

            c_raw = row_to_raw(row)
            c_norm = _norm(c_raw)
            _, _, c_scaled = get_radar_data(c_norm, cfg)
            sim = compute_similarity(t_scaled, c_scaled)

            candidates.append({
                "id":       pid,
                "name":     row["Player"],
                "age":      row.get("Age", ""),
                "team":     row.get("Squad", ""),
                "league":   row.get("Comp", ""),
                "position": row.get("Pos", ""),
                "sim":      sim,
            })

        # Sort by similarity descending, return top 4
        candidates.sort(key=lambda x: x["sim"], reverse=True)
        top4 = candidates[:4]

        # Only fetch images for the final 4
        for c in top4:
            c["photo"] = get_wikimedia_image(c["name"], team=c.get("team"))
            del c["sim"]

        return jsonify(top4)
    except Exception as e:
        traceback.print_exc()
        return jsonify([])


# ─────────────────────────────────────────────────────────────────────────────
# API — single-player stats
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/player-stats", methods=["POST"])
def api_player_stats():
    try:
        body      = request.get_json(force=True)
        player_id = body["player_id"]
        league    = body.get("league", "Premier League")
        season    = body.get("season", "2024-25")
        color1    = body.get("c1")

        adjusted  = body.get("adjusted", True)

        raw = get_player_stats(player_id, league, season)
        if not raw:
            return jsonify({"error": f"No stats found for player {player_id} in {season}."}), 400
        if "error" in raw:
             return jsonify({"error": f"API Restriction: {raw['error']}"}), 400

        norm  = normalize_stats(raw)
        if adjusted:
            norm = adjust_norm(norm, league)

        cfg   = get_season_metric_set(season, norm.get("position", "attacker"), norm)
        score = compute_composite_score_from_cfg(norm, cfg)

        labels, raw_vals, scaled = get_radar_data(norm, cfg)
        stat_rows = [
            {"label": lbl, "value": round(v, 3), "percentile": round(s * 100)}
            for lbl, v, s in zip(cfg["labels"], raw_vals, scaled)
        ]

        archetype_scores = get_archetype_scores(norm)
        archetype = classify(archetype_scores)
        insights  = generate_insights(norm, league, season, raw.get("position", ""))

        # Chart cache lookup
        cache_key = (str(player_id), league, season, adjusted, color1)
        if cache_key not in _chart_cache:
            charts = {
                "archetype":  generate_archetype_radar(norm, raw["name"], color_override=color1),
                "pizza":      generate_pizza(norm, raw["name"], color_override=color1),
                "efficiency": generate_efficiency_chart(norm, raw["name"]),
            }
            if len(_chart_cache) >= _CACHE_MAX:
                # Evict oldest entry
                _chart_cache.pop(next(iter(_chart_cache)))
            _chart_cache[cache_key] = charts
        else:
            charts = _chart_cache[cache_key]

        return jsonify({
            "player":            _player_summary(raw, score),
            "stat_rows":         stat_rows,
            "season_metric_set": season,
            "archetype_scores":  archetype_scores,
            "archetype":         archetype,
            "insights":          insights,
            "charts":            charts,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# API — compare (N players, 2–4)
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/api/compare", methods=["POST"])
def api_compare():
    try:
        body = request.get_json(force=True)
        c1   = body.get("c1")
        c2   = body.get("c2")
        c3   = body.get("c3")
        c4   = body.get("c4")
        custom_colors = [x for x in [c1, c2, c3, c4] if x] or None

        # Accept new list format OR legacy 2-player format
        if "players" in body:
            specs = body["players"]   # [{id, league, season}, ...]
        else:
            specs = [
                {"id": body["player_a_id"],
                 "league": str(body.get("league_a") or body.get("league", "39")),
                 "season": str(body.get("season_a") or body.get("season", "2023"))},
                {"id": body["player_b_id"],
                 "league": str(body.get("league_b") or body.get("league", "39")),
                 "season": str(body.get("season_b") or body.get("season", "2023"))},
            ]

        if len(specs) < 2:
            return jsonify({"error": "At least 2 players required."}), 400
        if len(specs) > 4:
            return jsonify({"error": "Maximum 4 players allowed."}), 400

        adjusted = body.get("adjusted", True)

        # Fetch & normalize all players
        raws, norms = [], []
        for i, spec in enumerate(specs):
            raw = get_player_stats(int(spec["id"]), str(spec["league"]), str(spec["season"]))
            if not raw:
                return jsonify({
                    "error": f"No stats for player {i+1} "
                             f"(ID {spec['id']}, league {spec['league']}, season {spec['season']})."
                }), 400
            raws.append(raw)
            n = normalize_stats(raw)
            if adjusted:
                n = adjust_norm(n, str(spec["league"]))
            norms.append(n)

        # Determine comparison metric set based on all player seasons + primary position
        seasons = [str(spec["season"]) for spec in specs]
        primary_position = norms[0].get("position", "attacker")
        cfg, mode = get_comparison_metric_set(seasons, primary_position, norms)

        # Compute scores based on the shared available metrics for fair comparison
        scores = [compute_composite_score_from_cfg(n, cfg) for n in norms]

        labels  = cfg["labels"]
        metrics = cfg["metrics"]
        maxvals = cfg["max_vals"]

        # Stat table (N values + winner per row)
        stat_table = []
        for lbl, metric, mx in zip(labels, metrics, maxvals):
            row_vals = []
            for norm in norms:
                val = norm.get(metric, 0) or 0
                pct = min(val / mx, 1.0) * 100 if mx > 0 else 0
                row_vals.append({"value": round(val, 2), "percentile": round(pct)})
            best   = max(rv["value"] for rv in row_vals)
            w_idx  = next(i for i, rv in enumerate(row_vals) if rv["value"] == best)
            stat_table.append({"label": lbl, "values": row_vals, "winner_idx": w_idx})

        # DataMB-style percentile table (each player → list of {label, value, percentile})
        pct_table = []
        for raw, norm in zip(raws, norms):
            _, raw_vals, scaled = get_radar_data(norm, cfg)
            pct_table.append({
                "player_name": raw["name"],
                "team":        raw.get("team", ""),
                "photo":       raw.get("photo", ""),
                "score":       compute_composite_score(norm),
                "stats": [
                    {"label": lbl, "value": round(v, 2), "percentile": round(s * 100)}
                    for lbl, v, s in zip(labels, raw_vals, scaled)
                ],
            })

        winner_idx = scores.index(max(scores))
        names      = [r["name"] for r in raws]

        players_out = []
        for r, s, n, spec in zip(raws, scores, norms, specs):
            p = _player_summary(r, s)
            p["archetype"] = classify(get_archetype_scores(n))
            p["insights"]  = generate_insights(n, str(spec["league"]), str(spec["season"]),
                                               r.get("position", ""), top_n=1)
            players_out.append(p)

        return jsonify({
            "players":       players_out,
            "scores":        scores,
            "winner_idx":    winner_idx,
            "stat_table":    stat_table,
            "pct_table":     pct_table,
            "comparison_mode": mode,
            "charts": {
                "radar":      generate_radar(norms, names, cfg=cfg, custom_colors=custom_colors),
                "bar":        generate_bar(norms, names, cfg=cfg, custom_colors=custom_colors),
                "percentile": generate_percentile(norms, names, cfg=cfg, custom_colors=custom_colors),
                "pizza":      generate_pizza(norms[0], raws[0]["name"], color_override=c1),
                "lollipop":   generate_lollipop(norms, names, cfg=cfg, custom_colors=custom_colors),
            },
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


import os
import json
from config import CACHE_DIR

@app.route("/api/scout", methods=["POST"])
def api_scout():
    try:
        body = request.get_json()
        target_id = int(body["target_id"])
        target_league = body["target_league"]
        target_season = body["target_season"]
        max_age = int(body.get("max_age", 40))
        pool_type = body.get("league_pool", "all")

        target_raw = get_player_stats(target_id, target_league, target_season)
        if not target_raw:
            return jsonify({"error": "Target player stats not found."}), 400

        from core.scorer import compute_similarity, _detect_position, get_scout_position_config
        from core.fetcher import _get_df
        import pandas as pd

        target_norm = normalize_stats(target_raw)
        cfg = get_scout_position_config(target_norm.get("position", "Attacker"))
        _, _, target_scaled = get_radar_data(target_norm, cfg)
        target_pos = _detect_position(target_norm['position'])

        df = _get_df()
        pool_df = df[df['season'] == target_season].copy()

        LEAGUE_MAP = {
            "Premier League": "Premier League",
            "La Liga": "La Liga",
            "Serie A": "Serie A",
            "Bundesliga": "Bundesliga",
            "Ligue 1": "Ligue 1",
        }
        if pool_type in LEAGUE_MAP:
            pool_df = pool_df[pool_df['Comp'].str.contains(LEAGUE_MAP[pool_type], case=False, na=False)]

        def build_candidates(age_cap):
            result = []
            for _, row in pool_df.iterrows():
                if int(row['player_id']) == target_id: continue
                try:
                    age = int(float(row['Age']))
                except (ValueError, TypeError):
                    age = 99
                if age > age_cap: continue
                if _detect_position(row.get('Pos', '')) != target_pos: continue
                try:
                    mins = float(row['Min']) if not pd.isna(row['Min']) else 0
                except (ValueError, TypeError):
                    mins = 0
                if mins < 400: continue

                def val(col, r=row):
                    try:
                        v = r[col]
                        return float(v) if not pd.isna(v) else 0
                    except (ValueError, TypeError, KeyError):
                        return 0

                sh = val('Sh')
                if not sh:
                    sot_pct, sot_v = val('SoT%'), val('SoT')
                    if sot_pct and sot_v: sh = round(sot_v / (sot_pct / 100), 1)
                    elif val('G/Sh') and val('Gls'): sh = round(val('Gls') / val('G/Sh'), 1) if val('G/Sh') > 0 else 0
                sot = val('SoT')
                if not sot:
                    if sh and val('SoT%'): sot = round(sh * val('SoT%') / 100, 1)
                    elif val('G/SoT') and val('Gls'): sot = round(val('Gls') / val('G/SoT'), 1) if val('G/SoT') > 0 else 0
                pass_acc = val('Cmp%')
                if not pass_acc and val('Cmp') and val('Att') and val('Att') > 0:
                    pass_acc = round(val('Cmp') / val('Att') * 100, 1)
                aer_pct = val('AerWon%')
                if not aer_pct:
                    aw, al = val('AerWon'), val('AerLost')
                    if aw + al > 0: aer_pct = round(aw / (aw + al) * 100, 1)
                    elif val('Won%'): aer_pct = val('Won%')
                dri_att = val('DriAtt')
                if not dri_att and val('Succ') and val('Succ%'):
                    dri_att = round(val('Succ') / (val('Succ%') / 100), 1)
                xg = val('xG')
                if not xg and val('xG_90') and val('90s'):
                    xg = round(val('xG_90') * val('90s'), 1)

                raw_cand = {
                    "id": int(row['player_id']), "name": row['Player'],
                    "position": row.get('Pos', 'Unknown'),
                    "goals": val('Gls'), "assists": val('Ast'),
                    "shots_total": sh, "shots_on": sot, "xg": xg,
                    "passes_key": val('KP'), "pass_accuracy": pass_acc,
                    "progressive_passes": val('PrgP'), "tackles": val('Tkl'),
                    "interceptions": val('Int'), "blocks": val('Blocks'),
                    "clearances": val('Clr'), "dribbles_success": val('Succ'),
                    "dribbles_attempted": dri_att, "progressive_carries": val('PrgC'),
                    "aerial_win_pct": aer_pct, "fouls_drawn": val('Fld') or val('Fld_misc'),
                    "fouls_committed": val('Fls'), "sca90": val('SCA90'),
                    "gca90": val('GCA90'), "npxg": val('npxG') or xg,
                    "xa": val('xA') or val('xAG'), "passes_penalty_area": val('PPA'),
                    "att_pen_touches": val('Att Pen'), "tkl_pct": val('Tkl%'),
                    "yellow_cards": val('CrdY'), "red_cards": val('CrdR'),
                    "photo": "", "team": row.get('Squad', ''),
                    "league": row.get('Comp', ''), "minutes": val('Min'),
                    "appearances": val('MP'), "age": val('Age')
                }
                norm_cand = normalize_stats(raw_cand)
                _, _, c_scaled = get_radar_data(norm_cand, cfg)
                sim = compute_similarity(target_scaled, c_scaled)
                result.append({
                    "id": raw_cand["id"], "name": raw_cand["name"],
                    "photo": "", "age": raw_cand["age"],
                    "team": raw_cand["team"], "league": raw_cand["league"],
                    "position": raw_cand["position"],
                    "score": compute_composite_score(norm_cand),
                    "sim_score": sim,
                })
            return result

        widened = False
        candidates = []
        for age_cap in [max_age, max_age + 5, 999]:
            candidates = build_candidates(age_cap)
            if candidates:
                widened = (age_cap != max_age)
                break

        candidates.sort(key=lambda x: x["sim_score"], reverse=True)
        top_matches = candidates[:15]
        # Images fetched client-side asynchronously via /api/player-image
        return jsonify({
            "target": {
                "id": target_norm["id"],
                "name": target_norm["name"],
                "photo": target_norm.get("photo", ""),
                "position": target_norm["position"]
            },
            "matches": top_matches,
            "total_pool": len(candidates),
            "widened": widened
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
