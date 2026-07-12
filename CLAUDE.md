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

- **Gadi scripts MUST get a small dry run before the full qsub** (e.g. 2
  years of input, ~1 SU): local unit tests use in-memory arrays and cannot
  hit dask/chunking failures — job 173287012 died on a groupby-quantile
  chunking error that no local test could catch. Dask groupby `.quantile`
  needs the time axis in ONE chunk (flox blockwise only).

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
- `sub_flood` — **ABANDONED 2026-07-09 (user decision, final).** Two Gadi
  extraction runs (~230 SU) died at the single end-of-job CSV write
  (walltime kill, then PermissionError); the user terminated all flood
  work. The recipe is **frozen without sub_flood**. The code paths
  (`scripts/loaders/agcd_rain.py`, sub_flood in `scripts/dli.py`,
  `scripts/run_flood_validation.py`) remain but are inert with no rain
  data and must not be revived unless the user explicitly reopens it.
  Consequence: the 2022-floods benchmark stays an honest miss (82.57),
  and the composites flood stratum can never be tested (spec fallback
  clause applies).

Structure choices that were **tested and rejected**: flat component mean
(dilutes single-hazard events like TC Yasi), top-k mean (order-statistic
inflation: a random day's top-3 of 11 ≈ 0.83), re-ranked subindices (no
improvement). Count-style inputs saturate from rank ties (1 active TC is
common → pct caps ≈ 0.7), which is why tc uses max-with-severity and drfa
uses the LGA footprint. SEAUS components exist because national fire counts
are swamped by routine northern-savanna burning.

Validation = the 12-event benchmark table printed by `scripts/run_dli.py`.
Exact current result (recomputed 2026-07-07 from demand_daily_panel):
**seven of 12 events ≥ 95th within-tier percentile** (Black Saturday 99.93,
Ash Wednesday 99.67, Dandenongs 99.61, Canberra 99.61, Dunalley 98.72,
Black Summer 97.76, NSW Jan 1994 95.30); near-misses TC Yasi 92.91 and
NSW Blue Mtns Oct 2013 89.59; honest misses 2022 floods 82.57 (DRFA is the
only flood signal and persists for weeks), TAS 2016 60.72 and QLD Deepwater
2018 69.82 (regionally severe, nationally moderate). Never round these up
("9/12 ≥ 93rd" was a past overstatement, corrected). **Do not tune the
combiner to push these up** — that is overfitting 12 data points. Any recipe
change must re-run the benchmark table; the gate is: keep the seven
≥95th-percentile fire events at or above the 93rd, and do not lower any
other event's percentile materially.

## Pipeline (run order) and checkpoints

| Runner | Output (data/derived/) | Runtime |
|---|---|---|
| `run_fire_association.py` | fire_polygons_simplified/windows, hotspot_fire_matches, fire_daily, hotspots_unmatched_idx | ~2 min |
| `run_satellite_clusters.py` | satellite_fire_matches, satellite_fire_daily | ~1 min |
| `run_demand_metrics.py` | fire_days, fire_seasons.json, demand_metrics_daily | ~30 s |
| (DRFA/TFB loaders) | drfa_events, drfa_daily_panel, tfb_vic_daily | seconds |
| `run_dli.py` | demand_daily_panel, dli_top50_days.csv + benchmark table | ~5 s |
| `run_exports.py` | CSVs in data/export/ | ~10 s |
| `run_flood_validation.py` | prints diagnostic table only, no file (needs rebuilt panel) | ~5 s |
| `run_crossval.py` | crossval_daily (needs DEA export, see plans) | — |
| `run_state_panel.py` | state_hazard_panel.parquet, state_hazard_summary.parquet | ~1–2 min |
| `run_compounding.py` | compounding_ratios.csv, compounding_null_samples.csv, compounding_impact_check.csv, compound_days_top.csv, state_cooccurrence.csv | ~2–4 min |

