# Flood Component (DLI v0.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily AGCD-rainfall flood subindex (`sub_flood`) to the DLI and validate it against dated historical flood extents.

**Architecture:** Gadi qsub job computes six daily rain-area-fraction components from AGCD 0.05° precip (1979–present) into one small CSV; laptop loads it, integrates into `assemble_components`/`compute_dli`, and re-runs the 12-event benchmark as the adoption gate. Design: `docs/superpowers/specs/2026-07-07-flood-component-design.md`.

**Tech Stack:** xarray+dask on Gadi (`module load conda/analysis3`); pandas locally; pytest.

## Global Constraints

- Python is `/opt/anaconda3/bin/python3`; never pip install. 17 GB RAM locally — all AGCD work happens on Gadi via **qsub only**.
- Gadi files are copied FLAT to `/g/data/gb02/sm5259/EM_Demand/` (no repo clone); scripts must not reference repo-relative subdirectories; qsub from that directory with `#PBS -l wd`.
- Components: `rain1d_area`, `rain3d_area`, `rain7d_area`, `seaus_rain1d`, `seaus_rain3d`, `seaus_rain7d`. Thresholds: per-cell, per-calendar-month 95th percentile of wet accumulations (≥ 1 mm) over **1979–2023**. SEAUS box: `SE_AUS_BBOX` = lon 140–154, lat −39 to −28 (`scripts/config.py:61`).
- `sub_flood` = mean of the six available `*_pct` ranks, added as a fifth equal subindex in `compute_dli`. Availability `"agcd_rain": ("1979-01-01", None)`. Rain columns are **never fillna(0)** — NaN outside the AGCD record.
- **Adoption gate:** re-run `scripts/run_dli.py`; adopt only if the 2022-floods benchmark percentile rises above its current 0.8257 AND the seven fire events currently ≥ 0.95 (Black Saturday, Ash Wednesday, Dandenongs, Canberra, Dunalley, Black Summer, NSW Jan 1994) all stay ≥ 0.93 AND no other event's percentile drops materially (TC Yasi 0.9291 and Blue Mtns 0.8959 are already below 0.93 — that is the current baseline, not a regression). If the gate fails, commit the code with sub_flood integration behind the reported numbers, report honestly, and STOP — never tune the combiner to the benchmarks (CLAUDE.md rule).
- Keep pytest green (42+ tests). Commit + push after each task; trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.

---

### Task 1: Gadi AGCD extraction job

**Files:**
- Create: `gadi/extract_agcd_rain.py`
- Create: `gadi/extract_agcd_rain.pbs`

**Interfaces:**
- Produces: `/g/data/gb02/sm5259/EM_Demand/agcd_rain_daily.csv` with columns `date,rain1d_area,rain3d_area,rain7d_area,seaus_rain1d,seaus_rain3d,seaus_rain7d` (date = AGCD day, fractions in [0,1]).

- [ ] **Step 1: Verify AGCD location and access.** Ask the user to run on Gadi and paste output:

```bash
ls /g/data/zv2/agcd/v1/precip/total/r005/01day/ | head
ncdump -h /g/data/zv2/agcd/v1/precip/total/r005/01day/$(ls /g/data/zv2/agcd/v1/precip/total/r005/01day/ | head -1) | head -30
```

Expected: annual files `agcd_v1_precip_total_r005_daily_YYYY.nc`, variable `precip`, dims `time,lat,lon`. If `zv2` is not readable, the user must join project zv2 on my.nci.org.au (data collection, auto-approved). Adjust `AGCD_DIR`/`VAR` below to whatever the paste shows, and add `gdata/zv2` to the PBS storage flags and to `GADI["storage_flags"]` in `scripts/config.py`.

- [ ] **Step 2: Write `gadi/extract_agcd_rain.py`**

```python
"""Daily flood-proxy components from AGCD precip. Runs on Gadi via qsub.

Outputs agcd_rain_daily.csv next to this file: for each day, the fraction
of land cells whose 1/3/7-day rain accumulation exceeds the cell's
calendar-month 95th wet-day (>=1 mm) percentile (base 1979-2023),
nationally and in the SEAUS box (lon 140-154, lat -39..-28).
"""
from pathlib import Path

import numpy as np
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
    acc = pr if win == 1 else pr.rolling(time=win).sum()
    wet = acc.where(acc >= 1.0)
    thr = wet.sel(time=BASE).groupby("time.month").quantile(0.95, dim="time")
    exceed = acc.groupby("time.month") >= thr
    land = pr.isel(time=0).notnull()
    exceed = exceed.where(land)
    for name, dom in [(f"rain{win}d_area", exceed),
                      (f"seaus_rain{win}d" if win > 1 else "seaus_rain1d",
                       exceed.sel(**SEAUS))]:
        frac = dom.mean(dim=("lat", "lon"), skipna=True)
        print(f"computing {name}...", flush=True)
        frames[name] = frac.compute().to_series()

import pandas as pd
out = pd.DataFrame(frames)
out.index.name = "date"
out = out.rename(columns={"rain3d_area_seaus": "seaus_rain3d"})
out.to_csv(OUT, float_format="%.6f")
print(f"wrote {OUT} ({len(out)} rows)", flush=True)
```

