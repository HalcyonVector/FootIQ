import pandas as pd
import requests
import hashlib
import os
import re
import unicodedata
from typing import List, Dict, Optional
from core import cache

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "football_master_with_xg.csv")

# Global dataframe to keep data in memory
_DF: Optional[pd.DataFrame] = None

def _get_df() -> pd.DataFrame:
    global _DF
    if _DF is None:
        print(f"[csv] Loading {CSV_PATH}...")
        _DF = pd.read_csv(CSV_PATH)
        # Ensure season is string for comparison
        _DF['season'] = _DF['season'].astype(str)
        # Create a stable ID if none exists (hash of Player + Squad + season)
        _DF['player_id'] = _DF.apply(lambda x: int(hashlib.md5(f"{x['Player']}{x['Squad']}{x['season']}".encode()).hexdigest()[:8], 16), axis=1)
    return _DF

def get_wikimedia_image(name: str, team: str = None) -> str:
    """Fetch player image via Wikipedia REST API with caching."""
    # Use v4 and include team in key to bypass any old incorrect cached images
    cache_key = f"wiki_img_v4_{name.replace(' ', '_')}_{str(team).replace(' ', '_')}"
    cached = cache.get(cache_key)
    if cached and cached.startswith("http"):
        # Reject known bad image patterns (flags, landscapes, logos)
        bad_patterns = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                        "emblem", "Emblem", "logo", "Logo", "shield", "Shield"]
        if not any(p in cached for p in bad_patterns):
            return cached
    # Don't use cached empty strings or bad images — retry

    HEADERS = {"User-Agent": "FootIQ/1.0 (football analytics; https://github.com/footiq)"}

    def _is_footballer(d: dict) -> bool:
        """Check if the summary data looks like a footballer/club."""
        extract = (d.get("extract") or "").lower()
        desc = (d.get("description") or "").lower()
        keywords = ["footballer", "soccer", "midfielder", "forward", "striker", "winger", 
                    "defender", "goalkeeper", "player", "club", "stats", "league", "born", "playing"]
        
        match = any(k in extract for k in keywords) or any(k in desc for k in keywords)
        
        # If team is provided, it's a very strong indicator if it's in the text
        if team:
            t_low = team.lower()
            # Handle common variations like "Nott'ham Forest" vs "Nottingham Forest"
            t_alt = t_low.replace("nott'ham", "nottingham").replace("utd", "united")
            if t_low in extract or t_alt in extract or t_low in desc or t_alt in desc:
                return True
        return match

    def _rest(title: str, force_verify: bool = False) -> str | None:
        try:
            slug = title.strip().replace(" ", "_")
            from urllib.parse import quote
            encoded_slug = quote(slug, safe="")
            
            # 1. Try Standard Summary API
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_slug}",
                headers=HEADERS, timeout=5
            )
            d = {}
            if r.status_code == 200:
                d = r.json()
                # Skip disambiguation pages
                if d.get("type") == "disambiguation":
                    return None
                
                # If we are searching by just the name, we MUST verify it's a footballer
                if force_verify and not _is_footballer(d):
                    return None

                img = (d.get("originalimage") or d.get("thumbnail") or {}).get("source")
                if img:
                    # Reject non-person images: flags, landscapes, city photos, logos
                    bad = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                           "emblem", "Logo", "logo", "shield", "Shield",
                           "city", "City", "town", "Town", "stadium", "Stadium",
                           "landscape", "Panorama"]
                    if not any(b in img for b in bad):
                        return img
            
            # 2. Deep Dive: Parse Infobox if summary is empty (common for non-superstars like Elliot Anderson)
            pr = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=parse&page={encoded_slug}&prop=wikitext&section=0&format=json",
                headers=HEADERS, timeout=5
            )
            if pr.status_code == 200:
                wt = pr.json().get("parse", {}).get("wikitext", {}).get("*", "")
                # Look for | image = filename.jpg (common in Infoboxes)
                infobox_img = re.search(r"\|\s*image\s*=\s*([^|\n\r]+)", wt)
                if infobox_img:
                    file_name = infobox_img.group(1).strip()
                    if file_name:
                        # Resolve filename to a direct URL using Action API
                        ir = requests.get(
                            f"https://en.wikipedia.org/w/api.php?action=query&titles=File:{quote(file_name)}&prop=imageinfo&iiprop=url&format=json",
                            headers=HEADERS, timeout=5
                        )
                        pages = ir.json().get("query", {}).get("pages", {})
                        for pid in pages:
                            ii_list = pages[pid].get("imageinfo", [])
                            if ii_list:
                                final_url = ii_list[0].get("url")
                                if final_url: return final_url
        except:
            pass
        return None

    def _search_wiki(query: str) -> str | None:
        """Use Wikipedia's opensearch to find the right article title, then fetch image."""
        try:
            from urllib.parse import quote
            r = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}&srlimit=5&format=json",
                headers=HEADERS, timeout=5
            )
            if r.status_code == 200:
                results = r.json().get("query", {}).get("search", [])
                for result in results:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "").lower()
                    # Must look like a footballer article AND title must contain part of the name
                    name_parts = clean_name.lower().split()
                    title_lower = title.lower()
                    name_match = any(part in title_lower for part in name_parts if len(part) > 3)
                    
                    is_foot = any(k in snippet for k in ["footballer", "football player", "midfielder", "forward", "defender", "striker", "winger", "born"])
                    if team and team.lower() in snippet: is_foot = True

                    if name_match and is_foot:
                        img = _rest(title)
                        if img:
                            return img
        except:
            pass
        return None

    def _ascii_fallback(n: str) -> str:
        """Strip accents for a plain ASCII version of the name."""
        return unicodedata.normalize("NFD", n).encode("ascii", "ignore").decode("ascii")

    # Strip nationality prefixes like "eg EGY" from CSV names
    clean_name = name.strip()
    parts = clean_name.split()
    if len(parts) > 2 and len(parts[0]) <= 3 and parts[0].isalpha() and parts[0].islower():
        clean_name = " ".join(parts[1:])

    ascii_name = _ascii_fallback(clean_name)

    # Try multiple variations, prioritizing SPECIFIC footballer articles and using team context
    img = ( (team and _rest(f"{clean_name} ({team})")) or
           _rest(f"{clean_name} (footballer)") or
           _rest(f"{clean_name} (soccer)") or
           _rest(clean_name, force_verify=True) or
           # Wikipedia search fallback — finds correct article even for less-known players
           (team and _search_wiki(f"{clean_name} {team} footballer")) or
           _search_wiki(f"{clean_name} footballer") or
           (None if ascii_name == clean_name else _rest(f"{ascii_name} (footballer)")) or
           _search_wiki(f"{ascii_name} footballer"))

    if img:
        # Don't cache flag/logo/landscape images
        bad_patterns = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                        "emblem", "Emblem", "logo", "Logo", "shield", "Shield"]
        if not any(p in img for p in bad_patterns):
            cache.put(cache_key, img)
            return img

    return ""

