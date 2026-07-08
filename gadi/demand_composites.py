"""Per-stratum ERA5 composites of high-demand days. Run via PBS (see .pbs).

Gadi-side files (flat, same directory): this script, composite_core.py,
read_era5.py (both copied unmodified from fires_swts/gadi/), and
demand_stratum_days.csv (from scripts/run_composite_strata.py).

Dry run:  python3 demand_composites.py --start 1990-01 --end 1991-12 --out test.nc
Full run: python3 demand_composites.py
"""
import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import xarray as xr

LAT_LIMS = [-60, -5]; LON_LIMS = [80, 180]; UTC = 12; NCOARSEN = 4
SL = "/g/data/rt52/era5/single-levels/reanalysis/"
PL = "/g/data/rt52/era5/pressure-levels/reanalysis/"
# (output_name, era5_varname, path, level)
FIELDS = [("msl",  "msl",  SL, None),
          ("t850", "t",    PL, 850),
          ("u850", "u",    PL, 850),
          ("v850", "v",    PL, 850),
          ("tcwv", "tcwv", SL, None)]
MIN_DAYS = 30  # strata below this are reported but not composited (spec §2)


def strata_to_composite(days, min_days=MIN_DAYS):
    """Sorted stratum names with at least min_days labelled days."""
    counts = days["stratum"].value_counts()
    return sorted(counts[counts >= min_days].index.tolist())


def hours1900_to_dates(time_hours):
    base = datetime(1900, 1, 1)
    return np.array([np.datetime64((base + timedelta(hours=int(h))).date())
                     for h in time_hours])


def main():
    from read_era5 import read_data  # Gadi-only import
    from composite_core import doy_anomaly_composite  # Gadi-only import

    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="demand_stratum_days.csv")
    ap.add_argument("--start", default="1979-01", help="yyyy-mm")
    ap.add_argument("--end",   default="2023-12", help="yyyy-mm")
    ap.add_argument("--out",   default="demand_composites.nc")
    a = ap.parse_args()

    days = pd.read_csv(a.labels, parse_dates=["date"])
    strata = strata_to_composite(days)
    counts = days["stratum"].value_counts()
    print(f"{len(days)} labelled days; composited strata: {strata}", flush=True)
    for s, n in counts.items():
        print(f"  {s}: {n}" + ("" if s in strata else "  [n<30, skipped]"),
              flush=True)

    lab = days.set_index("date")["stratum"]
    out = xr.Dataset()
    n_days_ref = lat = lon = None
    for oname, vname, path, level in FIELDS:
        print(f"\n=== {oname} ({vname}@{level}) ===", flush=True)
        field, time, lat, lon = read_data(vname, a.start, a.end, UTC,
                                          LAT_LIMS, LON_LIMS, path,
                                          Ncoarsen=NCOARSEN, level=level,
                                          progress=True)
        dates = hours1900_to_dates(time)
        # KEEP unlabelled days ("nan"): they feed the day-of-year climatology
        # inside doy_anomaly_composite. Filtering them (as the SWT script
        # does, where labels cover every day) would build the climatology
        # from high-demand days only and destroy the anomalies.
        strat = lab.reindex(pd.DatetimeIndex(dates)).values.astype(str)
        print(f"  days in period: {len(dates)}, labelled: {(strat != 'nan').sum()}",
              flush=True)
        mean, anom, p, n = doy_anomaly_composite(field, dates, strat, strata)
        dims = ("stratum", "lat", "lon")
        out[f"{oname}_mean"] = (dims, mean)
        out[f"{oname}_anom"] = (dims, anom)
        out[f"{oname}_p"]    = (dims, p)
        if n_days_ref is None:
            n_days_ref = n

    out = out.assign_coords(stratum=strata, lat=lat, lon=lon)
    out["n_days"] = ("stratum", n_days_ref)
    out.attrs.update(
        source="ERA5 rt52", utc=UTC, ncoarsen=NCOARSEN,
        domain=f"lon{LON_LIMS} lat{LAT_LIMS}", period=f"{a.start}..{a.end}",
        anomaly="day-of-year climatology over ALL days in period",
        labels=a.labels, min_days=MIN_DAYS,
        created=datetime.now().isoformat(timespec="seconds"))
    out.to_netcdf(a.out)
    print(f"\nwrote {a.out}", flush=True)
    print("per-stratum day counts:\n" +
          "\n".join(f"  {s}: {int(c)}" for s, c in zip(strata, n_days_ref)),
          flush=True)


if __name__ == "__main__":
    main()
