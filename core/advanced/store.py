"""
Lazy-loaded, memoized access to the precomputed advanced-metrics parquet.
Mirrors core/fetcher.py's _get_df() pattern for the FBref CSV — the running
app only ever reads this small file, never the 6GB raw event cache.

get_chart_events() and get_linkup_receptions() are deliberately NOT full-table
caches like get_advanced_df() — those two datasets are one-row-per-event and
Hive-partitioned by league/season (see config.py), specifically so a single
request reads one small on-disk slice instead of the whole dataset. That
matters on a memory-constrained host: loading every category's every event
for every league/season into a process-wide cache once needed >1GB RSS for
these two files alone (see scraping/build_advanced_metrics.py for the numbers
that drove this), which OOM-crashed a 512MB-RAM hosting tier the first time a
chart was ever requested.

Both read via a pyarrow.dataset.Dataset object cached per category (built
once, reused every call) rather than pandas.read_parquet(path, filters=...),
which re-discovers the partition layout from scratch on every call and, when
measured under repeated requests, showed steadily climbing RSS with no
corresponding growth in pyarrow's own tracked memory pool or in Python-heap
allocations (confirmed via tracemalloc) — i.e. native-allocator fragmentation
from the repeated re-scan, not a real object leak. Reusing one Dataset object
and pushing the player_id filter down to the Arrow scan itself (not just
league/season, then a pandas-level filter) cut that growth by roughly 60% in
the same test and left it visibly converging rather than climbing.
to_pylist() also fixes a real correctness gap pandas conversion would have
introduced: a missing release_s comes back as Python None (matching what
chart_events.py always produced), not NaN — visuals/passing.py and
visuals/tempo.py both filter on `is not None`, which a NaN silently defeats.
"""

import gc
import os
import pandas as pd
import pyarrow.dataset as pa_ds
import pyarrow.parquet as pq
from pyarrow.dataset import field as _f

from core.advanced import config

import pyarrow as _pa
_pa.set_cpu_count(1)        # see _read_parquet_lean: cores visible to the process != CPU it may use
_pa.set_io_thread_count(2)

_DF: pd.DataFrame | None = None
_LINKUP_PAIRS = None          # pyarrow Table (dictionary-encoded strings), see get_linkup_pairs()


def trim_memory() -> None:
    """Hand freed memory back to the OS. Loading a table leaves Arrow's allocator (and
    glibc's) holding on to what it used while decoding, so the process sits 100+ MB above
    what the data needs; on a 512 MB host that is the difference between staying up and the
    'exceeded its memory limit' restart."""
    gc.collect()
    try:
        _pa.default_memory_pool().release_unused()
    except Exception:
        pass
    try:                                    # glibc only (Linux / Render); a no-op elsewhere
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
_CHART_DATASETS: dict[str, pa_ds.Dataset] = {}
_LINKUP_RECEPTIONS_DATASET: pa_ds.Dataset | None = None


def _read_parquet_lean(path: str) -> pd.DataFrame:
    """pandas.read_parquet keeps the intermediate Arrow table's buffers alive
    alongside the converted DataFrame until the next full GC pass — measured
    locally as ~2.5x the DataFrame's own memory in peak RSS. self_destruct
    frees each Arrow column's buffer as soon as it's copied into a pandas
    block, and the explicit gc.collect() reclaims it immediately rather than
    waiting; only worth the extra step for the two tables kept cached for a
    process's entire lifetime (the per-request partition reads elsewhere in
    this module are already small enough that it wouldn't move the needle)."""
    # Single-threaded on purpose: the host reports many CPU cores but Render's free
    # tier gives the container a fraction of one, and Arrow's thread pool then
    # spends its whole quota being throttled.
    table = pq.read_table(path, use_threads=False)
    df = table.to_pandas(split_blocks=True, self_destruct=True, use_threads=False)
    del table
    trim_memory()
    return df


