"""
Quick diagnostic: load all master PKL files and summarise what was fetched.
Run from: cd "D:\Projects\Football Project" && python check_output.py
"""
import pickle, sys
from pathlib import Path
import pandas as pd

PKL_DIR = Path("data/cache/master")
pkls = sorted(PKL_DIR.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True)
print(f"Found {len(pkls)} master PKL files\n")

frames = []
for p in pkls:
    try:
        with open(p, "rb") as f:
            df = pickle.load(f)
        frames.append(df)
    except Exception as e:
        print(f"  SKIP {p.name}: {e}")

if not frames:
    print("No PKL files loaded.")
    sys.exit(1)

df = pd.concat(frames, ignore_index=True)
print(f"Shape       : {df.shape[0]:,} rows × {df.shape[1]} cols")
print(f"Seasons     : {sorted(df['season'].dropna().unique())}")
print(f"\nLeague breakdown:")
print(df.groupby("league")["player"].count().sort_values(ascending=False).to_string())

# Columns per stat type
ALL_STAT_TYPES = ["standard","shooting","playing_time","keeper","misc",
                  "passing","passing_types","gca","defense","possession","keepersadv"]
print("\nStat coverage (cols with any non-NaN value):")
for st in ALL_STAT_TYPES:
    cols = [c for c in df.columns if c.startswith(f"{st}__")]
    if not cols:
        print(f"  {st:16s}:   0 cols  ← MISSING")
        continue
    filled = sum(df[c].notna().any() for c in cols)
    pct_nan = df[cols].isna().mean().mean() * 100
    print(f"  {st:16s}: {len(cols):3d} cols | {filled:3d} filled | {pct_nan:5.1f}% NaN overall")

# Salah spot-check
print("\n--- Salah spot-check (standard + gca + passing + defense) ---")
salah = df[df["player"].str.contains("Salah", na=False)].sort_values("season")
check_cols = ["player","squad","league","season"]
for st, col in [("standard","standard__performance__gls"),
                ("gca","gca__sca__sca90"),
                ("passing","passing__total__total_cmp_pct"),
                ("defense","defense__tackles__tkl"),
                ("possession","possession__carries__carries")]:
    if col in df.columns:
        check_cols.append(col)
    else:
        # find any col from that stat type
        candidates = [c for c in df.columns if c.startswith(f"{st}__")]
        if candidates:
            check_cols.append(candidates[0])

check_cols = list(dict.fromkeys(check_cols))  # dedup preserve order
salah_m = salah[salah["player"] == "Mohamed Salah"]
if salah_m.empty:
    salah_m = salah[salah["player"].str.startswith("Mohamed Sal")]
if not salah_m.empty:
    print(salah_m[check_cols].to_string(index=False))
else:
    print("Mohamed Salah not found in data")

# Save combined CSV with timestamp so we never overwrite the previous good export
from datetime import datetime
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = Path(f"football_master_{stamp}.csv")
df.to_csv(out_path, index=False)
print(f"\n✓ Saved combined CSV → {out_path}  ({df.shape[0]:,} rows × {df.shape[1]} cols)")
print("  (Previous football_master.csv left untouched)")
