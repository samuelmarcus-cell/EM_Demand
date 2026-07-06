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
Demand Load Index from 1979 to the present.

## 2. Data sources

| Source | What it contributes | Period |
|---|---|---|
| NASA FIRMS hotspots (MODIS + VIIRS S-NPP) | Satellite fire detections: where and how intensely the landscape is burning, daily | MODIS 2000–, VIIRS 2012– |
| National Historical Bushfire Extents (fire polygons) | Mapped fire footprints with ignition dates — the only fire record before satellites | 1979– (usable) |
| DRFA activations | Commonwealth disaster-funding activations per Local Government Area — a direct trace of real emergency response, all hazards | 2006– |
| BoM tropical cyclone best-track | TC positions and intensities near Australia | full period |
| Victorian Total Fire Ban declarations | An operational decision record (how many fire districts under a ban) | 1945– |
| DEA Hotspots (Geoscience Australia) | An independent hotspot archive, used only to cross-validate FIRMS | 2002– |
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

Percentiles are folded into four hazard subindices, and the DLI is the
equal-weight mean of whichever subindices are available that day:

- `sub_fire` — mean of the seven fire percentiles (four national, two SEAUS,
  plus the Tier-3 polygon burn-window count);
- `sub_tc` — the **larger** of the TC count percentile and the TC severity
  (maximum wind) percentile;
- `sub_drfa` — the DRFA percentile based on the **LGA footprint** (how many
  local government areas are under activation), not the event count;
- `sub_tfb` — the Victorian Total Fire Ban percentile.

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

Result: **9 of 12 events score at or above the 93rd percentile** (Black
Saturday 99.9th, Ash Wednesday 99.7th, Canberra 99.6th). The honest misses
are documented, understood, and deliberately not tuned away:

- 2022 east-coast floods ≈ 83rd — DRFA is the only flood-sensitive
  component and its activations persist for weeks, flattening the peak;
- Tasmania 2016 and Deepwater 2018 ≈ 61st–70th — regionally severe events
  that genuinely were nationally moderate.

Tuning the combiner until these three pass would be overfitting twelve data
points; any future recipe change must re-run this benchmark and must not
degrade the fire benchmarks below the 93rd percentile.

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

## 8. Reproducibility

The full pipeline is deterministic and scripted (`scripts/run_*.py`, run
order in `CLAUDE.md`); random procedures (bootstraps) are seeded. Pure logic
is unit-tested (49 tests, `tests/`). Heavy Gadi-side steps (FFDI extraction)
are PBS scripts under `gadi/`. Outputs land as parquet checkpoints in
`data/derived/` and analysis-ready CSVs in `data/export/` (both gitignored;
regenerable from raw inputs).

## 9. Current limitations

- **Flood signal is thin.** DRFA activations are the only flood-sensitive
  component and they persist for weeks; flood peaks are under-sharp
  (see the 2022 benchmark miss).
- **Demand is proxied, not measured.** No national record of actual resource
  deployment exists at daily resolution back to 1979; the components are the
  best available traces of workload.
- **Tier 3 is coarse.** Pre-2000 fire activity rests on mapped polygons and
  estimated burn windows; a fire-danger (FFDI) component to strengthen this
  era is planned (`docs/superpowers/plans/2026-07-07-ffdi-component.md`).
- **The 12-event benchmark is a validation, not a proof.** It demonstrates
  the index responds to known extremes; it cannot certify behaviour on
  unremarkable days.
