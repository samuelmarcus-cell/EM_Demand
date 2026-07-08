# EM_Demand — forensic methodological reconstruction

**Date:** 2026-07-08. **How this was produced:** a complete read of the
repository — every Python module, loader, runner, test, PBS/Gadi script,
R script, the orchestration notebook, all documentation, the vendored
predecessor project, and the git history — with the code, not the
documentation, treated as ground truth. Statements are observations from
the code unless explicitly marked ***Inference:*** (a motivation not
stated anywhere but reconstructed from the implementation).

Written for a scientifically literate reader (e.g. a PhD examiner) who has
never seen this code. Sufficient, together with the raw datasets, to
reproduce the methodology.

---

## 0. Orientation: what this project is

The project constructs a **daily, national Demand Load Index (DLI)** for
Australian emergency management, 1979–present, from heterogeneous archival
traces of emergency workload (satellite fire detections, mapped fire
polygons, tropical-cyclone tracks, disaster-funding activations, fire-ban
declarations, and gridded rainfall). The index is explicitly a **measuring
instrument, not the scientific finding**: it identifies *which days* placed
extreme demand on the national emergency system, so that the meteorology of
those days can then be studied — first via an existing synoptic weather-type
(SWT) classification (Phase 2, complete), next via classification-free
composite maps (specified, not yet run), and ultimately via a state×hazard
compounding analysis (scaffolded only).

The project descends from a predecessor analysis (**Fires_SWTs**, vendored
in `fires_swts/`), whose central result — synoptic weather types
synchronise multi-state fire *danger* far more than realized *fire* —
motivated the reframe from fire occurrence to emergency *demand* as the
outcome variable. That predecessor was independently audited on 2026-07-07
(`fires_swts/AUDIT_2026-07-07.md`); the audit's consequences for this
project are woven in below (§7.4, §10).

### Pipeline dependency map

```
RAW DATA
  FIRMS hotspot CSVs (MODIS 2000-11–, VIIRS S-NPP 2012–)
  Fire-polygon geodatabase (~347k mapped fires, 1979– usable)
  BoM TC best-track CSV (1979–)
  DRFA activation CSV + ICA/AIDR catastrophe lists (2006–)
  CFA Victorian TFB history CSV (1945–)
  AGCD 0.05° daily rainfall (Gadi; 1979–)  [v0.2, gate pending]
  DEA Hotspots archive (cross-validation only)
  SWT climatology CSV (from Fires_SWTs; 1952–)
        │
        ▼  loaders (scripts/loaders/*) — harmonisation, sentinel cleaning
        ▼
  scripts/run_fire_association.py     hotspot ↔ polygon matching
        ▼
  scripts/run_satellite_clusters.py   ST-DBSCAN on unmatched hotspots
        ▼
  scripts/run_demand_metrics.py       per-day fire workload metrics, by region
        ▼
  scripts/run_dli.py                  17 components → percentile ranks
        │                             → 5 hazard subindices → DLI
        │                             + 12-event benchmark table (validation)
        ├──► scripts/run_exports.py   CSVs for R
        │        └──► R/*.R           figures
        ├──► scripts/run_phase2_swt.py  SWT attribution (month-matched RR,
        │                               block bootstrap)
        └──► scripts/run_flood_validation.py  flood-event diagnostic

SIDE CHANNELS
  scripts/run_dea_extract.py + run_crossval.py   FIRMS vs DEA validation
  gadi/extract_agcd_rain.{py,pbs}                rainfall components (HPC)
  gadi/extract_ffdi.{py,pbs}                     FFDI summaries + map slabs
                                                 (component PARKED; maps only)
```

Every stage checkpoints to parquet in `data/derived/` (git-ignored,
regenerable); final analysis-ready CSVs land in `data/export/`.

---

## 1. Shared conventions (scripts/config.py)

These conventions bind every stage; violations of any of them would be a
methodological error, so they are stated once here.

**Fixed local day.** All daily bucketing is UTC+10 (AEST, no daylight
saving): a timestamp's local date is `(t_utc + 10 h)` truncated to
midnight. ***Inference:*** a fixed offset guarantees that an afternoon and
an overnight satellite overpass of the same burning day land on the same
date, and avoids DST discontinuities in a 47-year daily series; the cost is
up to ±1 h of misbucketing in non-AEST states, negligible at daily
resolution. (Weakness: the constant is duplicated across four modules
rather than imported from config — see §10.)