# --- Team Color Mapping ---

TEAM_COLORS = {
    # Premier League
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Manchester City": "#6CABDD",
    "Manchester Utd": "#DA291C", "Liverpool": "#C8102E", "Chelsea": "#034694",
    "Tottenham": "#132257", "Newcastle Utd": "#241F20",
    # La Liga
    "Real Madrid": "#FEBE10", "Barcelona": "#004D98", "Atlético Madrid": "#CB3524",
    "Real Sociedad": "#0067B1", "Villareal": "#FFE100",
    # Bundesliga
    "Bayern Munich": "#DC052D", "Dortmund": "#FDE100", "Leverkusen": "#E32221",
    "RB Leipzig": "#DD013F",
    # Serie A
    "Inter": "#010E80", "Milan": "#FB090B", "Juventus": "#000000",
    "Napoli": "#12A0D7", "Roma": "#F0BC42", "Lazio": "#87D8F7",
    # Ligue 1
    "Paris S-G": "#004170", "Marseille": "#2FAEE0", "Monaco": "#E9212E",
    "Lille": "#E01E13", "Lyon": "#ED1C24"
}

def get_team_color(team_name: str) -> str:
    """Return the primary hex color for a team or a default blue."""
    return TEAM_COLORS.get(team_name, "#3b82f6")

