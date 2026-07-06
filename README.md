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

## Confidence tiers

| Tier | Period | Fire-activity basis |
|---|---|---|
| 1 | 2012– | VIIRS S-NPP + MODIS hotspots |
| 2 | 2000–2011 | MODIS only |
| 3 | 1979–1999 | Polygon-archive burn windows only |

Every component carries a per-tier availability flag; nothing NaN-fills silently.

## Roadmap

- **Phase 1 (this repo, in progress):** daily national demand panel + DLI v0.
  Components: hotspot-derived fire activity, DRFA daily activations, TC best-track,
  VIC TFBs, FFDI. Validation against Black Summer, Ash Wednesday 1983, Feb–Mar 2022
  floods, and other benchmark events.
- **Phase 2 (`scripts/phase2_attribution/`):** attribute demand days to SWTs
  (seasonally-matched bootstrap RR) and weather objects (regionalised presence);
  ERA5 + object composites on demand days. Data: SWT climatology, Gadi weather
  objects, ERA5.
- **Phase 3 (`scripts/phase3_compounding/`):** multi-hazard co-occurrence matrix
  (fire × flood × TC × heatwave at 0/±7/±30-day lags); hemispheric overlap with
  NIFC/CIFFC northern-hemisphere demand. Data: demand panel, NIFC preparedness
  levels, CIFFC sitreps.
- **Phase 4 (`scripts/phase4_capacity/`):** tiered capacity/escalation model
  (local → intrastate → interstate → international → ADF), "no donor available"
  day detection, storyline stress tests. Params stakeholder-elicited.

## Layout

- `EM_Demand_Phase1.ipynb` — orchestration notebook (logic lives in `scripts/`)
- `scripts/config.py` — all paths, domains, tiers, constants
- `scripts/loaders/` — one module per source, harmonised schemas
- `scripts/*.py` — pipeline stages (association, metrics, panel, DLI, exports)
- `gadi/` — PBS scripts for anything too heavy locally (qsub only, never interactive)
- `tests/` — unit tests for pure logic (`/opt/anaconda3/bin/python3 -m pytest tests/`)
- `docs/superpowers/specs/` — design documents

## Environment

Local: `/opt/anaconda3/bin/python3` (base env). R figures via the `rfigs` conda env
through `Rscript` subprocess. Gadi: project gb02, env xp65 — see `scripts/config.py`
`GADI` dict for paths and storage flags.
