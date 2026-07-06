# ERA5 SWT Circulation Composites — Implementation Plan

> **For agentic workers:** implement task-by-task. No git repo here → "commit" steps are replaced by "save file" + a run/verify step. Component A (Gadi) cannot be run locally; its *pure logic* is unit-tested locally and its I/O wrapper is dry-run on Gadi by the user.

**Goal:** Produce per-SWT ERA5 circulation composites (MSLP, Z500, U/V850, T850 anomalies) on Gadi, ship a small NetCDF back, and plot 4 headline-SWT maps in `Fires_SWTs.ipynb` (Step 6).

**Architecture:** A self-contained Gadi script reads `rt52` ERA5 @12 UTC, aligns to the daily SWT labels, computes day-of-year anomaly composites + significance, writes `era5_swt_composites.nc`. Local notebook cells load that file and render cartopy maps. The compositing math is a pure function unit-tested locally; the NetCDF schema is the A↔B contract.

**Tech Stack:** Python, numpy, pandas, xarray, netCDF4, scipy, matplotlib, cartopy; Barnes' `read_era5.read_data`; NCI `conda/analysis3` (xp65); PBS.

## Global Constraints
- ERA5 source: `/g/data/rt52/era5/{single-levels,pressure-levels}/reanalysis/`, sampled at **12 UTC** (`utc=12`).
- Fields: `msl` (single), `z`@500, `u`@850, `v`@850, `t`@850.
- Domain: lon **80–180°E**, lat **−60 to −5°S**; `Ncoarsen=4` (~1°).
- SWT labels: `SWT_climatology_v20260129.csv` (cols: date index `yyyy-mm-dd`, `assigned_SWT`).
- Anomaly = per-SWT mean minus the **day-of-year** climatology weighted by that SWT's doy occurrence (method of Barnes `compute_statistics.cluster_daily_pert`).
- Env on Gadi: `module use /g/data/xp65/public/modules && module load conda/analysis3`.
- Local Python for tests/notebook: `/opt/anaconda3/bin/python3`.
- Headline SWTs for plotting: `FH-B, WH-A, TH-C, WCT-B`.

---

### Task 1: Pure compositing core + local unit test

**Files:**
- Create: `/Users/smar0095/Fires_SWTs/gadi/composite_core.py`
- Test: `/Users/smar0095/Fires_SWTs/gadi/test_composite_core.py`

**Interfaces:**
- Produces: `mmdd_slot(dates) -> np.ndarray[int]` (0–365); `doy_anomaly_composite(field, dates, swt, swt_names) -> (mean, anom, p, n)` where `field` is `[T,Y,X]`, `dates` is `datetime64[D][T]`, `swt` is `str[T]`, returns arrays `[K,Y,X]`,`[K,Y,X]`,`[K,Y,X]`,`[K]`.

- [ ] **Step 1: Write `composite_core.py`**

```python
"""Pure (numpy) compositing core — no ERA5/Gadi I/O, so it is unit-testable locally."""
import numpy as np
import pandas as pd
from scipy.stats import norm

_REF  = pd.date_range("2020-01-01", "2020-12-31")          # leap year -> 366 day-of-year slots
_SLOT = {(t.month, t.day): i for i, t in enumerate(_REF)}

def mmdd_slot(dates):
    """Map each date to a 0..365 day-of-year slot (Feb-29 has its own slot)."""
    dti = pd.DatetimeIndex(dates)
    return np.array([_SLOT[(m, d)] for m, d in zip(dti.month, dti.day)], dtype=int)

def doy_anomaly_composite(field, dates, swt, swt_names):
    """Per-SWT seasonally-adjusted composite.
    field [T,Y,X] (12 UTC daily samples), dates datetime64[D][T], swt str[T].
    Returns mean[K,Y,X], anom[K,Y,X], p[K,Y,X] (two-sided), n[K]."""
    field = np.asarray(field, float)
    T, Y, X = field.shape
    doy = mmdd_slot(dates)
    clim = np.zeros((366, Y, X)); cnt = np.zeros(366)
    np.add.at(clim, doy, field); np.add.at(cnt, doy, 1)
    clim /= np.maximum(cnt, 1)[:, None, None]
    dayanom = field - clim[doy]                              # remove the seasonal cycle per day
    K = len(swt_names)
    mean = np.full((K, Y, X), np.nan); anom = np.full((K, Y, X), np.nan)
    p    = np.full((K, Y, X), np.nan); n = np.zeros(K, int)
    swt = np.asarray(swt)
    for k, name in enumerate(swt_names):
        m = swt == name; nk = int(m.sum()); n[k] = nk
        if nk == 0:
            continue
        mean[k] = field[m].mean(0)
        a = dayanom[m]; anom[k] = a.mean(0)
        if nk > 1:
            se = a.std(0, ddof=1) / np.sqrt(nk)
            with np.errstate(divide="ignore", invalid="ignore"):
                t = np.where(se > 0, anom[k] / se, 0.0)
            p[k] = 2 * norm.sf(np.abs(t))
    return mean, anom, p, n
```

