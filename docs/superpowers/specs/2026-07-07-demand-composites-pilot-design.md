# Do distinct hazards produce distinct synoptic fingerprints of demand? — pilot design

**Date:** 2026-07-07 (revised same day after review) · **Status:** for user
review · **Depends on:** Phase 1 panel; the flood stratum additionally
requires the sub_flood adoption gate to pass.

## 1. The scientific question

> **Do the different hazards that generate high national emergency-management
> demand arise from distinct large-scale atmospheric configurations?**

This is a hypothesis, not a description. It is falsifiable in both
directions, and either outcome is informative:

- **If yes** (fire-driven, cyclone-driven and flood-driven high-demand days
  have significantly different composite anomaly patterns), then "national
  EM demand" is not one meteorological phenomenon — it is several, and any
  forecasting, attribution, or capacity argument must treat the pathways
  separately. This is also the physical premise of the compounding phase:
  spatially compounding demand means *different* synoptic drivers loading
  the system at once, which only makes sense if the drivers are in fact
  distinct.
- **If no** (the composites are indistinct or mutually cancelling even
  after stratification), the hazard-pathway framing is wrong or the DLI's
  subindices do not separate hazards as intended — either way a result that
  must be known before building the compounding analysis on top.

**Secondary question (audit follow-up):** does the fire-demand composite
show the blocking-high / hot-northerly structure that the Fires_SWTs
*danger* result predicts? The audit found Black Saturday classified as
"active monsoon"; the composite tests the meteorology directly, with no
classifier in the loop. A monsoon-like fire composite would confirm the
classifier problem; a blocking-high fire composite coexisting with the
AM-E enrichment would show the SWT labels — not the atmosphere — are the
weak link.

### What this answers that the SWT analysis cannot

The Phase 2 SWT attribution asks "which *pre-defined* weather types are
over-represented on high-demand days?" — it can only ever return an answer
inside the Barnes classification, and the audit showed that classification
misfiles landmark days. Composites are **classification-free**: the days
are selected by demand and hazard, and the atmosphere is averaged as it is.
(Not "pattern-agnostic" — it is still pattern analysis; the patterns are
just discovered from the data rather than imposed.) Accordingly, this
analysis **supersedes the SWT attribution as the primary attribution
result**; the SWT RRs are demoted to a consistency check against it.

## 2. Day selection and stratification

- **Population:** days with DLI ≥ the 95th percentile within their
  confidence tier, 1979–2023 (~820 days; same selection as the SWT
  attribution, so the two are directly comparable).
- **Strata = argmax of the hazard subindices** on each day — no tuned
  threshold anywhere:
  - **fire** — `sub_fire` or `sub_tfb` largest (a total fire ban is a
    fire-danger decision, so it identifies the same hazard pathway);
  - **tc** — `sub_tc` largest;
  - **flood** — `sub_flood` largest. *Exists only if the adoption gate
    passes;* if it fails, the flood fingerprint cannot be tested in this
    pilot and the spec says so rather than substituting a proxy;
  - **drfa-led** — `sub_drfa` largest. **This stratum is not a hazard.**
    DRFA is a funding activation: it mixes hazards and lags the causal
    meteorology by days-to-weeks. It is composited *descriptively* (its
    incoherence or lagged character is itself worth seeing) but it is
    **excluded from the hypothesis test**, which compares fire vs tc vs
    flood only.
- **No "multi-hazard" stratum in the pilot.** The earlier draft defined one
  via an arbitrary cutoff (two subindices ≥ 0.90 — indefensible; why not
  0.85 or 0.95?). Defining what a compound-demand day *is* belongs to the
  state×hazard compounding panel, where it can be done on principled
  grounds. The pilot instead **reports the margin between each day's top
  two subindices** (distribution + table of near-ties), which is exactly
  the evidence that future definition needs.
- Assignment logic is a pure, unit-tested function
  (`scripts/composite_strata.py::assign_strata`); a thin runner writes
  `demand_stratum_days.csv` (`date,stratum`) for Gadi and prints stratum
  counts and the top-two-margin table. Strata with n < 30 are reported but
  not composited (too noisy to interpret).

## 3. Fields and anomalies

ERA5 (Gadi `rt52`), daily 12 UTC, lon 80–180 / lat −60 to −5, 4× coarsened
(identical domain/processing to the audited Fires_SWTs composites):

| Output | ERA5 var | Level | Why |
|---|---|---|---|
| `msl` | msl | single | circulation type: ridge vs closed low |
| `t850` | t | 850 hPa | heat advection (fire) vs tropical air |
| `u850`, `v850` | u, v | 850 hPa | the northerly-flow question directly |
| `tcwv` | tcwv | single | moisture: separates TC/flood from fire |

Anomalies are day-of-year anomalies (each day minus the 1979–2023
climatology for that calendar day), so a composite never shows mere
seasonality. Computed by `fires_swts/gadi/composite_core.py::
doy_anomaly_composite`, reused verbatim with stratum labels in place of
SWT labels — the same audited code that reproduced every Fires_SWTs number.

## 4. Computation (Gadi)

`gadi/demand_composites.py` + `.pbs`: light adaptation of
`fires_swts/gadi/era5_swt_composites.py` (swap label CSV, add tcwv, drop
z500). **Dry run first** (2 years) per the standing rule, then the full job
(~5–15 SU). Output `demand_composites.nc` (per stratum × field: mean, anom,
p, n_days; a few MB) → user copies to `data/raw/composites/` (gitignored).

## 5. How "distinct" is judged

1. **Primary, qualitative but pre-registered:** the hypothesis predicts
   *sign-opposite* MSLP anomalies (fire: positive/ridge; tc: deep negative)
   and *sign-opposite* TCWV anomalies (fire: dry; tc/flood: moist) over the
   relevant sectors. These predictions are written down here, before the
   maps exist.
2. **Supporting:** pointwise p < 0.05 stippling from the composite t-test,
   with two disclosed caveats carried into captions: no field-wise
   multiplicity correction (stippling is descriptive), and serial
   dependence within events makes it anti-conservative.
3. A formal field-significance / pattern-separation test (e.g. composite
   pattern correlation with block-resampled nulls) is deliberately deferred
   to the full analysis — the pilot decides whether that machinery is worth
   building.

## 6. Figures

`R/demand_composites.R` (rfigs env, house style): one figure per field
family, panels = strata (each titled with stratum and n):
`fig_composite_msl.png` (anomaly fill + mean contours),
`fig_composite_t850_wind.png` (T anomaly fill + wind anomaly vectors),
`fig_composite_tcwv.png`. README "Figures" section updated.

## 7. Out of scope

BARRA-R2 (full analysis only — resolution buys nothing at synoptic
composite scale); weather objects (own pipeline, follows in the full
analysis); lagged/build-up composites (Phase 3); any change to the frozen
DLI recipe; formal compound-day definition (compounding panel).

## 8. Testing & validation

- `tests/test_composite_strata.py`: argmax assignment, tfb→fire folding,
  flood-column-absent behaviour, NaN subindices, margin computation.
- `composite_core.py`: already unit-tested and audit-verified; not modified.
- Face-validity gate on delivery: the tc composite must show a closed low
  with high TCWV — if the machinery can't recover a cyclone from cyclone
  days, nothing else is interpretable.