Note for the implementer: the loop above must yield exactly the six Global-Constraints column names — verify the f-string naming produces `seaus_rain3d`/`seaus_rain7d` correctly (restructure the loop rather than post-hoc renaming if clearer). `exceed.where(land)` turns ocean cells NaN so `mean(skipna=True)` is a land fraction.

- [ ] **Step 3: Write `gadi/extract_agcd_rain.pbs`**

```bash
#!/bin/bash
#PBS -P gb02
#PBS -q normalbw
#PBS -l ncpus=14,mem=120GB,walltime=06:00:00,wd
#PBS -l storage=gdata/zv2+gdata/gb02+gdata/xp65
#PBS -N agcd_rain
module use /g/data/xp65/public/modules
module load conda/analysis3
# qsub this from the directory holding extract_agcd_rain.py (files sit flat on Gadi)
python3 extract_agcd_rain.py
```

- [ ] **Step 4: Hand off to the user.** Give them scp commands to upload both files to `/g/data/gb02/sm5259/EM_Demand/` and `qsub extract_agcd_rain.pbs` from that directory. **Do not poll Gadi over ssh — the user runs Gadi commands and pastes output.** While the job runs, continue to Task 2.

- [ ] **Step 5: Commit** `gadi/extract_agcd_rain.py`, `gadi/extract_agcd_rain.pbs` (+ config storage-flag edit if made). Push.

- [ ] **Step 6 (when the user confirms the job finished):** scp `agcd_rain_daily.csv` to `data/raw/agcd/agcd_rain_daily.csv` (create dir; data/raw is gitignored). Sanity-check: ~17,300+ rows from 1979-01-01, all six fractions in [0,1], national columns nonzero most days, 2022-02-28 values in the extreme tail of their columns.

### Task 2: Loader + tests (no Gadi data needed)

**Files:**
- Create: `scripts/loaders/agcd_rain.py`
- Create: `tests/test_agcd_rain.py`

**Interfaces:**
- Produces: `load_agcd_rain(path=None) -> pd.DataFrame` — columns `date` (datetime64) + the six component columns (float); default path `PATHS`-style `DATA_RAW / "agcd" / "agcd_rain_daily.csv"` (follow how other loaders in `scripts/loaders/` resolve paths — mirror their convention exactly).

- [ ] **Step 1: Write failing tests** (construct a small CSV in `tmp_path`; do not require the real file):

```python
import pandas as pd
from scripts.loaders.agcd_rain import load_agcd_rain

CSV = """date,rain1d_area,rain3d_area,rain7d_area,seaus_rain1d,seaus_rain3d,seaus_rain7d
1979-01-01,0.01,0.02,0.03,0.0,0.0,0.0
1979-01-02,0.10,0.12,0.15,0.20,0.25,0.30
"""

def test_load_agcd_rain(tmp_path):
    p = tmp_path / "agcd_rain_daily.csv"
    p.write_text(CSV)
    df = load_agcd_rain(p)
    assert list(df.columns) == ["date", "rain1d_area", "rain3d_area",
        "rain7d_area", "seaus_rain1d", "seaus_rain3d", "seaus_rain7d"]
    assert df["date"].dtype.kind == "M"
    assert df["rain3d_area"].iloc[1] == 0.12

def test_load_agcd_rain_rejects_bad_fraction(tmp_path):
    p = tmp_path / "agcd_rain_daily.csv"
    p.write_text(CSV.replace("0.30", "1.30"))
    import pytest
    with pytest.raises(ValueError):
        load_agcd_rain(p)
```

