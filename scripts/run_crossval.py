"""Run FIRMS vs DEA hotspot cross-validation.

USER ACTION REQUIRED first: export historic hotspot CSVs from
https://hotspots.dea.ga.gov.au/ into data/raw/dea_hotspots/ (see
scripts/loaders/hotspots_dea.py docstring).

Outputs (data/derived/):
    crossval_daily.parquet   daily counts/FRP by sensor family, both sources
Prints the per-family agreement table.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.crossval import agreement_stats, compare_daily
from scripts.loaders.hotspots_dea import load_dea

dea = load_dea()
print(f"DEA: {len(dea):,} hotspots, "
      f"{dea.datetime_utc.min():%Y-%m-%d} -> {dea.datetime_utc.max():%Y-%m-%d}", flush=True)

firms = pd.read_parquet(
    DATA_DERIVED / "hotspots_firms.parquet",
    columns=["lat", "lon", "datetime_utc", "frp", "sensor"],
)
compared = compare_daily(firms, dea)
compared.to_parquet(DATA_DERIVED / "crossval_daily.parquet")
print(f"overlap: {compared.date.min().date()} -> {compared.date.max().date()}, "
      f"{len(compared)} family-days\n", flush=True)
print(agreement_stats(compared).round(3).to_string(index=False), flush=True)
