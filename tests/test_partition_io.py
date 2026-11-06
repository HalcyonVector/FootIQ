"""write_partitioned must keep unchanged partitions byte-identical (so Git LFS
sees no change) while still updating partitions whose data changed."""
import os

import pandas as pd

from core.advanced.partition_io import write_partitioned


def _files(root):
    return {os.path.relpath(os.path.join(d, f), root): open(os.path.join(d, f), "rb").read()
            for d, _, fs in os.walk(root) for f in fs if f.endswith(".parquet")}


def _df(a_vals, b_vals):
    return pd.DataFrame({"league": ["L1"] * len(a_vals) + ["L2"] * len(b_vals), "season": "s",
                         "v": list(a_vals) + list(b_vals)})


def test_unchanged_partition_keeps_same_file_and_changed_one_updates(tmp_path):
    out = str(tmp_path / "ds")
    write_partitioned(_df([1, 2, 3], [10, 20]), out)
    first = _files(out)
    assert len(first) == 2

    write_partitioned(_df([1, 2, 3], [10, 20, 30]), out)   # only L2 changed
    second = _files(out)
    l1 = [k for k in first if "league=L1" in k][0]
    l2_old = [k for k in first if "league=L2" in k][0]
    assert l1 in second and second[l1] == first[l1]          # same name AND same bytes
    l2_new = [k for k in second if "league=L2" in k][0]
    assert second[l2_new] != first[l2_old]
    assert len(pd.read_parquet(out)) == 6


def test_removed_partition_disappears(tmp_path):
    out = str(tmp_path / "ds")
    write_partitioned(_df([1], [2]), out)
    write_partitioned(_df([1], []), out)
    assert all("league=L2" not in k for k in _files(out))


def test_empty_frame_leaves_empty_dir(tmp_path):
    out = str(tmp_path / "ds")
    write_partitioned(pd.DataFrame({"league": [], "season": [], "v": []}), out)
    assert os.path.isdir(out) and not _files(out)
