# Phase 2 weather objects — reuse from TFB_Objects (assessed 2026-07-07)

Source repo: <https://github.com/samuelmarcus-cell/TFB_Objects> (same
author; weather-object presence on Victorian TFB days, 1986–2022).

## What is already in EM_Demand (do not re-import)

- **Victorian TFBs**: already a DLI component (`sub_tfb` = `tfb_load_pct`
  from `tfb_vic_daily.parquet`, district counts, availability 1945–).
  TFB_Objects' `TFB_days.csv` (216 dates, binary) is a thinner view of the
  same source — nothing to gain.

## What to reuse: the weather-object extraction pipeline

`scripts/objects_tfb_table.py` in TFB_Objects is a working, tested Gadi
reader for the ERA5 weather-feature archive that EM_Demand's config
already points at (`GADI["weather_objects"]` =
`/g/data/if69/cj0591/GC26_energy_synoptics/data/weatherfeatures.era5/`).
Everything hard-won lives in its `OBJECT_CONFIG` + `prepare_dataset`:

- per-object dir/file templates: fronts 700/850 hPa (`F{y}_{m}.nc`, var
  `FRONT`), anticyclone `maxcl` (`A{y}_{m}.nc`, var `FLAG`), cyclone
  `mincl` (`C{y}_{m}.nc`, var `LABEL`), WCB (`hit_{y}_{m}.nc`, var
  `TOTAL`, **1-hourly**, 721-point lon grid)
- files carry no coordinates — must assign `lat = linspace(-90, 90, 361)`,
  `lon = arange(-180, 180, 0.5)` (720) or `arange(-180, 180.5, 0.5)` (721
  for WCB), squeeze the `dimz_*` singleton, rename `dimy/dimx → lat/lon`
- coverage ≈ 1979/1980–2022; missing months → NaN, never 0
- bbox in TFB_Objects (lat −39..−28, lon 140..154) **is identical to
  `SE_AUS_BBOX`** in `scripts/config.py:61` — reuse verbatim.

## Adaptation plan (when Phase 2 weather objects is picked up)

1. Gadi qsub job (flat-directory rules apply) adapted from
   `objects_tfb_table.py`: loop **all days 1979–2022** (not a date list)
   and output a daily CSV.
2. **Do not use binary presence** — TFB_Objects' output is ≈1.0 for every
   object on almost every day (fronts/anticyclones are near-ubiquitous in
   a 14°×11° box), so presence flags saturate exactly like the count
   components did in v0.1. Output instead, per object per day: (a) the
   **fraction of bbox cells covered** by the object, and optionally (b)
   presence in a tighter VIC-only box. Continuous coverage fractions rank
   cleanly within (tier, month).
3. Analysis mirrors `scripts/run_phase2_swt.py`: month-matched RR of
   object presence/high-coverage on within-tier ≥95th-pct DLI days,
   30-day block bootstrap. Compare with the SWT result (AM-E/AM-B
   enriched): objects say *which synoptic features* are present, SWTs say
   *which regime*.
4. Optional: TFB_Objects' composite notebook
   (`scripts/composite_anomaly_TFB.ipynb`, climatology / composite /
   anomaly 3-panels) adapts directly to top-DLI-day composites — combine
   with the build-up composite idea in `docs/phase3_methods_notes.md`.

WCB caution: the WCB files are 1-hourly (24× volume) — aggregate to the
project's fixed UTC+10 day (00–23 AEST = 14:00 UTC prev day – 13:00 UTC)
before computing coverage, and expect that step to dominate runtime.