**Confidence tiers.** Every day is labelled by the quality of its
fire-activity evidence: **Tier 1** 2012-01-01→ (VIIRS S-NPP + MODIS),
**Tier 2** 2000-11-01→2011-12-31 (MODIS only), **Tier 3**
1979-01-01→2000-10-31 (no satellites; mapped polygons only). All
cross-day statistics are computed *within tier* so that a 1985 day is
never ranked against a 2020 day whose data are richer. VIIRS is
deliberately restricted to the S-NPP satellite: adding NOAA-20 (2017) and
NOAA-21 (2022) would create detection-density step changes *inside*
Tier 1, which would masquerade as fire-activity trends.

**Availability discipline.** Each component carries an explicit
availability window (`COMPONENT_AVAILABILITY`): DRFA from 2006-03-20,
MODIS from 2000-11-01, VIIRS from 2012-01-01, Victorian TFBs from 1945,
fire polygons / TC track / AGCD rainfall from 1979. Outside its window a
component is NaN, never zero. *Within* the satellite era, a day with no
detections genuinely means no fire activity and is a zero. Every daily row
records `n_components_available` and `confidence_tier`, so downstream
users can see how much evidence supports each value. Nothing is silently
imputed.

**Data-hygiene sentinels.** The fire geodatabase contains OLE-epoch null
dates (1899-12-30; masked along with everything pre-1900), year-typo
dates (coerced to missing), and 1 January "placeholder" ignition dates
(flagged `jan1_ignition`, retained — dropping them would delete real
fires whose day-of-year was unknown).

**DRFA hazard vocabulary.** Free-text hazard descriptions are mapped by
substring tokens to five classes {fire, flood, tc, storm, other}; events
with no usable end date receive an assumed duration by class (fire 21 d,
flood 14 d, tc 7 d, storm/other 3 d). ***Inference:*** the durations are
order-of-magnitude judgments, not calibrated estimates; they matter only
for how long a DRFA event contributes to the daily activation count.

---

## 2. Stage 1 — ingestion and harmonisation (scripts/loaders/)

### 2.1 FIRMS hotspots (`hotspots_firms.py`)

*Input:* NASA FIRMS archive downloads (CSV/zip): MODIS Collection 6.1
(Terra + Aqua, Nov 2000–) and VIIRS 375 m Collection 2 (S-NPP, 2012–).
*Processing:* rows from any satellite other than Terra, Aqua, or S-NPP are
discarded in code (the S-NPP restriction is enforced here, not assumed of
the download); acquisition times (integer HHMM) are parsed to UTC
timestamps; FRP (fire radiative power, MW) is numeric-coerced (unparseable
→ NaN); exact duplicates on (lat, lon, time, sensor) are dropped.
*Output:* `hotspots_firms.parquet` — one row per detection with a
harmonised schema (lat, lon, datetime_utc, frp, sensor, confidence,
source).

### 2.2 Tropical cyclones (`tc_besttrack.py`)

*Input:* the BoM best-track database (IDCKMSTM0S.csv), 6-hourly fixes with
central pressure and maximum wind. *Processing:* fixes are bucketed to
UTC+10 days; per day the loader computes `n_tcs_active` (distinct storms
with a fix that day) and `tc_max_wind` (maximum wind across all fixes);
the full 1979–present range is reindexed with zeros on cyclone-free days
(a zero is informative here: the track archive is complete). *Output:*
`tc_daily_panel.parquet`.

### 2.3 Victorian Total Fire Bans (`tfb_vic.py`)

*Input:* the CFA declaration history (UTF-16 CSV; declarations name
districts and a date-time span). *Processing:* district strings are
matched against the known CFA district list, longest-name-first so that
e.g. "West and South Gippsland" is not mis-parsed as "South West";
whole-of-state declarations are flagged; each declaration is expanded
across its span; the daily panel records the maximum number of districts
under a ban. Revocations are not subtracted (a v0 simplification —
declared-then-revoked days remain counted). *Output:*
`tfb_daily_panel.parquet`, 1945–present.

### 2.4 DRFA activations (`drfa_activations.py`)

*Input:* the Commonwealth Disaster Recovery Funding Arrangements
activation register (one row per event × local government area, start
dates only), plus two "donor" catalogues that do carry end dates: the ICA
Historical Normalised Catastrophe list and the AIDR Disaster Mapper.
*Processing:* LGA rows are collapsed to events (keyed by AGRN), keeping
the earliest start date, the set of states, and `n_lga` (footprint size).
Because the register lacks end dates, each event's end is attached by a
priority cascade: (1) a date range parsed out of the event *name* if
present; (2) the best-matching donor event — required to share a hazard
class and a state, to start within 14 days, then ranked by start-date
proximity, token-set (Jaccard) name similarity with 72 stop-words
removed, and ICA-before-AIDR priority; zero-duration donors are excluded;
(3) failing both, the class-based assumed duration (§1). A guard rejects
donor ends earlier than the start. Every event records which of the four
sources supplied its end date. *Output:* `drfa_events.parquet` and, after
daily expansion, `drfa_daily_panel.parquet` (active-event count and
active-LGA count per day, 2006-03-20 →).

