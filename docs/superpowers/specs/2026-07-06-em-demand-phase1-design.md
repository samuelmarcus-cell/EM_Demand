# EM_Demand Phase 1 — Demand Load Index v0: Design

**Date:** 2026-07-06 | **Status:** Approved

## Reframe

Prior work (Fires_SWTs) showed meteorology controls the *danger* footprint, not fire realization. This project changes the outcome variable from fire to **emergency resource demand**: a daily, national **Demand Load Index (DLI)** from 1979 onward, validated against known extreme seasons. Phase 2+ attributes demand days to SWTs and weather objects.

## Confidence tiers

Every daily output carries `confidence_tier`:

| Tier | Period | Fire-activity basis |
|---|---|---|
| 1 | 2012– | VIIRS S-NPP + MODIS hotspots |
| 2 | 2000–2011 | MODIS only |
| 3 | 1979–1999 | Polygon-archive burn windows only |

Tier boundaries are satellite-driven. Every other component gets its own availability flag rather than silent NaN-fill:

| Component | Available |
|---|---|
| DRFA activations (LGA-level) | 2006-03-20 → present |
| AIDR disaster mapper (end dates, pre-2006 events) | ~1900s → present (728 events) |
| BARRA-R2 FFDI | 1979 → 2023 |
| VIC TFB (district-level) | 1945 → present |
| MODIS (FIRMS, C6.1) | 2000-11 → present |
| VIIRS S-NPP only (FIRMS) | 2012-01 → present |
| BoM TC best-track | full period |

Panel runs **1979 → today**. DLI averages available components only; records `n_components_available`.

## Data sources (local)

- DRFA: `~/Library/CloudStorage/OneDrive-MonashUniversity/PhD/Disaster_Data/drfa_activation_history_by_location_2026_march_19.csv` — 5,967 LGA-rows, 809 AGRNs, hazard_type, start date, **no end date**
- AIDR: same dir, `AIDR_disaster_mapper_data.xlsx`, sheet "Disaster Mapper Data" — 728 events with start AND end dates
- VIC TFB: `~/Downloads/TFBsHistory_20260706123204.csv` — UTF-16-LE, skiprows=1, 820 district-level declarations 1945–2026; date span format `DD/MM/YYYY HH:MM - DD/MM/YYYY HH:MM`; "the whole State of Victoria" rows; revocation column
- Fire polygons: `~/Fires_SWTs/bushfire_events_geo.csv` (85,793 footprints)
- SWTs: `~/Fires_SWTs/SWT_climatology_v20260129.csv`
- States geojson: `~/Fires_SWTs/gadi/aus_states.geojson`
- FIRMS hotspots: USER ACTION — archive download (MODIS C6.1 + VIIRS S-NPP, country=Australia) into `data/raw/firms/`
- DEA Hotspots: secondary, cross-validation only, `data/raw/dea_hotspots/`
- BoM TC best-track: public CSV → `data/raw/bom_tc/`

## Key design decisions

