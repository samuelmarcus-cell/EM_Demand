# Methodology

This document explains, step by step and in plain language, how the Demand
Load Index (DLI) is built, how it was validated, and what each statistical
test does and why it is there. It is written for a reader who is comfortable
with research methods but not necessarily with this codebase.

## 1. The research reframe

Prior work (the Fires_SWTs analysis) found that synoptic weather regimes
strongly synchronise fire *danger* across Australian states (relative risk up
to 2.13 for blocking-high types), but that realized *fire* barely expresses
this synchronisation, and no weather type converts danger into fire beyond
its seasonal timing. The implication: if you care about emergency management,
the outcome variable should be **demand on emergency resources**, not fire
occurrence. This project builds that outcome variable: a daily, national
Demand Load Index from 1979 to the present. The full predecessor analysis —
code, baked notebook, and figures — is included in this repository under
[`fires_swts/`](../fires_swts/README.md).

**How far Fires_SWTs can be trusted (audited 2026-07-07).** An independent
audit ([`fires_swts/AUDIT_2026-07-07.md`](../fires_swts/AUDIT_2026-07-07.md))
recomputed every headline number from scratch and found no errors. Its
verdicts: the danger-synchronisation results and the danger→fire conversion
null are SOLID and citable; the realized-fire RRs are FRAGILE (they depend on
a burn-window imputation and must be cited with the ignition-only
sensitivity); and a landmark-day spot-check found that Black Saturday and
4 Jan 2020 — archetypal hot-northerly fire days — are classified as "active
monsoon" (AM) types, which casts doubt on AM-family results everywhere
(see §7.5). This project therefore leans on the danger result and the
conversion null, not on the fire RRs or the AM labels.

## 2. Data sources

| Source | What it contributes | Period |
|---|---|---|
| NASA FIRMS hotspots (MODIS + VIIRS S-NPP) | Satellite fire detections: where and how intensely the landscape is burning, daily | MODIS 2000–, VIIRS 2012– |
| National Historical Bushfire Extents (fire polygons) | Mapped fire footprints with ignition dates — the only fire record before satellites | 1979– (usable) |
| DRFA activations | Commonwealth disaster-funding activations per Local Government Area — a direct trace of real emergency response, all hazards | 2006– |
| BoM tropical cyclone best-track | TC positions and intensities near Australia | full period |
| Victorian Total Fire Ban declarations | An operational decision record (how many fire districts under a ban) | 1945– |
| DEA Hotspots (Geoscience Australia) | An independent hotspot archive, used only to cross-validate FIRMS | 2002– |
| AGCD v1 daily rainfall (0.05°, Gadi) | Gridded rain — was to be the flood subindex; abandoned 2026-07-09 (§5.2) | 1900– (unused) |
| SWT climatology (Barnes) | One synoptic weather type per day, 30 types in 8 regime families | 1952– |

**Design principle — availability discipline:** every component is explicitly
NaN outside the window its source exists, and every day of the final panel
records how many components were available. Nothing is silently filled in.
Within the satellite era, a day with no detections genuinely means "no fire
activity" and is a zero, not a gap.

## 3. Confidence tiers

The fire-activity evidence changes fundamentally over time, so every day is
labelled with a confidence tier:

- **Tier 1 (2012–):** VIIRS S-NPP + MODIS hotspots (dense detections).
- **Tier 2 (2000–2011):** MODIS only (sparser).
- **Tier 3 (1979–1999):** no satellites — only mapped fire polygons and their
  estimated burn windows.

VIIRS is deliberately restricted to the S-NPP satellite. Adding NOAA-20/21
(launched 2017/2022) would create artificial step-jumps in detection density
*inside* Tier 1, which would masquerade as trends in fire activity.

All statistics that compare days against each other are computed **within
tier** so that a 1985 day is never ranked against a 2020 day whose data are
richer.

## 4. Building the daily fire-activity record

### 4.1 Attaching hotspots to known fires

Each FIRMS hotspot is matched to a mapped fire polygon if it falls within
1.5 km of the footprint **and** within the fire's plausible burn window
(ignition minus 3 days, through to the extinguish/capture date, or ignition
plus 21 days when no end date exists). The temporal gate matters: fire
footprints are permanent map shapes, and without it a 2019 hotspot could
"match" a 1983 fire scar. Where several agency captures of the same fire
overlap, the match with the tightest window (then the smallest area) wins.

