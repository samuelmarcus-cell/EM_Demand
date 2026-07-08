# Demand Composites Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether fire-, TC- and flood-driven high-demand days arise from
distinct large-scale atmospheric configurations, via classification-free ERA5
composite anomaly maps stratified by dominant hazard subindex.

**Architecture:** A pure, unit-tested stratum-assignment function
(`scripts/composite_strata.py`) + thin runner writes
`demand_stratum_days.csv`; a Gadi script (light adaptation of the audited
`fires_swts/gadi/era5_swt_composites.py`, reusing
`fires_swts/gadi/composite_core.py::doy_anomaly_composite` verbatim) computes
per-stratum composites of 5 ERA5 fields; an R script renders three figures.

**Tech Stack:** pandas/numpy + pytest locally; xarray + ERA5 rt52 on Gadi via
qsub; R (rfigs conda env: tidyverse, ncdf4, rnaturalearth).

**Spec:** `docs/superpowers/specs/2026-07-07-demand-composites-pilot-design.md`
— read it before starting; it is the scientific contract.

## Global Constraints

- Python is `/opt/anaconda3/bin/python3`; never `pip install`.
- Tests: `/opt/anaconda3/bin/python3 -m pytest tests/ -q` must stay green.
- Commit after each task; short imperative subject; trailer
  `Co-Authored-By: Claude <model> <noreply@anthropic.com>`; push after commit.
- The DLI recipe is FROZEN — nothing in this plan touches `scripts/dli.py`.
- Day selection: within-tier DLI ≥ 95th percentile via the existing
  `scripts/phase2_attribution/swt_attribution.py::flag_high_demand` (reuse,
  do not reimplement) — identical selection to the SWT attribution.
- Strata = argmax of subindices, **no tuned thresholds anywhere**; `sub_tfb`
  folds into the fire stratum; `sub_drfa` → stratum `drfa-led` (descriptive
  only, not a hazard); `sub_flood` used only if the column exists in the panel.
- Strata with n < 30 are reported but NOT composited.
- ERA5: rt52, daily 12 UTC, lon 80–180, lat −60 to −5, 4× coarsened —
  identical to the audited Fires_SWTs composites. Fields: msl (single),
  t850/u850/v850 (850 hPa), tcwv (single). NO z500.
- Anomalies: day-of-year climatology via
  `fires_swts/gadi/composite_core.py::doy_anomaly_composite` — reused
  verbatim, NOT modified. The climatology must be built from ALL days in the
  period, not just the labelled days (see Task 3 — this is the one behavioural
  difference from the SWT script and the easiest thing to get wrong).
- Gadi: never ssh/poll — the user runs qsub and pastes output. **Dry run
  (2 years) before the full job** (standing CLAUDE.md rule).
- Gadi scripts must be self-contained in one flat directory (no repo on Gadi):
  the Gadi-side files are `demand_composites.py`, `composite_core.py`,
  `read_era5.py`, `demand_stratum_days.csv`, `demand_composites.pbs`.
- R only via `/opt/anaconda3/envs/rfigs/bin/Rscript`; house style =
  `R/ffdi_maps.R` (ncdf4 reads xarray dims REVERSED: xarray
  (stratum, lat, lon) → ncdf4 `[lon, lat, stratum]`).

## Interfaces summary (all tasks)

- `assign_strata(panel: pd.DataFrame, threshold_pct: float = 0.95) -> pd.DataFrame`
  with columns `date` (datetime64), `stratum` (str), `margin` (float, NaN when
  fewer than two strata have a score). In `scripts/composite_strata.py`.
- `strata_to_composite(days: pd.DataFrame, min_days: int = 30) -> list[str]`
  sorted stratum names with ≥ min_days rows. In `gadi/demand_composites.py`.
- `data/derived/demand_stratum_days.csv`: header `date,stratum`, dates
  `YYYY-MM-DD`.
