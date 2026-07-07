# Phase 3 methods notes — compounding demand (spatial and temporal)

Two anchor papers, both about simultaneous hazard load straining shared
firefighting resources: Gauthier & Bevacqua 2026 (spatial compounding,
Europe) and Richardson et al. 2025 (temporal/seasonal compounding,
Australia–North America). Phase 3 needs both axes.

## Paper 1 — spatial compounding

Source: Gauthier & Bevacqua (2026), "Human-induced climate change
intensifies spatially compounding fire weather extremes across European
countries", *npj Natural Hazards* 3:39, doi:10.1038/s44304-026-00201-y.
European analogue of this project's Phase 3/4 question: days when extreme
fire weather hits many countries at once strain the EU Civil Protection
Mechanism's shared firefighting pool (37 countries; activated 18 times in
11 countries in 2025 alone).

## Ideas to adopt

1. **Area-fraction extent metric (precedent).** Their core measure is the
   daily % of European land simultaneously under FWI ≥ 50. This is the
   same construction as the planned FFDI component and the flood
   component's rain-area fractions — cite as published precedent for
   "extent simultaneously exposed" as a resource-strain metric.

2. **Spatial-shuffle null model (their Fig. 2) — Phase 3 core method.**
   Break cross-region correlations by spatially shuffling the data (they
   use 1,000 random spatial shuffles within the season), then compare the
   observed distribution of "extent simultaneously extreme" against the
   shuffled distribution. Their headline: ≥13% of Europe simultaneously
   extreme is 56× more likely in reality than under spatial independence.
   Australian adaptation: are NSW+VIC+SA (or state-level DLI/demand
   components) simultaneously extreme more often than independence
   predicts? Quantifies exactly the compound spatial demand that breaks
   interstate resource sharing. `demand_metrics_daily.parquet` already
   carries per-state metrics — the shuffle can operate on state series
   (month-matched shuffling to preserve seasonality, consistent with the
   project's within-month ranking convention).

3. **Event build-up composites (their Fig. 3b–f) — preconditioning.**
   For the top-10 events they composite standardized anomalies of FWI,
   temperature, precipitation, RH, wind from day −80 to +5. Fire danger
   builds gradually (dry/warm preconditioning), spiking ~10 days before
   the event. Australian adaptation: composite meteorological anomalies
   (and DLI components) around top within-tier DLI days — complements
   Phase 2 SWT attribution (categorical "what type of day") with a
   continuous "how was it preconditioned" view; natural bridge to
   sequential/compound demand in Phase 3.

4. **Framing citation for Phase 4.** Their motivation — simultaneous
   requests overwhelming a shared-resource mechanism — is the direct
   analogue of Australian interstate deployments / national resource
   sharing arrangements. Use in the capacity chapter's motivation.

## Paper 2 — temporal / seasonal compounding

Source: Richardson, Ribeiro et al. (2025), "Increasing fire weather
season overlap between North America and Australia challenges
firefighting cooperation", *Earth's Future* 13, e2024EF005030,
doi:10.1029/2024EF005030. USA/Canada/Australia share aircraft and
personnel because their fire seasons are historically asynchronous
(~12% of Australia's aerial fleet is overseas-owned); overlap has grown
~1 day/yr since 1979 (Jul–Dec) and is projected +4 to +29 days by 2050.

### Ideas to adopt

1. **Demand-season overlap — the domestic translation.** Their method:
   define Fire Weather Days as regional-mean FWI above its own median
   (justified operationally — it mirrors declared bushfire danger
   periods), then count days/year when BOTH regions are simultaneously
   in-season, and trend the annual counts. Australian internal analogue:
   interstate resource sharing rests on the same asynchrony (northern
   dry-season fires Jun–Oct vs southern summer Oct–Mar; fire vs TC/flood
   seasons). `demand_metrics_daily.parquet` already carries per-state
   metrics, and the DLI carries per-hazard subindices — compute
   state-pair and hazard-pair demand-season overlap days/year and their
   trends. A demand-index version of this has not been published.

2. **Trend statistics.** Sen's slope + Mann–Kendall, with the MK τ
   estimated via nonparametric block bootstrap (2,000 iterations;
   Patakamuri & O'Brien 2018 `modifiedmk`) to handle autocorrelation.
   Use for any "extreme-demand days per year" trend claim. Project
   caveat: trends must respect confidence-tier boundaries (satellite-era
   density step changes) — trend within tiers, or on tier-robust inputs
   only.

3. **Threshold sensitivity as standard practice.** They re-run the
   analysis at the 75th percentile threshold alongside the median and
   report both. Adopt for Phase 2/3: re-check the "extreme demand"
   definition (within-tier 95th pct) at the 90th and 97.5th and report
   stability.

4. **Climate-mode conditioning of demand years.** They composite
   high-overlap years by ENSO phase — NDJ Niño3.4 ±0.5 for La Niña/El
   Niño, Capotondi normalized Niño3-vs-Niño4 to split eastern- vs
   central-Pacific El Niño; Anderson–Darling test for distribution
   differences. Finding: CP El Niño links to high AUS–NA overlap.
   Phase 3 extension: condition extreme-demand frequency and
   hazard-season overlap on ENSO/IOD phase. Caution (standing user
   guidance): ENSO and IOD are correlated — never treat them as
   independent drivers; use sustained-event classification for IOD.

## Explicitly out of scope for this project

- CMIP6 detrending / human-induced-climate-change attribution (Gauthier
  & Bevacqua's second half; +14.8% of annual-max synchronous extent
  attributable). Different question — note as future work only.
- Driver decomposition of FWI trends (detrend each input, recompute) —
  climate-trend attribution, not demand characterization.
- Richardson et al.'s CMIP6 large-ensemble projections (SSP2-4.5 to
  2100) — climate-futures question; future-work citation only.
