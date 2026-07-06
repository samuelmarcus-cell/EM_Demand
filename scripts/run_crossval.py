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

dea_pq = DATA_DERIVED / "hotspots_dea.parquet"
if dea_pq.exists():
    dea = pd.read_parquet(
        dea_pq, columns=["lat", "lon", "datetime_utc", "frp", "sensor", "satellite"]
    )
    # the archive stores the same pass processed multiple times (~22% of rows)
    dea = dea.drop_duplicates(subset=["lat", "lon", "datetime_utc", "sensor"])
else:
    from scripts.loaders.hotspots_dea import load_dea
    dea = load_dea()

# like-for-like with FIRMS: VIIRS restricted to S-NPP where identifiable
if "satellite" in dea and not (dea["satellite"] == "unknown").all():
    is_viirs = dea["sensor"].str.upper().str.contains("VIIRS")
    dea = dea[~is_viirs | dea["satellite"].str.upper().str.contains("NPP")]
else:
    print("WARNING: DEA satellite unidentified — VIIRS comparison includes all platforms",
          flush=True)
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

# era split: DEA's ingestion changed around 2019 (multi-algorithm feed inflates
# counts); the pre-2019 era is the clean like-for-like comparison
for era, g in compared.groupby(compared.date >= "2019-01-01"):
    label = "2019-onward" if era else "pre-2019"
    print(f"\n{label}:\n" + agreement_stats(g).round(3).to_string(index=False), flush=True)
