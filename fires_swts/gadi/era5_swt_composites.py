"""Compute per-SWT ERA5 circulation composites on Gadi. Run via PBS (see .pbs).
Quick dry run:  python3 era5_swt_composites.py --start 1990-01 --end 1990-12 --out test.nc
Full run:       python3 era5_swt_composites.py
"""
import argparse, numpy as np, pandas as pd, xarray as xr
from datetime import datetime, timedelta
from composite_core import doy_anomaly_composite

LAT_LIMS = [-60, -5]; LON_LIMS = [80, 180]; UTC = 12; NCOARSEN = 4
SL = "/g/data/rt52/era5/single-levels/reanalysis/"
PL = "/g/data/rt52/era5/pressure-levels/reanalysis/"
# (output_name, era5_varname, path, level)
FIELDS = [("msl",   "msl", SL, None),
          ("z500",  "z",   PL, 500),
          ("u850",  "u",   PL, 850),
          ("v850",  "v",   PL, 850),
          ("t850",  "t",   PL, 850)]

def hours1900_to_dates(time_hours):
    base = datetime(1900, 1, 1)
    return np.array([np.datetime64((base + timedelta(hours=int(h))).date()) for h in time_hours])

def main():
    from read_era5 import read_data           # imported here so the module is importable off-Gadi
    ap = argparse.ArgumentParser()
    ap.add_argument("--swt_csv", default="SWT_climatology_v20260129.csv")
    ap.add_argument("--start", default=None, help="yyyy-mm (default: from csv)")
    ap.add_argument("--end",   default=None, help="yyyy-mm (default: from csv)")
    ap.add_argument("--out",   default="era5_swt_composites.nc")
    a = ap.parse_args()

    swt_df = pd.read_csv(a.swt_csv)
    swt_df.columns = ["date", "assigned_SWT"][:len(swt_df.columns)]
    swt_df["date"] = pd.to_datetime(swt_df["date"]).values.astype("datetime64[D]")
    swt_names = sorted(swt_df["assigned_SWT"].dropna().unique().tolist())
    start = a.start or swt_df["date"].min().strftime("%Y-%m")
    end   = a.end   or swt_df["date"].max().strftime("%Y-%m")
    print(f"Period {start}..{end}; {len(swt_names)} SWTs; {len(swt_df)} label-days", flush=True)

    lab = swt_df.set_index("date")["assigned_SWT"]
    out = xr.Dataset()
    n_days_ref = lat = lon = None
    for oname, vname, path, level in FIELDS:
        print(f"\n=== {oname} ({vname}@{level}) ===", flush=True)
        field, time, lat, lon = read_data(vname, start, end, UTC, LAT_LIMS, LON_LIMS,
                                          path, Ncoarsen=NCOARSEN, level=level, progress=True)
        dates = hours1900_to_dates(time)
        swt = lab.reindex(pd.DatetimeIndex(dates)).values.astype(str)   # align by date
        good = swt != "nan"
        field, dates, swt = field[good], dates[good], swt[good]
        print(f"  aligned days: {len(dates)}", flush=True)
        mean, anom, p, n = doy_anomaly_composite(field, dates, swt, swt_names)
        dims = ("swt", "lat", "lon")
        out[f"{oname}_mean"] = (dims, mean)
        out[f"{oname}_anom"] = (dims, anom)
        out[f"{oname}_p"]    = (dims, p)
        if n_days_ref is None:
            n_days_ref = n
    out = out.assign_coords(swt=swt_names, lat=lat, lon=lon)
    out["n_days"] = ("swt", n_days_ref)
    out.attrs.update(source="ERA5 rt52", utc=UTC, ncoarsen=NCOARSEN,
                     domain=f"lon{LON_LIMS} lat{LAT_LIMS}", period=f"{start}..{end}",
                     anomaly="day-of-year climatology (cluster_daily_pert method)",
                     created=datetime.now().isoformat(timespec="seconds"))
    out.to_netcdf(a.out)
    print(f"\nwrote {a.out}", flush=True)
    print("per-SWT day counts:\n" +
          "\n".join(f"  {s}: {int(c)}" for s, c in zip(swt_names, n_days_ref)), flush=True)

if __name__ == "__main__":
    main()