- `demand_composites.nc`: dims `(stratum, lat, lon)`; per field `{f}_mean`,
  `{f}_anom`, `{f}_p`; plus `n_days(stratum)`. Delivered by the user to
  `data/raw/composites/demand_composites.nc` (gitignored).

---

### Task 1: Stratum assignment (`assign_strata`)

**Files:**
- Create: `scripts/composite_strata.py`
- Create: `tests/test_composite_strata.py`

**Interfaces:**
- Consumes: `demand_daily_panel.parquet` columns `date, dli, confidence_tier,
  sub_fire, sub_tc, sub_drfa, sub_tfb` (+ `sub_flood` once the flood gate
  passes — must work with the column absent);
  `scripts.phase2_attribution.swt_attribution.flag_high_demand(panel, threshold_pct)`.
- Produces: `assign_strata` and `STRATUM_OF` as defined in the interfaces
  summary; Task 2's runner imports both.

Design decision (record in the docstring): the top-two **margin** is computed
between per-*stratum* scores, where the fire score = max(sub_fire, sub_tfb).
A sub_fire/sub_tfb near-tie is not a hazard ambiguity — both are fire — so
margins are only meaningful after folding. Ties across strata resolve to the
first column in `STRATUM_OF` order (deterministic; nanargmax takes the first
maximum).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_composite_strata.py
import numpy as np
import pandas as pd
import pytest

from scripts.composite_strata import STRATUM_OF, assign_strata


def make_panel(n=100):
    """Synthetic single-tier panel: dli ramps 0->1 so the top-5% days are rows 95-99."""
    return pd.DataFrame(
        {
            "date": pd.date_range("2015-01-01", periods=n),
            "dli": np.linspace(0, 1, n),
            "confidence_tier": 1,
            "sub_fire": 0.1,
            "sub_tfb": 0.1,
            "sub_tc": 0.1,
            "sub_drfa": 0.1,
        }
    )


def test_only_high_demand_days_selected():
    out = assign_strata(make_panel())
    assert len(out) == 5  # rows 95-99 of the 0..1 ramp
    assert out["date"].min() == pd.Timestamp("2015-04-06")


def test_argmax_assigns_dominant_hazard():
    df = make_panel()
    df.loc[99, "sub_tc"] = 0.9
    df.loc[98, "sub_fire"] = 0.9
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "tc"    # row 99
    assert s[pd.Timestamp("2015-04-09")] == "fire"  # row 98


def test_tfb_folds_into_fire_and_margin_uses_stratum_scores():
    df = make_panel()
    df.loc[99, ["sub_tfb", "sub_fire", "sub_tc"]] = [0.95, 0.5, 0.6]
    out = assign_strata(df).set_index("date")
    row = out.loc[pd.Timestamp("2015-04-10")]
    assert row["stratum"] == "fire"
    # fire score = max(0.5, 0.95); runner-up stratum is tc (0.6), NOT sub_fire
    assert row["margin"] == pytest.approx(0.95 - 0.6)


def test_flood_column_absent_is_fine():
    out = assign_strata(make_panel())  # no sub_flood column
    assert set(out["stratum"]) <= {"fire", "tc", "drfa-led"}


def test_flood_column_used_when_present():
    df = make_panel()
    df["sub_flood"] = 0.1
    df.loc[99, "sub_flood"] = 0.99
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "flood"


def test_all_nan_subindices_day_is_excluded():
    df = make_panel()
    df.loc[99, ["sub_fire", "sub_tfb", "sub_tc", "sub_drfa"]] = np.nan
    out = assign_strata(df)
    assert pd.Timestamp("2015-04-10") not in set(out["date"])
    assert len(out) == 4


def test_partial_nan_ignored():
    df = make_panel()
    df.loc[99, "sub_tc"] = np.nan
    df.loc[99, "sub_drfa"] = 0.8
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "drfa-led"


