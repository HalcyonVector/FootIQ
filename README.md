# FootIQ — Football Player Analytics

A Flask web app for Big 5 European football analytics. Search players, view per-90 stats, generate charts, compare players side-by-side, and find similar players via the scout matcher.

Data sources: **FBref** (standard + advanced stats) and **Understat** (xG, xA, xG chain/buildup). Seasons covered: 2017-18 through 2024-25.

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
- Per-90 stats table with league/season filters
- Three server-rendered charts:
  - **Pizza chart** — percentile breakdown across position-relevant metrics
  - **Archetype radar** — tactical profile (e.g. Ball-Winner, Deep Playmaker, Box Striker)
  - **Efficiency chart** — actual vs expected goal contribution (Goals vs xG, Assists vs xA, npG vs npxG) with xG Chain/Buildup panel where Understat data is available
- Wikipedia player photo (cached locally in `data/cache/`)

**Compare**
- Side-by-side stats for 2–4 players
- Metrics restricted to the intersection of what each player has data for (fair comparison)

**Scout Matcher**
- Input a target player → returns the 15 most similar players
- Filters: same position group, same season, 400+ minutes played
- Ranked by Euclidean distance on normalized metric vectors

---

## Tech Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.x, Flask, Flask-CORS |
| Data | pandas, `football_master_with_xg.csv` |
| Charts | Matplotlib (server-side → base64 PNG) |
| Frontend | HTML/CSS/Vanilla JS (no build step) |
| Images | Wikipedia REST API + local JSON cache |

---

## Project Structure

```
FootIQ/
├── app.py                      # Flask routes & in-memory chart cache
├── config.py                   # Paths, cache TTL, constants
├── requirements.txt
├── football_master_with_xg.csv # FBref + Understat merged dataset
│
├── core/
│   ├── scorer.py               # Composite scoring, position configs, archetype scores
│   ├── normalizer.py           # Per-90 normalization
│   ├── adjuster.py             # League-strength adjustments
│   ├── archetype.py            # Archetype label classification
│   ├── insights.py             # Auto-generated stat insights
│   ├── fetcher.py              # Wikipedia image fetch
│   └── cache.py                # JSON cache read/write (images)
│
├── visuals/
│   ├── solo.py                 # Pizza, archetype radar, efficiency charts
│   ├── pizza.py
│   ├── radar.py
│   ├── bar.py
│   ├── lollipop.py
│   └── percentile.py
│
├── templates/
│   ├── base.html               # Nav, particles, scroll animations
│   ├── hub.html                # Home / search
│   ├── player.html             # Player detail + charts
│   └── scout.html              # Scout matcher UI
│
├── static/
│   ├── css/style.css
│   └── js/app.js
│
├── data/
│   └── cache/                  # Wikipedia image cache (gitignored)
│
├── fetch_understat.py          # One-time: scrape Understat xG data
└── merge_understat.py          # One-time: merge Understat into FBref CSV
```

---

## API Endpoints

| Endpoint | Method | Params | Returns |
|---|---|---|---|
| `/api/player-stats` | GET | `name`, `league`, `season`, `adjusted` | Stats + 3 chart PNGs (base64) |
| `/api/compare` | GET | `players[]`, `league`, `season` | Side-by-side stats |
| `/api/scout` | GET | `player`, `league`, `season`, `max_age` | Top 15 similar players |

---

## Data Refresh

The dataset is pre-built. To rebuild from scratch:

```bash
# 1. Fetch Understat xG data
python fetch_understat.py

# 2. Merge into master CSV
python merge_understat.py
```

`football_master_with_xg.csv` is the merged output — the only file `app.py` reads.

---

## Troubleshooting

**`ModuleNotFoundError`** — run `pip install -r requirements.txt`

**Port 5000 in use** — change the port in `app.py`:
```python
app.run(port=5001, use_reloader=False)
```

**Charts slow on first load** — expected; Matplotlib renders 3 charts server-side. Subsequent loads for the same player/season/league are served from the in-memory cache instantly.

---

## Author

**Naveen** · [GitHub](https://github.com/HalcyonVector)
