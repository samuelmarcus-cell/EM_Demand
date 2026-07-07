# EM_Demand — instructions for AI assistants

## What this project is

Daily national **Demand Load Index (DLI)** for Australian emergency management,
1979–present. Reframes the Fires_SWTs finding (meteorology controls the *danger*
footprint, not fire realization): the outcome variable here is **emergency
resource demand**, not fire occurrence. Phase 1 (complete) builds the index;
Phase 2 attributes high-demand days to synoptic weather types and weather
objects; Phase 3 studies compound/sequential demand; Phase 4 confronts demand
with capacity. Design doc: `docs/superpowers/specs/2026-07-06-em-demand-phase1-design.md`.
Implementation plans for remaining work: `docs/superpowers/plans/`.

The user is a PhD candidate (compound hazards & EM capacity, Monash). They are
not across implementation detail — give **plain-language progress updates**,
work in small validated steps, and commit + push after each validated step.

## Non-negotiable working rules

1. Python is `/opt/anaconda3/bin/python3` (pandas 2.x, geopandas 1.1.3,
   shapely 2.1.2, pyarrow 21.0.0, sklearn 1.7.2). Never `pip install` or touch
   dask versioning. R only via the `rfigs` conda env + `Rscript` subprocess
   (rpy2 is broken).
2. Machine has **17 GB RAM**. Stream big inputs in chunks; never load the fire
   gdb or the DEA archive whole.
3. All logic lives in importable `scripts/` modules; `scripts/run_*.py` are
   thin runners; the notebook is orchestration only. Unit-test pure logic in
   `tests/` (pytest, currently 42 passing — keep it green).
4. Checkpoints: parquet in `data/derived/` (gitignored), final CSVs in
   `data/export/` (gitignored). Runners print progress with `flush=True`.
5. Heavy steps: run in background writing to a log in `data/derived/`, and
   monitor the log. Verify a "stuck" process with `ps` (CPU state/time) before
   declaring it dead — GDAL grinding looks identical to hung.
6. Availability discipline: every component is NaN outside its availability
   window (`COMPONENT_AVAILABILITY` in `scripts/config.py`); within the hotspot
   era a missing day means zero fire activity (fill 0). Never NaN-fill silently.
   Every daily row carries `confidence_tier` and `n_components_available`.
7. Daily bucketing is fixed UTC+10 (AEST, no DST) everywhere.
8. Commit messages: short imperative subject (+ optional why-paragraph),
   trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`. Push after
   each commit (SSH remote is configured).

## Hard-won environment traps (violating these costs hours)

- **Fire polygon gdb** (`~/Fires_SWTs/Bushfire Extents - Historical (2025).gdb`):
  - Set `pyogrio.set_gdal_config_options({"OGR_ORGANIZE_POLYGONS": "SKIP"})`
    before reading geometry — GDAL's organizePolygons is O(parts²) and stalls
    30+ min on monster multipart extents.
  - SKIP yields INVALID geometries (holes become shells). Downstream must be
    validity-blind: `simplify(tol, preserve_topology=False)` and
    `sjoin(predicate="dwithin", distance=...)` ONLY. Topology-preserving
    simplify or `buffer` will stall for hours.
  - Stream in chunks: `gpd.read_file(..., rows=slice(skip, skip+20000))`.
  - Date columns have mixed tz offsets → parse with
    `pd.to_datetime(s, errors="coerce", utc=True).dt.tz_localize(None)`.
  - Sentinels: OLE null `1899-12-30` (mask everything pre-1900), year-0200/2525
    typos (benign UserWarnings, coerced to NaT), Jan-1 ignition placeholders
    (flag via `jan1_ignition`, never drop).
- **Notebook execution**: `jupyter nbconvert --execute` silently does nothing
  here; use `nbclient.NotebookClient(nb).execute()`.
- **VIIRS = S-NPP only** (design decision 3) — including NOAA-20/21 creates
  density step-changes inside Tier 1.
- **Gadi**: project gb02, `module use /g/data/xp65/public/modules && module
  load conda/analysis3`, storage flags
  `gdata/if69+gdata/su28+gdata/gb02+gdata/xp65+gdata/ia39+gdata/rt52`,
  compute via **qsub only**. BARRA-R2 zarr is time-LAST → `.transpose(...)`
  before time operations. Constants in `scripts/config.py::GADI`.

## The DLI recipe (do not casually change)

Components → percentile-rank within `(confidence_tier, calendar month)` →
hazard subindices → DLI = mean of available subindices
(`scripts/dli.py::compute_dli`):

- `sub_fire` = mean of available fire percentiles (4 national hotspot metrics,
  2 SEAUS metrics, Tier-3 polygon burn windows)
- `sub_tc` = max(`tc_load_pct`, `tc_severity_pct`)
- `sub_drfa` = `drfa_lga_pct` (LGA footprint, not event count)
- `sub_tfb` = `tfb_load_pct`

Structure choices that were **tested and rejected**: flat component mean
(dilutes single-hazard events like TC Yasi), top-k mean (order-statistic
inflation: a random day's top-3 of 11 ≈ 0.83), re-ranked subindices (no
improvement). Count-style inputs saturate from rank ties (1 active TC is
common → pct caps ≈ 0.7), which is why tc uses max-with-severity and drfa
uses the LGA footprint. SEAUS components exist because national fire counts
are swamped by routine northern-savanna burning.

Validation = the 12-event benchmark table printed by `scripts/run_dli.py`.
Current result: 9/12 events ≥ 93rd within-tier percentile; the honest misses
are the 2022 floods (~83rd; DRFA is the only flood signal and persists for
weeks) and TAS 2016 / QLD Deepwater 2018 (~61st–70th; regionally severe,
nationally moderate). **Do not tune the combiner to push these up** — that is
overfitting 12 data points. Any recipe change must re-run the benchmark table
and must not degrade the fire benchmarks below the 93rd percentile.

## Pipeline (run order) and checkpoints

| Runner | Output (data/derived/) | Runtime |
|---|---|---|
| `run_fire_association.py` | fire_polygons_simplified/windows, hotspot_fire_matches, fire_daily, hotspots_unmatched_idx | ~2 min |
| `run_satellite_clusters.py` | satellite_fire_matches, satellite_fire_daily | ~1 min |
| `run_demand_metrics.py` | fire_days, fire_seasons.json, demand_metrics_daily | ~30 s |
| (DRFA/TFB loaders) | drfa_events, drfa_daily_panel, tfb_vic_daily | seconds |
| `run_dli.py` | demand_daily_panel, dli_top50_days.csv + benchmark table | ~5 s |
| `run_exports.py` | CSVs in data/export/ | ~10 s |
| `run_crossval.py` | crossval_daily (needs DEA export, see plans) | — |

Tests: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`.
`EM_Demand_Phase1.ipynb` re-executes end-to-end in ~1 min via nbclient.

