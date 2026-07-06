# FFDI Fire-Danger × SWT — Implementation Plan

> **For agentic workers:** implement task-by-task. No git repo → "commit" steps are "save file" + a run/verify step. The Gadi step (Task 3) cannot be run locally; its pure logic is unit-tested locally (Task 2) and the data step is dry-run on Gadi by the user.

**Goal:** Test whether synoptic types synchronise fire *danger* (FFDI) across states — using BARRA-R2 daily FFDI on NCI — mirroring the realized-fire Steps 2/4/5, plus a danger-composite map.

**Architecture:** A Gadi script opens the FFDI Zarr, masks to states (offline, from a shipped GeoJSON), and emits two small artifacts (per-state daily FFDI CSV + per-SWT gridded anomaly NetCDF). Locally, pure functions turn the per-state series into "high-danger day" flags and a daily frame, which feed the **existing** `simultaneity_rr` / `pair_permutation` machinery; figures render in Python/ggplot.

**Tech Stack:** Python, xarray+zarr, geopandas, numpy/pandas, statsmodels, matplotlib, cartopy; NCI `conda/analysis3` (xp65); reuses `gadi/composite_core.py` and notebook Step 2/4/5 functions.

## Global Constraints
- FFDI source (bias-input): `/g/data/ia39/ncra/fire/bias-input/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr`; extremes use the `bias-output/` twin. Needs `ia39` membership.
- Period = 1979 ∩ FFDI ∩ SWT (`SWT_climatology_v20260129.csv`, daily `assigned_SWT`).
- Regions = **7 states**, ACT→NSW.
- High-danger day = state area-mean FFDI **≥ that state's monthly 90th percentile** (self-normalising per state & month).
- Env on Gadi: `module use /g/data/xp65/public/modules && module load conda/analysis3`. Local Python: `/opt/anaconda3/bin/python3`.
- Headline SWTs: `FH-B, WH-A, TH-C, WCT-B`. Reuse the Step-6 anomaly method (`composite_core.doy_anomaly_composite`).

---

### Task 1: Australian state polygons (local) → ship to Gadi

**Files:** Create `/Users/smar0095/Fires_SWTs/gadi/aus_states.geojson` (built by a one-off script).

- [ ] **Step 1: Write `gadi/make_aus_states.py`**

```python
"""Build a 7-state Australia polygon GeoJSON (ACT folded into NSW) for offline masking on Gadi."""
import geopandas as gpd, cartopy.io.shapereader as shpreader
shp = shpreader.natural_earth(resolution="50m", category="cultural", name="admin_1_states_provinces")
gdf = gpd.read_file(shp)
au = gdf[gdf["admin"] == "Australia"].copy()
namemap = {"New South Wales":"NSW","Victoria":"VIC","Queensland":"QLD","South Australia":"SA",
           "Western Australia":"WA","Tasmania":"TAS","Northern Territory":"NT",
           "Australian Capital Territory":"NSW"}   # ACT -> NSW
au["state"] = au["name"].map(namemap)
au = au.dropna(subset=["state"]).dissolve(by="state").reset_index()[["state","geometry"]]
au.to_file("/Users/smar0095/Fires_SWTs/gadi/aus_states.geojson", driver="GeoJSON")
print("wrote aus_states.geojson with states:", sorted(au["state"]))
```

- [ ] **Step 2: Run it**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 make_aus_states.py`
Expected: `wrote aus_states.geojson with states: ['NSW', 'NT', 'QLD', 'SA', 'TAS', 'VIC', 'WA']`

---

### Task 2: Pure danger-frame core + local unit test

**Files:** Create `/Users/smar0095/Fires_SWTs/gadi/ffdi_core.py`; Test `/Users/smar0095/Fires_SWTs/gadi/test_ffdi_core.py`

**Interfaces:**
- Produces: `high_danger_flags(state_daily, q=0.90) -> df[date,state,month,ffdi,hot]`; `build_danger_daily(flags, swt, min_states=2) -> df[day,month,assigned_SWT,regime,n_states,fire_day,multi_day]`.

- [ ] **Step 1: Write `ffdi_core.py`**

```python
"""Pure logic: per-state high-danger flags + the daily danger frame (no zarr/Gadi I/O)."""
import pandas as pd