def _normalize_str(s: str) -> str:
    """Strip all diacritics/accents and lowercase. Ødegaard→odegaard, Šeško→sesko."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()

def search_players(name: str, league: str, season: str) -> List[Dict]:
    """Search for players in a specific league and season using the CSV."""
    df = _get_df()
    if "-" not in str(season):
        season = f"{season}-{str(int(season)+1)[2:]}"

    norm_name = _normalize_str(name)
    mask = (
        df['Player'].apply(lambda p: norm_name in _normalize_str(str(p))) &
        df['Comp'].str.contains(league, case=False, na=False) &
        (df['season'] == season)
    )
    results = df[mask].head(15)
    return _format_results(results)

def search_players_global(name: str, season: str) -> List[Dict]:
    """Search for players across all leagues in the CSV for a specific season."""
    df = _get_df()
    if "-" not in str(season):
        season = f"{season}-{str(int(season)+1)[2:]}"

    norm_name = _normalize_str(name)
    mask = (
        df['Player'].apply(lambda p: norm_name in _normalize_str(str(p))) &
        (df['season'] == season)
    )
    results = df[mask].head(15)
    return _format_results(results)

def search_players_by_league(league: str, season: str, page: int = 1) -> List[Dict]:
    """Fetch players by league (used for pool generation)."""
    df = _get_df()
    if "-" not in str(season):
        season = f"{season}-{str(int(season)+1)[2:]}"
        
    mask = (
        df['Comp'].str.contains(league, case=False, na=False) &
        (df['season'] == season)
    )
    # Simple pagination
    start = (page - 1) * 20
    results = df[mask].iloc[start:start+20]
    return _format_results(results)

def get_player_stats(player_id: int, league: str, season: str) -> Optional[Dict]:
    """Fetch full stats for a single player from CSV by their generated ID."""
    df = _get_df()
    # Normalize season
    if "-" not in str(season):
        season = f"{season}-{str(int(season)+1)[2:]}"

    player_row = df[df['player_id'] == int(player_id)]

    # Filter by season if possible to avoid grabbing wrong year
    season_row = player_row[player_row['season'] == season]
    if not season_row.empty:
        player_row = season_row

    if player_row.empty:
        return None

    row = player_row.iloc[0]
    
    # Mapping CSV columns to the app's 'raw' format
    # Note: Using .get() style or direct check because some columns might be NaN
    def val(col):
        try: return float(row[col]) if not pd.isna(row[col]) else 0
        except: return 0

    name = row['Player']
    squad = row.get('Squad')
    photo = get_wikimedia_image(name, team=squad)

    # Helper to safely derive a value
    def derive(primary, *fallbacks):
        """Return first non-zero value from primary or fallbacks."""
        v = val(primary)
        if v and v > 0:
            return v
        for fb in fallbacks:
            v = fb() if callable(fb) else val(fb)
            if v and v > 0:
                return v
        return 0

    # Derive shots total: Sh = SoT / (SoT%/100), or Gls / G/Sh
    shots_total = val('Sh')
    if not shots_total:
        sot_pct = val('SoT%')
        sot = val('SoT')
        if sot_pct and sot:
            shots_total = round(sot / (sot_pct / 100), 1)
        elif val('G/Sh') and val('Gls'):
            shots_total = round(val('Gls') / val('G/Sh'), 1) if val('G/Sh') > 0 else 0

    # Derive SoT: SoT = Sh * SoT%/100, or Gls / G/SoT
    shots_on = val('SoT')
    if not shots_on:
        sh = shots_total or val('Sh')
        sot_pct = val('SoT%')
        if sh and sot_pct:
            shots_on = round(sh * sot_pct / 100, 1)
        elif val('G/SoT') and val('Gls'):
            shots_on = round(val('Gls') / val('G/SoT'), 1) if val('G/SoT') > 0 else 0

    # Derive dribbles attempted: DriAtt = Succ / (Succ%/100)
    dri_att = val('DriAtt')
    if not dri_att:
        succ = val('Succ')
        succ_pct = val('Succ%')
        if succ and succ_pct:
            dri_att = round(succ / (succ_pct / 100), 1)

    # Aerial win %: AerWon% direct, else compute from AerWon/AerLost, else use Won% (aerial duels)
    aer_won_pct = val('AerWon%')
    if not aer_won_pct:
        aer_won = val('AerWon')
        aer_lost = val('AerLost')
        if aer_won + aer_lost > 0:
            aer_won_pct = round(aer_won / (aer_won + aer_lost) * 100, 1)
        elif val('Won%'):
            aer_won_pct = val('Won%')  # Won% in misc stats = aerial duel win %

    # xG: use direct or per-90 * 90s
    xg = val('xG')
    if not xg and val('xG_90') and val('90s'):
        xg = round(val('xG_90') * val('90s'), 1)

    # xAG: use direct or per-90 * 90s
    xag = val('xAG')
    if not xag and val('xAG_90') and val('90s'):
        xag = round(val('xAG_90') * val('90s'), 1)

    # KP: no direct derivation available for 2023-24, stays 0
    # Cmp%: no derivation for 2023-24, stays 0 — but check Cmp/Att
    pass_acc = val('Cmp%')
    if not pass_acc:
        cmp = val('Cmp')
        att = val('Att')
        if cmp and att and att > 0:
            pass_acc = round(cmp / att * 100, 1)

    return {
        "id":          int(row['player_id']),
        "name":        name,
        "photo":       photo,
        "age":         val('Age'),
        "nationality": row.get('Nation', 'Unknown'),
        "team":        row.get('Squad', 'Unknown'),
        "team_logo":   "https://media.api-sports.io/football/teams/placeholder.png",
        "league":      row.get('Comp', 'Unknown'),
        "league_logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Ligue_1_logo.svg/512px-Ligue_1_logo.svg.png",
        "position":    row.get('Pos', 'Unknown'),
        "appearances": val('MP'),
        "minutes":     val('Min'),
        # attacking
        "goals":              val('Gls'),
        "assists":            val('Ast'),
        "shots_total":        shots_total,
        "shots_on":           shots_on,
        "xg":                 xg,
        # passing
        "passes_total":       val('Att'),
        "passes_key":         val('KP'),
        "pass_accuracy":      pass_acc,
        "progressive_passes": val('PrgP'),
        # defensive
        "tackles":            val('Tkl'),
        "interceptions":      val('Int'),
        "blocks":             val('Blocks'),
        "clearances":         val('Clr'),
        # dribbles / carries
        "dribbles_success":   val('Succ'),
        "dribbles_attempted": dri_att,
        "progressive_carries":val('PrgC'),
        # aerial
        "aerial_win_pct":     aer_won_pct,
        # discipline
        "fouls_drawn":        val('Fld') or val('Fld_misc'),
        "fouls_committed":    val('Fls'),
        "yellow_cards":       val('CrdY'),
        "red_cards":          val('CrdR'),
        "team_color":         get_team_color(row.get('Squad', '')),
        # Understat xG chain metrics
        "xg_chain":           val('xGChain'),
        "xg_buildup":         val('xGBuildup'),
        "npxg":               val('npxG'),
        "xa":                 xag,
    }

def _format_results(results_df: pd.DataFrame) -> List[Dict]:
    """Convert dataframe rows to the list of dicts the frontend expects."""
    players = []
    for _, row in results_df.iterrows():
        players.append({
            "id":          int(row['player_id']),
            "name":        row['Player'],
            "photo":       "", # Empty initially to save bandwidth in search results
            "age":         row.get('Age', ''),
            "nationality": row.get('Nation', ''),
            "team":        row.get('Squad', 'Unknown'),
            "league":      row.get('Comp', ''),
            "position":    row.get('Pos', 'Unknown'),
            "appearances": row.get('MP', 0),
            "minutes":     row.get('Min', 0),
        })
    return players