- [ ] **Step 2: Write `test_composite_core.py`**

```python
"""Run: /opt/anaconda3/bin/python3 gadi/test_composite_core.py  -> prints OK or asserts."""
import numpy as np, pandas as pd
from composite_core import mmdd_slot, doy_anomaly_composite

def test_slot_count():
    d = pd.date_range("2019-01-01", "2021-12-31").values.astype("datetime64[D]")
    s = mmdd_slot(d)
    assert s.min() == 0 and s.max() == 365

def test_recovers_known_offset():
    # synthetic: seasonal cycle + a +5.0 offset injected ONLY on SWT 'A' days
    dates = pd.date_range("1990-01-01", "2010-12-31").values.astype("datetime64[D]")
    T = len(dates); Y, X = 3, 4
    doy = mmdd_slot(dates)
    seasonal = np.cos(2*np.pi*doy/366)[:, None, None] * np.ones((T, Y, X))
    rng = np.random.default_rng(0)
    swt = np.where(rng.random(T) < 0.2, "A", "B")
    field = seasonal + rng.normal(0, 0.1, (T, Y, X))
    field[swt == "A"] += 5.0
    mean, anom, p, n = doy_anomaly_composite(field, dates, swt, ["A", "B"])
    assert n[0] > 100 and n[1] > 100
    assert np.allclose(anom[0], 5.0, atol=0.1)          # offset recovered
    assert np.allclose(anom[1], 0.0, atol=0.1)          # B near zero
    assert np.nanmax(p[0]) < 0.01                        # A highly significant
    assert np.nanmin(p[1]) > 0.05                        # B not significant

if __name__ == "__main__":
    test_slot_count(); test_recovers_known_offset()
    print("OK: composite_core tests passed")
```