def high_danger_flags(state_daily, q=0.90):
    """state_daily: long df [date, state, ffdi]. A state-day is 'hot' if its FFDI is
    >= that state's q-quantile WITHIN its calendar month (self-normalising by state & season)."""
    d = state_daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.month
    thr = d.groupby(["state", "month"])["ffdi"].transform(lambda x: x.quantile(q))
    d["hot"] = d["ffdi"] >= thr
    return d[["date", "state", "month", "ffdi", "hot"]]

def build_danger_daily(flags, swt, min_states=2):
    """flags: output of high_danger_flags. swt: df with [day, month, assigned_SWT, regime].
    Returns the full daily frame over SWT days with #dangerous-states, fire_day, multi_day."""
    hot = flags[flags["hot"]]
    per = hot.groupby("date")["state"].nunique().rename("n_states")
    d = swt.copy()
    d["day"] = pd.to_datetime(d["day"])
    d = d.merge(per, left_on="day", right_index=True, how="left")
    d["n_states"]  = d["n_states"].fillna(0).astype(int)
    d["fire_day"]  = d["n_states"] >= 1
    d["multi_day"] = d["n_states"] >= min_states
    return d
```

- [ ] **Step 2: Write `test_ffdi_core.py`**

```python
"""Run: /opt/anaconda3/bin/python3 gadi/test_ffdi_core.py"""
import numpy as np, pandas as pd
from ffdi_core import high_danger_flags, build_danger_daily

def _synth():
    dates = pd.date_range("1990-01-01", "2009-12-31")
    rng = np.random.default_rng(0)
    rows = []
    for st in ["NSW", "VIC", "SA"]:
        ffdi = rng.gamma(2, 5, len(dates))
        rows.append(pd.DataFrame({"date": dates, "state": st, "ffdi": ffdi}))
    return pd.concat(rows, ignore_index=True)

def test_flag_rate_is_about_10pct():
    f = high_danger_flags(_synth(), q=0.90)
    # >= monthly 90th pctile -> ~10% of each state's days flagged
    rate = f.groupby("state")["hot"].mean()
    assert (rate.between(0.08, 0.13)).all(), rate.to_dict()

def test_build_danger_daily_counts():
    f = high_danger_flags(_synth(), q=0.90)
    swt = pd.DataFrame({"day": pd.date_range("1990-01-01", "2009-12-31")})
    swt["month"] = swt["day"].dt.month; swt["assigned_SWT"] = "X"; swt["regime"] = "X"
    d = build_danger_daily(f, swt, min_states=2)
    assert len(d) == len(swt)
    assert d["n_states"].max() <= 3 and d["n_states"].min() >= 0
    assert (d["multi_day"] == (d["n_states"] >= 2)).all()

if __name__ == "__main__":
    test_flag_rate_is_about_10pct(); test_build_danger_daily_counts()
    print("OK: ffdi_core tests passed")
```

- [ ] **Step 3: Run the test**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 test_ffdi_core.py`
Expected: `OK: ffdi_core tests passed`

---

### Task 3: Gadi extract script (`gadi/ffdi_extract.py`)

**Files:** Create `/Users/smar0095/Fires_SWTs/gadi/ffdi_extract.py`. Depends (same dir on Gadi): `composite_core.py`, `aus_states.geojson`, the SWT csv.

**Interfaces:**
- Consumes: `composite_core.doy_anomaly_composite`.
- Produces: `ffdi_state_daily.csv` (long: date,state,ffdi); `ffdi_swt_composite.nc` (dims swt,lat,lon: `ffdi_mean,ffdi_anom,ffdi_p`, `n_days(swt)`).

- [ ] **Step 1: Write the script**