Tests: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`.
`EM_Demand_Phase1.ipynb` re-executes end-to-end in ~1 min via nbclient.

## Current status / open items

- **Strategic pivot (2026-07-07, user decision):** the index is a tool, not
  the point — the research object is the synoptic meteorology of spatially
  compounding hazard demand. **DLI recipe FROZEN 2026-07-09 without
  sub_flood** (flood component abandoned by user decision — see recipe
  section above); the FFDI component is **parked** (plan kept for
  reference only). Priorities: (1) ~~flood gate~~ dead, (2) composites
  pilot DONE (see below), (3) ~~state×hazard compounding panel~~ DONE
  (see below), (4) weather objects in the real compound-day analysis.
  See `docs/METHODOLOGY.md` §10.
- **Fires_SWTs audited 2026-07-07** (`fires_swts/AUDIT_2026-07-07.md`, also
  at `~/Fires_SWTs/`): all numbers reproduce; danger RRs + conversion null
  SOLID (citable); fire RRs FRAGILE (burn-window imputation — cite only with
  ignition-only sensitivity); **red flag: Black Saturday + 2020-01-04
  classify as AM** → treat AM-family results (incl. our AM-E 1.52) with
  caution; SWT classifier needs its own audit. See METHODOLOGY.md §7.5.
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
- **FFDI component: PARKED** (pivot decision — index frozen). The plan
  (`docs/superpowers/plans/2026-07-07-ffdi-component.md`) and the extracted
  `ffdi_daily_summary.csv` are kept for reference; do not implement.
- **Phase 2 SWT attribution: done 2026-07-07** (`scripts/run_phase2_swt.py`
  → `data/derived/swt_demand_rr*.csv`; month-matched RR of within-tier
  ≥95th-pct DLI days, 30-day block bootstrap). Headline: AM-E RR 1.52
  [1.30–1.74] and AM-B 1.27 [1.02–1.50] are the only all-period SWTs whose
  CIs clear 1; Tier 1 adds TH-C 2.00 [1.29–2.83]. Suppressed: COL-A 0.19,
  EH-A 0.39, WCT-B/WH-B 0.52. Contrast with Fires_SWTs *danger* result
  (FH-B 2.13 top): demand is multi-hazard, so monsoon-family (AM) types
  outrank the fire blocking highs. FH-B itself is NOT demand-enriched (0.69).
  **Audit caveat:** AM labels are suspect (Black Saturday classifies AM-E) —
  report AM results only with the METHODOLOGY.md §7.5 caveat attached.
- **Figures (2026-07-07, done):** `R/figs/`
  fig_dli_timeseries.png (numbered benchmark events + 90-day rolling mean),
  fig_hotspot_maps.png (7 landmark days), fig_drfa_choropleth.png (LGA 2025
  boundaries via `PATHS.lga_boundaries`, 100% name join after 2 ABS renames).
  Done 2026-07-07 (later same day): fig_ffdi_maps.png (10 fire benchmark
  days; TC/flood days excluded — FFDI is fire danger, low on those days)
  + README "Figures" section. `ffdi_daily_summary.csv` + `ffdi_maps.nc`
  are in `data/raw/ffdi/` (gitignored; regenerate via
  `gadi/extract_ffdi.pbs` — loads the full 40 GB zarr into RAM in one
  pass, 8 CPUs/96 GB, ~10 min; year-by-year reads take 8 h, don't).
  NB the pbs must be qsub'd from the directory holding `extract_ffdi.py`
  + `ffdi_map_dates.csv` (files sit flat on Gadi, no repo). The FFDI
  summary CSV unblocks the FFDI-component plan.
- **Flood component (v0.2, Tasks 1–5 implemented 2026-07-07):** Tasks 1–4
  complete: Gadi job to extract AGCD daily rainfall area fractions (JSON
  spec → agcd_rain_daily.csv), loader (`scripts/loaders/agcd_rain.py`),
  DLI integration (`scripts/dli.py` sub_flood = mean of six rain percentiles),
  validation runner (`scripts/run_flood_validation.py`).
  **ABANDONED 2026-07-09 before the adoption gate could run** — both full
  Gadi extraction attempts (173344347 walltime kill; 173365325
  PermissionError at the final CSV write) lost their finished compute
  because the script wrote output only once at job end. User decision:
  no more flood work, final. The adoption gate was never evaluated; the
  code stays but is inert. (Flood docs — plan, spec, data inventory,
  event-days CSV — deleted in the 2026-07-09 docs cleanup;
  `scripts/run_flood_validation.py` therefore cannot run, which is moot.)
- **Composite pilot implemented 2026-07-08.** Stratum assignment:
  `scripts/composite_strata.py` (argmax of hazard subindices; tfb folds into
  fire); runner: `scripts/run_composite_strata.py` → `data/derived/demand_stratum_days.csv`
  (current: 869 high-demand days — fire 387, tc 387, drfa-led 95; flood stratum
  absent until AGCD gate closes). Gadi composites: `gadi/demand_composites.py`
  + `.pbs` (msl, t850, u850, v850, tcwv; climatology from ALL days; reuses
  `fires_swts/gadi/composite_core.py` + `read_era5.py`). Figures:
  `R/demand_composites.R` → `R/figs/fig_composite_msl.png`,
  `fig_composite_t850_wind.png`, `fig_composite_tcwv.png`. Workflow: run
  `scripts/run_composite_strata.py` → copy `demand_stratum_days.csv` +
  `gadi/demand_composites.{py,pbs}` + `fires_swts/gadi/composite_core.py` +
  `fires_swts/gadi/read_era5.py` to flat Gadi dir → dry run (--start 1990-01
  --end 1991-12, ~1 SU) → full qsub (~5–15 SU) → copy `demand_composites.nc`
  to `data/raw/composites/` → `Rscript R/demand_composites.R`. **Validated
  2026-07-08** (full job 173343702, 7.11 SU; composited days within period:
  fire 370, tc 347, drfa-led 77): face-validity gate PASSED (tc composite =
  significant negative MSLP anomaly + closed mean-contour low over tropical
  N Australia + strong positive TCWV). Pre-registered predictions (spec §5)
  all confirmed: fire = blocking ridge over Tasman/SE Aus + dry TCWV + hot
  (+2 K) T850 plume; tc = tropical low + moist; drfa-led weak/incoherent
  (descriptive, as expected for a lagged funding proxy). Pilot answer:
  distinct synoptic fingerprints per hazard — supports the compounding-phase
  premise. Spec:
  `docs/superpowers/specs/2026-07-07-demand-composites-pilot-design.md`.
- **State×hazard compounding panel: DONE 2026-07-10.** Fire compounding
  1.3–2.2× chance (≥2 to ≥4 states high simultaneously, thr 0.95, 300 km,
  1,000 shuffles); TC compounding 3.3× (≥2 states); cross-hazard (fire
  some states, TC others) 0.8× — significantly *below* chance, consistent
  with opposing synoptic drivers in the composites pilot. Face-validity gate
  PASSED (Black Summer → NSW/SA/TAS/VIC/WA high fire; Yasi → NT/QLD high
  TC). Impact check: multi-state DRFA follows multi-state hazard days 30.8%
  vs 22.9% after quiet days (30-day window). Fire tier-1/2 score re-ranked
  within (state, tier, month) 2026-07-10 to restore within-group-95th
  convention (definitional fix, not tuning). Panel: `data/derived/state_hazard_panel.parquet`;
  ratios: `data/derived/compounding_ratios.csv`; runners: `scripts/run_state_panel.py`
  + `scripts/run_compounding.py` (use `-m` from repo root); spec:
  `docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md`;
  replication guide: `docs/METHODOLOGY.md` §12.
- Phase 2 weather objects: not yet planned, but scaffolded —
  `docs/phase2_weather_objects_notes.md` (reuse the TFB_Objects repo's
  extraction pipeline; use coverage fractions, NOT binary presence, which
  saturates). Phase 3 scaffolded in `docs/phase3_methods_notes.md`
  (spatial-shuffle null + build-up composites, after Gauthier & Bevacqua
  2026 npj Nat. Hazards). Phase 4: stub only.