***Inference:*** the elaborate end-date machinery exists because an
activation with no duration cannot enter a *daily* index at all; the
per-event provenance label is the honesty mechanism. This is nonetheless
the single most heuristic piece of the ingestion layer (§10), and the
donor-matching logic has **no unit tests** — a genuine coverage gap.

### 2.5 AGCD rainfall (`agcd_rain.py`; v0.2, adoption gate pending)

*Input:* `agcd_rain_daily.csv`, produced on the Gadi supercomputer
(§8.1) — six columns per day: the fraction of Australian (and separately
SE-Australian) land area whose 1-, 3-, and 7-day rainfall accumulation
exceeds the local per-cell, per-calendar-month 95th percentile of wet
days. *Processing (local):* schema and range validation ([0, 1] or NaN;
out-of-range raises). *Known accepted quirk:* AGCD's "day" is the 24 h
ending 09:00 local time, so its rain day leads the project's UTC+10 day
by ~9 hours; this is documented and accepted at daily resolution rather
than corrected.

### 2.6 DEA hotspots (`hotspots_dea.py`) — validation only

Geoscience Australia's independent hotspot archive, harmonised to the
FIRMS schema through column-alias mapping, clipped to an Australian
bounding box, and streamed in 1M-row chunks to respect the 17 GB RAM
budget. Never feeds the index; consumed only by the cross-validation
(§7.2).

---

## 3. Stage 2 — attaching hotspots to mapped fires (scripts/fire_association.py)

**Purpose.** A satellite detection says *something is burning here today*;
a fire polygon says *a named fire eventually covered this footprint*.
Joining them converts anonymous detections into per-fire daily activity —
needed because workload metrics (how many *distinct* fires; how many *new*
fires) require fire identity, which raw detections lack.

**The temporal gate is the scientifically load-bearing step.** Fire
polygons are permanent map shapes; without a time gate, a 2019 detection
would happily "match" a 1983 fire scar it happens to fall inside. Each
fire gets a plausible burn window: (ignition − 3 days) to
(max(extinguish date, capture date, ignition + 21 days) + 3 days), with a
fallback cascade when dates are missing and a typo guard when the
computed end precedes ignition. The ±3-day gate absorbs satellite revisit
gaps and date imprecision; the 21-day default is the assumed lifetime of
a fire with no recorded end. ***Inference:*** these constants are
judgment values; sensitivity to them was not tested in code, but their
effect is bounded — a wrong window mis-assigns detections between the
"matched fire" and "satellite-only cluster" pathways (§4), both of which
feed the same daily metrics.

**Spatial matching.** Polygons (streamed from the geodatabase in
20,000-fire chunks; geometries Douglas-Peucker-simplified with 100 m
tolerance) and detections are projected to the Australian Albers
equal-area CRS (EPSG:3577); a detection matches a fire if it lies within
**1.5 km** of the footprint and inside the burn window. Matching proceeds
month-by-month to bound memory. Where multiple agency captures of the same
fire overlap, the match with the tightest temporal window (then the
smallest area) wins — temporal precision is more diagnostic of "the same
fire" than footprint size.

**A deliberate engineering compromise with methodological consequences:**
the geodatabase can only be read at practical speed with GDAL's polygon
organisation disabled, which yields topologically *invalid* multipart
geometries (interior holes become shells). Every downstream geometric
operation is therefore restricted to validity-blind primitives
(non-topology-preserving simplify; distance-within joins). The effect of
hole-filling is to make footprints slightly *larger*, i.e. matching is
marginally more permissive; at a 1.5 km buffer this is second-order.

**Tier-3 pathway.** For the pre-satellite era the same burn-window logic,
applied to *all* polygons without geometry, yields a single national
daily count of active burn windows (`burn_window_daily`) — the only fire
signal available before November 2000. This is live code consumed by
`run_dli.py` (an earlier internal review note calling it orphaned was
wrong; verified against `scripts/run_dli.py:31`).

*Outputs:* `fire_polygons_windows.parquet`, `hotspot_fire_matches.parquet`,
`fire_daily.parquet`, `hotspots_unmatched_idx.parquet`.

---

## 4. Stage 3 — clustering unmatched detections (scripts/satellite_clusters.py)

**Purpose.** Most Australian burning — especially routine northern-savanna
fire — is never mapped as a polygon, so most detections match nothing in
Stage 2. To count *fires* rather than *detections*, the leftovers are
grouped into fire events by spatio-temporal clustering.

