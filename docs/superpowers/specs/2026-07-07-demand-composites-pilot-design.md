# Pilot: ERA5 composite maps of high-demand days, stratified by hazard — design

**Date:** 2026-07-07 · **Status:** approved in conversation (option C), spec
for review · **Depends on:** Phase 1 panel (`demand_daily_panel.parquet`);
independent of the flood adoption gate.

## 1. Purpose

The strategic pivot (METHODOLOGY.md §10) calls for **pattern-agnostic
meteorology**: instead of asking which pre-baked SWT label is enriched on
high-demand days (a result now carrying the §7.5 AM caveat), ask directly —
*what is the atmosphere actually doing on high-demand days?* This pilot
produces composite anomaly **maps** of the synoptic fields on those days,
stratified by which hazard drove the demand. It is deliberately a pilot: it
reuses the audited Fires_SWTs compositing machinery unchanged, runs cheap
(~5–15 SU), and its output shapes the later full compound-day analysis
(which is where BARRA-R2 and the weather-object pipeline come in — NOT here).

## 2. Day selection and stratification

- **Population:** days whose DLI is ≥ the 95th percentile *within their
  confidence tier*, 1979–2023 (~820 days; same definition as Phase 2 SWT
  attribution, so results are directly comparable).
- **Stratification — dominant hazard.** Lumping all high-demand days into
  one composite would cancel opposing patterns (a cyclone day and a
  blocking-high fire day have opposite MSLP anomalies). Each day is
  assigned one stratum from its subindices:
  - **multi** — two or more subindices ≥ 0.90 that day (multiple hazards
    simultaneously extreme; the compounding-relevant stratum);
  - otherwise **fire** / **tc** / **drfa** — the argmax subindex, with
    `sub_tfb` folded into **fire** (a total fire ban is a fire-danger
    signal). If `sub_flood` has been adopted by run time it participates
    like any other subindex (stratum name **flood**); if not, flood days
    surface via **drfa**.
- Assignment logic lives in a pure function
  `scripts/composite_strata.py::assign_strata(panel) -> DataFrame[date, stratum]`,
  unit-tested; a thin runner writes `demand_stratum_days.csv`
  (`date,stratum`) for Gadi.
- Per-stratum day counts are printed and stored in the output; any stratum
  with **n < 30** is dropped from the figures (reported, not composited —
  too noisy).

## 3. Fields and anomalies

ERA5 reanalysis (Gadi `rt52`), daily 12 UTC samples, domain lon 80–180 /
lat −60 to −5, 4× coarsened (identical to the Fires_SWTs SWT composites):

| Output | ERA5 var | Level |
|---|---|---|
| `msl` | msl | single |
| `t850` | t | 850 hPa |
| `u850`, `v850` | u, v | 850 hPa |
| `tcwv` | tcwv | single |

TCWV is the addition relative to Fires_SWTs (moisture matters for the
flood/TC strata); z500 is dropped (MSLP carries the story at this scale).

Anomalies are **day-of-year anomalies**: each day's field minus the
1979–2023 climatology for that calendar day
(`fires_swts/gadi/composite_core.py::doy_anomaly_composite`, reused
verbatim — the stratum label is passed where the SWT label used to go).
This removes seasonality, so a summer stratum does not just show "summer".

## 4. Computation (Gadi)

- `gadi/demand_composites.py` + `.pbs`: a light adaptation of
  `fires_swts/gadi/era5_swt_composites.py` — swap the SWT CSV for
  `demand_stratum_days.csv`, add tcwv, drop z500. Same job shape as the
  SWT-composites run (~5–15 SU on the personal 10 KSU allocation).
- Flat-directory Gadi rules apply (qsub from the directory holding the
  script + CSV + `composite_core.py` + `read_era5.py`).
- Output: `demand_composites.nc` — per stratum × field: `*_mean`, `*_anom`,
  `*_p`, plus `n_days` — a few MB; user scp's it to
  `data/raw/composites/` (gitignored).

## 5. Significance and its honest limits

`composite_core` returns pointwise two-sided p-values (t-statistic on the
day anomalies, normal approximation). Figures stipple **p < 0.05**. Two
disclosed caveats, carried into the figure captions:

1. No field-wise multiplicity correction — stippling is descriptive, not a
   formal test.
2. Days within one event/season are serially dependent, so effective n is
   below nominal n; stippling is anti-conservative. (The Phase 2 block
   bootstrap addressed this for the RRs; the pilot maps do not re-solve it.)

## 6. Figures

`R/demand_composites.R` (rfigs conda env via Rscript, house style of
`R/figs/`), reading the nc:

- `fig_composite_msl.png` — MSLP anomaly fill + mean-field contours, one
  panel per stratum, stippled.
- `fig_composite_t850_wind.png` — 850 hPa temperature anomaly fill + wind
  anomaly vectors per stratum.
- `fig_composite_tcwv.png` — column water vapour anomaly per stratum.

Each panel titled with stratum name and n. README "Figures" section updated.

## 7. Out of scope (explicitly)

- BARRA-R2 (reserved for the full compound-day analysis — higher resolution
  buys nothing at composite/synoptic scale).
- Weather objects (own pipeline, `docs/phase2_weather_objects_notes.md`).
- Lagged/build-up composites (Phase 3 idea, `docs/phase3_methods_notes.md`).
- Any change to the DLI itself (recipe frozen).

## 8. Testing & validation

- `tests/test_composite_strata.py`: stratum assignment on synthetic panels
  (dominance, the ≥0.90-twice multi rule, tfb→fire folding, NaN subindices).
- `composite_core.py` is already unit-tested (`test_composite_core.py`) and
  audited (all Fires_SWTs numbers reproduced) — reused, not modified.
- Face validity check on delivery: the tc stratum should show a closed
  MSLP low + high TCWV; the fire stratum a high/ridge with hot northerly
  850 hPa flow. If the fire composite looks monsoon-like, that is itself a
  finding (echoing the audit's AM red flag).