### 4.2 Clustering the leftovers into satellite-only fires

Hotspots that match no polygon (most northern-savanna burning is never
mapped) are grouped into fire events by spatio-temporal clustering
(ST-DBSCAN): detections within 5 km and 2 days of one another belong to the
same fire. Isolated single detections are treated as noise and dropped.
This yields a per-fire-per-day table covering both mapped and unmapped fire.

### 4.3 Daily demand-relevant metrics

From that table, each day gets metrics chosen to proxy *response workload*
rather than area burned:

- **concurrent burden** — how many distinct fires are active (each active
  fire needs crews, whatever its size);
- **ignition load** — how many fires started today (new incidents drive
  dispatch decisions);
- **growth load** — how much fires escalated versus yesterday (escalation,
  not steady burning, drives surge demand);
- **FRP load** — total fire radiative power, a physical intensity measure.

Each metric is computed nationally **and** for a south-east Australia box.
The SEAUS versions exist because national counts are dominated by routine,
low-consequence savanna burning in the north — without them, a catastrophic
Victorian fire day can look nationally unremarkable.

Day boundaries use fixed UTC+10 (AEST, no daylight saving) everywhere, so an
afternoon and an overnight satellite pass of the same burning day land on the
same date.

## 5. The Demand Load Index

### 5.1 Percentile ranking — making apples comparable

Raw components live on wildly different scales (a count of fires; megawatts;
a number of LGAs). Each component is therefore converted to a **percentile
rank between 0 and 1, computed within its (confidence tier × calendar month)
group**. In words: "how unusual is today, compared with other January days in
the same data era?" The month grouping removes seasonality (January is always
busier than June — that is not information); the tier grouping stops
satellite-era step-changes from contaminating the ranks.

### 5.2 Hazard subindices — the structure that survived testing

Percentiles are folded into hazard subindices, and the DLI is the
equal-weight mean of whichever subindices are available that day:

- `sub_fire` — mean of the seven fire percentiles (four national, two SEAUS,
  plus the Tier-3 polygon burn-window count);
- `sub_tc` — the **larger** of the TC count percentile and the TC severity
  (maximum wind) percentile;
- `sub_drfa` — the DRFA percentile based on the **LGA footprint** (how many
  local government areas are under activation), not the event count;
- `sub_tfb` — the Victorian Total Fire Ban percentile;
- `sub_flood` *(ABANDONED 2026-07-09 — never entered the index)* — was to
  be the mean of six rainfall percentiles: the fraction of land area whose
  1-, 3- and 7-day rain accumulation exceeds its local per-month wet-day
  95th percentile, nationally and for the SEAUS box, from AGCD gridded
  rainfall (area fractions, not rain amounts, because flood *demand*
  scales with how much of the country is being rained on hard). The
  component was fully coded and tested, but both full Gadi extraction
  runs failed at the final output write (a walltime kill, then a file
  PermissionError — the script saved results only once, at job end, so
  each failure lost the finished compute). The user terminated the
  component before its adoption gate could ever be evaluated. **The DLI
  is therefore frozen without a flood subindex**, and the 2022-floods
  benchmark remains an honest miss (82.6th, carried by DRFA alone).

Two failure modes drove these choices, both variants were tested and
rejected:

1. **Flat mean of all components** dilutes single-hazard catastrophes:
   TC Yasi scored unremarkably because ten quiet fire components averaged
   away one screaming cyclone component.
2. **"Top-3 components" mean** suffers order-statistic inflation: the top-3
   of eleven roughly-uniform percentiles averages ≈ 0.83 on a completely
   ordinary day, destroying contrast.
3. **Count-style components saturate.** One active TC is common, so the
   percentile of "number of active TCs" ties at ≈ 0.7 and cannot distinguish
   Yasi from a fizzler — hence the max-with-severity design for TCs and the
   LGA footprint for DRFA.

### 5.3 Validation — the 12-event benchmark

Rather than tuning to look good, the index was tested against 12 well-known
extreme events (Black Saturday, Ash Wednesday, the 2003 Canberra fires,
TC Yasi, Black Summer, the 2022 east-coast floods, …). The question asked:
*on the event's peak day, what within-tier percentile does the DLI reach?*

