"""
Partitioned-parquet writer shared by the build scripts.

Why not just df.to_parquet(partition_cols=...): a rebuild rewrites every
partition with a new random file name -- and, depending on the pyarrow
version that happens to run, even byte-different content for IDENTICAL data.
The dataset is shipped as a content-hashed zip (scraping/data_release.py), so
that churn would make every weekly update look "changed" and re-upload
~250 MB even when only the current season's partitions really changed.

write_partitioned() writes to a temp dir, then for every partition whose
data is unchanged it keeps the OLD file (same name, same bytes), so an
unchanged dataset hashes identically and nothing is uploaded. The swap into
place happens last, so a crash mid-write leaves the previous dataset intact.
"""

import os
import shutil

import pyarrow as pa
import pyarrow.parquet as pq


def _parquet_files(d: str) -> list[str]:
    return sorted(f for f in os.listdir(d) if f.endswith(".parquet"))


def _preserve_unchanged(new_root: str, old_root: str) -> tuple[int, int]:
    kept = total = 0
    for dirpath, _dirs, files in os.walk(new_root):
        if not any(f.endswith(".parquet") for f in files):
            continue
        total += 1
        old_dir = os.path.join(old_root, os.path.relpath(dirpath, new_root))
        if not os.path.isdir(old_dir):
            continue
        new_files, old_files = _parquet_files(dirpath), _parquet_files(old_dir)
        if len(new_files) != 1 or len(old_files) != 1:
            continue
        new_path, old_path = os.path.join(dirpath, new_files[0]), os.path.join(old_dir, old_files[0])
        try:
            same = pq.read_table(new_path).equals(pq.read_table(old_path))
        except Exception:
            same = False
        if same:
            os.remove(new_path)
            shutil.copy2(old_path, os.path.join(dirpath, old_files[0]))
            kept += 1
    return kept, total


def write_partitioned(df_or_table, out_dir: str, partition_cols=("league", "season"), compression: str = "snappy") -> None:
    tmp = out_dir + ".new"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp, exist_ok=True)
    table = df_or_table if isinstance(df_or_table, pa.Table) else pa.Table.from_pandas(df_or_table, preserve_index=False)
    if table.num_rows:
        pq.write_to_dataset(table, tmp, partition_cols=list(partition_cols), compression=compression)
        if os.path.isdir(out_dir):
            kept, total = _preserve_unchanged(tmp, out_dir)
            print(f"[partition_io] {os.path.basename(out_dir)}: {total - kept}/{total} partitions changed", flush=True)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.rename(tmp, out_dir)
