# EM_Demand

**The reframe: demand, not fire, is the outcome variable.**

Prior work (Fires_SWTs) showed that synoptic weather regimes control the *danger*
footprint across Australian states far more than realized fire — blocking-high SWTs
synchronise multi-state fire danger (RR up to 2.13) while realized fire barely
responds, and no SWT converts danger to fire beyond seasonal timing. This project
therefore changes the outcome variable to **emergency resource demand**: a daily,
national **Demand Load Index (DLI)** from 1979 onward, validated against known
extreme seasons, and later attributed to synoptic weather types and weather objects.

PhD project — Samuel Marcus, Monash University / ARC 21st Century Weather CRC.

**Full plain-language methodology (every step and statistical test explained):
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).**

## Headline results so far

- **DLI validated against 12 benchmark events:** 7/12 score ≥ 95th
  within-tier percentile (Black Saturday 99.9th, Ash Wednesday 99.7th,
  Canberra 2003 99.6th); TC Yasi 92.9th and Blue Mountains 2013 89.6th are
  near-misses. The misses are understood and documented, not tuned away.
- **Fire record cross-validated:** FIRMS vs the independent DEA Hotspots
  archive agrees at Spearman 0.92 (daily MODIS counts, 2002–2018), passing
  the ≥ 0.90 gate that covers Tier 2 end-to-end.
- **Phase 2 SWT attribution:** high-demand days are enriched under AM-E
  (RR 1.52 [1.30–1.74]) and AM-B (1.27 [1.02–1.50]); TH-C reaches 2.00 in
  the modern era. The fire-danger champion FH-B (danger RR 2.13 in
  Fires_SWTs) shows **no** demand enrichment — demand is multi-hazard, and
  the weather types that drive it are not the fire blocking highs.
  *Caveat:* an independent audit (`fires_swts/AUDIT_2026-07-07.md`) found
  the AM type labels suspect — see `docs/METHODOLOGY.md` §7.5.

## Confidence tiers

| Tier | Period | Fire-activity basis |
|---|---|---|
| 1 | 2012– | VIIRS S-NPP + MODIS hotspots |
| 2 | 2000–2011 | MODIS only |
| 3 | 1979–1999 | Polygon-archive burn windows only |

Every component carries a per-tier availability flag; nothing NaN-fills silently.

## Roadmap

- **Phase 1 (complete):** daily national demand panel + DLI, 1979–present.
  Components: hotspot-derived fire activity (national + SE Aus), DRFA daily
  activations (event count + LGA footprint), TC best-track (count + max wind),
  VIC TFBs. Hazard-subindex structure validated against 12 benchmark events
  (7/12 ≥ 95th within-tier percentile; see `scripts/run_dli.py`). FIRMS-vs-DEA
  cross-validation done (Spearman 0.92 gate passed). **v0.2 flood component
  (AGCD daily rainfall area fractions → sub_flood) is integrated in code;
  adoption gate pending Gadi extraction.** After that gate, **the DLI recipe
  is frozen** (2026-07-07 decision; the planned FFDI component is parked) —
  the index is a tool, the research object is the synoptic meteorology of
  spatially compounding demand (`docs/METHODOLOGY.md` §10).
- **Phase 2:** SWT attribution done (`scripts/run_phase2_swt.py`; AM caveat
  above). **Current focus: pilot ERA5 composite maps** of high-demand days
  stratified by dominant hazard — pattern-agnostic meteorology that does not
  depend on the SWT labels. Weather objects
  (`docs/phase2_weather_objects_notes.md`) follow in the full compound-day
  analysis.
- **Phase 3 (`scripts/phase3_compounding/`):** multi-hazard co-occurrence matrix
  (fire × flood × TC × heatwave at 0/±7/±30-day lags); hemispheric overlap with
  NIFC/CIFFC northern-hemisphere demand. Data: demand panel, NIFC preparedness
  levels, CIFFC sitreps.
- **Phase 4 (`scripts/phase4_capacity/`):** tiered capacity/escalation model
  (local → intrastate → interstate → international → ADF), "no donor available"
  day detection, storyline stress tests. Params stakeholder-elicited.

## Figures

Committed PNGs in `R/figs/` (each rendered by the matching `R/*.R` script via
the `rfigs` conda env; input CSVs come from `scripts/run_figures_data.py` and
`scripts/export_drfa_map.py`):

- `fig_dli_timeseries.png` — daily DLI 1979–2023 by confidence tier, numbered
  benchmark events, 90-day rolling mean (`R/figures_dli.R`)
- `fig_hotspot_maps.png` — satellite hotspots on 7 landmark demand days
  (`R/figures_dli.R`)
- `fig_drfa_choropleth.png` — DRFA activation counts by LGA, 2025 boundaries
  (`R/drfa_map.R`)
- `fig_ffdi_maps.png` — FFDI danger footprint on the 10 fire benchmark days;
  TC/flood days excluded since FFDI is fire danger (`R/ffdi_maps.R`; needs
  `data/raw/ffdi/ffdi_maps.nc` from `gadi/extract_ffdi.pbs`)

**Composite figures** (validated 2026-07-08; face-validity gate passed and
all pre-registered predictions confirmed — see
`docs/superpowers/specs/2026-07-07-demand-composites-pilot-design.md` §5):

- `fig_composite_msl.png` — MSLP anomaly fill + mean contours, panels by
  hazard stratum (fire / tc; no flood stratum — flood component abandoned
  2026-07-09, see METHODOLOGY §5.2); rendered by `R/demand_composites.R`
- `fig_composite_t850_wind.png` — 850 hPa temperature anomaly + wind anomaly
  vectors, panels by hazard stratum
- `fig_composite_tcwv.png` — total column water vapour anomaly, panels by
  hazard stratum
- `fig_supp_drfa_{msl,t850_wind,tcwv}.png` — supplementary: the same fields
  for DRFA-led days. DRFA is a funding activation, not a hazard, so it is
  kept out of the main hazard panels; shown for completeness, excluded from
  the fingerprint comparison

## Layout

- `EM_Demand_Phase1.ipynb` — orchestration notebook (logic lives in `scripts/`)
- `scripts/config.py` — all paths, domains, tiers, constants
- `scripts/loaders/` — one module per source, harmonised schemas
- `scripts/*.py` — pipeline stages (association, metrics, panel, DLI, exports)
- `gadi/` — PBS scripts for anything too heavy locally (qsub only, never interactive)
- `tests/` — unit tests for pure logic (`/opt/anaconda3/bin/python3 -m pytest tests/`)
- `docs/superpowers/specs/` — design documents; `docs/superpowers/plans/` — implementation plans
- `docs/METHODOLOGY.md` — plain-language walkthrough of every step and test
- `CLAUDE.md` — working rules, environment traps, and the DLI recipe (read first)

## Environment

Local: `/opt/anaconda3/bin/python3` (base env). R figures via the `rfigs` conda env
through `Rscript` subprocess. Gadi: project gb02, env xp65 — see `scripts/config.py`
`GADI` dict for paths and storage flags.
