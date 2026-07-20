"""
Player photo + team color lookups. Extracted from the old CSV-backed
core/fetcher.py — these were never actually CSV-specific (just name/team
based), so they carry over unchanged to the new WhoScored-backed search.
"""

import re
import time
import unicodedata
from urllib.parse import quote

import requests

from core import cache

# Overall wall-clock budget for one photo lookup. A cache MISS (first time
# any given player is looked up) previously had no ceiling at all — up to
# ~8 fallback title variants, some issuing up to 3 sequential Wikipedia API
# calls each at a 5s timeout, meaning a player whose page didn't match any
# variant could hang for a minute or more. That's the exact "search bar
# stuck for ages on an uncached player" symptom: the request doesn't block
# the UI thread, but it does tie up one of the browser's ~6 concurrent
# connections to this app for that whole time, so anything else (including
# the next /api/search) can end up queued behind it.
_LOOKUP_BUDGET_S = 4.0
_REQUEST_TIMEOUT_S = 2.0


# Letters with no NFD decomposition (they're distinct base characters, not a
# base letter + combining accent) — NFD+ascii-ignore alone silently DROPS
# these instead of transliterating them, breaking search for e.g. "Odegaard"
# (Ø doesn't decompose to "O" + a combining mark, so it just disappears,
# leaving "degaard").
_MANUAL_TRANSLATE = str.maketrans({
    "Ø": "O", "ø": "o", "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe",
    "Đ": "D", "đ": "d", "Ł": "L", "ł": "l", "Þ": "TH", "þ": "th",
    "ß": "ss", "Ð": "D", "ð": "d",
})


def _normalize_str(s: str) -> str:
    """Strip all diacritics/accents and lowercase. Ødegaard->odegaard, Šeško->sesko."""
    s = (s or "").translate(_MANUAL_TRANSLATE)
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


