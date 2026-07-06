# FFDI Component (DLI v0.2 candidate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily FFDI (Forest Fire Danger Index) hazard subindex to the DLI, sourced from a precomputed zarr on Gadi, with a strict adoption gate against the 12-event benchmark.

**Architecture:** A Gadi PBS job reduces the national daily FFDI zarr (1979–2023) to a small daily CSV of 4 national/SEAUS summary metrics. The user scps that CSV locally; a loader harmonises it; `scripts/dli.py` gains two FFDI components and a `sub_ffdi` subindex — adopted into the DLI **only if** the benchmark table does not degrade.

**Tech Stack:** xarray + zarr on Gadi (xp65 `conda/analysis3` env); pandas locally; pytest.

## Global Constraints

- Local python is `/opt/anaconda3/bin/python3`. Never pip install.
- Gadi: project `gb02`, compute via **qsub only** (never run heavy work on login nodes). Module setup: `module use /g/data/xp65/public/modules && module load conda/analysis3`. Storage flags: `gdata/if69+gdata/su28+gdata/gb02+gdata/xp65+gdata/ia39+gdata/rt52`.
- The FFDI zarr is **precomputed** at `/g/data/ia39/ncra/fire/bias-input/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr` (see `scripts/config.py::GADI["ffdi_zarr"]`). Do NOT compute FFDI from raw met variables.
- BARRA-R2-derived zarrs on Gadi are often time-LAST → `.transpose("time", ...)` before any time operation.
- Availability window is already registered: `COMPONENT_AVAILABILITY["ffdi"] = ("1979-01-01", "2023-12-31")`. Every FFDI value outside that window must be NaN.
- SE Australia bbox is `scripts/config.py::SE_AUS_BBOX` = lon 140–154, lat −39 to −28. Use it, don't hardcode new numbers.
- Keep all 42 existing tests green: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`.
- **DLI recipe guard (from CLAUDE.md):** any change to the combiner must re-run `scripts/run_dli.py` and must NOT push fire benchmarks below the 93rd within-tier percentile. Do not tune to improve the known misses (2022 floods, TAS 2016, Deepwater) — that is overfitting 12 data points.
- Commit after each task; message style: short imperative subject, trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`. Push after each commit.
- Give the user a plain-language progress update after each task (they are not across implementation detail).

---

### Task 1: Gadi extraction script + PBS job

**Files:**
- Create: `gadi/extract_ffdi.py`
- Create: `gadi/extract_ffdi.pbs`

**Interfaces:**
- Produces: `/g/data/gb02/sm5259/EM_Demand/ffdi_daily_summary.csv` with columns `date, ffdi_mean, frac_ge50, frac_ge75, seaus_frac_ge50` (one row per day, 1979–2023).
- No local tests possible (Gadi-only data); validation is by inspecting the PBS log and CSV head/tail.

- [ ] **Step 1: Write the extraction script**

```python
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
```

- [ ] **Step 2: Write the PBS script**

```bash
#!/bin/bash
#PBS -P gb02
#PBS -q normal
#PBS -l ncpus=4
#PBS -l mem=32GB
#PBS -l walltime=02:00:00
#PBS -l storage=gdata/if69+gdata/su28+gdata/gb02+gdata/xp65+gdata/ia39+gdata/rt52
#PBS -l wd
#PBS -N ffdi_extract
#PBS -j oe

module use /g/data/xp65/public/modules
module load conda/analysis3

python3 gadi/extract_ffdi.py
```

- [ ] **Step 3: Commit locally**

```bash
git add gadi/extract_ffdi.py gadi/extract_ffdi.pbs
git commit -m "Add Gadi FFDI zarr extraction job"
git push
```

- [ ] **Step 4: USER ACTION — run on Gadi.** Ask the user (plain language) to:

```bash
# on Gadi, from the repo clone
qsub gadi/extract_ffdi.pbs
# when the job finishes, check the log (ffdi_extract.o*) then confirm:
head -3 /g/data/gb02/sm5259/EM_Demand/ffdi_daily_summary.csv
```

