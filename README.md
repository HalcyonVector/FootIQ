# FootIQ — Event-Level Football Analytics

A Flask web app for Big 5 European football analytics, built directly from parsed WhoScored/Opta match-event data — not season-aggregate box scores. Search a player and browse 11 metric categories (Passing, Carrying, Shooting, Aerial Duels, Hold-Up Play, Decision Making, Final Third, Half-Spaces, Tempo Control, Defending, Post-Recovery, Goalkeeping) plus Combination Play, a pairwise pass-network view with a pitch-diagram chart.

Data source: **WhoScored/Opta** match-event JSON (passes, carries, duels, and their outcomes, with pitch coordinates and qualifiers). Coverage: **top 5 European leagues, 2023-24 through 2025-26** (~5,250 matches parsed).

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
- Search across the top 5 leagues, percentile-ranked within same-position cohorts
- 11 Advanced Metrics tabs (12th — Goalkeeping — swaps in for keepers)
- **Final Third**: Completeness (geometric-mean floor across 4 pillars, penalized by spread) and Impact (per-touch value from a player's 2 strongest pillars)
- **Combination Play**: most-found teammates, plus a pitch chart of exactly what a chosen teammate does after receiving a pass — progressive pass, carry, take-on, shot, or lost possession

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.x, Flask, Flask-CORS |
| Data | pandas, pyarrow — `data/advanced/*.parquet` |
| Charts | Matplotlib + mplsoccer (server-side → base64 PNG) |
| Frontend | HTML/CSS/Vanilla JS (no build step) |
| Images | Wikipedia REST API + local JSON cache |

---

## Project Structure

```
FootIQ/
├── app.py                       # Flask routes & in-memory chart cache
├── config.py                    # Wikipedia-image cache paths/TTL
├── requirements.txt
│
├── core/
│   ├── position.py               # Canonical position-group classification
│   ├── media.py                  # Wikipedia photo lookup, team colors
│   ├── cache.py                  # JSON cache read/write (images)
│   └── advanced/                 # The whole event-metrics engine
│       ├── config.py              # Raw-cache path, league/season-key maps
│       ├── raw_loader.py          # Parses raw WhoScored match JSON
│       ├── minutes.py             # Per-player minutes played (sub-aware, stoppage-time-aware)
│       ├── geometry.py            # Pitch geometry — progressive-pass/carry tests, zones, angle bias
│       ├── qualifiers.py          # Opta qualifier lookups (assists, crosses, set-piece detection, ...)
│       ├── carries.py             # Derives carries from gaps between a player's own touches
│       ├── possession_chains.py   # Forward event-tracing (depth- and time-windowed)
│       ├── linkup.py              # Combination Play pairwise pass/reception pipeline
│       ├── aggregator.py          # Orchestrates match parsing -> per-player-season rollup
│       ├── store.py               # Lazy-loads the precomputed parquet files
│       ├── identity.py            # player_id -> parquet row lookup
│       ├── lookup.py              # Player search (backs /api/search)
│       ├── percentiles.py         # Cohort-based percentile ranking + Final Third composites
│       ├── metrics_master.py      # Category -> metric list, labels, units
│       └── categories/            # One module per metric category
│
├── visuals/
│   └── linkup.py                 # Combination Play pitch-diagram chart (mplsoccer)
│
├── scraping/
│   ├── scrape_whoscored.py        # Resumable WhoScored match-JSON scraper
│   └── build_advanced_metrics.py  # Rebuilds data/advanced/*.parquet from the raw cache
│
├── templates/
│   ├── base.html                  # Nav, particles, scroll animations
│   └── player.html                # Search + stats page (the whole app)
│
├── static/
│   ├── css/style.css
│   └── js/app.js
│
└── data/
    ├── advanced/                  # Precomputed parquet — the only data app.py reads
    └── cache/                     # Wikipedia image cache (gitignored)
```

---

## API Endpoints

| Endpoint | Method | Params | Returns |
|---|---|---|---|
| `/api/search` | GET | `name`, `league`, `season` | Matching players |
| `/api/advanced-stats` | POST | `player_id`, `league`, `season` | 11-12 metric categories, percentile-ranked |
| `/api/linkup-teammates` | POST | `player_id`, `league`, `season` | Top 10 most-passed-to teammates |
| `/api/linkup-detail` | POST | `passer_id`, `teammate_id`, `league`, `season` | Reception-outcome stats + pitch chart |

---

## Data Refresh

The raw match-event JSON lives outside the repo (`core/advanced/config.py::WHOSCORED_CACHE_DIR`, override via `FOOTIQ_WHOSCORED_DIR` env var). To scrape more matches and rebuild:

```bash
python scraping/scrape_whoscored.py            # resumable — safe to re-run/interrupt
python scraping/build_advanced_metrics.py      # parses the raw cache -> data/advanced/*.parquet
```

`data/advanced/player_season_advanced.parquet` and `linkup_pairs.parquet` are the only files `app.py` reads at request time — the 6GB+ raw event cache never touches the running app.

---

## Troubleshooting

**`ModuleNotFoundError`** — run `pip install -r requirements.txt`

**Port 5000 in use** — change the port in `app.py`:
```python
app.run(port=5001, use_reloader=False)
```

**A player has no Advanced Metrics / Combination Play data** — they may not have enough minutes/events in that league-season, or the season isn't covered (top 5 leagues, 2023-24 to 2025-26 only).

---

## Author

**Sagnik**

GitHub: [@HalcyonVector](https://github.com/HalcyonVector)
