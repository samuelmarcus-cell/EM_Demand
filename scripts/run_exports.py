"""Run Section 6: write analysis-ready CSVs to data/export/."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.export_for_r import write_exports

panel = pd.read_parquet(DATA_DERIVED / "demand_daily_panel.parquet")
metrics = pd.read_parquet(DATA_DERIVED / "demand_metrics_daily.parquet")
top50 = pd.read_csv(DATA_DERIVED / "dli_top50_days.csv", parse_dates=["date"])
write_exports(panel, metrics, top50)
print("done", flush=True)