- [ ] **Step 3: Run the test (expect PASS)**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 test_composite_core.py`
Expected: `OK: composite_core tests passed`

---

### Task 2: Gadi driver script (`era5_swt_composites.py`)

**Files:**
- Create: `/Users/smar0095/Fires_SWTs/gadi/era5_swt_composites.py`
- Depends on (copy into same dir on Gadi): `read_era5.py` (from `Australian_synoptic_weather_types/utils/`), `composite_core.py`, the SWT csv.

**Interfaces:**
- Consumes: `read_era5.read_data(...)`, `composite_core.doy_anomaly_composite(...)`.
- Produces: NetCDF `era5_swt_composites.nc` — dims `(swt, lat, lon)`; vars `{f}_mean,{f}_anom,{f}_p` for `f in [msl,z500,u850,v850,t850]`; `n_days(swt)`; coords `swt,lat,lon`; provenance attrs.

- [ ] **Step 1: Write the script**

```python
"""Compute per-SWT ERA5 circulation composites on Gadi. Run via PBS (see .pbs).
Quick dry run:  python3 era5_swt_composites.py --start 1990-01 --end 1990-12 --out test.nc
Full run:       python3 era5_swt_composites.py
"""
import argparse, numpy as np, pandas as pd, xarray as xr
from datetime import datetime, timedelta
from read_era5 import read_data
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
    start = a.start or swt_df["date"].min().astype("datetime64[M]").astype(str)
    end   = a.end   or swt_df["date"].max().astype("datetime64[M]").astype(str)
    print(f"Period {start}..{end}; {len(swt_names)} SWTs; {len(swt_df)} label-days", flush=True)

    out = xr.Dataset()
    n_days_ref = None
    for oname, vname, path, level in FIELDS:
        print(f"\n=== {oname} ({vname}@{level}) ===", flush=True)
        field, time, lat, lon = read_data(vname, start, end, UTC, LAT_LIMS, LON_LIMS,
                                          path, Ncoarsen=NCOARSEN, level=level, progress=True)
        dates = hours1900_to_dates(time)
        # align field-days to SWT labels by date (intersection)
        lab = swt_df.set_index("date")["assigned_SWT"]
        keep = np.array([d in lab.index for d in dates])
        field, dates = field[keep], dates[keep]
        swt = lab.reindex(pd.DatetimeIndex(dates)).values.astype(str)
        good = swt != "nan"
        field, dates, swt = field[good], dates[good], swt[good]
        print(f"  aligned days: {len(dates)}", flush=True)
        mean, anom, p, n = doy_anomaly_composite(field, dates, swt, swt_names)
        dims = ("swt", "lat", "lon")
        out[f"{oname}_mean"] = (dims, mean)
        out[f"{oname}_anom"] = (dims, anom)
        out[f"{oname}_p"]    = (dims, p)
        if n_days_ref is None:
            n_days_ref = n; out["lat"] = lat; out["lon"] = lon; out["swt"] = swt_names
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
```

- [ ] **Step 2: Local syntax/import sanity (no rt52 access needed)**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 -c "import ast; ast.parse(open('era5_swt_composites.py').read()); print('syntax OK')"`
Expected: `syntax OK` (we do NOT import it fully locally — `read_era5`/rt52 only exist on Gadi).

---

### Task 3: PBS job + run/transfer instructions

**Files:**
- Create: `/Users/smar0095/Fires_SWTs/gadi/era5_swt_composites.pbs`
- Create: `/Users/smar0095/Fires_SWTs/gadi/README_RUN.md`

- [ ] **Step 1: Write the PBS script**

```bash
#!/bin/bash
#PBS -P <PROJECT>
#PBS -q normal
#PBS -l ncpus=2
#PBS -l mem=9GB
#PBS -l walltime=04:00:00
#PBS -l storage=gdata/rt52+gdata/xp65+gdata/<PROJECT>
#PBS -l wd
#PBS -N era5_swt_comp
#PBS -j oe
module use /g/data/xp65/public/modules
module load conda/analysis3
python3 era5_swt_composites.py
```

- [ ] **Step 2: Write `README_RUN.md`** (the exact recipe)

````markdown
# Running the ERA5 SWT composites on Gadi

## 1. Put these 4 files in one Gadi working dir (e.g. /g/data/<PROJECT>/<user>/swt_comp/)
- era5_swt_composites.py
- composite_core.py
- read_era5.py        (copy from Australian_synoptic_weather_types/utils/read_era5.py)
- SWT_climatology_v20260129.csv

## 2. Find your project + fill placeholders
Run `nci_account` (shows your projects + SU balance). Pick a project WITH a compute
allocation. Replace every `<PROJECT>` in era5_swt_composites.pbs (in -P AND -l storage).

## 3. Cheap dry run first (~1 SU, 1 year)
module use /g/data/xp65/public/modules && module load conda/analysis3
python3 era5_swt_composites.py --start 1990-01 --end 1990-12 --out test.nc
# expect: prints per-field progress, "aligned days: ~365", "wrote test.nc"