Result (exact, recomputed from `demand_daily_panel.parquet`): **seven of
12 events score at or above the 95th percentile** (Black Saturday 99.93rd,
Ash Wednesday 99.67th, Dandenongs 99.61st, Canberra 99.61st, Dunalley
98.72nd, Black Summer 97.76th, NSW Jan 1994 95.30th), with TC Yasi at
92.91st and the NSW Blue Mountains Oct 2013 at 89.59th. The honest misses
are documented, understood, and deliberately not tuned away:

- 2022 east-coast floods 82.6th — DRFA is the only flood-sensitive
  component and its activations persist for weeks, flattening the peak;
- Tasmania 2016 (60.7th) and Deepwater 2018 (69.8th) — regionally severe
  events that genuinely were nationally moderate.

Note the benchmark's epistemic status: it is a face-validity check, not
independent validation — the events are selected *because* they are known
high-demand days, and some components (TC tracks, DRFA) directly encode
those same events. What it genuinely tests is the combiner: whether the
recipe surfaces known extremes without dilution or inflation.

Tuning the combiner until the misses pass would be overfitting twelve data
points; any future recipe change must re-run this benchmark, keep the
seven ≥95th-percentile fire events at or above the 93rd, and not lower
any other event's percentile materially.

## 6. Cross-validation of the fire record (FIRMS vs DEA)

Because tiers 1–2 rest entirely on the FIRMS archive, it was checked against
Geoscience Australia's independently processed DEA Hotspots archive
(48.8 million detections). Both records were reduced to daily national
detection counts per sensor family, and the two daily series were compared.

**The statistics.** *Pearson correlation* asks whether the two series move
together linearly; *Spearman correlation* asks whether they **rank** days the
same way — which is the property that actually matters here, because the DLI
consumes ranks, not raw counts. The acceptance gate was Spearman ≥ 0.90 for
MODIS.

**Making the comparison fair required three corrections**, all of them
DEA-side quirks discovered during the analysis:

1. DEA's feed covers Southeast Asia and New Zealand; it was clipped to the
   Australian bounding box to match FIRMS.
2. DEA stores the same satellite pass processed through multiple algorithms
   — about 22% of rows are exact duplicates, which were removed.
