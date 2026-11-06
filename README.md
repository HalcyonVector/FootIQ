# FootIQ: Event-Level Football Analytics

**Live demo: [footiq.onrender.com](https://footiq.onrender.com)** — free-tier hosting, so the first request after a period of inactivity can take ~30-60s to spin back up.

A Flask web app for football analytics across 15 leagues and competitions, built directly from parsed WhoScored/Opta match-event data, not season-aggregate box scores. Search a player and browse 12 metric categories (Passing, Carrying, Shooting, Aerial Duels, Hold-Up Play, Decision Making, Final Third, Half-Spaces, Tempo Control, Defending, Post-Recovery, Goalkeeping), Combination Play (a pairwise pass-network view), Compare (2 to 4 players side by side), Scout (statistical-twin search), and Explore (rank every player-season by a single metric).

Data source: WhoScored/Opta match-event JSON (passes, carries, duels, and their outcomes, with pitch coordinates and qualifiers). Coverage: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Championship, Eredivisie, Primeira Liga, Belgian Pro League, Süper Lig, Scottish Premiership, Champions League, Europa League, World Cup, and European Championship, spanning 2023-24 through 2025-26 (plus World Cup 2022 and Euro 2024 as one-off tournament entries). Europa Conference League was scraped in full but excluded: WhoScored never returned usable match-event data for any of its 447 matches, a coverage gap on their end rather than something fixable by scraping again.

---

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**

---

## Features

**Player page**
- Search across 15 leagues and competitions, percentile-ranked within same-position cohorts
- Season switcher on the profile (every league/season a player appears in) and shareable URLs (the address bar always holds the current player-season) (`/player?player_id=&league=&season=`)
- A "Limited sample" badge when a player has under 450 minutes AND under a third of the minutes their team played in that competition (so a Europa League regular is not flagged, a league fringe player is)
- Open-play xG, xG per shot and xA are real percentile metrics (Shooting and Passing tabs), so Compare, Scout and Explore use them too
- 12 Advanced Metrics tabs (Goalkeeping swaps in for keepers)
- Position-weighted Composite Rating: a single headline number combining every category with a power mean, so a player's strongest categories are rewarded rather than diluted by ones that were never their job
- **Final Third**: Completeness (geometric-mean floor across 4 pillars) and Impact (per-touch value from a player's 2 strongest pillars)
- **Similar players**: the six closest statistical profiles (same engine as Scout), loaded only when you scroll down to them, each linking to that player and to a pre-filled Compare
- **Combination Play**: most-found teammates, plus a pitch chart of exactly what a chosen teammate does after receiving a pass
- **Season Overview**: stat line (apps, goals, assists, xG, xA, average rating, cards...), auto-generated strengths and areas to improve, a per-match form chart, a shot map sized by xG with goal-placement view, touch and defensive-action heatmaps, a pass map (chances created, progressive passes, passes into the box, incomplete passes), and a career table across every season in the dataset. xG comes from a home-grown logistic model fitted on the dataset's own shots (see `core/advanced/xg.py`)

**Compare**
- 2 to 4 players side by side, any league, any season
- Season Overview side by side: stat line (best value highlighted, per-90 rows), shot maps and heatmaps
- Full per-category stat table plus a headline radar chart

**Scout**
- Statistical-twin search across every league and season, or narrowed to the top 5
- Filterable by max age

**League tables and team pages** (`/league`, `/team`)
- Points, goal difference, last-5 form and xG for/against for every team in a competition-season, built from the per-match rows (no extra data)
- Team page: record, goal-difference form chart, sortable squad table (apps, minutes, goals, xG, rating) and every result with xG

**Explore**
- Rank every player-season by a single chosen metric, no reference player required
- Filterable by league, season, position, and minutes played

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.x, Flask, Flask-CORS |
| Data | pandas, pyarrow, `data/advanced/*.parquet` |
| Charts | Client-side SVG (`static/js/charts.js`) drawn from JSON specs built in `visuals/specs.py` |
| Frontend | HTML, CSS, vanilla JS, no build step |
| Images | Wikipedia REST API with a local JSON cache |
| Testing | pytest |

---

## Project Structure

```
FootIQ/
├── app.py                       Flask routes and in-memory chart cache
├── config.py                    Wikipedia-image cache paths and TTL
├── requirements.txt
│
├── core/
│   ├── position.py               Canonical position-group classification
│   ├── media.py                  Wikipedia photo lookup, team colors
│   ├── cache.py                  JSON cache read/write (images)
│   └── advanced/                 The event-metrics engine
│       ├── config.py              Raw-cache path, league/season-key maps
│       ├── raw_loader.py          Parses raw WhoScored match JSON
│       ├── minutes.py             Per-player minutes played (sub-aware, stoppage-time-aware)
│       ├── geometry.py            Pitch geometry: progressive-pass/carry tests, zones, angle bias
│       ├── qualifiers.py          Opta qualifier lookups (assists, crosses, set pieces, and more)
│       ├── carries.py             Derives carries from gaps between a player's own touches
│       ├── possession_chains.py   Forward event tracing (depth and time windowed)
│       ├── linkup.py              Combination Play pairwise pass/reception pipeline
│       ├── aggregator.py          Orchestrates match parsing into a per-player-season rollup
│       ├── chart_events.py        Per-category raw event coordinates behind the charts
│       ├── overview.py            Per-match stat line, shots and heatmap grids (Season Overview)
│       ├── xg.py                  Expected-goals model (numpy logistic regression, coefficients in xg_model.json)
│       ├── tables.py              League tables and team pages from the per-match rows
│       ├── summary.py             Season line, form, career and strengths shaping at request time
│       ├── composite.py           Position-weighted Composite Rating (power mean)
│       ├── scout.py               Cross-league, cross-season similarity search
│       ├── explore.py             Single-metric ranked stat browsing
│       ├── store.py               Lazy-loads the precomputed parquet files
│       ├── identity.py            player_id to parquet row lookup
│       ├── lookup.py              Player search (backs /api/search)
│       ├── percentiles.py         Cohort-based percentile ranking
│       ├── metrics_master.py      Category to metric list, labels, units
│       └── categories/            One module per metric category
│
├── visuals/specs.py             Chart specs (JSON) for every Advanced Metrics tab, Combination Play and Compare
│
├── scraping/
│   ├── scrape_whoscored.py        Resumable WhoScored match-JSON scraper, optional parallel workers
│   ├── build_advanced_metrics.py  Rebuilds data/advanced/*.parquet from the raw cache
│   ├── build_overview_data.py     Builds player_matches/, shots/ (with assisting-pass coordinates), heatmaps/ and xg_model.json
│   ├── data_release.py            Publishes / fetches data/advanced as a GitHub Release asset (data/DATA_VERSION pins it)
│   └── auto_update.py             Weekly scrape, rebuild, publish, commit the pointer
│
├── templates/
│   ├── base.html                  Nav, particles, scroll animations
│   ├── player.html                Search and stats page
│   ├── compare.html                Side-by-side player comparison
│   ├── scout.html                  Statistical-twin search
│   ├── league.html / team.html     League tables and team pages
│   └── explore.html                Ranked stat browsing
│
├── static/
│   ├── css/style.css
│   └── js/                        app.js, overview.js, similar.js, compare.js, league.js, explore.js, custom-select.js
│
├── tests/                        Pytest suite for the core metric math
│
└── data/
    ├── DATA_VERSION               Pointer to the checksummed data zip (a GitHub Release asset)
    ├── advanced/                  Precomputed parquet, the only data app.py reads (not in git; fetched, see Data Refresh)
    └── cache/                     Wikipedia image cache (gitignored)
```

---

## API Endpoints

| Endpoint | Method | Params | Returns |
|---|---|---|---|
| `/api/search` | GET | `name`, `league`, `season` | Matching players |
| `/api/advanced-stats` | POST | `player_id`, `league`, `season` | 12 metric categories, percentile-ranked |
| `/api/player` | GET | `id`, `league`, `season` | One player-season plus every season they appear in |
| `/api/player-overview` | POST | `player_id`, `league`, `season` | Stat line, form, career, shots with xG, heatmaps |
| `/api/pass-map` | POST | `player_id`, `league`, `season` | Passes (progressive / into-box flags) and chances created |
| `/api/league-table` | GET | `league`, `season` | Standings with xG for/against and form |
| `/api/team` | GET | `league`, `season`, `team` | Record, results and squad table for one team |
| `/api/linkup-teammates` | POST | `player_id`, `league`, `season` | Top 10 most-passed-to teammates |
| `/api/linkup-detail` | POST | `passer_id`, `teammate_id`, `league`, `season` | Reception-outcome stats and pitch chart |
| `/api/category-chart` | POST | `player_id`, `league`, `season`, `category` | Per-category chart grid |
| `/api/compare-stats` | POST | `players` (2 to 4 entries) | Full stat table plus headline radar |
| `/api/scout-similar` | POST | `player_id`, `league`, `season`, `max_age`, `league_pool` | Ranked statistical twins |
| `/api/explore` | POST | `metric`, `league`, `season`, `position_group`, `min_minutes` | Ranked player-seasons |

---

## Data Refresh

The raw match-event JSON lives outside the repo (`core/advanced/config.py`'s `WHOSCORED_CACHE_DIR`, override via the `FOOTIQ_WHOSCORED_DIR` env var). To scrape more matches and rebuild:

```bash
python scraping/scrape_whoscored.py            # resumable, safe to re-run or interrupt
python scraping/build_advanced_metrics.py      # parses the raw cache into data/advanced/*.parquet
python scraping/build_overview_data.py         # Season Overview tables + xG model (about 15 minutes); also adds
                                               # the xG/xA columns to player_season_advanced.parquet
```

The parquet is **not in git** (it was in Git LFS, which doesn't fit GitHub's free 1 GB storage + bandwidth once every deploy re-downloads it). `data/DATA_VERSION` pins a checksummed zip stored as a GitHub Release asset (release tag `data`):

```bash
python scraping/data_release.py fetch     # fresh clone / new machine: download, verify, install data/advanced
python scraping/data_release.py publish   # after a rebuild: upload the zip, rewrite data/DATA_VERSION (needs `gh` logged in)
```

Render's build step runs `fetch`; `scraping/auto_update.py` runs `publish` and commits only `data/DATA_VERSION`. Assets are immutable and named by content hash, the last two are kept (so rolling back a deploy still finds its data), and an unchanged dataset uploads nothing.

Add `--workers N` to `scrape_whoscored.py` to run multiple leagues and seasons concurrently, each in its own Chrome instance. Defaults to 1 (sequential).

`data/advanced/player_season_advanced.parquet` and `linkup_summary.parquet` are loaded fully into memory (small, no per-event data). `linkup_receptions/` and `chart_events/<category>/` are Hive-partitioned by league/season — each request reads only its own player/league/season slice off disk, not the whole dataset, so per-tab chart rendering stays within a modest memory footprint. `player_matches/`, `shots/` and `heatmaps/` (Season Overview) follow the same partitioned, per-request-slice pattern. The raw event cache never touches the running app.

---

## Testing

```bash
pip install pytest
python -m pytest tests/
```

Covers the core metric math: progressive-action geometry, position-group classification, and the Composite Rating's power-mean aggregation.

---

## Troubleshooting

**`ModuleNotFoundError`**: run `pip install -r requirements.txt`

**Port 5000 in use**: change the port in `app.py`
```python
app.run(port=5001, use_reloader=False)
```

**A player has no Advanced Metrics or Combination Play data**: they may not have enough minutes or events in that league-season, or the season is not covered yet.

---

## Author

**Sagnik**

GitHub: [@HalcyonVector](https://github.com/HalcyonVector)