def get_wikimedia_image(name: str, team: str = None) -> str:
    """Fetch player image via Wikipedia REST API with caching."""
    cache_key = f"wiki_img_v4_{name.replace(' ', '_')}_{str(team).replace(' ', '_')}"
    cached = cache.get(cache_key)
    if cached and cached.startswith("http"):
        bad_patterns = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                        "emblem", "Emblem", "logo", "Logo", "shield", "Shield"]
        if not any(p in cached for p in bad_patterns):
            return cached

    deadline = time.monotonic() + _LOOKUP_BUDGET_S

    def _expired() -> bool:
        return time.monotonic() >= deadline

    HEADERS = {"User-Agent": "FootIQ/1.0 (football analytics; https://github.com/footiq)"}

    def _is_footballer(d: dict) -> bool:
        extract = (d.get("extract") or "").lower()
        desc = (d.get("description") or "").lower()
        keywords = ["footballer", "soccer", "midfielder", "forward", "striker", "winger",
                    "defender", "goalkeeper", "player", "club", "stats", "league", "born", "playing"]
        match = any(k in extract for k in keywords) or any(k in desc for k in keywords)
        if team:
            t_low = team.lower()
            t_alt = t_low.replace("nott'ham", "nottingham").replace("utd", "united")
            if t_low in extract or t_alt in extract or t_low in desc or t_alt in desc:
                return True
        return match

    def _rest(title: str, force_verify: bool = False) -> str | None:
        if _expired():
            return None
        try:
            slug = title.strip().replace(" ", "_")
            encoded_slug = quote(slug, safe="")
            r = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_slug}",
                headers=HEADERS, timeout=_REQUEST_TIMEOUT_S
            )
            if r.status_code != 200:
                # Page doesn't exist under this exact title — there's no
                # wikitext to parse either, so trying that fallback here
                # would just be a second guaranteed-wasted request.
                return None

            d = r.json()
            if d.get("type") == "disambiguation":
                return None
            if force_verify and not _is_footballer(d):
                return None
            img = (d.get("originalimage") or d.get("thumbnail") or {}).get("source")
            if img:
                bad = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                       "emblem", "Logo", "logo", "shield", "Shield",
                       "city", "City", "town", "Town", "stadium", "Stadium",
                       "landscape", "Panorama"]
                if not any(b in img for b in bad):
                    return img

            if _expired():
                return None
            pr = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=parse&page={encoded_slug}&prop=wikitext&section=0&format=json",
                headers=HEADERS, timeout=_REQUEST_TIMEOUT_S
            )
            if pr.status_code == 200:
                wt = pr.json().get("parse", {}).get("wikitext", {}).get("*", "")
                infobox_img = re.search(r"\|\s*image\s*=\s*([^|\n\r]+)", wt)
                if infobox_img:
                    file_name = infobox_img.group(1).strip()
                    if file_name and not _expired():
                        ir = requests.get(
                            f"https://en.wikipedia.org/w/api.php?action=query&titles=File:{quote(file_name)}&prop=imageinfo&iiprop=url&format=json",
                            headers=HEADERS, timeout=_REQUEST_TIMEOUT_S
                        )
                        pages = ir.json().get("query", {}).get("pages", {})
                        for pid in pages:
                            ii_list = pages[pid].get("imageinfo", [])
                            if ii_list:
                                final_url = ii_list[0].get("url")
                                if final_url:
                                    return final_url
        except Exception:
            pass
        return None

    def _search_wiki(query: str) -> str | None:
        if _expired():
            return None
        try:
            r = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={quote(query)}&srlimit=3&format=json",
                headers=HEADERS, timeout=_REQUEST_TIMEOUT_S
            )
            if r.status_code == 200:
                results = r.json().get("query", {}).get("search", [])
                for result in results:
                    if _expired():
                        break
                    title = result.get("title", "")
                    snippet = result.get("snippet", "").lower()
                    name_parts = [p for p in clean_name.lower().split() if len(p) > 3]
                    title_lower = title.lower()
                    # ALL significant name parts must appear, not just one —
                    # "any" let a shared surname alone match a different
                    # person entirely (e.g. searching "Jobe Bellingham"
                    # matching a page titled "Jude Bellingham", since only
                    # "Bellingham" needed to be present).
                    name_match = bool(name_parts) and all(part in title_lower for part in name_parts)
                    is_foot = any(k in snippet for k in ["footballer", "football player", "midfielder", "forward", "defender", "striker", "winger", "born"])
                    if team and team.lower() in snippet:
                        is_foot = True
                    if name_match and is_foot:
                        img = _rest(title)
                        if img:
                            return img
        except Exception:
            pass
        return None

    def _ascii_fallback(n: str) -> str:
        return unicodedata.normalize("NFD", n).encode("ascii", "ignore").decode("ascii")

    clean_name = name.strip()
    parts = clean_name.split()
    if len(parts) > 2 and len(parts[0]) <= 3 and parts[0].isalpha() and parts[0].islower():
        clean_name = " ".join(parts[1:])

    ascii_name = _ascii_fallback(clean_name)

    # Each fallback is a thunk, not a direct call — the loop stops trying
    # further variants as soon as either one succeeds or the time budget
    # runs out, instead of always grinding through every variant even on a
    # near-certain miss (previously this was a plain `or` chain, so a player
    # with no matching Wikipedia page paid the full cost of ALL of them).
    #
    # Plain name goes FIRST: most footballers' pages are just their name with
    # no disambiguation suffix, so for the common case this resolves in one
    # request instead of burning three guaranteed-404 disambiguated variants
    # before ever trying the title that was actually going to work.
    attempts = [lambda: _rest(clean_name, force_verify=True)]
    if team:
        attempts.append(lambda: _rest(f"{clean_name} ({team})"))
    attempts += [
        lambda: _rest(f"{clean_name} (footballer)"),
        lambda: _rest(f"{clean_name} (soccer)"),
    ]
    if team:
        attempts.append(lambda: _search_wiki(f"{clean_name} {team} footballer"))
    attempts.append(lambda: _search_wiki(f"{clean_name} footballer"))
    if ascii_name != clean_name:
        attempts.append(lambda: _rest(f"{ascii_name} (footballer)"))
        attempts.append(lambda: _search_wiki(f"{ascii_name} footballer"))

    img = None
    for attempt in attempts:
        if _expired():
            break
        img = attempt()
        if img:
            break

    if img:
        bad_patterns = ["Flag_of_", "flag_of_", "coat_of_arms", "Coat_of_arms",
                        "emblem", "Emblem", "logo", "Logo", "shield", "Shield"]
        if not any(p in img for p in bad_patterns):
            cache.put(cache_key, img)
            return img

    return ""


TEAM_COLORS = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Manchester City": "#6CABDD",
    "Manchester Utd": "#DA291C", "Liverpool": "#C8102E", "Chelsea": "#034694",
    "Tottenham": "#132257", "Newcastle Utd": "#241F20",
    "Real Madrid": "#FEBE10", "Barcelona": "#004D98", "Atlético Madrid": "#CB3524",
    "Real Sociedad": "#0067B1", "Villareal": "#FFE100",
    "Bayern Munich": "#DC052D", "Dortmund": "#FDE100", "Leverkusen": "#E32221",
    "RB Leipzig": "#DD013F",
    "Inter": "#010E80", "Milan": "#FB090B", "Juventus": "#000000",
    "Napoli": "#12A0D7", "Roma": "#F0BC42", "Lazio": "#87D8F7",
    "Paris S-G": "#004170", "Marseille": "#2FAEE0", "Monaco": "#E9212E",
    "Lille": "#E01E13", "Lyon": "#ED1C24",
}


def get_team_color(team_name: str) -> str:
    return TEAM_COLORS.get(team_name, "#3b82f6")
