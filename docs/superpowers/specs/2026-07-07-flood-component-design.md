# Flood component (DLI v0.2) — design

**Date:** 2026-07-07. **Status:** approved direction (user confirmed national
aggregation 2026-07-07); implementation plan at
`docs/superpowers/plans/2026-07-07-flood-component.md`.

## Problem

The DLI's only flood signal is DRFA activations (`sub_drfa`), which persist
for weeks and blur event timing. The honest benchmark misses are the
Feb/Mar 2022 NSW/QLD floods (~83rd within-tier percentile). No jurisdiction
publishes a daily flood time series, so a daily flood signal must be built
from a meteorological proxy: gridded rainfall.

## Approach (chosen)

**AGCD daily precipitation as the daily engine**, mirroring the fire
component design (national + SEAUS aggregation). Methodological anchor:
Sharples et al. 2026, JSHESS (doi:10.1071/ES24042) — AGCD hydroclimate
anomalies and compound events preceding disasters.

Alternatives considered and rejected:
- *State flood extent layers as the signal*: dated historical extents exist
  only for QLD/VIC/WA and record events, not days (see
  `docs/flood_data_layers.md`). They are the **validation set**, not the
  engine — the same role DEA Hotspots played for FIRMS.
- *SEAUS-only aggregation*: rejected; floods are national (Fitzroy 2023,
  Townsville 2019 sit outside the SEAUS box). National + SEAUS matches the
  fire design and lets ranking handle the tropical-north wet-season base rate.

## Component definition

Data: AGCD v1 daily precip, 0.05°, on Gadi (`/g/data/zv2/agcd/`, verify path
and add `gdata/zv2` to storage flags — first task of the plan).

Per grid cell and calendar month, compute the **95th percentile of wet days
(≥ 1 mm)** over 1979–2023 for three accumulations: 1-day, 3-day and 7-day
rolling sums. Daily metric = **fraction of land cells where the accumulation
exceeds its cell/month p95**, computed for two domains:

| Component | Domain | Accumulation |
|---|---|---|
| `rain1d_area` | national | 1-day |
| `rain3d_area` | national | 3-day |
| `rain7d_area` | national | 7-day |
| `seaus_rain1d` / `seaus_rain3d` / `seaus_rain7d` | SE_AUS_BBOX (140–154E, 39–28S) | 1/3/7-day |

Area fractions are continuous, so they avoid the rank-tie saturation that
plagued count-style inputs. Daily bucketing: AGCD days are already 24-h
totals ending 09:00 local — accept as-is, note the ~9-h offset from the
project's fixed UTC+10 convention in the loader docstring.

**Subindex:** `sub_flood` = mean of the six available `*_pct` columns
(same shape as `sub_fire`), entering the DLI as a fifth equal subindex.
Availability: `"agcd_rain": ("1979-01-01", None)` in
`COMPONENT_AVAILABILITY` (all tiers; AGCD is homogeneous across them).

**Deferred to v0.3 (do not build now):** exposure weighting — masking to
"flood-prone AND populated" cells using the design-likelihood layers (GA
Flood Studies DB eCat 79139 + state 1% AEP layers). Build only if the
unweighted version fails validation.

## Validation and adoption gate

1. **Dated-event diagnostic:** curate event dates from the dated historical
   extents (QLD Flood Extent Series 1893–2025, VIC Oct 2022 +
   Historic_extents, WA DWER-123/124 — links in
   `docs/flood_data_layers.md`). Print each event day's `sub_flood`
   within-tier percentile. Expect the extreme tail; this is diagnostic,
   not a hard gate (flash-flood-scale events may legitimately miss a
   national area metric).
2. **Hard adoption gate (recipe change rules apply):** re-run the 12-event
   benchmark table (`scripts/run_dli.py`). Adopt sub_flood only if the
   2022 floods benchmark rises above its current ~83rd percentile AND no
   fire benchmark drops below the 93rd. Otherwise report and stop — do not
   tune the combiner to the benchmarks.

## Pipeline shape

Gadi qsub job (AGCD is too large for the 17 GB laptop) → small daily CSV
(`agcd_rain_daily.csv`, ~17k rows × 7 cols) → scp to `data/raw/agcd/` →
local loader + `assemble_components`/`compute_dli` integration → benchmark
rerun. Gadi scripts must be flat-directory safe (files are copied flat to
`/g/data/gb02/sm5259/EM_Demand/`, no repo clone; qsub from that directory).
