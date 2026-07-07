# Phase 3 methods notes — spatially compounding demand

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

## Explicitly out of scope for this project

- CMIP6 detrending / human-induced-climate-change attribution (their
  second half; they find +14.8% of annual-max synchronous extent
  attributable to climate change). Different question — note as future
  work only.
- Driver decomposition of FWI trends (detrend each input, recompute) —
  climate-trend attribution, not demand characterization.
