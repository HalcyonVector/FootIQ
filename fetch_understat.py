"""
Fetch xG/xA/npxG player data from Understat for Big 5 leagues, 2014-2025.
Endpoint: https://understat.com/main/getLeagueData/{league}/{season}

Run: python fetch_understat.py
Output: understat_players.csv
"""
import json, time, csv
from curl_cffi import requests as curl_requests

SESSION = curl_requests.Session(impersonate="chrome120")
HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Understat league keys → our league names
LEAGUES = {
    "EPL":        "ENG-Premier League",
    "La_liga":    "ESP-La Liga",
    "Bundesliga": "GER-Bundesliga",
    "Serie_A":    "ITA-Serie A",
    "Ligue_1":    "FRA-Ligue 1",
}

# Seasons: 2014 = 2014/15, ..., 2024 = 2024/25
SEASONS = list(range(2014, 2025))

all_rows = []
errors = []

for league_key, league_name in LEAGUES.items():
    for season in SEASONS:
        url = f"https://understat.com/main/getLeagueData/{league_key}/{season}"
        ref = f"https://understat.com/league/{league_key}/{season}"
        try:
            r = SESSION.get(url, headers={**HEADERS, "Referer": ref}, timeout=25)
        except Exception as e:
            print(f"  ERROR {league_key} {season}: {e}")
            errors.append((league_key, season, str(e)))
            time.sleep(3)
            continue

        if r.status_code != 200 or not r.text.strip():
            print(f"  SKIP {league_key} {season}: HTTP {r.status_code} empty={not r.text.strip()}")
            errors.append((league_key, season, f"HTTP {r.status_code}"))
            time.sleep(2)
            continue

        try:
            data = r.json()
        except Exception as e:
            print(f"  PARSE ERROR {league_key} {season}: {e}  snippet: {r.text[:100]}")
            errors.append((league_key, season, f"parse: {e}"))
            time.sleep(2)
            continue

        players = data.get("players", [])
        if not players:
            print(f"  EMPTY {league_key} {season}: no players key. Top keys: {list(data.keys())[:5]}")
            errors.append((league_key, season, "no players"))
            time.sleep(1)
            continue

        # Flatten player records
        season_str = f"{season}-{str(season+1)[2:]}"  # "2023-24"
        for p in players:
            row = {
                "player_name":  p.get("player_name", ""),
                "team":         p.get("team_title", ""),
                "season":       season_str,
                "league":       league_name,
                "games":        p.get("games", ""),
                "minutes":      p.get("time", ""),
                "goals":        p.get("goals", ""),
                "npg":          p.get("npg", ""),
                "assists":      p.get("assists", ""),
                "xG":           p.get("xG", ""),
                "npxG":         p.get("npxG", ""),
                "xA":           p.get("xA", ""),
                "xGChain":      p.get("xGChain", ""),
                "xGBuildup":    p.get("xGBuildup", ""),
                "yellow_cards": p.get("yellow_cards", ""),
                "red_cards":    p.get("red_cards", ""),
                "key_passes":   p.get("key_passes", ""),
                "understat_id": p.get("id", ""),
                "position":     p.get("position", ""),
            }
            all_rows.append(row)

        print(f"  ✓ {league_name} {season_str}: {len(players)} players")
        time.sleep(0.8)  # polite delay

# Save
if all_rows:
    fieldnames = list(all_rows[0].keys())
    with open("understat_players.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\n✓ Saved {len(all_rows)} rows to understat_players.csv")
else:
    print("\n✗ No data collected")

if errors:
    print(f"\nErrors ({len(errors)}):")
    for e in errors:
        print(f"  {e}")

# Quick sanity check
if all_rows:
    import pandas as pd
    df = pd.read_csv("understat_players.csv")
    print(f"\nShape: {df.shape}")
    print(f"Leagues: {sorted(df['league'].unique())}")
    print(f"Seasons: {sorted(df['season'].unique())}")
    # Sample top xG scorers 2023-24 EPL
    epl = df[(df['league']=='ENG-Premier League') & (df['season']=='2023-24')]
    if len(epl):
        top = epl.nlargest(5, 'xG')[['player_name','team','xG','npxG','xA','xGChain']]
        print(f"\nTop 5 xG EPL 2023-24:\n{top.to_string(index=False)}")