def test_margin_nan_when_single_stratum_scored():
    df = make_panel()
    df.loc[99, ["sub_tfb", "sub_tc", "sub_drfa"]] = np.nan
    out = assign_strata(df).set_index("date")
    assert np.isnan(out.loc[pd.Timestamp("2015-04-10"), "margin"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_composite_strata.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.composite_strata'`

- [ ] **Step 3: Implement**

```python
# scripts/composite_strata.py
"""Assign each high-demand day to its dominant-hazard stratum (pilot composites).

Selection: within-tier DLI >= 95th percentile (same flag_high_demand as the
Phase 2 SWT attribution, so the two analyses use identical day populations).
Stratum: argmax of the hazard subindices — no tuned threshold. sub_tfb folds
into fire (a total fire ban is a fire-danger decision). sub_drfa maps to
'drfa-led', which is a funding activation, not a hazard: composited
descriptively, excluded from the hypothesis test (see spec §2).

Margin: difference between the top two per-STRATUM scores, where the fire
score = max(sub_fire, sub_tfb). Folding first means a sub_fire/sub_tfb
near-tie (both fire) is not reported as hazard ambiguity. Ties across strata
resolve to the first stratum in STRATUM_OF order (nanargmax is deterministic).
"""
import numpy as np
import pandas as pd

from scripts.phase2_attribution.swt_attribution import flag_high_demand

STRATUM_OF = {
    "sub_fire": "fire",
    "sub_tfb": "fire",
    "sub_tc": "tc",
    "sub_flood": "flood",
    "sub_drfa": "drfa-led",
}


def assign_strata(panel, threshold_pct=0.95):
    """Return DataFrame(date, stratum, margin) for within-tier high-DLI days.

    Days whose subindices are all NaN are excluded (no basis for assignment).
    margin is NaN when fewer than two strata have a score that day.
    """
    d = panel.dropna(subset=["dli"]).copy()
    high = d[flag_high_demand(d, threshold_pct)]

    scores = {}
    for col, stratum in STRATUM_OF.items():
        if col not in high.columns:
            continue
        v = high[col].to_numpy(float)
        scores[stratum] = np.fmax(scores[stratum], v) if stratum in scores else v
    sc = pd.DataFrame(scores, index=high.index)

    valid = sc.notna().any(axis=1)
    high, sc = high[valid], sc[valid]

    arr = sc.to_numpy(float)
    stratum = sc.columns.to_numpy()[np.nanargmax(arr, axis=1)]
    ranked = np.sort(np.where(np.isnan(arr), -np.inf, arr), axis=1)
    top2 = ranked[:, -2]
    margin = np.where(np.isfinite(top2), ranked[:, -1] - top2, np.nan)

    return pd.DataFrame(
        {"date": high["date"].to_numpy(), "stratum": stratum, "margin": margin}
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_composite_strata.py -q`
Expected: 8 passed.
Then the full suite: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`
Expected: all pass (42 pre-existing + 8 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/composite_strata.py tests/test_composite_strata.py
git commit -m "Add argmax stratum assignment for composite pilot" && git push
```

---

### Task 2: Runner — write `demand_stratum_days.csv` + margin report

**Files:**
- Create: `scripts/run_composite_strata.py`

**Interfaces:**
- Consumes: `assign_strata` from Task 1; `scripts.config.DATA_DERIVED`;
  `data/derived/demand_daily_panel.parquet`.
- Produces: `data/derived/demand_stratum_days.csv` (`date,stratum`, dates
  `YYYY-MM-DD`) — the label file Task 3's Gadi script reads.

Runners in this repo are thin: no logic beyond load → call → save → print
(see `scripts/run_phase2_swt.py` for the pattern, including the
`sys.path.insert` header). Near-ties are reported without any cutoff: print
the margin distribution quantiles plus the 20 smallest-margin days — the spec
explicitly refuses an arbitrary "near-tie" threshold.

- [ ] **Step 1: Write the runner**

```python
# scripts/run_composite_strata.py
"""Write the stratum-label file for the Gadi composite job, and print the
stratum counts + top-two-margin evidence the compounding panel will need.

Output: data/derived/demand_stratum_days.csv (date,stratum)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.composite_strata import assign_strata
from scripts.config import DATA_DERIVED

panel = pd.read_parquet(DATA_DERIVED / "demand_daily_panel.parquet")
days = assign_strata(panel)

out = DATA_DERIVED / "demand_stratum_days.csv"
days[["date", "stratum"]].to_csv(out, index=False, date_format="%Y-%m-%d")
print(f"wrote {out} ({len(days)} high-demand days)", flush=True)

counts = days["stratum"].value_counts()
print("\nStratum counts (n < 30 reported but NOT composited):", flush=True)
for s, n in counts.items():
    note = "" if n >= 30 else "   [n<30 — not composited]"
    print(f"  {s:>9}: {n}{note}", flush=True)

print("\nTop-two margin distribution (per-stratum scores):", flush=True)
q = days["margin"].quantile([0.05, 0.25, 0.5, 0.75, 0.95])
print(q.round(3).to_string(), flush=True)

print("\n20 smallest margins (near-ties — evidence for the future "
      "compound-day definition):", flush=True)
near = days.nsmallest(20, "margin")[["date", "stratum", "margin"]]
print(near.assign(margin=near["margin"].round(4)).to_string(index=False),
      flush=True)
```

- [ ] **Step 2: Run it**

Run: `/opt/anaconda3/bin/python3 scripts/run_composite_strata.py`
Expected: writes `data/derived/demand_stratum_days.csv`; prints ~820 days
total; strata among {fire, tc, drfa-led} (no flood yet — the current panel
has no `sub_flood` column until the AGCD gate closes); a margin quantile
table and a 20-row near-tie table. Sanity: no stratum count of 0 rows printed
as negative/NaN; dates span 1979–2023.

- [ ] **Step 3: Spot-check the CSV**

Run: `head -3 data/derived/demand_stratum_days.csv`
Expected: `date,stratum` header then `YYYY-MM-DD,<stratum>` rows.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_composite_strata.py
git commit -m "Add stratum-label runner for composite pilot" && git push
```

(The CSV itself is in gitignored `data/derived/` — do not force-add it.)

---

### Task 3: Gadi composite script + PBS

**Files:**
- Create: `gadi/demand_composites.py`
- Create: `gadi/demand_composites.pbs`
- Test: `tests/test_composite_strata.py` (append one test)

**Interfaces:**
- Consumes: `demand_stratum_days.csv` (Task 2);
  `composite_core.doy_anomaly_composite(field, dates, labels, names)` and
  `read_era5.read_data(vname, start, end, utc, lat_lims, lon_lims, path,
  Ncoarsen=, level=, progress=)` — both copied unmodified to the Gadi
  directory alongside this script (they live in `fires_swts/gadi/`).
- Produces: `demand_composites.nc` per the interfaces summary; the user
  copies it to `data/raw/composites/` for Task 4.

**The one behavioural difference from `era5_swt_composites.py`, and why it
matters:** the SWT script drops unlabelled days before compositing
(`good = swt != "nan"`), which is harmless there because every day has an SWT
label — the day-of-year climatology inside `doy_anomaly_composite` still sees
the full record. Here only ~820 of ~16,000 days are labelled. Dropping
unlabelled days would build the "climatology" from high-demand days only and
destroy the anomalies. **Do not filter: pass the full field with unlabelled
days carrying the string "nan"**, which is simply not in the strata name list,
so it forms no composite but still feeds the climatology.

- [ ] **Step 1: Write the failing test for the min-days filter**

Append to `tests/test_composite_strata.py`:

```python
def test_strata_to_composite_min_days():
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "gadi" / "demand_composites.py"
    spec = importlib.util.spec_from_file_location("demand_composites", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    days = pd.DataFrame(
        {
            "date": pd.date_range("2015-01-01", periods=40),
            "stratum": ["fire"] * 30 + ["tc"] * 10,
        }
    )
    assert mod.strata_to_composite(days) == ["fire"]
    assert mod.strata_to_composite(days, min_days=10) == ["fire", "tc"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_composite_strata.py::test_strata_to_composite_min_days -q`
Expected: FAIL — file not found / no attribute `strata_to_composite`.

- [ ] **Step 3: Write the Gadi script**

Note the module must import cleanly OFF Gadi (the test above exec's it), so
`read_era5` is imported inside `main()` exactly as in the SWT script.

```python
# gadi/demand_composites.py
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

from composite_core import doy_anomaly_composite

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
```

- [ ] **Step 4: Write the PBS file**

Same resources as the proven `era5_swt_composites.pbs` (that job composited
5 fields over the full period in 9 GB):

```bash
# gadi/demand_composites.pbs
#!/bin/bash
#PBS -P gb02
#PBS -q normal
#PBS -l ncpus=2
#PBS -l mem=9GB
#PBS -l walltime=08:00:00
#PBS -l storage=gdata/rt52+gdata/xp65+gdata/gb02
#PBS -l wd
#PBS -N demand_comp
#PBS -j oe
module use /g/data/xp65/public/modules
module load conda/analysis3
python3 demand_composites.py
```

- [ ] **Step 5: Run the tests**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_composite_strata.py -q`
Expected: 9 passed. Then the full suite: all green.

- [ ] **Step 6: Commit**

```bash
git add gadi/demand_composites.py gadi/demand_composites.pbs tests/test_composite_strata.py
git commit -m "Add Gadi per-stratum ERA5 composite job" && git push
```

- [ ] **Step 7: STOP — hand the Gadi steps to the user**

This is a human checkpoint; the executor cannot run Gadi jobs. Tell the user
(plain language) to:

1. Copy to their flat Gadi work dir (e.g. via `scp` from local repo root):
   `gadi/demand_composites.py`, `gadi/demand_composites.pbs`,
   `fires_swts/gadi/composite_core.py`, `fires_swts/gadi/read_era5.py`,
   `data/derived/demand_stratum_days.csv`.
2. Dry run FIRST (standing rule), from the directory holding the files:
   `qsub -- /bin/bash -c "cd \$PBS_O_WORKDIR && module use /g/data/xp65/public/modules && module load conda/analysis3 && python3 demand_composites.py --start 1990-01 --end 1991-12 --out test.nc"`
   — or simpler, an interactive-free one-liner mirroring past sessions; the
   key is `--start 1990-01 --end 1991-12 --out test.nc` (~1 SU).
3. Paste the dry-run log. Expected: stratum counts, five `=== field ===`
   blocks each reporting `days in period: ~730`, and `wrote test.nc`.
4. If clean: `qsub demand_composites.pbs` (full 1979–2023, ~5–15 SU), paste
   the tail of the log when done.
5. Copy `demand_composites.nc` back to the local repo at
   `data/raw/composites/demand_composites.nc` (create the directory).

Do not proceed to validate Task 4's figures until the file has arrived —
but Task 4 (writing the R script) can be implemented meanwhile.

---

### Task 4: R figures

**Files:**
- Create: `R/demand_composites.R`

**Interfaces:**
- Consumes: `data/raw/composites/demand_composites.nc` (dims reversed by
  ncdf4 to `[lon, lat, stratum]`; variables `msl_mean, msl_anom, msl_p,
  t850_*, u850_*, v850_*, tcwv_*, n_days`; coord `stratum` is a character
  vector).
- Produces: `R/figs/fig_composite_msl.png`, `R/figs/fig_composite_t850_wind.png`,
  `R/figs/fig_composite_tcwv.png`.

Spec requirements: one figure per field family; panels = strata, each titled
`<stratum> (n = <n_days>)`; MSL figure = anomaly fill + mean contours; t850
figure = temperature anomaly fill + wind anomaly vectors; tcwv = anomaly
fill. p < 0.05 stippling on all anomaly fills, with the two caveats **in the
figure captions** (no multiplicity correction — stippling is descriptive;
serial dependence makes it anti-conservative). House style: `R/ffdi_maps.R`
(tidyverse, ncdf4, rnaturalearth coastline, theme_minimal, ggsave to
`R/figs/`).

- [ ] **Step 1: Write the script**

```r
# R/demand_composites.R
# Composite anomaly maps of high-demand days by dominant-hazard stratum.
# Run: /opt/anaconda3/envs/rfigs/bin/Rscript R/demand_composites.R
#
# ncdf4 reverses xarray dim order: xarray (stratum, lat, lon) -> ncdf4
# [lon, lat, stratum].

library(tidyverse)
library(ncdf4)
library(rnaturalearth)

nc_path <- "data/raw/composites/demand_composites.nc"
if (!file.exists(nc_path)) {
  stop("Missing ", nc_path,
       " - run the Gadi job (gadi/demand_composites.pbs) and copy the output here.")
}

nc      <- nc_open(nc_path)
lat     <- ncvar_get(nc, "lat")
lon     <- ncvar_get(nc, "lon")
strata  <- as.character(ncvar_get(nc, "stratum"))
n_days  <- ncvar_get(nc, "n_days")
get3d   <- function(v) ncvar_get(nc, v)  # [lon, lat, stratum]

panel_lab <- setNames(paste0(strata, " (n = ", n_days, ")"), strata)

grid <- expand_grid(stratum = factor(strata, levels = strata),
                    lat = lat, lon = lon)
# as.vector([lon,lat,stratum]): lon varies fastest, then lat, then stratum.
# expand_grid(stratum, lat, lon): lon fastest, then lat, then stratum. Match.

frame_of <- function(prefix) {
  grid |>
    mutate(anom = as.vector(get3d(paste0(prefix, "_anom"))),
           mean = as.vector(get3d(paste0(prefix, "_mean"))),
           p    = as.vector(get3d(paste0(prefix, "_p"))),
           panel = factor(panel_lab[as.character(stratum)],
                          levels = panel_lab))
}

aus <- ne_countries(country = "Australia", scale = "medium", returnclass = "sf")

caption_txt <- paste(
  "Stippling: pointwise p < 0.05 (composite t-test). Descriptive only:",
  "no field-wise multiplicity correction, and serial dependence within",
  "events makes it anti-conservative.")

# Stipple layer: every 3rd grid point with p < 0.05
stipple <- function(df) {
  df |>
    filter(p < 0.05,
           lon %in% lon[seq(1, length(lon), 3)],
           lat %in% lat[seq(1, length(lat), 3)])
}

base_theme <- theme_minimal(base_size = 9) +
  theme(panel.grid = element_blank(),
        plot.caption = element_text(size = 6.5, hjust = 0))

dir.create("R/figs", showWarnings = FALSE, recursive = TRUE)

# -- MSL: anomaly fill (hPa) + mean contours ---------------------------------
msl <- frame_of("msl") |> mutate(anom = anom / 100, mean = mean / 100)
p1 <- ggplot(msl) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_contour(aes(lon, lat, z = mean), colour = "grey25",
               linewidth = 0.2, bins = 12) +
  geom_point(data = stipple(msl), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "RdBu", name = "MSLP anom (hPa)",
                       limits = c(-1, 1) * max(abs(msl$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "MSLP composite anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_msl.png", p1, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_msl.png\n")

# -- T850 anomaly fill + 850 hPa wind anomaly vectors ------------------------
t850 <- frame_of("t850")
u    <- as.vector(get3d("u850_anom"))
v    <- as.vector(get3d("v850_anom"))
t850$u <- u; t850$v <- v
vec <- t850 |>
  filter(lon %in% lon[seq(1, length(lon), 4)],
         lat %in% lat[seq(1, length(lat), 4)])
sc <- 1.5  # degrees per (m/s) vector scaling
p2 <- ggplot(t850) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_point(data = stipple(t850), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_segment(data = vec,
               aes(lon, lat, xend = lon + sc * u, yend = lat + sc * v),
               arrow = arrow(length = unit(0.03, "cm")),
               linewidth = 0.15, colour = "grey15") +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "RdBu", name = "T850 anom (K)",
                       limits = c(-1, 1) * max(abs(t850$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "850 hPa temperature + wind anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_t850_wind.png", p2, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_t850_wind.png\n")

# -- TCWV anomaly fill --------------------------------------------------------
tcwv <- frame_of("tcwv")
p3 <- ggplot(tcwv) +
  geom_raster(aes(lon, lat, fill = anom)) +
  geom_point(data = stipple(tcwv), aes(lon, lat), size = 0.05,
             colour = "black", alpha = 0.5) +
  geom_sf(data = aus, fill = NA, colour = "grey40", linewidth = 0.2,
          inherit.aes = FALSE) +
  scale_fill_distiller(palette = "BrBG", direction = 1,
                       name = "TCWV anom (kg m⁻²)",
                       limits = c(-1, 1) * max(abs(tcwv$anom), na.rm = TRUE)) +
  coord_sf(xlim = range(lon), ylim = range(lat), expand = FALSE) +
  facet_wrap(~panel) +
  labs(title = "Total column water vapour anomalies, high-demand days by dominant hazard",
       x = NULL, y = NULL, caption = caption_txt) +
  base_theme
ggsave("R/figs/fig_composite_tcwv.png", p3, width = 10, height = 6, dpi = 300)
cat("wrote R/figs/fig_composite_tcwv.png\n")

nc_close(nc)
```

- [ ] **Step 2: Syntax-check without data**

Run: `/opt/anaconda3/envs/rfigs/bin/Rscript R/demand_composites.R`
Expected (before the nc arrives): clean stop with the "Missing
data/raw/composites/..." message — this proves the script parses and the
guard works. If the nc HAS arrived, expected: three `wrote R/figs/...` lines.

- [ ] **Step 3: Commit**

```bash
git add R/demand_composites.R
git commit -m "Add composite figure script (msl, t850+wind, tcwv)" && git push
```

- [ ] **Step 4: Validation once the nc arrives (may be a later session)**

Run the script; open all three PNGs and check:

1. **Face-validity gate (spec §8, blocking):** the tc panel of the MSL figure
   shows a closed low, and its tcwv panel a strong positive anomaly. If the
   machinery can't recover a cyclone from cyclone days, STOP — nothing else
   is interpretable; report to the user.
2. **Pre-registered predictions (spec §5, report, don't tune):** fire panel —
   positive MSLP anomaly (ridge) and negative tcwv (dry); tc panel — deep
   negative MSLP and positive tcwv. Report agreement/disagreement verbatim.
3. drfa-led panel: describe what it shows (incoherence or lagged structure is
   itself the result); it is NOT part of the hypothesis test.

---

### Task 5: Documentation

**Files:**
- Modify: `README.md` (Figures section — add the three composite figures)
- Modify: `CLAUDE.md` (Current status: pilot composites implemented; record
  the label file → Gadi → nc → R workflow and where the gate/validation
  checklist lives)
- Modify: `docs/METHODOLOGY.md` §10 (mark the pilot as implemented, pointing
  to the spec for the hypothesis and to Task 4 Step 4 items as the evaluation
  protocol)

**Interfaces:** none (prose only). Follow existing entries' style; keep the
CLAUDE.md status entry short and dated 2026-07-08. State clearly that figure
validation (face-validity gate + pre-registered predictions) is PENDING until
`demand_composites.nc` arrives, if that is still true at commit time.

- [ ] **Step 1: Edit the three files**
- [ ] **Step 2: Re-run the full test suite** (docs changes can't break it,
  but the plan ends green): `/opt/anaconda3/bin/python3 -m pytest tests/ -q`
- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md docs/METHODOLOGY.md
git commit -m "Document composite pilot workflow and pending validation" && git push
```
