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
- 12 Advanced Metrics tabs (Goalkeeping swaps in for keepers)
- Position-weighted Composite Rating: a single headline number combining every category with a power mean, so a player's strongest categories are rewarded rather than diluted by ones that were never their job
- **Final Third**: Completeness (geometric-mean floor across 4 pillars) and Impact (per-touch value from a player's 2 strongest pillars)
- **Combination Play**: most-found teammates, plus a pitch chart of exactly what a chosen teammate does after receiving a pass

**Compare**
- 2 to 4 players side by side, any league, any season
- Full per-category stat table plus a headline radar chart

**Scout**
- Statistical-twin search across every league and season, or narrowed to the top 5
- Filterable by max age

**Explore**
- Rank every player-season by a single chosen metric, no reference player required
- Filterable by league, season, position, and minutes played

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.x, Flask, Flask-CORS |
| Data | pandas, pyarrow, `data/advanced/*.parquet` |
| Charts | Matplotlib + mplsoccer (server-side, rendered to base64 PNG) |
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
├── visuals/                     One chart module per category, plus linkup and compare
│
├── scraping/
│   ├── scrape_whoscored.py        Resumable WhoScored match-JSON scraper, optional parallel workers
│   └── build_advanced_metrics.py  Rebuilds data/advanced/*.parquet from the raw cache
│
├── templates/
│   ├── base.html                  Nav, particles, scroll animations
│   ├── player.html                Search and stats page
│   ├── compare.html                Side-by-side player comparison
│   ├── scout.html                  Statistical-twin search
│   └── explore.html                Ranked stat browsing
│
├── static/
│   ├── css/style.css
│   └── js/                        app.js, compare.js, explore.js, custom-select.js
│
├── tests/                        Pytest suite for the core metric math
│
└── data/
    ├── advanced/                  Precomputed parquet, the only data app.py reads
    └── cache/                     Wikipedia image cache (gitignored)
```

---

## API Endpoints

| Endpoint | Method | Params | Returns |
|---|---|---|---|
| `/api/search` | GET | `name`, `league`, `season` | Matching players |
| `/api/advanced-stats` | POST | `player_id`, `league`, `season` | 12 metric categories, percentile-ranked |
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
```

Add `--workers N` to `scrape_whoscored.py` to run multiple leagues and seasons concurrently, each in its own Chrome instance. Defaults to 1 (sequential).

`data/advanced/player_season_advanced.parquet` and `linkup_summary.parquet` are loaded fully into memory (small, no per-event data). `linkup_receptions/` and `chart_events/<category>/` are Hive-partitioned by league/season — each request reads only its own player/league/season slice off disk, not the whole dataset, so per-tab chart rendering stays within a modest memory footprint. The raw event cache never touches the running app.

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
