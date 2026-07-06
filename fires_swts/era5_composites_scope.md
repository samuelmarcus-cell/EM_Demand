# Step 6 — ERA5 circulation composites per SWT (design / scope)

_Date: 2026-06-24. Part of the Fires×SWT compound analysis (`Fires_SWTs.ipynb`)._

## Purpose
Steps 4–5 showed the blocking-high SWTs (FH-B, WH-A, TH-C) are **propensity-dominated** — they raise the *amount* of large-fire activity rather than broadly synchronising distant regions — with two narrow spatial signatures (TH-C → more adjacent states; FH-B → SA–TAS coupling). This step composites the ERA5 **circulation** for each SWT to show the synoptic pattern behind the elevated amount, and to inspect whether FH-B's SA–TAS coupling and TH-C's multi-state spread have a circulation signature.

## Architecture — two bounded components
```
[Gadi/NCI]  era5_swt_composites.py (+ PBS)  ──►  era5_swt_composites.nc  ──(scp/rsync)──►  [local]  Step 6 notebook cells
   reads rt52 ERA5 @12 UTC + SWT csv            small (~tens of MB)                         composite maps + interpretation
```
Interface = the output NetCDF schema (below). Component B is built/tested against a synthetic file of that schema **before** A is ever run on Gadi.

> **Constraint:** I cannot access Gadi — the user runs Component A. The script must be self-contained, print sanity checks (coverage, per-SWT day counts), and depend only on `rt52` (ERA5) + the SWT csv (avoid the WxSysLib path under another user's `gb02`).

## Decisions (locked)
- **Goal:** circulation composites (mechanism). Not fire-weather / not model covariates (deferred).
- **Dataset / source:** ERA5 from NCI **`rt52`**, **hourly sampled at 12 UTC** — the exact hour the SWTs were assigned at (matches Barnes' `read_save_era5.py`, `utc=12`).
- **Variables (4 fields):** MSLP (`msl`, single-level); Z500 (`z`@500), U850 (`u`@850), V850 (`v`@850), T850 (`t`@850) (pressure-level).
- **Domain:** lon 80–180°E, lat −60 to −5°S (Barnes' plot extent; wide enough for the blocking ridge + Tasman). Native 0.25°, coarsen factor configurable (default ~1° via `Ncoarsen=4`).
- **Period:** SWT csv range (1952–2025). Switch to restrict ≥1979 as a sensitivity check (pre-1979 `rt52` is the preliminary back-extension).
- **Anomaly:** seasonally-adjusted via **day-of-year climatology** (reusing the method of Barnes' `compute_statistics.cluster_daily_pert`: per-SWT mean minus the doy-weighted climatology). Consistent with the month/season-matched nulls used in Steps 2–5.
- **Composite:** every SWT (cheap once data is read); plot the 4 headline (FH-B, WH-A, TH-C, WCT-B). Per-grid-cell two-sided significance (t = mean_anom / (sd/√n)) for stippling.

## Component A — Gadi job (`era5_swt_composites.py` + `.pbs`)
- **Reuse:** `utils/read_era5.read_data(varname, date_start, date_end, utc=12, lat_lims, lon_lims, path_data, level, Ncoarsen)` from the Barnes repo (self-contained, netCDF4). Paths: `/g/data/rt52/era5/single-levels/reanalysis/` (msl) and `/g/data/rt52/era5/pressure-levels/reanalysis/` (z,u,v,t).
- **SWT labels:** read `SWT_climatology_v20260129.csv` (date → assigned_SWT), align to the daily field time axis (12 UTC ≈ one sample/day).
- **Anomaly + composite:** doy climatology per grid cell; per-SWT mean anomaly + within-SWT sd → t-stat → p.
- **Output `era5_swt_composites.nc`** — dims `(swt, lat, lon)`:
  - per field: `{f}_mean`, `{f}_anom`, `{f}_p` for `f in {msl, z500, u850, v850, t850}`
  - coords: `swt` (30 names), `lat`, `lon`; plus `n_days(swt)`; provenance in attrs (source, utc, period, Ncoarsen, anomaly method).
- **Run mechanics (env `xp65`):**
  ```bash
  module use /g/data/xp65/public/modules
  module load conda/analysis3
  ```
  PBS: `#PBS -l storage=gdata/rt52+gdata/xp65+gdata/<user-proj>`, modest mem/walltime; prints coverage + per-SWT counts.
- **Transfer back:** from a data-mover node, e.g. `rsync -vP <user>@gadi-dm.nci.org.au:<path>/era5_swt_composites.nc ./` (resumable).

## Component B — local notebook "Step 6"
- **Reuse:** cartopy style from `example_scripts/plot_summer_composite.py` (MSLP contours + auto H/L labelling via `extreme_vals`, wind quivers, gridlines) and the 30-colour `SWTcolors` palette from `plotting/plotting.py`.
- **Figure:** one panel per headline SWT (FH-B, WH-A, TH-C, WCT-B): **T850 or Z500 anomaly (filled)** + **raw MSLP contours with H/L** + **850 hPa wind-anomaly quivers**, stippled where significant; `n_days` in title.
- **Interpretation targets:** FH-B blocking high positioned to drive **SA–TAS coupling**? TH-C pattern fanning fire across **SE states**? WCT-B (suppressor) cool maritime onshore flow?
- **Pre-build:** generate a synthetic `era5_swt_composites.nc` (same schema, random fields) so the plotting cells run and are verified before the real file arrives. Check local `cartopy` availability; fall back to a plain lat/lon map + coastline if absent.

## Scope boundaries (YAGNI)
**In:** the 4 fields, per-SWT anomaly composites, 4 headline maps, significance stippling. **Out (later, if useful):** BARRA / surface fire-weather fields; reanalysis covariates in the statistical models; all-30-SWT atlas; case-study single-day maps (Black Summer).

## Risks
- I can't run/verify Component A on Gadi → mitigate with self-contained code, sanity prints, synthetic-file testing of B.
- rt52 hourly over 73 yrs is a real I/O job → keep `Ncoarsen` coarse, 12 UTC only; restrict ≥1979 if needed.
- Local `cartopy`/`metpy` may be absent → check and fall back.
- WxSysLib (`get_GADI_ERA5_filename`) lives under `gb02/mb0427` → avoid; use self-contained `read_era5` instead.