Expected first data row date is 1979-01-01 (or the zarr's actual start); last row late 2023. If the job dies on memory, resubmit with `mem=64GB`. If the variable/dim auto-detection picks wrong names, the printed `var=... dims=...` line in the log shows what's there — adjust the `next(...)` detection lines and resubmit.

---

### Task 2: Bring the CSV local + register the path

**Files:**
- Modify: `scripts/config.py` (Paths dataclass)

**Interfaces:**
- Produces: `PATHS.ffdi_daily` → `data/raw/ffdi/ffdi_daily_summary.csv`.

- [ ] **Step 1: USER ACTION — copy the CSV down**

```bash
mkdir -p data/raw/ffdi
scp gadi:/g/data/gb02/sm5259/EM_Demand/ffdi_daily_summary.csv data/raw/ffdi/
```

(Replace `gadi:` with the user's actual ssh alias for gadi.nci.org.au if different.)

- [ ] **Step 2: Add the path to the Paths dataclass** in `scripts/config.py` (inside `class Paths`, after `bom_tc_dir`):

```python
    ffdi_daily: Path = DATA_RAW / "ffdi" / "ffdi_daily_summary.csv"
```

- [ ] **Step 3: Verify it resolves**

Run: `/opt/anaconda3/bin/python3 -c "from scripts.config import PATHS; print(PATHS.ffdi_daily.exists())"`
Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add scripts/config.py
git commit -m "Register local FFDI daily summary path"
git push
```

---

### Task 3: FFDI loader

**Files:**
- Create: `scripts/loaders/ffdi.py`
- Test: `tests/test_ffdi_loader.py`

**Interfaces:**
- Produces: `load_ffdi(path=None) -> pd.DataFrame` with columns `date` (datetime64, normalized), `ffdi_mean`, `frac_ge50`, `frac_ge75`, `seaus_frac_ge50` (floats), sorted by date, deduplicated.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.loaders.ffdi import load_ffdi


def test_load_ffdi(tmp_path):
    p = tmp_path / "ffdi_daily_summary.csv"
    p.write_text(
        "date,ffdi_mean,frac_ge50,frac_ge75,seaus_frac_ge50\n"
        "1979-01-02,5.1,0.01,0.0,0.0\n"
        "1979-01-01,4.0,0.0,0.0,0.0\n"
        "1979-01-01,4.0,0.0,0.0,0.0\n"
    )
    out = load_ffdi(p)
    assert list(out.columns) == [
        "date", "ffdi_mean", "frac_ge50", "frac_ge75", "seaus_frac_ge50"
    ]
    assert len(out) == 2  # deduped
    assert out["date"].iloc[0] == pd.Timestamp("1979-01-01")  # sorted
    assert out["ffdi_mean"].dtype == float
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_ffdi_loader.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.loaders.ffdi'`

- [ ] **Step 3: Write the loader**

```python
"""Loader for the Gadi-extracted daily FFDI summary CSV.

Produced by gadi/extract_ffdi.py (see that file for column semantics).
Availability: COMPONENT_AVAILABILITY["ffdi"] = 1979-01-01 .. 2023-12-31.
"""

import pandas as pd

from scripts.config import PATHS

_COLS = ["date", "ffdi_mean", "frac_ge50", "frac_ge75", "seaus_frac_ge50"]


def load_ffdi(path=None) -> pd.DataFrame:
    df = pd.read_csv(path or PATHS.ffdi_daily)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df[_COLS].astype({c: float for c in _COLS[1:]})
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
```

- [ ] **Step 4: Run tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`
Expected: all pass (43).

- [ ] **Step 5: Commit**

```bash
git add scripts/loaders/ffdi.py tests/test_ffdi_loader.py
git commit -m "Add FFDI daily summary loader"
git push
```

---

### Task 4: Wire FFDI into the DLI — with adoption gate

**Files:**
- Modify: `scripts/dli.py` (`assemble_components` signature + `compute_dli`)
- Modify: `scripts/run_dli.py` (pass the FFDI frame)
- Test: `tests/test_dli.py` (extend existing fixtures)

**Interfaces:**
- Consumes: `load_ffdi()` from Task 3.
- Produces: `assemble_components(..., ffdi_panel=None)` adding components `ffdi_severe` (= `frac_ge50`) and `seaus_ffdi` (= `seaus_frac_ge50`), masked by availability key `"ffdi"`; `compute_dli` gains `sub_ffdi = max(ffdi_severe_pct, seaus_ffdi_pct)` **only if the gate passes** (see Step 6).

Rationale for the two components: `frac_ge50` is a national severe-danger footprint (continuous, no rank-tie saturation) and `seaus_frac_ge50` counters savanna swamping the same way the SEAUS hotspot components do. FFDI notably strengthens Tier 3 (1979–1999), which currently has only 4 non-fire-hotspot components.

- [ ] **Step 1: Extend the failing test.** In `tests/test_dli.py`, add to the existing fixture set:

```python
def _ffdi():
    dates = pd.date_range("1979-01-01", "2015-12-31", freq="D")
    return pd.DataFrame({
        "date": dates,
        "ffdi_mean": 5.0,
        "frac_ge50": [0.2 if d.year == 1983 else 0.0 for d in dates],
        "frac_ge75": 0.0,
        "seaus_frac_ge50": [0.3 if d.year == 1983 else 0.0 for d in dates],
    })


def test_ffdi_component_masked_and_subindexed():
    comps = assemble_components(_dm(), _bw(), _drfa(), _tfb(), _tc(), ffdi_panel=_ffdi(),
                                start="1979-01-01", end="2015-12-31")
    assert comps.loc["1983-02-16", "ffdi_severe"] == 0.2
    assert comps.loc["1983-02-16", "seaus_ffdi"] == 0.3
    out = compute_dli(comps).set_index("date")
    row = out.loc["1983-02-16"]
    assert row["sub_ffdi"] == max(row["ffdi_severe_pct"], row["seaus_ffdi_pct"])


def test_ffdi_absent_when_not_passed():
    comps = assemble_components(_dm(), _bw(), _drfa(), _tfb(), _tc(),
                                start="1979-01-01", end="2015-12-31")
    assert "ffdi_severe" not in comps.columns
```

(Use the fixture helpers already defined in `tests/test_dli.py` — `_dm()`, `_bw()`, `_drfa()`, `_tfb()`, `_tc()`. If theirs end before 2015-12-31, keep the existing end date the file uses and adjust the FFDI fixture dates to match; also update the existing `n_components_available` assertions: +2 on dates within 1979–2023 when ffdi is passed — only in the new test, existing tests call without `ffdi_panel` and must stay untouched.)

- [ ] **Step 2: Run to verify failure**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_dli.py -q`
Expected: FAIL with `TypeError: assemble_components() got an unexpected keyword argument 'ffdi_panel'`

- [ ] **Step 3: Implement.** In `scripts/dli.py::assemble_components`, add keyword param `ffdi_panel=None` and, just before `return out`:

```python
    if ffdi_panel is not None:
        out["ffdi_severe"] = _masked(ffdi_panel, "frac_ge50", idx, "ffdi")
        out["seaus_ffdi"] = _masked(ffdi_panel, "seaus_frac_ge50", idx, "ffdi")
```

In `compute_dli`, after building `subs`:

```python
    if "ffdi_severe" in ranks.columns:
        subs["sub_ffdi"] = ranks[["ffdi_severe", "seaus_ffdi"]].max(axis=1, skipna=True)
```

(Placed before `out[subs.columns] = subs` and the `dli = subs.mean(...)` line so it participates in the mean.)

- [ ] **Step 4: Run all tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Update the runner.** In `scripts/run_dli.py`, import `from scripts.loaders.ffdi import load_ffdi` and pass `ffdi_panel=load_ffdi() if PATHS.ffdi_daily.exists() else None` into `assemble_components`. Keep the runner working when the CSV is absent.

- [ ] **Step 6: ADOPTION GATE — re-run the benchmark**

Run: `/opt/anaconda3/bin/python3 scripts/run_dli.py`

Compare the printed 12-event benchmark table against the v0.1 baseline (recorded in CLAUDE.md: 9/12 ≥ 93rd pct; Black Saturday 99.9, Ash Wednesday 99.7, Canberra 99.6, Dandenongs 99.6, Dunalley 98.7, Black Summer 97.8, NSW 1994 95.3, Yasi 92.9, Blue Mtns 89.6; floods 82.6, TAS 60.7, Deepwater 69.8).

**Adopt `sub_ffdi` into the DLI only if:** no fire benchmark that was ≥ 93rd drops below 93rd, and no benchmark drops by more than ~3 percentile points. Improvement of the Tier-3 events (Ash Wednesday) is the hoped-for gain.

**If the gate fails:** keep the `ffdi_severe`/`seaus_ffdi` components and their `_pct` columns in the panel (they're useful data), but remove the `subs["sub_ffdi"] = ...` lines from `compute_dli` so the DLI itself is unchanged, and record the gate result in CLAUDE.md. Do NOT iterate on FFDI thresholds/weights to force a pass — that is overfitting.

- [ ] **Step 7: Update docs + commit**

Update CLAUDE.md "Current status" (FFDI adopted or panel-only, with the new benchmark numbers) and the DLI recipe section if adopted. Then:

```bash
git add scripts/dli.py scripts/run_dli.py tests/test_dli.py CLAUDE.md
git commit -m "Add FFDI components and sub_ffdi with benchmark gate"
git push
```

- [ ] **Step 8: Re-run exports and the notebook** so downstream artifacts include the new columns:

Run: `/opt/anaconda3/bin/python3 scripts/run_exports.py`
Then re-execute `EM_Demand_Phase1.ipynb` via nbclient (NOT `jupyter nbconvert --execute` — it silently no-ops in this environment):

```bash
/opt/anaconda3/bin/python3 -c "
import nbformat, nbclient
nb = nbformat.read('EM_Demand_Phase1.ipynb', as_version=4)
nbclient.NotebookClient(nb, timeout=240).execute()
nbformat.write(nb, 'EM_Demand_Phase1.ipynb')
print('notebook OK')"
```

Commit the notebook if it changed. Report the benchmark comparison to the user in plain language.
