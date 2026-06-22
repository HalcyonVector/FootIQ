"""
Merge Understat xG data into football_master.csv.
Fills xG/npxG/xA/xGChain/xGBuildup for seasons where FBref had no data.

Run: python merge_understat.py
Output: football_master_with_xg.csv
"""
import pandas as pd
import unicodedata, re

# ── Load ──────────────────────────────────────────────────────────────────────
print("Loading data...")
fbref = pd.read_csv("football_master.csv", low_memory=False)
under = pd.read_csv("understat_players.csv", low_memory=False)

print(f"  FBref:     {fbref.shape}  seasons: {sorted(fbref['season'].unique())}")
print(f"  Understat: {under.shape}  seasons: {sorted(under['season'].unique())}")

# ── Normalise names for matching ──────────────────────────────────────────────
def norm(s):
    if not isinstance(s, str): return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())

# FBref 'Player' → normalised
fbref["_name"] = fbref["Player"].apply(norm)

# Understat 'player_name' → normalised
under["_name"] = under["player_name"].apply(norm)

# Season mapping: FBref uses "2021-22", Understat uses "2021-22" — should match
# Understat league → matches FBref 'Comp'
LEAGUE_MAP = {
    "ENG-Premier League": "Premier League",
    "ESP-La Liga":        "La Liga",
    "GER-Bundesliga":     "Bundesliga",
    "ITA-Serie A":        "Serie A",
    "FRA-Ligue 1":        "Ligue 1",
}
under["_comp"] = under["league"].map(LEAGUE_MAP)

# ── Check what FBref seasons actually need xG filled ─────────────────────────
print("\nFBref xG fill by season:")
for s in sorted(fbref["season"].unique()):
    sub = fbref[fbref["season"] == s]
    pct = sub["xG"].notna().mean()
    print(f"  {s}: {pct:.0%} filled ({len(sub)} rows)")

# ── Build Understat lookup: deduplicate by max minutes (handles mid-season transfers) ──
under_cols = ["xG","npxG","xA","xGChain","xGBuildup","key_passes","games","minutes"]
under["minutes"] = pd.to_numeric(under["minutes"], errors="coerce").fillna(0)
under_dedup = (under.sort_values("minutes", ascending=False)
                    .drop_duplicates(subset=["_name","_comp","season"])
                    .set_index(["_name","_comp","season"])[under_cols]
                    .sort_index())

# ── Merge via vectorised join instead of row-by-row ───────────────────────────
print("\nMerging...")
fbref["_comp"] = fbref["Comp"]
fbref_idx = fbref.set_index(["_name","_comp","season"])
joined = fbref_idx.join(under_dedup.add_suffix("_under"), how="left")
fbref = joined.reset_index()

matched = fbref["xG_under"].notna().sum()
total = len(fbref)
print(f"  Matched:   {matched}/{total} ({matched/total:.1%})")

from collections import Counter
unmatched = fbref[fbref["xG_under"].isna()]
print(f"  Unmatched by season: {dict(Counter(unmatched['season']))}")

total = len(fbref)
print(f"  Matched:   {matched}/{total} ({matched/total:.1%})")


# ── Fill strategy: use Understat where FBref xG is null ──────────────────────
print("\nFilling xG gaps with Understat data...")
before = fbref["xG"].notna().sum()

fbref["xG"]       = fbref["xG"].combine_first(fbref["xG_under"])
fbref["npxG"]     = fbref["npxG"].combine_first(fbref["npxG_under"])
fbref["xAG"]      = fbref["xAG"].combine_first(fbref["xA_under"])  # FBref calls it xAG

# Also add new Understat-only columns
fbref["xGChain"]   = fbref["xGChain_under"]
fbref["xGBuildup"] = fbref["xGBuildup_under"]

after = fbref["xG"].notna().sum()
print(f"  xG filled: {before} → {after} rows ({after - before} added)")

# Drop temp columns
drop_cols = [c for c in ["_name","_comp","xG_under","npxG_under","xA_under",
                          "xGChain_under","xGBuildup_under"] if c in fbref.columns]
fbref.drop(columns=drop_cols, inplace=True)

# ── Save ──────────────────────────────────────────────────────────────────────
out = "football_master_with_xg.csv"
fbref.to_csv(out, index=False)
print(f"\n✓ Saved {out}  shape={fbref.shape}")

# ── Final summary ─────────────────────────────────────────────────────────────
print("\nFinal xG fill by season:")
for s in sorted(fbref["season"].unique()):
    sub = fbref[fbref["season"] == s]
    pct = sub["xG"].notna().mean()
    print(f"  {s}: {pct:.0%}")

print("\nSample — EPL 2021-22 top xG:")
epl = fbref[(fbref["Comp"]=="Premier League") & (fbref["season"]=="2021-22")]
epl_xg = epl[epl["xG"].notna()].nlargest(5, "xG")[["Player","Squad","xG","npxG","xGChain"]]
print(epl_xg.to_string(index=False))