def get_advanced_df() -> pd.DataFrame:
    global _DF
    if _DF is None:
        if os.path.exists(config.PLAYER_SEASON_PARQUET):
            _DF = _read_parquet_lean(config.PLAYER_SEASON_PARQUET)
            if not _DF.empty:
                from core.media import _normalize_str
                from core.position import pos_group
                # Precomputed once here instead of re-normalizing every
                # player's name / re-classifying every player's position
                # group on every single search/Scout/Explore request —
                # turns a per-request O(n) Python-level pass into a
                # one-time cost at load/reload.
                # Per distinct value, then looked up per row: ~14k distinct names across
                # 35k rows, and only a couple of dozen distinct positions.
                names = {n: _normalize_str(str(n)) for n in _DF["player_name"].unique()}
                groups = {p: pos_group(p) for p in _DF["position"].unique()}
                _DF["_norm_name"] = _DF["player_name"].map(names)
                _DF["_pos_group"] = _DF["position"].map(groups)
        else:
            _DF = pd.DataFrame()
    return _DF


def _linkup_pairs():
    """The passer/receiver pair list (~520k rows). Held as an Arrow table with
    dictionary-encoded strings (~23 MB) instead of a pandas frame of Python strings
    (~62 MB, and a 100+ MB spike while loading); a lookup filters it in ~25 ms."""
    global _LINKUP_PAIRS
    if _LINKUP_PAIRS is None:
        if os.path.exists(config.LINKUP_SUMMARY_PARQUET):
            _LINKUP_PAIRS = pq.read_table(
                config.LINKUP_SUMMARY_PARQUET, use_threads=False,
                read_dictionary=["passer_name", "receiver_name", "team_name", "league", "season"],
            ).combine_chunks()
            trim_memory()
        else:
            _LINKUP_PAIRS = False
    return _LINKUP_PAIRS or None


def get_linkup_pairs(passer_id: int, league: str, season: str, receiver_id: int | None = None) -> list[dict]:
    """[{passer_name, receiver_id, receiver_name, count}] for one passer in one league-season, most
    passes first (all of them, or just the one pair when receiver_id is given)."""
    import pyarrow.compute as pc
    tbl = _linkup_pairs()
    if tbl is None:
        return []
    mask = pc.and_(pc.equal(tbl["passer_id"], int(passer_id)),
                   pc.and_(pc.equal(tbl["league"], league), pc.equal(tbl["season"], season)))
    if receiver_id is not None:
        mask = pc.and_(mask, pc.equal(tbl["receiver_id"], int(receiver_id)))
    rows = tbl.select(["passer_name", "receiver_id", "receiver_name", "count"]).filter(mask).to_pylist()
    rows.sort(key=lambda r: -r["count"])
    return rows


def _chart_dataset(category: str) -> pa_ds.Dataset | None:
    if category not in _CHART_DATASETS:
        cat_dir = os.path.join(config.CHART_EVENTS_DIR, category)
        _CHART_DATASETS[category] = pa_ds.dataset(cat_dir, format="parquet", partitioning="hive") \
            if os.path.isdir(cat_dir) else None
    return _CHART_DATASETS[category]


def _linkup_receptions_dataset() -> pa_ds.Dataset | None:
    global _LINKUP_RECEPTIONS_DATASET
    if _LINKUP_RECEPTIONS_DATASET is None and os.path.isdir(config.LINKUP_RECEPTIONS_DIR):
        _LINKUP_RECEPTIONS_DATASET = pa_ds.dataset(config.LINKUP_RECEPTIONS_DIR, format="parquet", partitioning="hive")
    return _LINKUP_RECEPTIONS_DATASET