```python
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

    da = ds[var].sel(time=slice(a.start, a.end))            # daily FFDI [time,lat,lon]
    LA, LO = da[lat].values, da[lon].values

    # ---- offline state mask: assign each cell centroid to a state (point-in-polygon) ----
    states = gpd.read_file(a.geojson)
    glon, glat = np.meshgrid(LO, LA)
    cells = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in zip(glon.ravel(), glat.ravel())], crs=states.crs)
    joined = gpd.sjoin(cells, states[["state", "geometry"]], how="left", predicate="within")
    smask = joined["state"].values.reshape(glat.shape)       # [lat,lon] of state names / nan
    mask_da = xr.DataArray(smask, coords={lat: LA, lon: LO}, dims=(lat, lon))
    print("cells per state:", {s: int((smask == s).sum()) for s in STATES}, flush=True)

    # ---- Artifact A: per-state daily area-mean FFDI -> long CSV ----
    recs = []
    for s in STATES:
        ser = da.where(mask_da == s).mean(dim=(lat, lon)).compute()
        recs.append(pd.DataFrame({"date": pd.to_datetime(ser["time"].values).date,
                                  "state": s, "ffdi": ser.values}))
    pd.concat(recs, ignore_index=True).to_csv(a.out_csv, index=False)
    print(f"wrote {a.out_csv}", flush=True)

    # ---- Artifact B: per-SWT gridded FFDI anomaly composite (coarsened) ----
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
```

- [ ] **Step 2: Local syntax check** (rt52/zarr only exist on Gadi)

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 -c "import ast; ast.parse(open('ffdi_extract.py').read()); print('syntax OK')"`
Expected: `syntax OK`

---

### Task 4: PBS job + run instructions

**Files:** Create `gadi/ffdi_extract.pbs`, `gadi/README_FFDI.md`

- [ ] **Step 1: Write `ffdi_extract.pbs`**

```bash
#!/bin/bash
#PBS -P gb02
#PBS -q normal
#PBS -l ncpus=4
#PBS -l mem=32GB
#PBS -l walltime=06:00:00
#PBS -l storage=gdata/ia39+gdata/xp65+gdata/gb02
#PBS -l wd
#PBS -N ffdi_extract
#PBS -j oe
module use /g/data/xp65/public/modules
module load conda/analysis3
python3 ffdi_extract.py
```

- [ ] **Step 2: Write `README_FFDI.md`**

````markdown
# Running the FFDI extract on Gadi

## 1. Files in one Gadi dir (e.g. /g/data/gb02/sm5259/ffdi/)
ffdi_extract.py, composite_core.py, ffdi_core.py, aus_states.geojson, SWT_climatology_v20260129.csv, ffdi_extract.pbs

## 2. Dry run first (one year — prints the Zarr schema; cheap)
module use /g/data/xp65/public/modules && module load conda/analysis3
python3 ffdi_extract.py --start 2000-01 --end 2000-12 --out_csv t.csv --out_nc t.nc
# Check the printed schema: confirm the FFDI var name + lat/lon coord names.
# If auto-detection was wrong, re-run with --var <name> --lat <name> --lon <name>.
# Confirm "cells per state" are all > 0 and "aligned days" ~365.

## 3. Full run
qsub ffdi_extract.pbs           # ~tens of SU; 0.05deg daily 1979- is I/O heavy
qstat -u $USER

## 4. Copy results to laptop
rsync -vP sm5259@gadi-dm.nci.org.au:/g/data/gb02/sm5259/ffdi/ffdi_state_daily.csv \
          sm5259@gadi-dm.nci.org.au:/g/data/gb02/sm5259/ffdi/ffdi_swt_composite.nc \
          /Users/smar0095/Fires_SWTs/

## (optional, extremes) repeat with the bias-output zarr:
python3 ffdi_extract.py --zarr /g/data/ia39/ncra/fire/bias-output/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr \
        --out_csv ffdi_state_daily_biascorr.csv --out_nc ffdi_swt_composite_biascorr.nc
````

---

### Task 5: Local synthetic artifacts (build Step 8 before Gadi)

**Files:** Create `gadi/make_synthetic_ffdi.py`

- [ ] **Step 1: Write it** (matches the artifact schemas)

```python
"""Synthetic ffdi_state_daily.csv + ffdi_swt_composite.nc so Step 8 builds without Gadi."""
import numpy as np, pandas as pd
from netCDF4 import Dataset
D = "/Users/smar0095/Fires_SWTs"
dates = pd.date_range("1979-01-01", "2024-12-31")
rng = np.random.default_rng(0)
seas = 1 + 0.6*np.cos(2*np.pi*(dates.dayofyear-15)/365)      # summer-peaked
rows = []
for s in ["NSW","VIC","QLD","SA","WA","TAS","NT"]:
    rows.append(pd.DataFrame({"date": dates.date, "state": s,
                              "ffdi": np.clip(rng.gamma(2,5,len(dates))*seas, 0, None)}))
