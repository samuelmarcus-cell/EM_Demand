"""Daily flood-proxy components from AGCD precip. Runs on Gadi via qsub.

Outputs agcd_rain_daily.csv next to this file: for each day, the fraction
of land cells whose 1/3/7-day rain accumulation exceeds the cell's
calendar-month 95th wet-day (>=1 mm) percentile (base 1979-2023),
nationally and in the SEAUS box (lon 140-154, lat -39..-28).
"""
import sys
from pathlib import Path

import pandas as pd
import xarray as xr

AGCD_DIR = "/g/data/zv2/agcd/v1/precip/total/r005/01day"
VAR = "precip"
BASE = slice("1979-01-01", "2023-12-31")
SEAUS = {"lon": slice(140.0, 154.0), "lat": slice(-39.0, -28.0)}
OUT = Path(__file__).resolve().parent / "agcd_rain_daily.csv"

DRY = "--dry" in sys.argv  # 6-year smoke test: exercises the full dask path cheaply
END = None
if DRY:
    BASE = slice("1979-01-01", "1984-12-31")
    END = "1984-12-31"
    OUT = OUT.with_name("agcd_rain_dry.csv")
    print("DRY RUN: 1979-1984 only", flush=True)

print("opening AGCD...", flush=True)
ds = xr.open_mfdataset(f"{AGCD_DIR}/*.nc", chunks={"lat": 64}, parallel=True)
pr = ds[VAR].sel(time=slice("1979-01-01", END))
if pr.lat.values[0] > pr.lat.values[-1]:  # ensure ascending for slice()
    pr = pr.sortby("lat")
# Monthly groupby-quantile requires the time axis in ONE chunk (flox only
# supports nanquantile blockwise); lat=16 keeps each chunk ~1 GB.
pr = pr.chunk({"time": -1, "lat": 16, "lon": -1})

frames = {}
for win in (1, 3, 7):
    acc = pr if win == 1 else pr.rolling(time=win).sum()  # first win-1 days of 1979 are NaN by construction (window not yet filled)
    wet = acc.where(acc >= 1.0)
    thr = wet.sel(time=BASE).groupby("time.month").quantile(0.95, dim="time")
    # scalar q: some xarray versions add a 'quantile' dim, others only a coord
    if "quantile" in thr.dims:
        thr = thr.squeeze("quantile", drop=True)
    thr = thr.drop_vars("quantile", errors="ignore")
    exceed = acc.groupby("time.month") >= thr
    land = pr.isel(time=0).notnull()
    exceed = exceed.where(land)

    # National + SEAUS area fractions in ONE compute (one archive read)
    both = xr.Dataset(
        {
            f"rain{win}d_area": exceed.mean(dim=("lat", "lon"), skipna=True),
            f"seaus_rain{win}d": exceed.sel(**SEAUS).mean(dim=("lat", "lon"), skipna=True),
        }
    )
    print(f"computing rain{win}d (national + seaus)...", flush=True)
    both = both.compute()
    frames[f"rain{win}d_area"] = both[f"rain{win}d_area"].to_series()
    frames[f"seaus_rain{win}d"] = both[f"seaus_rain{win}d"].to_series()

out = pd.DataFrame(frames)
out.index = pd.to_datetime(out.index).normalize()  # AGCD stamps are 09:00 (9am-to-9am rain day)
out.index.name = "date"
out.to_csv(OUT, float_format="%.6f")
print(f"wrote {OUT} ({len(out)} rows)", flush=True)