3. Archive spans differ per sensor (DEA's S-NPP record only starts in 2014),
   so overlap is computed per sensor family: absence of archive is not
   disagreement.

**Result: MODIS daily counts agree at Spearman 0.92 over 2002–2018** — the
gate passes, and this window fully covers Tier 2, the era where MODIS is the
sole satellite source. Agreement is lower after 2019 (MODIS 0.87, VIIRS
0.79), but the divergence is attributable to DEA's post-2019 multi-algorithm
live feed inflating its counts roughly two-fold, not to FIRMS. Conclusion:
the FIRMS record underpinning tiers 1–2 is not idiosyncratic.

## 7. Phase 2 — attributing high-demand days to weather types

With the index built and validated, the first attribution question: **which
synoptic weather types are over-represented on high-demand days?**

### 7.1 Definitions

A **high-demand day** is a day whose DLI is in the top 5% *within its
confidence tier* (a pooled threshold would just select modern days, whose
richer data produce more extreme index values).

Each day carries one of 30 synoptic weather types (SWTs) from the Barnes
continental classification — daily since 1952, in eight regime families
(WH, CH, EH, TH, FH, COL, WCT, AM).

### 7.2 Relative risk with a month-matched baseline

For each SWT the analysis computes a **relative risk (RR)**:

> RR = (rate of high-demand days under this SWT) ÷ (rate expected if the SWT
> had no effect beyond *when in the year* it occurs)

The denominator is the subtle part. Weather types are strongly seasonal, and
so is demand. A naive baseline would "discover" that summer weather types
predict demand — a restatement of "summer is busy". The month-matched
baseline instead asks: given the calendar months in which this SWT actually
occurred, what high-demand rate would those months predict anyway? RR > 1
then means the weather type adds risk *beyond* its seasonal timing.

### 7.3 Moving-block bootstrap confidence intervals

Daily series violate the independence assumption of textbook confidence
intervals: a fire season persists for weeks, so 30 consecutive high-demand
days are nowhere near 30 independent observations, and treating them as such
would produce dishonestly narrow intervals. The fix is a **moving-block
bootstrap**: instead of resampling individual days, the analysis resamples
contiguous 30-day blocks of the time series (1,000 times), recomputes every
RR each time, and reads the 2.5th–97.5th percentile of those resampled RRs
as the confidence interval. Blocks preserve the wiggly, persistent structure
of the real series, so the intervals reflect the true effective sample size.
Resampled days keep their original calendar month so the month-matched
baseline stays honest inside every resample.

### 7.4 Results

Over the full record, only two weather types have confidence intervals clear
of RR = 1:

- **AM-E: RR 1.52 [1.30–1.74]** — high-demand days are ~50% more likely;
- **AM-B: RR 1.27 [1.02–1.50]**.

Within Tier 1 (2012–), **TH-C reaches RR 2.00 [1.29–2.83]**. At the other
end, several regimes actively suppress demand: COL-A 0.19, EH-A 0.39,
WCT-B 0.52.

**The headline contrast:** the champion of multi-state fire *danger* in
Fires_SWTs — FH-B, danger RR 2.13 — shows **no demand enrichment (0.69)**.
Demand is multi-hazard (cyclones, floods, storms, fire), so the weather
types that drive national emergency workload are not the fire blocking
highs; the AM family dominates instead. The two analyses answer different
questions, and that difference is itself the finding.

### 7.5 Caveat: the AM labels are under suspicion

The 2026-07-07 audit of Fires_SWTs
([`fires_swts/AUDIT_2026-07-07.md`](../fires_swts/AUDIT_2026-07-07.md))
spot-checked landmark days against their assigned weather types and found
that **Black Saturday (7 Feb 2009) and 4 Jan 2020 — both textbook
hot-northerly southern fire catastrophes — are classified AM-E and AM-B**
("active monsoon"). Either the AM family names are misleading shorthand for
broader circulation clusters, or the classifier confuses tropical northerly
surges with mid-latitude hot northerlies. Either way, the AM-E demand
enrichment above may partly consist of misfiled southern fire-catastrophe
days rather than genuine monsoon-driven demand. Until the SWT classifier is
audited separately, the AM results should be reported with this caveat
attached — which is one reason the project is moving to **pattern-agnostic
meteorology** (composite maps of the actual fields on high-demand days)
rather than relying on the pre-baked type labels.

## 8. Reproducibility

The full pipeline is deterministic and scripted (`scripts/run_*.py`, run
order in `CLAUDE.md`); random procedures (bootstraps) are seeded. Pure logic
is unit-tested (49 tests, `tests/`). Heavy Gadi-side steps (FFDI extraction)
are PBS scripts under `gadi/`. Outputs land as parquet checkpoints in
`data/derived/` and analysis-ready CSVs in `data/export/` (both gitignored;
regenerable from raw inputs).

## 9. Current limitations

- **Flood signal is thin (permanent).** DRFA activations are the only
  flood-sensitive component and they persist for weeks; flood peaks are
  under-sharp (see the 2022 benchmark miss). The AGCD rainfall subindex
  that was to fix this was abandoned 2026-07-09 (§5.2) — the limitation
  now stands as a disclosed property of the frozen index, and any
  flood-related conclusion must carry it.
- **Demand is proxied, not measured.** No national record of actual resource
  deployment exists at daily resolution back to 1979; the components are the
  best available traces of workload.
- **Tier 3 is coarse.** Pre-2000 fire activity rests on mapped polygons and
  estimated burn windows.
- **The 12-event benchmark is a validation, not a proof.** It demonstrates
  the index responds to known extremes; it cannot certify behaviour on
  unremarkable days.
- **The SWT attribution inherits an unaudited classifier** (§7.5).

## 10. Project direction (decided 2026-07-07)

The index is a **tool, not the point** — the research object is the
underlying synoptic meteorology of severe hazards that spatially compound
in their demand on nationwide EM resources. Decisions:

1. **The DLI recipe is frozen — as of 2026-07-09, without a flood
   subindex.** The AGCD flood component was abandoned before its adoption
   gate could run (§5.2); no new components. The planned FFDI component
   is parked indefinitely.
2. **Classification-free attribution — pilot implemented, evaluation
   pending.** A pilot study tests the hypothesis that *different hazards
   generating high demand arise from distinct large-scale atmospheric
   configurations*, by compositing the actual ERA5 fields (MSLP, 850 hPa
   temperature and wind, column water vapour) on high-demand days stratified
   by dominant hazard (argmax of hazard subindices: fire 387 days, tc 387
   days, drfa-led 95 days; no flood stratum — the flood component was
   abandoned, so the flood fingerprint is permanently untestable in this
   framework). It discovers the patterns from the data instead of imposing the
   SWT classification (§7.5), and it supersedes the SWT attribution as the
   primary attribution analysis — the SWT RRs become a consistency check.
   **Evaluated 2026-07-08: face-validity gate passed, all pre-registered
   predictions confirmed — full results and replication guide in §11.**
   Spec: `docs/superpowers/specs/2026-07-07-demand-composites-pilot-design.md`.
3. **Then a state×hazard compounding panel** — which states are under
   which hazard load on the same day — as the substrate for the real
   compound-demand analysis, which will also bring in the weather-object
   pipeline (`docs/phase2_weather_objects_notes.md`).
4. **Fires_SWTs is demoted from foundation to audited input** (§1); its
   SWT classifier still needs its own audit.

## 11. Composite pilot — results and how to replicate it (2026-07-08)

This section is written so the analysis can be rebuilt from scratch by a
person, with every methodological choice explained. It is the record of
*why* each step is the way it is, not just what was run.

### 11.1 The question and the logic of the method

Hypothesis (spec §1): the different hazards that generate high national EM
demand arise from **distinct large-scale atmospheric configurations**. The
test is a composite: take all high-demand days attributed to one hazard,
average the atmosphere over them, subtract what the atmosphere looks like
on an ordinary day at that time of year, and see what structure survives.
If fire days and cyclone days average to visibly different, physically
sensible patterns, the hypothesis holds. Averaging kills anything that
isn't common to most of the days — so any surviving structure is a real
shared signature, not one memorable event.

Why composites and not the SWT weather types: the SWT attribution can only
answer inside Barnes's pre-defined categories, and §7.5 showed those
categories misfile landmark days (Black Saturday → "active monsoon").
Composites have no classifier in the loop: days are chosen by *demand*,
and the atmosphere is simply averaged as it was.

### 11.2 Choosing and labelling the days

1. **High-demand days:** DLI ≥ the 95th percentile *within its confidence
   tier*, 1979–present (same selection as the SWT attribution, so results
   are comparable). Within-tier, because a raw percentile would let the
   data-rich satellite era dominate.
2. **Dominant hazard = argmax of the hazard subindices** on each day
   (`scripts/composite_strata.py::assign_strata`). Argmax was chosen
   **because it has no tunable threshold** — an earlier draft defined
   "multi-hazard days" as two subindices ≥ 0.90 and could not justify the
   0.90. Every numeric cutoff needs a justification; argmax needs none.
3. `sub_tfb` folds into fire (a total fire ban is a fire-danger decision).
4. `sub_drfa` days form a **descriptive-only** stratum: DRFA is a funding
   activation, not a hazard — it mixes hazards and lags the weather by
   days-to-weeks, so it is excluded from the hypothesis test and plotted
   only in supplementary figures.
5. Result (runner `scripts/run_composite_strata.py`): 869 high-demand
   days — fire 387, tc 387, drfa-led 95. No flood stratum: `sub_flood`
   was abandoned 2026-07-09 (§5.2), so per the spec's fallback clause the
   flood fingerprint cannot be tested. Strata with n < 30
   would be reported but not composited (too noisy); none are.

**Top-two margins** (how decisively each day's biggest subindex beats its
second — the evidence a future compound-day definition needs): median
margin 0.110; quantiles 5% = 0.009, 25% = 0.049, 75% = 0.181, 95% = 0.309.
So a twentieth of days are effective ties between two hazards — those are
the candidate compound-demand days, and they will be defined properly in
the compounding panel, not by an arbitrary cutoff here.

### 11.3 Fields, anomalies, and the one subtle trap

ERA5 daily 12 UTC fields (Gadi project `rt52`), lon 80–180 / lat −60..−5,
4× coarsened: `msl` (circulation: ridge vs low), `t850` + `u850`/`v850`
(heat advection and the northerly-flow question), `tcwv` (moisture —
separates fire from tc/flood). Composites are **day-of-year anomalies**:
each day minus the 1979–2023 climatology for that calendar day, so a
summer composite never just shows "it was summer".

The trap: the climatology must be built from **ALL days in the period,
not just the labelled ones**. The labels CSV covers only 869 days; if you
(or a rewritten script) compute the calendar-day climatology from labelled
days only, the "anomaly" becomes high-demand days minus *other high-demand
days* and everything cancels. `gadi/demand_composites.py` reindexes the
labels onto the full date range and leaves unlabelled days in for the
climatology; only the compositing step selects by label.

### 11.4 Exact replication steps

```
/opt/anaconda3/bin/python3 scripts/run_composite_strata.py
# → data/derived/demand_stratum_days.csv + counts + margin table

# copy to a flat dir on Gadi (/g/data/gb02/<user>/EM_Demand):
#   demand_stratum_days.csv, gadi/demand_composites.py, gadi/demand_composites.pbs,
#   fires_swts/gadi/composite_core.py, fires_swts/gadi/read_era5.py

# on Gadi: DRY RUN FIRST (standing rule — local tests cannot hit
# dask/chunking failures): python args --start 1990-01 --end 1991-12, ~0.3 SU.
# Then the full job: qsub demand_composites.pbs   (job 173343702: 7.11 SU,
# 1h35 walltime, 2 CPUs / 9 GB). Days composited within 1979–2023:
# fire 370, tc 347, drfa-led 77 (the rest of the 869 fall after 2023).

# copy demand_composites.nc back to data/raw/composites/, then:
/opt/anaconda3/envs/rfigs/bin/Rscript R/demand_composites.R
```

R-side trap: ncdf4 returns arrays with dimensions reversed relative to
xarray — (stratum, lat, lon) arrives as [lon, lat, stratum]; the script's
`expand_grid`/`as.vector` pairing depends on that order.

Gadi-side lesson (cost us a full AGCD run): results are written only at
the end of a job, so an over-tight walltime loses *everything*. Budget
walltime at ~2× the dry-run-scaled estimate.

### 11.5 Results against the pre-registered predictions

The predictions were written in the spec (§5) before any map existed, and
the rule is report-never-tune. All confirmed:

| Prediction (spec §5) | Outcome |
|---|---|
| fire: positive MSLP / ridge | Confirmed — significant high anomaly over the Tasman/SE Australia with a deep low anomaly south of the Bight (blocking dipole) |
| fire: dry TCWV | Confirmed — significant dry anomaly over eastern/interior Australia |
| tc: deep negative MSLP | Confirmed in structure — significant negative anomaly with a closed low in the mean contours over tropical NW Australia; magnitude modest (−1 to −2 hPa), as expected when compact cyclones at varying locations are averaged |
| tc (and flood): moist TCWV | Confirmed for tc (strong +TCWV across the tropical north); flood permanently untestable (component abandoned) |

**Face-validity gate (blocking, spec §8): PASSED** — the tc composite
shows a closed low with high TCWV, i.e. the machinery recovers a cyclone
from cyclone days.

**Secondary (audit follow-up):** the fire composite shows the blocking
ridge + hot (+2 K) T850 plume with northerly flow over SE Australia — the
structure the Fires_SWTs *danger* result predicts. Since the composite has
no classifier in the loop, this is direct evidence that the SWT *labels*
(which file Black Saturday under "active monsoon") are the weak link, not
the atmosphere. The AM-family caveat of §7.5 stands.

**drfa-led (descriptive):** weak and spatially incoherent — consistent
with a lagged, hazard-mixing funding proxy. Its incoherence is the result.

### 11.6 What this does and does not establish

Established: fire-driven and tc-driven high demand have visibly distinct,
physically correct synoptic fingerprints, recovered by an index built
entirely from demand-side data that never saw the atmosphere. That is
(a) a validation of the DLI's hazard subindices, and (b) the physical
premise of the compounding phase — spatially compounding demand means
*different* drivers loading the system at once, which requires the
drivers to be distinct.

Not established: any formal statistical separation of the patterns. The
stippling is pointwise p < 0.05 with no field-wise multiplicity correction
and serial dependence within events (anti-conservative) — descriptive
only, disclosed in every caption. The formal pattern-separation test
(composite pattern correlation against block-resampled nulls) is
deliberately deferred to the full analysis; the pilot's job was to decide
whether that machinery is worth building. It is.
