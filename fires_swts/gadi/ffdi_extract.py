"""Extract per-state daily FFDI + per-SWT gridded FFDI anomaly composites from the BARRA-R2 Zarr.
Dry run: python3 ffdi_extract.py --start 2000-01 --end 2000-12 --out_csv t.csv --out_nc t.nc
Full:    python3 ffdi_extract.py
First run PRINTS the Zarr schema; pass --var/--lat/--lon if the auto-detected names are wrong."""
import argparse, numpy as np, pandas as pd, xarray as xr, geopandas as gpd
from shapely.geometry import Point
from datetime import datetime
from composite_core import doy_anomaly_composite

ZARR = "/g/data/ia39/ncra/fire/bias-input/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr"
STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zarr", default=ZARR)
    ap.add_argument("--swt_csv", default="SWT_climatology_v20260129.csv")
    ap.add_argument("--geojson", default="aus_states.geojson")
    ap.add_argument("--var", default=None); ap.add_argument("--lat", default=None); ap.add_argument("--lon", default=None)
    ap.add_argument("--start", default="1979-01"); ap.add_argument("--end", default=None)
    ap.add_argument("--coarsen", type=int, default=5)        # 0.05 -> 0.25 deg for the gridded composite
    ap.add_argument("--out_csv", default="ffdi_state_daily.csv")
    ap.add_argument("--out_nc",  default="ffdi_swt_composite.nc")
    a = ap.parse_args()

    ds = xr.open_zarr(a.zarr)
    print("=== Zarr schema ===\n", ds, flush=True)
    var = a.var or [v for v in ds.data_vars][0]
    lat = a.lat or ("lat" if "lat" in ds.coords else "latitude")
    lon = a.lon or ("lon" if "lon" in ds.coords else "longitude")
    print(f"using var={var}, lat={lat}, lon={lon}", flush=True)

    # zarr stores (lat,lon,time) -> force time-first so the composite gets [T,Y,X]
    da = ds[var].sel(time=slice(a.start, a.end)).transpose("time", lat, lon)
    LA, LO = da[lat].values, da[lon].values

    # ---- offline state mask: assign each cell centroid to a state (point-in-polygon) ----
    states = gpd.read_file(a.geojson)
    glon, glat = np.meshgrid(LO, LA)
    cells = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in zip(glon.ravel(), glat.ravel())], crs=states.crs)
    joined = gpd.sjoin(cells, states[["state", "geometry"]], how="left", predicate="within")
    smask = joined["state"].values.reshape(glat.shape)       # [lat,lon] of state names / nan
    mask_da = xr.DataArray(smask, coords={lat: LA, lon: LO}, dims=(lat, lon))
    print("cells per state:", {s: int((smask == s).sum()) for s in STATES}, flush=True)

    # ---- Output A: per-state daily area-mean FFDI (per-state pass; memory-frugal) ----
    recs = []
    for s in STATES:
        ser = da.where(mask_da == s).mean(dim=(lat, lon)).compute()
        recs.append(pd.DataFrame({"date": pd.to_datetime(ser["time"].values).date,
                                  "state": s, "ffdi": ser.values}))
        print(f"  state mean done: {s}", flush=True)
    pd.concat(recs, ignore_index=True).to_csv(a.out_csv, index=False)
    print(f"wrote {a.out_csv}", flush=True)

    # ---- Output B: per-SWT gridded FFDI anomaly composite (coarsened) ----
    swt = pd.read_csv(a.swt_csv); swt.columns = ["date", "assigned_SWT"][:len(swt.columns)]
    swt["date"] = pd.to_datetime(swt["date"]).values.astype("datetime64[D]")
    swt_names = sorted(swt["assigned_SWT"].dropna().unique().tolist())
    lab = swt.set_index("date")["assigned_SWT"]
    dac = da.coarsen({lat: a.coarsen, lon: a.coarsen}, boundary="trim").mean().compute()
    field = dac.values                                       # [T, y, x]
    dates = pd.to_datetime(dac["time"].values).values.astype("datetime64[D]")
    swtv = lab.reindex(pd.DatetimeIndex(dates)).values.astype(str)
    keep = swtv != "nan"
    field, dates, swtv = field[keep], dates[keep], swtv[keep]
    mean, anom, p, n = doy_anomaly_composite(field, dates, swtv, swt_names)
    out = xr.Dataset(
        {"ffdi_mean": (("swt", "lat", "lon"), mean), "ffdi_anom": (("swt", "lat", "lon"), anom),
         "ffdi_p": (("swt", "lat", "lon"), p), "n_days": ("swt", n)},
        coords={"swt": swt_names, "lat": dac[lat].values, "lon": dac[lon].values})
    out.attrs.update(source=a.zarr, period=f"{a.start}..{a.end}", created=datetime.now().isoformat(timespec="seconds"))
    out.to_netcdf(a.out_nc)
    print(f"wrote {a.out_nc}; aligned days={len(dates)}", flush=True)

if __name__ == "__main__":
    main()