**Method.** ST-DBSCAN implemented by embedding time as a third spatial
coordinate: detections are projected to EPSG:3577 kilometres, time is
scaled at 2.5 km/day, and standard DBSCAN runs with **eps = 5 km** and
**min_samples = 3**, so that detections within ~5 km and ~2 days of a
core point join the same cluster. Clustering is done independently within
each July–June fire season (labels `SAT_{season}_{n}`), which bounds
memory and prevents label collisions; season boundaries at 1 July fall in
the fire-quiet austral winter for the fire-prone south. Isolated
detections (fewer than 3 companions) are treated as noise and dropped.

***Inference on parameter choice:*** 5 km/2 days matches the scale of a
single fire complex as seen by 375 m–1 km sensors with ~daily revisit;
`min_samples = 3` suppresses single-pixel false alarms at the cost of
losing genuinely small single-detection fires. No sensitivity analysis of
these values exists in the repository — a fair criticism (§10) — but the
metrics they feed are percentile-ranked (§6.1), which mutes moderate
changes in absolute counts.

*Outputs:* `satellite_fire_matches.parquet`, `satellite_fire_daily.parquet`.

---

## 5. Stage 4 — daily fire workload metrics (scripts/demand_metrics.py)

**Purpose.** Convert per-fire-per-day activity into metrics chosen to
proxy *response workload* rather than area burned.

Each fire-day (from both pathways combined) carries a detection count,
summed FRP, and a mean-coordinate centroid. Centroids are assigned to a
state by point-in-polygon, with a nearest-state fallback for
coastal/offshore centroids so nothing is silently dropped. Per region —
national ("AUS"), a south-east Australia box (140–154° E, 39–28° S,
"SEAUS"), and each state — the following daily metrics are computed:

- **concurrent_burden** — distinct fires active (every active fire needs
  crews, whatever its size);
- **ignition_load** — fires on their first observed day (new incidents
  drive dispatch);
- **growth_load** — Σ max(0, today's detections − yesterday's) per fire,
  resetting when a fire skips a day (escalation, not steady burning,
  drives surge demand; the reset prevents stale carry-over across
  detection gaps);
- **frp_load** — total fire radiative power (physical intensity);
- **dispersion_km** — mean pairwise great-circle distance between active
  fire centroids (NaN with < 2 fires): how *spread out* the load is;
- **n_states_active** and **unseasonal_hotspots** — detections occurring
  outside the state's climatological fire season, defined per state as
  the minimal set of months holding ≥ 80% of cumulative FRP.

The SEAUS duplicates exist because national counts are dominated by
routine, low-consequence savanna burning: without them, a catastrophic
Victorian fire day can look nationally unremarkable. Note that
`dispersion_km`, `n_states_active`, and `unseasonal_hotspots` are computed
and stored but are **not** DLI components; ***Inference:*** they are
pre-built substrate for the Phase 3 compounding analysis.

*Outputs:* `fire_days.parquet`, `fire_seasons.json`,
`demand_metrics_daily.parquet`.

---

## 6. Stage 5 — the Demand Load Index (scripts/dli.py, scripts/run_dli.py)

### 6.1 Percentile ranking

Raw components live on incommensurable scales (fire counts; megawatts;
LGAs; area fractions). Each of the **17 components** is converted to a
percentile rank in (0, 1] computed **within its (confidence tier ×
calendar month) group** (pandas `rank(pct=True)`, average-rank ties, NaN
passthrough). The month grouping removes seasonality — January being
busier than June is climate, not information; the tier grouping prevents
satellite-era step changes from contaminating ranks. This is the single
most consequential statistical decision in the project: it converts every
"how much?" into "how unusual for this month, in this data era?" — which
is the correct question for an anomaly index, at the price of discarding
absolute magnitudes (§10).

### 6.2 Component table

| Component | Source | Availability |
|---|---|---|
| fire_burden, fire_ignitions, fire_growth, fire_intensity | Stage 4, AUS | zero-filled tiers 1–2; NaN tier 3 |
| seaus_burden, seaus_intensity | Stage 4, SEAUS box | as above |
| fire_windows | Tier-3 polygon burn-window count | tier 3 only |
| drfa_load, drfa_lga | DRFA daily panel | 2006-03-20 → |
| tfb_load | Victorian TFB districts | 1945 → |
| tc_load, tc_severity | TC daily panel | 1979 →, zero-filled |
| rain{1,3,7}d_area, seaus_rain{1,3,7}d | AGCD (Gadi) | 1979 →, reindex only — **never** zero-filled |

### 6.3 Subindices and the index

Percentiles fold into five **hazard subindices**; the DLI is the
equal-weight mean of whichever subindices are available that day:

