"""Daily flood-proxy components from AGCD precip. Runs on Gadi via qsub.

Outputs agcd_rain_daily.csv next to this file: for each day, the fraction
of land cells whose 1/3/7-day rain accumulation exceeds the cell's
calendar-month 95th wet-day (>=1 mm) percentile (base 1979-2023),
nationally and in the SEAUS box (lon 140-154, lat -39..-28).
"""
from pathlib import Path

import pandas as pd
import xarray as xr

AGCD_DIR = "/g/data/zv2/agcd/v1/precip/total/r005/01day"
VAR = "precip"
BASE = slice("1979-01-01", "2023-12-31")
SEAUS = {"lon": slice(140.0, 154.0), "lat": slice(-39.0, -28.0)}
OUT = Path(__file__).resolve().parent / "agcd_rain_daily.csv"

print("opening AGCD...", flush=True)
ds = xr.open_mfdataset(f"{AGCD_DIR}/*.nc", chunks={"lat": 64}, parallel=True)
pr = ds[VAR].sel(time=slice("1979-01-01", None))
if pr.lat.values[0] > pr.lat.values[-1]:  # ensure ascending for slice()
    pr = pr.sortby("lat")

frames = {}
for win in (1, 3, 7):
    acc = pr if win == 1 else pr.rolling(time=win).sum()  # first win-1 days of 1979 are NaN by construction (window not yet filled)
    wet = acc.where(acc >= 1.0)
    thr = wet.sel(time=BASE).groupby("time.month").quantile(0.95, dim="time")
    thr = thr.squeeze("quantile", drop=True)
    exceed = acc.groupby("time.month") >= thr
    land = pr.isel(time=0).notnull()
    exceed = exceed.where(land)

    # National rain area fraction
    frac_national = exceed.mean(dim=("lat", "lon"), skipna=True)
    print(f"computing rain{win}d_area...", flush=True)
    frames[f"rain{win}d_area"] = frac_national.compute().to_series()

    # SEAUS rain area fraction
    exceed_seaus = exceed.sel(**SEAUS)
    frac_seaus = exceed_seaus.mean(dim=("lat", "lon"), skipna=True)
    print(f"computing seaus_rain{win}d...", flush=True)
    frames[f"seaus_rain{win}d"] = frac_seaus.compute().to_series()

out = pd.DataFrame(frames)
out.index = pd.to_datetime(out.index).normalize()  # AGCD stamps are 09:00 (9am-to-9am rain day)
out.index.name = "date"
out.to_csv(OUT, float_format="%.6f")
print(f"wrote {OUT} ({len(out)} rows)", flush=True)