def get_linkup_receptions(passer_id: int, receiver_id: int, league: str, season: str) -> list[dict]:
    """Every filter (including passer_id/receiver_id, not just the league/
    season partition keys) is pushed into the Arrow scan itself, so only this
    one pair's rows are ever materialized — never the other ~8M reception
    events across the rest of the dataset. Returns
    [{reception_x, reception_y, outcome, end_x, end_y}, ...]."""
    dataset = _linkup_receptions_dataset()
    if dataset is None:
        return []
    table = dataset.to_table(
        columns=["reception_x", "reception_y", "outcome", "end_x", "end_y"],
        filter=(_f("league") == league) & (_f("season") == season)
        & (_f("passer_id") == passer_id) & (_f("receiver_id") == receiver_id),
    )
    return table.to_pylist()


def get_chart_events(category: str, player_id: int, league: str, season: str) -> list[dict]:
    """Per-request replacement for the old full-table get_chart_events_df().
    Every filter — including player_id, not just league/season — is pushed
    into the Arrow scan itself via a Dataset object cached per category (built
    once, reused every call): re-discovering the partition layout from
    pandas.read_parquet(path, filters=...) on every call measured as steadily
    climbing RSS under repeated requests even though nothing was actually
    leaking (see this module's docstring). Returns a list of per-event dicts
    with the same field names visuals/*.py has always expected."""
    dataset = _chart_dataset(category)
    if dataset is None:
        return []
    fields = [f.name for f in dataset.schema if f.name not in ("whoscored_player_id", "league", "season")]
    table = dataset.to_table(
        columns=fields,
        filter=(_f("league") == league) & (_f("season") == season) & (_f("whoscored_player_id") == player_id),
    )
    return table.to_pylist()


# ── Player Overview datasets (scraping/build_overview_data.py) ──────────────
# Same per-request partition-slice pattern as get_chart_events(): one cached
# Dataset object per table, every filter pushed into the Arrow scan.

_OVERVIEW_DATASETS: dict[str, pa_ds.Dataset | None] = {}


def _overview_dataset(name: str, path: str) -> pa_ds.Dataset | None:
    if name not in _OVERVIEW_DATASETS:
        _OVERVIEW_DATASETS[name] = pa_ds.dataset(path, format="parquet", partitioning="hive") \
            if os.path.isdir(path) and os.listdir(path) else None
    return _OVERVIEW_DATASETS[name]


def get_player_matches(player_id: int, league: str | None = None, season: str | None = None) -> list[dict]:
    """A player's per-match rows. With league+season: that one partition.
    Without: every league/season the player appears in (career view)."""
    ds = _overview_dataset("matches", config.PLAYER_MATCHES_DIR)
    if ds is None:
        return []
    flt = _f("whoscored_player_id") == int(player_id)
    if league is not None:
        flt = flt & (_f("league") == league)
    if season is not None:
        flt = flt & (_f("season") == season)
    return ds.to_table(filter=flt).to_pylist()


def get_team_match_counts(league: str, season: str) -> dict[str, int]:
    """{team name: matches played} in one competition-season, from the
    per-match table (one partition scan, a few thousand rows)."""
    ds = _overview_dataset("matches", config.PLAYER_MATCHES_DIR)
    if ds is None:
        return {}
    t = ds.to_table(columns=["team", "match_key"],
                    filter=(_f("league") == league) & (_f("season") == season)).to_pandas()
    return t.drop_duplicates().groupby("team")["match_key"].nunique().to_dict()


def get_season_matches(league: str, season: str):
    """Every player-match row of one competition-season as a DataFrame (a few
    thousand rows) -- league tables and team pages are built from this."""
    import pandas as pd
    ds = _overview_dataset("matches", config.PLAYER_MATCHES_DIR)
    if ds is None:
        return pd.DataFrame()
    return ds.to_table(filter=(_f("league") == league) & (_f("season") == season)).to_pandas()


_ASSIST_COLS = ("assist_pid", "ax", "ay", "aex", "aey")


