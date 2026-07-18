"""
Canonical position-group classification, shared by the FBref-based system
(app.py, core/scorer.py, core/insights.py) and the new WhoScored-event-based
advanced-metrics system. Previously duplicated 3x with minor stylistic
differences but identical behavior; consolidated here as the single source
of truth rather than adding a 4th copy.
"""

POS_GROUPS = {
    "attacker":   ["attacker", "forward", "winger", "striker", "fw"],
    "midfielder": ["midfielder", "midfield", "mf"],
    "defender":   ["defender", "back", "defence", "defense", "df"],
    "goalkeeper": ["goalkeeper", "keeper", "gk"],
}


# WhoScored's own position codes (distinct from FBref's FW/MF/DF/GK scheme —
# a WhoScored roster tags e.g. a center-back "DC", not "DF"). Order matters:
# check the 2-letter prefixes (DM, AM) before the 1-letter ones (D, M), since
# "DMC" would otherwise match the "D" defender check first and be misclassified
# as a defender instead of a (defensive) midfielder.
_WHOSCORED_EXACT = {"gk": "goalkeeper", "fw": "attacker"}
_WHOSCORED_PREFIXES = [
    ("dm", "midfielder"),   # DMC, DML, DMR — defensive midfield
    ("am", "midfielder"),   # AMC, AML, AMR — attacking midfield
    ("fw", "attacker"),     # FWL, FWR
    ("d", "defender"),      # DC, DL, DR
    ("m", "midfielder"),    # MC, ML, MR
]


def pos_group(pos_str: str) -> str:
    """Map a position string to one of four canonical groups: attacker,
    midfielder, defender, goalkeeper. Handles both FBref's scheme ('FW',
    'DF,MF', 'Forward', 'GK') and WhoScored's ('DC', 'AMC', 'DMR', 'FWR').
    Defaults to 'attacker' for unrecognized/empty input (e.g. 'Sub', None,
    or NaN — pandas turns a missing string cell into a float NaN)."""
    if not isinstance(pos_str, str):
        pos_str = ""
    low = pos_str.lower().strip()
    # Compound codes like "FW,MF" — use the first part
    first = low.split(",")[0].strip() if "," in low else low

    if first == "fw": return "attacker"
    if first == "mf": return "midfielder"
    if first == "df": return "defender"
    if first == "gk": return "goalkeeper"

    if first in _WHOSCORED_EXACT:
        return _WHOSCORED_EXACT[first]
    for prefix, group in _WHOSCORED_PREFIXES:
        if first.startswith(prefix):
            return group

    for group, keys in POS_GROUPS.items():
        if any(k in low for k in keys):
            return group
    return "attacker"