- `sub_fire` = mean of the seven fire percentiles (skipna);
- `sub_tc` = **max**(tc count percentile, tc max-wind percentile);
- `sub_drfa` = the LGA-footprint percentile (not the event count);
- `sub_tfb` = the TFB percentile;
- `sub_flood` = mean of the six rain percentiles (skipna, with an explicit
  all-NaN guard) — v0.2, in the code but pending its adoption gate.

The structure encodes three failure modes that were tested and rejected
during development (recorded in CLAUDE.md and the git history, and
therefore observations, not inferences):

1. a **flat mean of all components** dilutes single-hazard catastrophes
   (ten quiet fire components average away one screaming cyclone — TC
   Yasi scored unremarkably);
2. a **top-k mean** suffers order-statistic inflation (the top-3 of ~11
   near-uniform ranks averages ≈ 0.83 on an ordinary day);
3. **count-style components saturate** (one active TC is common, so the
   count percentile ties at ≈ 0.7 and cannot distinguish Yasi from a
   fizzler) — hence max-with-severity for TC and the LGA footprint for
   DRFA.

*Output:* `demand_daily_panel.parquet` — per day: 17 components, 17
percentile columns, 5 subindices, `dli`, `confidence_tier`,
`n_components_available`; plus `dli_top50_days.csv` (top 50 per tier).

---

## 7. Validation

### 7.1 The 12-event benchmark (run_dli.py)

Twelve well-known extreme events, each anchored to a peak date: Ash
Wednesday (1983-02-16), NSW Jan 1994 (1994-01-08), VIC Dandenongs
(1997-01-21), Canberra (2003-01-18), Black Saturday (2009-02-07), TC Yasi
(2011-02-02), TAS Dunalley (2013-01-04), NSW Blue Mountains (2013-10-17),
TAS fires (2016-01-20), QLD Deepwater (2018-11-28), Black Summer peak
(2020-01-04), east-coast floods (2022-02-28). For each, the script
reports the fraction of same-tier days with strictly lower DLI (a
left-exclusive within-tier percentile).

Current results: **seven of twelve at or above the 95th percentile**
(Black Saturday 99.93, Ash Wednesday 99.67, Dandenongs 99.61, Canberra
99.61, Dunalley 98.72, Black Summer 97.76, NSW Jan 1994 95.30);
near-misses TC Yasi 92.91 and Blue Mountains 89.59; honest misses the
2022 floods 82.57 (DRFA was the only flood-sensitive component and
persists for weeks), TAS 2016 60.72 and Deepwater 2018 69.82 (regionally
severe, nationally moderate).

**What this does and does not validate.** The events were selected
*because* they are known high-demand days, and some components (TC
tracks, DRFA) directly encode those same events — so this is a
**face-validity check of the combiner**, not independent validation: it
shows the recipe surfaces known extremes without dilution or inflation.
The documented governance rule prohibits tuning the combiner to raise
these numbers (overfitting 12 points), and any recipe change must keep
the seven ≥95th fire events at or above the 93rd. An earlier overstated
summary ("9/12 ≥ 93rd") was found and corrected project-wide.

### 7.2 FIRMS vs DEA cross-validation (run_crossval.py)

Because Tiers 1–2 rest entirely on FIRMS, its daily national detection
counts per sensor family were compared with Geoscience Australia's
independently processed DEA archive. Three fairness corrections, all
DEA-side: geographic clipping to Australia; removal of ~22% exact
duplicate rows (DEA ingests the same pass under multiple algorithms);
per-sensor-family overlap windows (DEA's S-NPP record starts later —
absence of archive is not disagreement). Agreement is measured by
Spearman rank correlation of daily counts, because the DLI consumes
*ranks*, not counts. **Result:** MODIS Spearman 0.92 over 2002–2018,
passing the pre-declared ≥ 0.90 gate and fully covering Tier 2; post-2019
divergence (0.87/0.79) is attributable to DEA's inflated multi-algorithm
live feed. Conclusion: the FIRMS record is not idiosyncratic.

### 7.3 Flood-event diagnostic (run_flood_validation.py)

Seven dated historical flood peaks (each date verified against
gauge/portal records — e.g. Brisbane River peak 2011-01-13; Fitzroy
Crossing record 2023-01-04) are printed with their `sub_flood` value,
within-tier percentile, and the six rain component percentiles.
Explicitly diagnostic (print-only, no pass/fail): localized events like
Warmun may legitimately sit low nationally. The formal **adoption gate**
for the flood component is separate: the 2022-floods benchmark must rise
above its current 82.57 with no fire benchmark falling below the 93rd —
and if it fails, the documented protocol is to report and stop, not
iterate.

### 7.4 Phase 2 statistics: SWT attribution (run_phase2_swt.py)

