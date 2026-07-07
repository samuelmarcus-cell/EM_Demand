# Fires_SWTs — predecessor analysis (imported)

This directory is a copy of the predecessor **Fires_SWTs** analysis (bushfire ×
synoptic-weather-type simultaneity), imported into the EM_Demand repository on
**2026-07-07** so that the project is self-contained. The original working copy
lives at `~/Fires_SWTs` and is still read by parts of the pipeline via absolute
paths; nothing there was moved or altered.

## Why it matters for EM_Demand

The headline findings of Fires_SWTs motivated the EM_Demand reframe:

- Synoptic weather types synchronise multi-state fire **DANGER** — the FH-B
  type has a relative risk of **2.13** for multi-state extreme-FFDI days
  (period-matched, 1979–2023) — far more than they synchronise **realized
  FIRE**, where no significant multi-state fire synchronisation was found.
- No SWT converts danger into fire beyond what seasonal timing already
  explains: ignition, not meteorology, is the bottleneck for realization.

Hence EM_Demand's reframe: the outcome variable becomes **emergency resource
demand** (which meteorology plausibly does control) rather than fire occurrence.

## Independent audit (2026-07-07)

The analysis was audited by an independent agent (read-only; all headline
results recomputed from scratch): see [`AUDIT_2026-07-07.md`](AUDIT_2026-07-07.md).
Bottom line: every headline number reproduces exactly; the **danger** results
and the danger→fire conversion null are SOLID; the realized-fire RRs are
numerically correct but FRAGILE to the burn-window imputation (cite them only
with the ignition-only sensitivity attached); and two archetypal hot-northerly
fire catastrophes (Black Saturday 2009, 4 Jan 2020) classify as "active
monsoon" (AM) types — so AM-family results in downstream analyses, including
EM_Demand's Phase 2 AM-E demand enrichment, should be treated with caution
until the SWT classifier itself is audited.

## Contents

- `Fires_SWTs.ipynb` — the full baked analysis, Steps 1–10 (outputs preserved).
- `*.py`, `*.md` — supporting scripts and planning/scope documents.
- `gadi/` — HPC extraction code (ERA5 SWT composites, FFDI, weather objects).
- `R/` — figure-generation scripts and exported CSVs; final figures in
  `R/figs/`, rendered with the `rfigs` conda env via `Rscript`.
- `SWT_climatology_v20260129.csv`, `bushfire_events_geo.csv`,
  `ffdi_state_daily.csv`, `era5_swt_composites.nc`, `ffdi_swt_composite.nc` —
  key derived datasets.

## Not included

The raw fire geodatabase `Bushfire Extents - Historical (2025).gdb` (847 MB) is
**not** imported — too large for git. Its path is configured in
`scripts/config.py::PATHS.fire_polygons_gdb` and still points at `~/Fires_SWTs`.