1. **DRFA end dates (evolved during build from approved option a):** priority cascade per event — (i) **"name"**: official date ranges embedded in DRFA event names ("(22 February - 5 April 2022)", "(1-4 February 2022)") are authoritative; (ii) **donor match**: pooled ICA catastrophe master (Event Start/Finish; best coverage — reuses the aus-disaster app's `load_ica` date recipe) + AIDR mapper, matched by hazard class + state overlap + start-date proximity (±14d), best = smallest gap then name-Jaccard then ICA-over-AIDR; zero-duration donor records excluded (no duration info); (iii) **assumed** per-hazard-class windows (fire 21d, flood 14d, tc 7d, storm 3d; config-tunable). `end_date_source ∈ {name, ica, aidr, assumed}`. Achieved: 272/809 events (34%) evidence-based.
2. **TFB upgrade:** parse district-level CSV → daily VIC TFB flag + `n_districts`, from 1945 (was 1986 dates-only).
3. **VIIRS = S-NPP only** for a consistent Tier-1 record (no NOAA-20/21 density step-changes).
4. **Hotspot schema (both loaders):** `lat, lon, datetime_utc, frp, sensor, confidence, source`. Cross-validation cell: overlap-season daily national counts + FRP-sum correlation between FIRMS and DEA before tier decisions bake in.
5. **Per-state fire seasons** defined from 2000– hotspot climatology (months containing central 80% of FRP), applied to all tiers including Tier 3.
6. **DLI v0:** percentile-rank each component within calendar month (removes seasonality), equal-weight mean, computed within tier. Raw component panel retained as the primary product.
7. **Domain constants:** analysis regionalisation by state; composite domain for Phase 2 = lon 105–180°E, lat 45–8°S. Never whole-domain presence flags (saturate).
8. **Notebook = orchestration only.** All logic in importable `scripts/` modules (Gadi-reusable). Parquet for big intermediates, CSV for final outputs.

## Sections (notebook `EM_Demand_Phase1.ipynb`)

0. Config (dataclass; paths, bboxes, period, RUN_CONTEXT, tier definitions, hazard windows)
1. Loaders (FIRMS, DEA, DRFA+AIDR, TC, TFB) — `# USER ACTION REQUIRED` pattern for gated downloads
2. Hotspot→fire association: sindex spatial join to polygon footprints (1–2 km buffer, temporal gate) + ST-DBSCAN (~5 km/2 day) satellite-only clusters → per-fire-per-day `fire_id, date, n_hotspots, frp_sum, state(s)`; parquet checkpoint; PBS twin if too heavy locally
3. Daily demand metrics: `growth_load`, `ignition_load`, `concurrent_burden`, `dispersion` (port Fires_SWTs Step 4), `unseasonality` — national + per-state + SE-Aus
4. DRFA daily activation panel: `n_active_events`, `n_jurisdictions_active`, `n_hazard_types_active`, per-hazard flags
5. DLI v0 + validation: Black Summer, TAS 2016/2013, QLD 2018, NSW 2013, Feb–Mar 2022 floods (DRFA layer, not fire layer); Tier 3: Ash Wednesday 1983, Jan 1994 NSW, Jan 1997 VIC. All must rank in the extreme tail within tier, else iterate. Top-50 demand days per tier with component breakdowns.
6. Exports: `demand_daily_panel.csv`, `dli_top50_days.csv`, R-tidy CSVs (no R yet)
7. Phase 2–4 stubs: real module files, full docstrings, `raise NotImplementedError`, PBS stubs

## Repo layout

As per approved skeleton: `scripts/{config.py, loaders/, fire_association.py, demand_metrics.py, drfa_panel.py, dli.py, export_for_r.py, phase2_attribution/, phase3_compounding/, phase4_capacity/}`, `gadi/`, `tests/`, `data/{raw,derived}`.

## Environment constraints (hard-won, do not violate)

- Local python `/opt/anaconda3/bin/python3`; do not touch dask versioning; pyarrow 21.0.0 and sklearn 1.7.2 confirmed present
- R via `rfigs` env + Rscript subprocess only (rpy2 broken)
- Gadi: project gb02, env xp65, storage flags `gdata/if69+su28+gb02+xp65+ia39+rt52`; BARRA-R2 zarr is time-last (`.transpose`), 1979–2023, qsub only; weather objects need `assign_weatherfeature_coords`
- Data hygiene: `1899-12-30` OLE sentinel; Jan-1 placeholder ignition dates — flag, never silently drop

## Testing

Unit tests for pure logic: DRFA event dedup + daily explode, AIDR fuzzy-join, TFB span parsing, tier assignment, DLI percentile machinery. Run with base-env python. Validation = known-event checks in Section 5.

## Thin slice (first build)

Section 0 config + DRFA loader (`loaders/drfa_activations.py`) + AIDR join + `drfa_panel.py` → daily panel columns end-to-end, validated against Feb–Mar 2022 east-coast floods.