## 4. Full run via PBS
qsub era5_swt_composites.pbs          # returns a job id
qstat -u $USER                        # watch it; logs land in era5_swt_comp.o<id>
# Estimated cost: ~5-20 SU (2 cpus x a few hours x 2 SU/cpu-hr on `normal`).

## 5. Copy the result back to your laptop (run THIS on your laptop)
rsync -vP <user>@gadi-dm.nci.org.au:/g/data/<PROJECT>/<user>/swt_comp/era5_swt_composites.nc \
      /Users/smar0095/Fires_SWTs/
````

---

### Task 4: Local synthetic NetCDF (so Step 6 plotting is built/tested without Gadi)

**Files:**
- Create: `/Users/smar0095/Fires_SWTs/gadi/make_synthetic_nc.py`

- [ ] **Step 1: Write the generator (matches the exact output schema)**

```python
"""Make a synthetic era5_swt_composites.nc with the real schema so plotting can be built now."""
import numpy as np, xarray as xr
swt_names = ["FH-B","WH-A","TH-C","WCT-B","AM-A","CH-A"]    # subset incl. headline 4 is fine
lat = np.arange(-60, -4, 1.0); lon = np.arange(80, 181, 1.0)
K, Y, X = len(swt_names), len(lat), len(lon)
rng = np.random.default_rng(0)
ds = xr.Dataset(coords={"swt": swt_names, "lat": lat, "lon": lon})
for f, base in [("msl", 101300.0), ("z500", 5500.0), ("u850", 0.0), ("v850", 0.0), ("t850", 273.0)]:
    ds[f"{f}_mean"] = (("swt","lat","lon"), base + rng.normal(0, 50, (K,Y,X)))
    ds[f"{f}_anom"] = (("swt","lat","lon"), rng.normal(0, 20, (K,Y,X)))
    ds[f"{f}_p"]    = (("swt","lat","lon"), rng.random((K,Y,X)))
ds["n_days"] = ("swt", rng.integers(150, 400, K))
ds.to_netcdf("/Users/smar0095/Fires_SWTs/era5_swt_composites_SYNTH.nc")
print("wrote era5_swt_composites_SYNTH.nc")
```

- [ ] **Step 2: Run it**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 make_synthetic_nc.py`
Expected: `wrote era5_swt_composites_SYNTH.nc`

---

### Task 5: Step 6 notebook cells (plot composites)

**Files:**
- Modify: `/Users/smar0095/Fires_SWTs/Fires_SWTs.ipynb` (append Step 6: 1 markdown + 2 code cells)

**Interfaces:**
- Consumes: `era5_swt_composites.nc` (or the SYNTH file while testing).

- [ ] **Step 1: Check local cartopy availability**

Run: `/opt/anaconda3/bin/python3 -c "import cartopy, xarray; print('cartopy', cartopy.__version__)"`
Expected: a version string. If it errors → `/opt/anaconda3/bin/python3 -m pip install cartopy` (or use the plain-axes fallback noted in Step 3).

- [ ] **Step 2: Append markdown cell**

```markdown
## Step 6 — ERA5 circulation composites per SWT

Composite ERA5 (rt52, 12 UTC) circulation for each SWT, as day-of-year anomalies, to show
the synoptic pattern behind the elevated fire AMOUNT (Steps 2-5) and inspect FH-B's SA-TAS
coupling and TH-C's multi-state spread. Fields: MSLP (raw contours + H/L), 850 hPa wind
anomaly (quivers), T850 anomaly (shading). Composites computed on Gadi
(`gadi/era5_swt_composites.py`); this cell only plots the returned NetCDF.
```

- [ ] **Step 3: Append plotting code cell** (set `NC = .../era5_swt_composites_SYNTH.nc` to test, swap to real file when it lands)

```python
import xarray as xr, numpy as np, matplotlib.pyplot as plt
try:
    import cartopy.crs as ccrs
    from cartopy.feature import LAND
    HAVE_CARTOPY = True
except Exception:
    HAVE_CARTOPY = False