pd.concat(rows, ignore_index=True).to_csv(f"{D}/ffdi_state_daily.csv", index=False)
# gridded composite (same schema as real)
swt = ["FH-B","WH-A","TH-C","WCT-B","AM-A"]; lat = np.arange(-44,-9,0.25); lon = np.arange(112,154,0.25)
K,Y,X = len(swt),len(lat),len(lon)
nc = Dataset(f"{D}/ffdi_swt_composite.nc","w")
nc.createDimension("swt",K); nc.createDimension("lat",Y); nc.createDimension("lon",X)
v=nc.createVariable("swt",str,("swt",));  [v.__setitem__(i,s) for i,s in enumerate(swt)]
nc.createVariable("lat","f4",("lat",))[:]=lat; nc.createVariable("lon","f4",("lon",))[:]=lon
nc.createVariable("ffdi_mean","f4",("swt","lat","lon"))[:]=5+rng.normal(0,3,(K,Y,X))
nc.createVariable("ffdi_anom","f4",("swt","lat","lon"))[:]=rng.normal(0,2,(K,Y,X))
nc.createVariable("ffdi_p","f4",("swt","lat","lon"))[:]=rng.random((K,Y,X))
nc.createVariable("n_days","i4",("swt",))[:]=rng.integers(400,2000,K)
nc.close(); print("wrote synthetic ffdi_state_daily.csv + ffdi_swt_composite.nc")
```

- [ ] **Step 2: Run it**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 make_synthetic_ffdi.py`
Expected: `wrote synthetic ffdi_state_daily.csv + ffdi_swt_composite.nc`

---

### Task 6: Notebook "Step 8 — FFDI fire danger" cells

**Files:** Modify `/Users/smar0095/Fires_SWTs/Fires_SWTs.ipynb` (append 1 markdown + 3 code cells).

**Interfaces:**
- Consumes: `ffdi_state_daily.csv`, `ffdi_swt_composite.nc`; reuses `gadi/ffdi_core.py` (`high_danger_flags`, `build_danger_daily`) and the notebook's existing `simultaneity_rr(level_col, daily_df=..., fdr=True)` and `pair_permutation(pair_days, M, PAIRS)`.

- [ ] **Step 1: Append markdown** (Step 8 header explaining danger vs fire, the percentile definition, period 1979-).

- [ ] **Step 2: Append build cell** — load CSV, flag high-danger days, build the danger daily frame, run the danger RR:

```python
import sys; sys.path.append(f"{DATA_DIR}/gadi")
from ffdi_core import high_danger_flags, build_danger_daily
ffdi = pd.read_csv(f"{DATA_DIR}/ffdi_state_daily.csv")
flags = high_danger_flags(ffdi, q=0.90)
swt_danger = swt[["day","month","assigned_SWT","regime"]].copy()      # `swt` from Step 2
ddaily = build_danger_daily(flags, swt_danger, min_states=MIN_STATES)
print(f"high-danger days: >=1 state {int((ddaily.n_states>=1).mean()*100)}%, "
      f">=2 states {int(ddaily.multi_day.mean()*100)}%")
swt_danger_rr = simultaneity_rr("assigned_SWT", daily_df=ddaily, fdr=True)
print(swt_danger_rr[["assigned_SWT","n_multi","RR_mean","CI_low","CI_high","sig_fdr"]].round(3).to_string(index=False))
```

