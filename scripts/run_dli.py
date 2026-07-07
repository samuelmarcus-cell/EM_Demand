"""Run Section 5: DLI v0 assembly + known-event validation.

Outputs (data/derived/):
    demand_daily_panel.parquet  components + percentiles + DLI, 1979-today
    dli_top50_days.csv          top 50 DLI days per tier

Prints the benchmark-event validation table: each event day's DLI and its
rank within its confidence tier (must sit in the extreme tail).
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.dli import assemble_components, compute_dli
from scripts.figures_data import BENCHMARKS
from scripts.fire_association import burn_window_daily, load_polygon_windows
from scripts.loaders.agcd_rain import load_agcd_rain
from scripts.loaders.tc_besttrack import load_tc_tracks, tc_daily_panel

t0 = time.time()
dm = pd.read_parquet(DATA_DERIVED / "demand_metrics_daily.parquet")
drfa = pd.read_parquet(DATA_DERIVED / "drfa_daily_panel.parquet")
tfb = pd.read_parquet(DATA_DERIVED / "tfb_vic_daily.parquet")
tc = tc_daily_panel(load_tc_tracks(), start="1979-01-01")
bw = burn_window_daily(load_polygon_windows(), start="1979-01-01")
rain = load_agcd_rain()
print(f"inputs loaded ({time.time()-t0:.0f}s)", flush=True)

components = assemble_components(dm, bw, drfa, tfb, tc, rain)
panel = compute_dli(components)
panel.to_parquet(DATA_DERIVED / "demand_daily_panel.parquet")
print(f"panel: {len(panel)} days {panel['date'].min().date()} -> {panel['date'].max().date()} "
      f"({time.time()-t0:.0f}s)", flush=True)

top50 = (
    panel.sort_values("dli", ascending=False)
    .groupby("confidence_tier")
    .head(50)
    .sort_values(["confidence_tier", "dli"], ascending=[True, False])
)
top50.to_csv(DATA_DERIVED / "dli_top50_days.csv", index=False)

print("\nBenchmark validation (rank = DLI percentile within tier):", flush=True)
p = panel.set_index("date")
for name, day in BENCHMARKS.items():
    row = p.loc[day]
    tier = int(row["confidence_tier"])
    in_tier = p[p["confidence_tier"] == tier]["dli"]
    pct = (in_tier < row["dli"]).mean()
    print(f"  {name:26s} {day}  tier {tier}  DLI {row['dli']:.3f}  "
          f"pct {pct:.4f}  n_comp {int(row['n_components_available'])}", flush=True)
print(f"done in {time.time()-t0:.0f}s", flush=True)
