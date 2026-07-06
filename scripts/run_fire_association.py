"""Run Section 2 association end-to-end. Heavy — run once, checkpoint everything.

Outputs (data/derived/):
    fire_polygons_windows.parquet   fire attributes + windows (no geometry)
    hotspot_fire_matches.parquet    hotspot_idx, fire_uid, date_local, frp, state
    fire_daily.parquet              fire_id, date, state, n_hotspots, frp_sum
    hotspots_unmatched_idx.parquet  indices into hotspots_firms.parquet
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.fire_association import associate_hotspots, fire_daily_table, load_fire_polygons

t0 = time.time()
poly_ckpt = DATA_DERIVED / "fire_polygons_simplified.parquet"
if poly_ckpt.exists():
    import geopandas as gpd

    print("loading simplified polygons from checkpoint ...", flush=True)
    fires = gpd.read_parquet(poly_ckpt)
else:
    print("loading + simplifying fire polygons ...", flush=True)
    fires = load_fire_polygons(verbose=True)
    fires.to_parquet(poly_ckpt)
print(f"  {len(fires)} fires in hotspot era ({time.time()-t0:.0f}s)", flush=True)
fires.drop(columns="geometry").to_parquet(DATA_DERIVED / "fire_polygons_windows.parquet")

print("loading hotspots ...", flush=True)
hotspots = pd.read_parquet(
    DATA_DERIVED / "hotspots_firms.parquet", columns=["lat", "lon", "datetime_utc", "frp"]
)
print(f"  {len(hotspots)} hotspots ({time.time()-t0:.0f}s)", flush=True)

print("associating (monthly chunks) ...", flush=True)
matches = associate_hotspots(hotspots, fires, verbose=True)
print(f"  matched {len(matches)} / {len(hotspots)} "
      f"({100*len(matches)/len(hotspots):.1f}%) ({time.time()-t0:.0f}s)", flush=True)
matches.to_parquet(DATA_DERIVED / "hotspot_fire_matches.parquet")

daily = fire_daily_table(matches)
daily.to_parquet(DATA_DERIVED / "fire_daily.parquet")
print(f"  fire_daily: {len(daily)} fire-days, {daily['fire_id'].nunique()} fires", flush=True)

unmatched = hotspots.index.difference(matches["hotspot_idx"])
pd.DataFrame({"hotspot_idx": unmatched}).to_parquet(DATA_DERIVED / "hotspots_unmatched_idx.parquet")
print(f"  unmatched: {len(unmatched)}", flush=True)
print(f"done in {time.time()-t0:.0f}s", flush=True)