def get_player_shots(player_id: int, league: str, season: str) -> list[dict]:
    ds = _overview_dataset("shots", config.SHOTS_DIR)
    if ds is None:
        return []
    cols = [f.name for f in ds.schema if f.name not in ("whoscored_player_id", "league", "season") + _ASSIST_COLS]
    return ds.to_table(
        columns=cols,
        filter=(_f("league") == league) & (_f("season") == season) & (_f("whoscored_player_id") == int(player_id)),
    ).to_pylist()


def get_chances_created(player_id: int, league: str, season: str) -> list[dict]:
    """Shots this player set up with a pass, with the pass's start/end
    coordinates and the chance's xG / outcome (the "key pass" map)."""
    ds = _overview_dataset("shots", config.SHOTS_DIR)
    if ds is None or "assist_pid" not in ds.schema.names:
        return []
    return ds.to_table(
        columns=["ax", "ay", "aex", "aey", "xg", "outcome", "minute"],
        filter=(_f("league") == league) & (_f("season") == season) & (_f("assist_pid") == int(player_id)),
    ).to_pylist()


def get_player_heat(player_id: int, league: str, season: str) -> dict | None:
    """{touches: [GRID_X*GRID_Y], defs: [...]} flattened column-major by x (see overview._cell)."""
    ds = _overview_dataset("heat", config.HEATMAPS_DIR)
    if ds is None:
        return None
    rows = ds.to_table(
        columns=["touches", "defs"],
        filter=(_f("league") == league) & (_f("season") == season) & (_f("whoscored_player_id") == int(player_id)),
    ).to_pylist()
    return rows[0] if rows else None


def reload():
    """Force a re-read from disk (e.g. after rebuilding the parquet)."""
    global _DF, _LINKUP_PAIRS, _CHART_DATASETS, _LINKUP_RECEPTIONS_DATASET, _OVERVIEW_DATASETS
    _DF = None
    _LINKUP_PAIRS = None
    _CHART_DATASETS = {}
    _LINKUP_RECEPTIONS_DATASET = None
    _OVERVIEW_DATASETS = {}
    return get_advanced_df()


def warm_essentials(progress=None) -> None:
    """The part of start-up every data request needs: the player-season table and the
    link-up pairs. The app opens its gate as soon as these (and the search index) are
    ready; the dataset handles in warm_datasets() are built after that."""
    step = progress or (lambda name: None)
    step("import aggregator")
    from core.advanced.aggregator import CHART_CATEGORIES  # noqa: F401  (the import is the point)
    step("player-season table")
    get_advanced_df()
    step("linkup summary")
    _linkup_pairs()


def warm_datasets(progress=None) -> None:
    """Dataset handles for the event, shot and heatmap partitions. Each is a directory scan,
    slow on a throttled disk and CPU; a request that arrives before its own handle exists
    simply builds it (the accessors are lazy), so this only hides that cost."""
    step = progress or (lambda name: None)
    from core.advanced.aggregator import CHART_CATEGORIES
    for category in CHART_CATEGORIES:
        step(f"chart dataset: {category}")
        _chart_dataset(category)
    step("linkup receptions")
    _linkup_receptions_dataset()
    for name, path in (("matches", config.PLAYER_MATCHES_DIR), ("shots", config.SHOTS_DIR), ("heat", config.HEATMAPS_DIR)):
        step(f"overview dataset: {name}")
        _overview_dataset(name, path)
    trim_memory()


def warm_up(progress=None) -> None:
    """Pre-loads everything a chart/stats request would otherwise load lazily
    on first use — called once at app startup (app.py) so a fresh gunicorn
    worker (a cold Render spin-up, or this app's own --max-requests worker
    recycling) pays this cost once at boot, not on whichever real visitor's
    request happens to be first. Measured live: a category-chart request
    hitting a genuinely cold worker took 40s; the categories after it, with
    everything already built, took under 6s. Building all 12 categories'
    Dataset objects up front (each one is a directory scan across every
    league/season partition) accounts for most of that gap."""
    warm_essentials(progress)
    warm_datasets(progress)
    (progress or (lambda name: None))("done")
