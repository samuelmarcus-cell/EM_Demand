"""Daily per-state weather-object presence over Australia (fronts, anticyclones, cyclones)
from the 21CW ERA5 weather-feature catalogues, for the Fires x SWT analysis.

Coord recipe (assign_weatherfeature_coords) is verbatim from the GC26_energy_synoptics demand
notebook; state masking uses OUR aus_states.geojson (7 states, point-in-polygon).

Files are MONTHLY, foldered by YEAR: <dir>/<YYYY>/<prefix><YYYY>_<MM>.nc. We open only the
requested years, subset to Australia, LOAD that small coarse slice into memory ONCE per object
(int8, a few GB at full 1979-2023 -> safe), then reduce per-state in plain numpy (no 7x reread,
no float upcast from .where). This avoids both the open-everything glob and the OOM/slow paths.

Dry run (one year): python3 weather_objects_extract.py --start 2010-01 --end 2010-12 --out t.csv
Full (1979-2023):   python3 weather_objects_extract.py
Output object_presence_daily.csv [date, state, object, present]  (present=1 if object over the
state at ANY sub-daily step that day).
"""
import argparse, glob, time, numpy as np, pandas as pd, xarray as xr, geopandas as gpd
from shapely.geometry import Point

DATADIR = "/g/data/if69/cj0591/GC26_energy_synoptics/data/weatherfeatures.era5"  # alt: /g/data/su28/weatherfeatures.era5
STATES  = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]
OBJECTS = {  # dir under DATADIR, filename prefix, and the variable carrying the 0/1 flag
    "front850":    {"dir": "fronts/cdf.850hPa", "prefix": "F", "var": "FRONT"},
    "front700":    {"dir": "fronts/cdf.700hPa", "prefix": "F", "var": "FRONT"},
    "anticyclone": {"dir": "maxcl/cdf",         "prefix": "A", "var": "FLAG"},
    "cyclone":     {"dir": "mincl/cdf",         "prefix": "C", "var": "INPUT"},
}

def select_files(datadir, dirpath, prefix, y0, y1):
    """Only the monthly files for years [y0, y1] (missing years just contribute nothing)."""
    fs = []
    for y in range(y0, y1 + 1):
        fs += sorted(glob.glob(f"{datadir}/{dirpath}/{y}/{prefix}*.nc"))
    return fs

def assign_weatherfeature_coords(ds):
    """VERBATIM from GC26 demand notebook: feature files ship without coords; rebuild the global
    0.5-deg grid and rename dims to latitude/longitude."""
    ds = ds.squeeze()
    y_dim = list(ds.dims)[1]; x_dim = list(ds.dims)[2]
    nx = ds.sizes[x_dim]
    ds = ds.assign_coords({y_dim: (y_dim, np.arange(-90, 90.5, 0.5)),
                           x_dim: (x_dim, -180 + 0.5 * np.arange(nx))})
    ds = ds.rename({y_dim: "latitude", x_dim: "longitude"})
    if ds.longitude.size != 720:
        ds = ds.sel(longitude=np.arange(-180, 180, .5))
    return ds

def state_label_array(lat, lon, geojson):
    """Pure point-in-polygon (NO xarray, locally testable): [len(lat), len(lon)] array of state
    names (NaN off-land). Args are (lat, lon); Points are (x=lon, y=lat)."""
    g = gpd.read_file(geojson)
    glon, glat = np.meshgrid(lon, lat)
    cells = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in zip(glon.ravel(), glat.ravel())], crs=g.crs)
    joined = gpd.sjoin(cells, g[["state", "geometry"]], how="left", predicate="within")
    return joined["state"].values.reshape(glat.shape)

def state_daily_presence(vals, times, smask, states):
    """Pure numpy/pandas (locally testable). vals int [T,lat,lon]; times datetime64[T];
    smask [lat,lon] state labels. Returns long df [date, state, present] where present=1 if the
    object flag==1 at ANY cell of the state on ANY sub-daily step that day."""
    idx = pd.DatetimeIndex(times); recs = []
    for s in states:
        cm = (smask == s)
        if not cm.any():
            continue
        present_t = (vals[:, cm] == 1).any(axis=1)                 # [T] bool; indexes only the state's cells
        daily = pd.Series(present_t, index=idx).resample("1D").max()
        recs.append(pd.DataFrame({"date": daily.index.normalize(), "state": s,
                                  "present": daily.values.astype(int)}))
    return pd.concat(recs, ignore_index=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datadir", default=DATADIR)
    ap.add_argument("--geojson", default="aus_states.geojson")
    ap.add_argument("--start", default="1979-01"); ap.add_argument("--end", default="2023-12")
    ap.add_argument("--out", default="object_presence_daily.csv")
    a = ap.parse_args()
    y0, y1 = int(a.start[:4]), int(a.end[:4])

    recs = []
    for name, obj in OBJECTS.items():
        t0 = time.time()
        files = select_files(a.datadir, obj["dir"], obj["prefix"], y0, y1)
        if not files:
            print(f"[{name}] NO FILES for {y0}-{y1} under {obj['dir']} -- skipping", flush=True); continue
        ds = xr.open_mfdataset(files, combine="by_coords", chunks={"time": 720})
        ds = assign_weatherfeature_coords(ds).sel(latitude=slice(-55, -9), longitude=slice(110, 155))
        da = ds[obj["var"]].sel(time=slice(a.start, a.end)).load()       # small Aus slice into RAM, ONCE
        smask = state_label_array(da.latitude.values, da.longitude.values, a.geojson)
        print(f"[{name}] grid {da.shape} ({len(files)} files); cells/state " +
              str({s: int((smask == s).sum()) for s in STATES}), flush=True)
        df = state_daily_presence(da.values, da.time.values, smask, STATES)
        df["object"] = name; recs.append(df)
        print(f"[{name}] done in {time.time()-t0:.1f}s", flush=True)
    out = pd.concat(recs, ignore_index=True)[["date", "state", "object", "present"]]
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(out):,} rows, {out['date'].min().date()}..{out['date'].max().date()}, "
          f"objects={out['object'].unique().tolist()}", flush=True)

if __name__ == "__main__":
    main()
