"""Reduce the precomputed national FFDI zarr to a daily summary CSV.

Runs on Gadi via qsub (gadi/extract_ffdi.pbs). Output:
    /g/data/gb02/sm5259/EM_Demand/ffdi_daily_summary.csv
Columns: date, ffdi_mean, frac_ge50, frac_ge75, seaus_frac_ge50
    ffdi_mean        national land mean daily FFDI
    frac_ge50        fraction of national land cells with FFDI >= 50 (Severe)
    frac_ge75        fraction >= 75 (Extreme)
    seaus_frac_ge50  fraction >= 50 within the SE Australia bbox
"""

import numpy as np
import pandas as pd
import xarray as xr

ZARR = ("/g/data/ia39/ncra/fire/bias-input/ffdi/"
        "AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr")
OUT = "/g/data/gb02/sm5259/EM_Demand/ffdi_daily_summary.csv"
SE_AUS = {"lon_min": 140.0, "lon_max": 154.0, "lat_min": -39.0, "lat_max": -28.0}

try:
    ds = xr.open_zarr(ZARR)
except Exception:
    ds = xr.open_zarr(ZARR, consolidated=False)

# Auto-detect the FFDI variable and coordinate names.
var = next(v for v in ds.data_vars if ds[v].ndim >= 3)
da = ds[var]
tdim = next(d for d in da.dims if "time" in d.lower())
latd = next(d for d in da.dims if d.lower() in ("lat", "latitude", "y"))
lond = next(d for d in da.dims if d.lower() in ("lon", "longitude", "x"))
print(f"var={var} dims={da.dims} shape={da.shape}", flush=True)
da = da.transpose(tdim, latd, lond)  # BARRA-derived zarrs are often time-LAST

rows = []
years = np.unique(da[tdim].dt.year.values)
for yr in years:
    chunk = da.sel({tdim: str(yr)}).load()  # one year at a time, keeps memory low
    land = chunk.notnull()
    mean = chunk.mean(dim=(latd, lond), skipna=True)
    ge50 = (chunk >= 50).sum(dim=(latd, lond)) / land.sum(dim=(latd, lond))
    ge75 = (chunk >= 75).sum(dim=(latd, lond)) / land.sum(dim=(latd, lond))
    lat = chunk[latd]
    se = chunk.sel({
        latd: lat[(lat >= SE_AUS["lat_min"]) & (lat <= SE_AUS["lat_max"])],
        lond: chunk[lond][(chunk[lond] >= SE_AUS["lon_min"]) & (chunk[lond] <= SE_AUS["lon_max"])],
    })
    se_land = se.notnull()
    se50 = (se >= 50).sum(dim=(latd, lond)) / se_land.sum(dim=(latd, lond))
    rows.append(pd.DataFrame({
        "date": pd.to_datetime(chunk[tdim].values).normalize(),
        "ffdi_mean": mean.values,
        "frac_ge50": ge50.values,
        "frac_ge75": ge75.values,
        "seaus_frac_ge50": se50.values,
    }))
    print(f"{yr} done ({len(rows[-1])} days)", flush=True)

out = pd.concat(rows, ignore_index=True)
out.to_csv(OUT, index=False, float_format="%.5f")
print(f"wrote {len(out)} rows -> {OUT}", flush=True)
