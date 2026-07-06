"""Export tidy CSVs for the R figures. Reads existing checkpoints only."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.figures_data import BENCHMARKS, benchmark_table, hotspots_for_days

EXPORT = DATA_DERIVED.parent / "export"
EXPORT.mkdir(parents=True, exist_ok=True)

# map days: iconic fire benchmarks in the satellite era + the top-2 DLI days
MAP_DAYS = ["2003-01-18", "2009-02-07", "2011-02-02", "2013-01-04", "2020-01-04"]

panel = pd.read_parquet(DATA_DERIVED / "demand_daily_panel.parquet",
                        columns=["date", "dli", "confidence_tier"])
panel.to_csv(EXPORT / "fig_dli_daily.csv", index=False, float_format="%.4f")

bench = benchmark_table(panel, BENCHMARKS)
bench.to_csv(EXPORT / "fig_benchmarks.csv", index=False, float_format="%.4f")
print(bench.to_string(index=False), flush=True)

top = pd.read_csv(DATA_DERIVED / "dli_top50_days.csv", usecols=["date"]).head(2)
days = sorted(set(MAP_DAYS) | set(top["date"]))
hs = pd.read_parquet(DATA_DERIVED / "hotspots_firms.parquet",
                     columns=["lat", "lon", "datetime_utc", "frp"])
hmap = hotspots_for_days(hs, days)
hmap.to_csv(EXPORT / "fig_hotspots_days.csv", index=False, float_format="%.4f")
print(f"{len(hmap):,} hotspots across {hmap.date.nunique()} map days", flush=True)
