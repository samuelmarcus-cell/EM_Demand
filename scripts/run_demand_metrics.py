"""Run Section 3: fire-day table + daily demand metrics panel.

Outputs (data/derived/):
    fire_days.parquet             per-fire-per-day with centroid + state
    fire_seasons.json             per-state climatological season months
    demand_metrics_daily.parquet  long-format daily metrics by region
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED, PATHS
from scripts.demand_metrics import assign_states, build_fire_days, demand_metrics_panel, fire_seasons

t0 = time.time()
matches = pd.concat(
    [
        pd.read_parquet(DATA_DERIVED / "hotspot_fire_matches.parquet"),
        pd.read_parquet(DATA_DERIVED / "satellite_fire_matches.parquet"),
    ],
    ignore_index=True,
)[["hotspot_idx", "fire_uid", "date_local", "frp"]]
coords = pd.read_parquet(DATA_DERIVED / "hotspots_firms.parquet", columns=["lat", "lon"])
print(f"{len(matches)} match rows loaded ({time.time()-t0:.0f}s)", flush=True)

fire_days = build_fire_days(matches, coords)
del matches, coords
print(f"fire_days: {len(fire_days)} rows ({time.time()-t0:.0f}s)", flush=True)

fire_days = assign_states(fire_days, PATHS.aus_states_geojson)
print(f"states assigned ({time.time()-t0:.0f}s)", flush=True)
fire_days.to_parquet(DATA_DERIVED / "fire_days.parquet")

seasons = fire_seasons(fire_days)
(DATA_DERIVED / "fire_seasons.json").write_text(
    json.dumps({s: sorted(m) for s, m in seasons.items()}, indent=2)
)
print("fire seasons:", {s: sorted(m) for s, m in seasons.items()}, flush=True)

panel = demand_metrics_panel(fire_days, seasons)
panel.to_parquet(DATA_DERIVED / "demand_metrics_daily.parquet")
print(f"panel: {len(panel)} region-days ({time.time()-t0:.0f}s)", flush=True)
print(f"done in {time.time()-t0:.0f}s", flush=True)