- [ ] **Step 2: Run to verify FAIL** (`/opt/anaconda3/bin/python3 -m pytest tests/test_agcd_rain.py -q` → import error).
- [ ] **Step 3: Implement the loader** — read CSV, parse `date`, validate the six columns exist and all values are NaN-or-in-[0,1] (raise `ValueError` otherwise), docstring noting AGCD days end 09:00 local (~9 h offset from the project's fixed UTC+10 buckets — accepted, documented).
- [ ] **Step 4: Run tests → PASS; run full suite → green.**
- [ ] **Step 5: Commit + push.**

### Task 3: DLI integration + adoption gate

**Files:**
- Modify: `scripts/config.py` (add `"agcd_rain": ("1979-01-01", None)` to `COMPONENT_AVAILABILITY`, ~line 46)
- Modify: `scripts/dli.py` (`assemble_components` ~line 65, `compute_dli` ~line 113, module docstring)
- Modify: `scripts/run_dli.py` (load + pass the rain panel)
- Test: `tests/test_dli.py` (extend existing)

**Interfaces:**
- Consumes: `load_agcd_rain()` from Task 2; requires the real CSV from Task 1 step 6 before the gate can run.
- Produces: `demand_daily_panel.parquet` gains six `*_pct` columns + `sub_flood`; `dli` now averages five subindices.

- [ ] **Step 1: Failing test** — build a minimal components frame (mirror existing fixtures in `tests/test_dli.py`) including the six rain columns and assert `compute_dli` output has `sub_flood` equal to the mean of the six rank columns and that `dli` includes it.
- [ ] **Step 2: Implement.** `assemble_components(..., rain_panel, ...)` (new required arg after `tc_panel`): `rain = rain_panel.set_index("date"); out[c] = rain[c].reindex(idx)` for the six columns — reindex only, **no fillna** (NaN past the AGCD record end is correct; availability discipline). In `compute_dli`: `rain_cols = [...six...]; subs["sub_flood"] = ranks[rain_cols].mean(axis=1, skipna=True)`. Update both docstrings (the recipe listing at `scripts/dli.py:7-20`).
- [ ] **Step 3: Full suite green.**
- [ ] **Step 4: Run the gate:** `/opt/anaconda3/bin/python3 scripts/run_dli.py`. Record the full benchmark table in the task report. Gate: 2022 floods pct > 0.8257 AND the seven fire events currently ≥ 0.95 all stay ≥ 0.93 AND no other event drops materially (Yasi 0.9291 / Blue Mtns 0.8959 are the current baseline, not gate failures). If it fails: keep the code, report the table verbatim, mark the task DONE_WITH_CONCERNS, and stop — the human decides. Do not iterate on thresholds/combiner.
- [ ] **Step 5: Commit + push** (include the before/after benchmark table in the commit body).

### Task 4: Dated-event validation diagnostic

**Files:**
- Create: `docs/flood_event_days.csv`
- Create: `scripts/run_flood_validation.py`

- [ ] **Step 1: Curate `docs/flood_event_days.csv`** (`name,date,source` — peak-flood dates from the dated-extent jurisdictions, `docs/flood_data_layers.md` has the portals). Seed list (verify each date against the portal/source before committing):

```csv
name,date,source
QLD Brisbane 2011,2011-01-11,QLD Flood Extent Series
QLD Australia Day 2013,2013-01-27,QLD Flood Extent Series
QLD Townsville 2019,2019-02-03,QLD Flood Extent Series
QLD/NSW Feb-Mar 2022,2022-02-28,QLD Flood Extent Series (benchmark day)
VIC October 2022,2022-10-14,VIC VFD Oct 2022 dataset
WA Warmun 2011,2011-03-13,WA DWER-123
WA Fitzroy 2023,2023-01-04,WA DWER-123
```

- [ ] **Step 2: Write `scripts/run_flood_validation.py`** — thin runner modeled on the benchmark loop in `scripts/run_dli.py:47-55`: load `demand_daily_panel.parquet`, and for each event day print `sub_flood`, its within-tier percentile, and the six component `*_pct` values. Diagnostic only — print, no pass/fail.
- [ ] **Step 3: Run it, paste the table into the task report.** Expect most events in the extreme tail; localized events (Warmun) may legitimately sit lower — report, don't tune.
- [ ] **Step 4: Commit + push.**

### Task 5: Documentation

**Files:**
- Modify: `CLAUDE.md` (DLI recipe section: add sub_flood; status section: record gate outcome)
- Modify: `README.md` (pipeline table + flood component note)
- Modify: `scripts/run_exports.py` if it enumerates columns explicitly (check; add the new `*_pct` + `sub_flood`)

- [ ] **Step 1: Update docs; re-run `scripts/run_exports.py`; full suite green; commit + push.**