## Current status / open items

- Phase 1 complete (all 7 design sections), pushed to
  `github.com:samuelmarcus-cell/EM_Demand.git`.
- **DEA cross-validation: done 2026-07-07.** Daily-count Spearman vs DEA:
  MODIS 0.92 pre-2019 (gate ≥ 0.90 passed — covers Tier 2 fully), 0.87 after;
  VIIRS S-NPP 0.87 / 0.79. Post-2019 divergence is DEA-side: its live feed
  ingests the same pass via multiple algorithms (~22% exact duplicates,
  removed; counts still ~2× FIRMS after), and its S-NPP feed is partial
  before 2019 (no FRP either). Conclusion: FIRMS is not idiosyncratic;
  tiers 1–2 stand. Rerun: `scripts/run_crossval.py` (needs
  `data/derived/hotspots_dea.parquet` from `scripts/run_dea_extract.py`).
- **FFDI component (v0.2 candidate)**: precomputed daily FFDI zarr exists on
  Gadi (`GADI["ffdi_zarr"]`, 1979–2023). Plan:
  `docs/superpowers/plans/2026-07-07-ffdi-component.md`.
- **Phase 2 SWT attribution: done 2026-07-07** (`scripts/run_phase2_swt.py`
  → `data/derived/swt_demand_rr*.csv`; month-matched RR of within-tier
  ≥95th-pct DLI days, 30-day block bootstrap). Headline: AM-E RR 1.52
  [1.30–1.74] and AM-B 1.27 [1.02–1.50] are the only all-period SWTs whose
  CIs clear 1; Tier 1 adds TH-C 2.00 [1.29–2.83]. Suppressed: COL-A 0.19,
  EH-A 0.39, WCT-B/WH-B 0.52. Contrast with Fires_SWTs *danger* result
  (FH-B 2.13 top): demand is multi-hazard, so monsoon-family (AM) types
  outrank the fire blocking highs. FH-B itself is NOT demand-enriched (0.69).
- **Figures (2026-07-07, in progress):** plan
  `docs/superpowers/plans/2026-07-07-figures.md`. Done: `R/figs/`
  fig_dli_timeseries.png (numbered benchmark events + 90-day rolling mean),
  fig_hotspot_maps.png (7 landmark days), fig_drfa_choropleth.png (LGA 2025
  boundaries via `PATHS.lga_boundaries`, 100% name join after 2 ABS renames).
  Pending: FFDI danger-footprint maps (`R/ffdi_maps.R`, plan Task 3 steps 4–5)
  blocked on Gadi job output `ffdi_maps.nc` + `ffdi_daily_summary.csv`
  (scp both to `data/raw/ffdi/`); then README "Figures" section + final review.
  NB `gadi/extract_ffdi.pbs` must be qsub'd from the directory holding
  `extract_ffdi.py` + `ffdi_map_dates.csv` (files sit flat on Gadi, no repo).
- **Flood component (v0.2 candidate, designed 2026-07-07):** AGCD daily
  rainfall as the daily engine (national + SEAUS area fractions over
  within-month wet-day p95, 1/3/7-day accumulations) → new `sub_flood`.
  Spec: `docs/superpowers/specs/2026-07-07-flood-component-design.md`.
  Plan (ready to execute): `docs/superpowers/plans/2026-07-07-flood-component.md`.
  Adoption gate: 2022-floods benchmark must rise above ~0.83 with no fire
  benchmark below 0.93 — never tune to pass it. Validation set = dated
  historical flood extents (QLD 1893–2025 the standout; VIC, WA also):
  inventory in `docs/flood_data_layers.md`. First step needs the user to
  verify AGCD access on Gadi (`/g/data/zv2/agcd/`, may need to join
  project zv2). Do NOT poll Gadi over ssh — the user runs Gadi commands
  and pastes output.
- Phase 2 weather objects: not yet planned, but scaffolded —
  `docs/phase2_weather_objects_notes.md` (reuse the TFB_Objects repo's
  extraction pipeline; use coverage fractions, NOT binary presence, which
  saturates). Phase 3 scaffolded in `docs/phase3_methods_notes.md`
  (spatial-shuffle null + build-up composites, after Gauthier & Bevacqua
  2026 npj Nat. Hazards). Phase 4: stub only.