**Question:** which of the 30 synoptic weather types are over-represented
on high-demand days? **High-demand day:** DLI ≥ its tier's 95th
percentile (a pooled threshold would simply select modern days).

**Estimator — month-matched relative risk.** For each SWT: observed rate
of high-demand days under that SWT, divided by the rate *expected from
the calendar months in which that SWT occurred* (the pooled per-month
high-demand proportions, averaged over the SWT's days). The null
hypothesis is RR = 1: the type adds no risk beyond its seasonal timing.
This directly neutralises the objection that summer types would "win"
merely by co-occurring with the fire season.

**Uncertainty — moving-block bootstrap.** Daily series are strongly
autocorrelated (a fire season persists for weeks), so i.i.d. resampling
would give dishonestly narrow intervals. Instead, 1,000 resamples of
contiguous **30-day blocks** (with wraparound at the series end) rebuild
the series; resampled days keep their original calendar months so the
month-matched baseline stays honest inside every resample; the CI is the
2.5th–97.5th percentile of resampled RRs. Seeded, hence reproducible.

**Results:** all-period, only AM-E (RR 1.52 [1.30–1.74]) and AM-B (1.27
[1.02–1.50]) clear 1; within Tier 1, TH-C reaches 2.00 [1.29–2.83];
several types actively suppress demand (COL-A 0.19, EH-A 0.39, WCT-B
0.52). Strikingly, FH-B — the champion of multi-state fire *danger* in
the predecessor study (danger RR 2.13) — shows **no demand enrichment**
(0.69): national demand is multi-hazard, and its weather types are not
the fire blocking highs.

**Limitations, disclosed:** (i) no multiplicity correction is applied
across the 30 simultaneous CIs — with 30 types, one or two spuriously
"significant" intervals are expected by chance, so the per-type CIs are
evidence, not confirmatory tests; (ii) month-matching controls seasonal
prevalence but not sub-monthly confounding; (iii) enrichment is
association, not mechanism; and (iv) — most seriously — the independent
audit of the predecessor found that archetypal hot-northerly fire
catastrophes (Black Saturday; 2020-01-04) are *classified as AM types*,
so the AM enrichment may partly consist of misfiled fire-catastrophe
days. The classifier itself has not been audited. For exactly this
reason the project has demoted the SWT attribution to a consistency
check and specified a classification-free composite analysis as the
primary attribution method (spec in
`docs/superpowers/specs/2026-07-07-demand-composites-pilot-design.md`).

---

## 8. HPC extractions (gadi/)

Two computations are too large for the 17 GB local machine and run on
NCI Gadi via PBS, with results returned as small CSVs/netCDFs.

### 8.1 AGCD rainfall components (`extract_agcd_rain.{py,pbs}`)

For each of the 1/3/7-day rolling accumulations of the 0.05° AGCD daily
rainfall grid: restrict to wet values (≥ 1 mm); compute each cell's
per-calendar-month 95th percentile over the 1979–2023 base period; for
every day output the fraction of land cells exceeding their threshold,
nationally and in the SEAUS box. Land = cells with non-missing rainfall.
Output dates are normalized from AGCD's 09:00 stamps. Job: 14 CPUs,
120 GB, ≤ 6 h. Two implementation lessons are baked into the code and the
project instructions: dask's grouped quantile requires the entire time
axis in a single chunk (the first submission crashed on this), and the
script exposes a `--dry` flag (6-year subset) because local unit tests on
in-memory arrays *cannot* reach chunked-execution failures — every Gadi
script now gets a ~1-SU dry run before the full job.

### 8.2 FFDI summaries and map slabs (`extract_ffdi.{py,pbs}`)

Reads the precomputed BARRA-R2 FFDI zarr (1979–2023) in one full-array
pass (year-by-year chunked reads are ~50× slower); outputs (a) daily
national/SEAUS summaries (land-mean FFDI; area fractions ≥ 50 "Severe"
and ≥ 75 "Extreme") and (b) 2-D FFDI slabs for ~148 landmark dates, as a
compressed netCDF for the R map figure. **Status:** the planned FFDI
*component* is parked (the index recipe is frozen); only the map figure
consumes these outputs.

---

## 9. Presentation layer (R/, notebook)

R scripts (run via the `rfigs` conda environment) read only exported
CSVs/netCDF — no analysis logic: a tier-faceted DLI time series with a
90-day rolling mean and the 12 numbered benchmark events; hotspot maps of
landmark days (points sized by FRP); a DRFA choropleth on 2025 ABS LGA
boundaries (100% name join after two documented ABS renames applied in
the export script); and FFDI danger-footprint maps for the ten *fire*
benchmark days (TC/flood days excluded — FFDI is a fire-danger quantity
and is uninformatively low on them). One technical trap is documented in
code: R's ncdf4 reverses xarray's dimension order, and the plotting code
indexes accordingly.

`EM_Demand_Phase1.ipynb` was verified cell-by-cell to contain **zero
analysis logic**: it loads checkpoints, invokes the runner scripts by
subprocess, and displays results. It is the human-readable end-to-end
exhibit of the (now frozen) Phase 1, re-executable in ~1 minute.

---

## 10. Hidden assumptions and potential weaknesses (consolidated, critical)

Ordered roughly by potential to bias results.

1. **Demand is proxied, not measured.** No national daily record of actual
   resource deployment exists back to 1979. Every component is a *trace*
   of workload (detections, activations, declarations), and the index's
   meaning rests on the assumption that these traces co-vary with true
   demand. This is acknowledged in the documentation and is the
   irreducible limitation of the study.
2. **DRFA is an administrative, not physical, signal.** Activations lag
   and persist for weeks (visible in the 2022-floods benchmark miss),
   their end dates are attached by heuristic donor matching (untested
   code), and until the flood component is adopted, DRFA is the *only*
   flood- and storm-sensitive component. The pilot-composites spec now
   explicitly refuses to treat DRFA-dominant days as a hazard stratum.
3. **The Tier-3 fire signal is one column.** Pre-2000 `sub_fire` is
   solely the count of open polygon burn windows — no intensity, growth,
   or location content — and those windows are themselves ~21-day
   imputations when end dates are missing. The predecessor audit showed
   burn-window imputation is exactly the kind of assumption that can
   dominate results; within-tier ranking prevents cross-era
   contamination, but Tier-3 DLI values are categorically weaker
   evidence. (The FFDI component would have strengthened this era; it
   was consciously parked when the index was frozen.)
4. **No multiplicity control in Phase 2** across 30 simultaneous RR
   intervals (§7.4); the predecessor study applied per-table
   Benjamini–Hochberg, this one does not. Any single "significant" type
   should be read accordingly.
5. **The SWT classifier is unaudited and suspect** for exactly the family
   (AM) that carries the headline enrichment (§7.4-iv). The project's
   response — demote and replace with composites — is appropriate, but
   until then the Phase 2 result should not be cited without the caveat.
6. **Benchmark circularity.** Some components encode the benchmark events
   directly; the 12-event table is a combiner check only (§7.1). The
   governance rules (no tuning; fixed gates) are the mitigation.
7. **Clustering and matching parameters are untested judgment values**
   (1.5 km buffer; ±3-day gate; 21-day default window; 5 km/2-day
   DBSCAN; min_samples 3; 80% FRP season share). Percentile ranking
   mutes but does not eliminate sensitivity; no formal sensitivity
   analysis exists.
8. **Equal weighting of subindices** is a modelling choice with no
   empirical calibration — defensible as the least-informative prior, and
   the tested alternatives were worse, but "demand" as measured is the
   *average unusualness across hazards*, not a calibrated workload.
9. **Percentile ranks discard magnitude.** Within-group ranking means the
   worst day of a quiet month can outrank a moderately bad day of an
   awful month; the DLI measures relative unusualness, not absolute load.
10. **Geometric compromises.** Invalid (hole-filled) polygons make
    matching slightly permissive; centroid-based state assignment can
    misattribute sprawling or coastal fires, and the nearest-state
    fallback has no deterministic tie-break; SEAUS filtering is by
    centroid, so a fire straddling the box boundary is all-in or all-out.
11. **Temporal quirks accepted at daily resolution:** the fixed UTC+10
    day (±1 h across states, duplicated constant in four modules); the
    AGCD 09:00 rain-day offset (~9 h lead); block-bootstrap wraparound
    joining the series end to its start (negligible at n ≈ 17,000 with
    30-day blocks).
12. **Silent robustness choices:** date typos fall back to assumed
    windows without logging; NaN FRP sums to zero in aggregates; TFB
    revocations not subtracted. Each is small; none is documented as
    having been quantified.
13. **Test coverage is strong on pure logic (56 passing tests) but absent
    exactly where heuristics live:** DRFA donor matching, the DEA loader,
    bootstrap CI coverage, and everything that only fails at HPC scale
    (hence the new mandatory Gadi dry-run rule).

---

## 11. Reproducibility

**Software.** Python 3 (Anaconda; pandas 2.x, geopandas 1.1.3, shapely
2.1.2, pyarrow 21, scikit-learn 1.7.2, pyogrio); R via a dedicated conda
environment invoked through `Rscript` (rpy2 unusable); on Gadi, the
`xp65 conda/analysis3` environment via PBS `qsub` only. A 17 GB-RAM
machine suffices locally if the documented streaming/chunking discipline
is followed.

**Datasets to obtain** (paths configured in `scripts/config.py`): FIRMS
archive CSVs (MODIS C6.1 + VIIRS S-NPP C2); the Historical Bushfire
Extents geodatabase (~847 MB, not in git); BoM TC best-track CSV; DRFA
activation register + ICA and AIDR catalogues; CFA TFB history; DEA
Hotspots export (validation only); the SWT climatology CSV (vendored);
AGCD rainfall on Gadi (`/g/data/zv2/...`); BARRA-R2 FFDI zarr on Gadi
(maps only).

**Execution order** (each step checkpoints; ~4 min total locally once raw
data are staged, excluding Gadi jobs):

1. Loader extractions (FIRMS parquet, TC, TFB, DRFA panels).
2. `run_fire_association.py` (~2 min) → matches, windows, unmatched idx.
3. `run_satellite_clusters.py` (~1 min) → satellite fire events.
4. `run_demand_metrics.py` (~30 s) → daily metrics panel.
5. Gadi: `extract_agcd_rain.pbs` (dry run first) → `agcd_rain_daily.csv`
   → `data/raw/agcd/`.
6. `run_dli.py` (~5 s) → `demand_daily_panel.parquet` + the printed
   benchmark table (the numbers in §7.1 should reproduce exactly).
7. `run_exports.py` → CSVs; R scripts → figures.
8. Optional: `run_dea_extract.py` + `run_crossval.py` (validation);
   `run_phase2_swt.py` (attribution; seeded, reproduces §7.4);
   `run_flood_validation.py` (diagnostic).
9. `pytest tests/ -q` → 56 passing; the notebook re-executes end-to-end
   via nbclient (nbconvert silently no-ops in this environment).

---

## 12. The study as a whole

**Research question.** What is the synoptic meteorology of days that
place extreme, potentially spatially compounding, demand on Australia's
national emergency-management system?

**Primary contribution (method).** The DLI itself: a reproducible,
availability-disciplined, tier-honest daily reconstruction of national
emergency demand over 47 years, from sources never previously combined —
with its limitations quantified rather than hidden.

**Secondary contributions.** (i) The FIRMS-vs-DEA cross-validation — an
independent check of the fire record underpinning two decades of the
index, with three documented DEA-side artefacts corrected. (ii) The
commissioned audit of the predecessor study, which sorted its claims into
citable (danger synchronisation; the danger→fire conversion null) and
fragile (realized-fire RRs; AM-family labels). (iii) The month-matched
RR + block-bootstrap machinery, reusable for any daily categorical
exposure.

**Hypotheses tested so far.** One: *specific synoptic weather types are
over-represented on high-demand days beyond their seasonal timing* (null
RR = 1). Finding: yes for AM-E/AM-B (and TH-C in the modern era), no for
the fire blocking highs — but the positive finding carries the classifier
caveat. The next registered hypothesis (specified, not yet run): *distinct
hazards generating high demand arise from distinct large-scale
atmospheric configurations*, tested by hazard-stratified ERA5 composites
with pre-registered anomaly-sign predictions.

**Major findings to date.** (1) National emergency demand is genuinely
multi-hazard: the weather types that drive it are not the fire-danger
types — the fire-danger champion FH-B shows no demand enrichment. (2) The
index reproduces seven of twelve landmark extremes above the 95th
percentile without tuning, with its misses understood (flood-blindness →
the v0.2 rainfall component; regional-vs-national severity). (3) The
FIRMS fire record is consistent with an independent archive where their
sensors overlap.

**Methods vs results.** Stages 1–6 and the Gadi extractions are methods;
§7.1–7.3 are validation of the instrument; §7.4's RRs are the only
*scientific result* produced so far, and the project itself now treats
them as provisional pending the composite analysis.

**Internal inconsistencies, honestly stated.** The repository records a
mid-course correction: Phase 1 was drifting toward index-building as an
end in itself (an FFDI component was planned and its data even
extracted), and Phase 2 leaned on an unverified classifier. On
2026-07-07, following the audit and a strategic review, the index was
frozen (pending one last gated component), the FFDI component parked, and
attribution re-founded on classification-free composites. The
documentation (`METHODOLOGY.md` §10) now reflects this; older plan files
retained for the record (`docs/superpowers/plans/2026-07-07-ffdi-component.md`)
describe work that will deliberately not happen. Residual loose ends: the
duplicated UTC-offset constants; the untested DRFA donor matching;
`dispersion_km`/`n_states_active`/`unseasonal_hotspots` computed but not
yet consumed (Phase 3 substrate); and Phase 3–4 module stubs that raise
NotImplementedError by design.
