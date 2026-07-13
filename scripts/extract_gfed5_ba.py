"""Extract GFED5 monthly burned area for Australia and SE Australia.

Reads BA*.nc files from data/raw/gfed5/, clips to AUS and SEAUS bboxes,
sums Total burned area (km²) per month. Outputs:
    data/derived/gfed5_monthly_ba.csv
Columns: year, month, ba_aus_km2, ba_seaus_km2
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "gfed5"
OUT = Path(__file__).resolve().parents[1] / "data" / "derived" / "gfed5_monthly_ba.csv"

AUS = {"lon_min": 110.0, "lon_max": 155.0, "lat_min": -44.0, "lat_max": -10.0}
SE_AUS = {"lon_min": 140.0, "lon_max": 154.0, "lat_min": -39.0, "lat_max": -28.0}


def _clip_and_sum(da, bbox):
    subset = da.sel(
        lat=slice(bbox["lat_min"], bbox["lat_max"]),
        lon=slice(bbox["lon_min"], bbox["lon_max"]),
    )
    return float(subset.sum(skipna=True))


rows = []
for f in sorted(RAW.glob("BA??????.nc")):
    ds = xr.open_dataset(f)
    da = ds["Total"].squeeze("time", drop=True)

    yyyymm = f.stem[2:]
    year, month = int(yyyymm[:4]), int(yyyymm[4:])

    ba_aus = _clip_and_sum(da, AUS)
    ba_seaus = _clip_and_sum(da, SE_AUS)

    rows.append({"year": year, "month": month, "ba_aus_km2": ba_aus, "ba_seaus_km2": ba_seaus})
    ds.close()

df = pd.DataFrame(rows).sort_values(["year", "month"]).reset_index(drop=True)
OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False, float_format="%.2f")
print(f"wrote {len(df)} rows -> {OUT}")