NC = f"{DATA_DIR}/era5_swt_composites_SYNTH.nc"   # -> era5_swt_composites.nc once real data is back
cmp = xr.open_dataset(NC)
HEAD = ["FH-B", "WH-A", "TH-C", "WCT-B"]
lon, lat = cmp["lon"].values, cmp["lat"].values

fig, axes = plt.subplots(2, 2, figsize=(12, 9),
                         subplot_kw=dict(projection=ccrs.PlateCarree()) if HAVE_CARTOPY else None)
for ax, swt in zip(axes.ravel(), HEAD):
    d = cmp.sel(swt=swt)
    if HAVE_CARTOPY:
        ax.add_feature(LAND, facecolor="0.92"); ax.coastlines(linewidth=0.4)
        tr = dict(transform=ccrs.PlateCarree())
    else:
        tr = {}
    # T850 anomaly shading
    vmax = float(np.nanmax(np.abs(cmp["t850_anom"].sel(swt=HEAD).values)))
    cf = ax.contourf(lon, lat, d["t850_anom"], levels=np.linspace(-vmax, vmax, 13),
                     cmap="RdBu_r", extend="both", **tr)
    # raw MSLP contours
    c = ax.contour(lon, lat, d["msl_mean"]/100, levels=np.arange(980, 1040, 4),
                   colors="k", linewidths=0.6, **tr)
    ax.clabel(c, c.levels[::2], fontsize=6, fmt="%d")
    # 850 wind anomaly quivers (subsampled)
    s = 3
    ax.quiver(lon[::s], lat[::s], d["u850_anom"].values[::s, ::s], d["v850_anom"].values[::s, ::s],
              scale=120, width=0.003, color="0.25", **tr)
    # significance stipple (T850) where p<0.05
    yy, xx = np.where(d["t850_p"].values < 0.05)
    ax.scatter(lon[xx], lat[yy], s=0.4, color="k", alpha=0.25, **tr)
    if HAVE_CARTOPY:
        ax.set_extent([80, 180, -60, -5], crs=ccrs.PlateCarree())
    ax.set_title(f"{swt}  (n={int(d['n_days'])} days)")
fig.colorbar(cf, ax=axes, label="T850 anomaly (K)", shrink=0.6)
fig.suptitle("Step 6 — ERA5 circulation composites (MSLP contours, 850hPa wind anom, T850 anom)")
fig.savefig(f"{DATA_DIR}/swt_circulation_composites.png", dpi=150, bbox_inches="tight")
plt.show()
print("saved swt_circulation_composites.png")
```

- [ ] **Step 4: Run the two new cells against the SYNTH file**

Run (headless check): `cd /Users/smar0095/Fires_SWTs && /opt/anaconda3/bin/jupyter nbconvert --to notebook --execute --inplace Fires_SWTs.ipynb` (or just execute the two new cells).
Expected: `saved swt_circulation_composites.png` and a 4-panel figure renders without error.

- [ ] **Step 5: When the real `era5_swt_composites.nc` arrives**, change `NC` to the real file, add `*_mean`→ also expose `z500_anom` option, re-run, and interpret (FH-B blocking high & SA-TAS; TH-C SE spread; WCT-B onshore flow).

---

## Self-review
- **Spec coverage:** rt52@12UTC ✓(T2); 5 fields ✓(FIELDS); domain/Ncoarsen ✓(constants); doy anomaly ✓(T1); significance ✓(T1 p); schema ✓(T2 out); env xp65 + PBS + SU/project ✓(T3); reuse read_era5/cluster_daily_pert method/plot style ✓; local build-before-Gadi via synthetic ✓(T4,T5).
- **Placeholders:** `<PROJECT>` is an intentional user-filled value (documented in README_RUN), not a plan gap. No code placeholders.
- **Type consistency:** `doy_anomaly_composite` signature identical in T1/T2; output var names `{f}_mean/_anom/_p` consistent T2↔T4↔T5; `swt/lat/lon` coords consistent.
- **Note:** Step-6 cell reads `z500_anom`/`msl_mean` etc. — all present in both synthetic (T4) and real (T2) schemas.