- [ ] **Step 3: Append synchronisation cell** — region-pairs on danger (reuse `pair_permutation`):

```python
from itertools import combinations
STATES_D = ["NSW","VIC","QLD","SA","WA","TAS","NT"]
hot = flags[flags.hot].assign(v=1)
burn_d = hot.pivot_table(index="date", columns="state", values="v", fill_value=0).reindex(columns=STATES_D, fill_value=0)
burn_d["n_states"] = burn_d.sum(axis=1)
burn_d = burn_d.reset_index().rename(columns={"date":"day"})
burn_d["day"] = pd.to_datetime(burn_d["day"])
burn_d = burn_d.merge(swt[["day","month","assigned_SWT"]], on="day", how="left")
pair_days_d = burn_d[(burn_d.n_states>=2) & burn_d.assigned_SWT.notna()].copy()
PAIRS_D = list(combinations(STATES_D,2)); S = pair_days_d[STATES_D].to_numpy()
idx = [(STATES_D.index(a),STATES_D.index(b)) for a,b in PAIRS_D]
M_d = np.stack([S[:,i]*S[:,j] for i,j in idx], axis=1).astype(float)
res_d = pair_permutation(pair_days_d, M_d, PAIRS_D)
HEAD = ["FH-B","WH-A","TH-C","WCT-B"]; subd = res_d[res_d.assigned_SWT.isin(HEAD)].copy()
subd["sig_fdr"],_,_,_ = multipletests(np.clip(subd.pval,1e-4,1),0.05,method="fdr_bh")
print("DANGER region-pairs surviving FDR:",
      ", ".join(f"{r.assigned_SWT}:{r.pair}(+{r.excess:.3f})" for r in subd[(subd.excess>0)&subd.sig_fdr].itertuples()) or "none")
```

- [ ] **Step 4: Append composite-map cell** — same netCDF4 + cartopy pattern as Step 6 but reading `ffdi_swt_composite.nc` and plotting `ffdi_anom` (no wind/MSLP layers).

- [ ] **Step 5: Generate synthetic artifacts then execute the notebook**

Run: `cd /Users/smar0095/Fires_SWTs/gadi && /opt/anaconda3/bin/python3 make_synthetic_ffdi.py`
then `cd /Users/smar0095/Fires_SWTs && /opt/anaconda3/bin/jupyter nbconvert --to notebook --execute --inplace Fires_SWTs.ipynb`
Expected: Step 8 prints danger RR + region-pair result and renders the FFDI composite map (synthetic until the real artifacts arrive). Swap to real files by rsyncing them into `DATA_DIR`.

---

## Self-review
- **Spec coverage:** bias-input primary + bias-output extremes ✓(T3,T4 optional cmd); states/ACT→NSW ✓(T1); percentile danger ✓(T2); composite map ✓(T3 nc, T6 cell); propensity RR ✓(T6 s2); synchronisation ✓(T6 s3); Gadi→2 artifacts ✓(T3); offline mask via shipped GeoJSON ✓(T1,T3); reuse composite_core + simultaneity_rr + pair_permutation ✓.
- **Placeholders:** `gb02`/paths are concrete (user's project). The bias-output **extreme-day RR** (severe/extreme/catastrophic counts) is scoped but left as a follow-on cell using the bias-output CSV — noted, not a hidden gap.
- **Type consistency:** `high_danger_flags`/`build_danger_daily` signatures identical T2↔T6; artifact schema (`ffdi_mean/anom/p`, `n_days`, state CSV cols `date,state,ffdi`) consistent T3↔T5↔T6; reused `simultaneity_rr(daily_df=...)` and `pair_permutation(pair_days,M,PAIRS)` match the notebook's current signatures.
