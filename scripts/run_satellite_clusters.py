"""Run Section 2b: ST-DBSCAN clustering of polygon-unmatched hotspots.

Outputs (data/derived/):
    satellite_fire_matches.parquet  hotspot_idx, fire_uid (SAT_*), date_local, frp, state=NA
    satellite_fire_daily.parquet    fire_id, date, state, n_hotspots, frp_sum
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.fire_association import fire_daily_table
from scripts.satellite_clusters import cluster_unmatched

t0 = time.time()
idx = pd.read_parquet(DATA_DERIVED / "hotspots_unmatched_idx.parquet")["hotspot_idx"]
hs = pd.read_parquet(
    DATA_DERIVED / "hotspots_firms.parquet", columns=["lat", "lon", "datetime_utc", "frp"]
).loc[idx]
print(f"{len(hs)} unmatched hotspots loaded ({time.time()-t0:.0f}s)", flush=True)

print("clustering per season ...", flush=True)
sat = cluster_unmatched(hs, verbose=True)
print(f"clustered {len(sat)} points into {sat['fire_uid'].nunique()} satellite-only fires "
      f"({100*len(sat)/len(hs):.1f}% of unmatched; rest is noise) ({time.time()-t0:.0f}s)", flush=True)
sat.to_parquet(DATA_DERIVED / "satellite_fire_matches.parquet")

daily = fire_daily_table(sat)
daily.to_parquet(DATA_DERIVED / "satellite_fire_daily.parquet")
print(f"satellite_fire_daily: {len(daily)} fire-days, {daily['fire_id'].nunique()} fires", flush=True)
print(f"done in {time.time()-t0:.0f}s", flush=True)
