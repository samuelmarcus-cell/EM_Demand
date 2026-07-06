# FFDI fire-danger × SWT analysis (design / scope)

_Date: 2026-06-25. Next analytical block after the realized-fire chapter (`Fires_SWTs.ipynb` Steps 2–7)._

## Purpose / headline question
The realized-fire results showed synoptic types raise fire **propensity** broadly but mostly don't **synchronise** distant regions (except FH-B→SA-TAS, TH-C→SE). Realized fire is confounded by ignitions/fuel/suppression. **FFDI (fire danger) is the unconfounded atmospheric signal.** Headline question: **does synoptic type synchronise fire *danger* across regions, even though it didn't synchronise realized *fire*?** Plus cleaner versions of the propensity and mechanism results.

## Data & products (NCRA BARRA-R2 FFDI on `ia39`; user is a member)
- **Primary — `bias-input`** (raw BARRA-R2-derived FFDI, internally consistent → relative/percentile/anomaly work):
  `/g/data/ia39/ncra/fire/bias-input/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr`
- **Secondary — `bias-output`** (AGCD-calibrated → absolute-threshold extreme-day work only):
  `/g/data/ia39/ncra/fire/bias-output/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr`
- Grid AUST-05i (0.05°), daily, ~1979→end-of-record. Exact var name, time coverage, coord names verified at runtime on Gadi.
- SWT labels: `SWT_climatology_v20260129.csv` (daily `assigned_SWT`). **Period = 1979 ∩ FFDI ∩ SWT** (~46 yr).

## State aggregation + "high-danger day" definition
- Mask 0.05° cells → **7 states** (ACT→NSW), via geopandas Natural-Earth admin-1 AU state polygons (or `regionmask`); each land cell tagged with one state.
- **State daily value (default):** **area-mean FFDI** over the state's cells.
- **High-danger day (default):** state value above its **monthly 90th percentile** (self-normalising per state AND per season, so tropical and temperate states participate fairly). Threshold computed on the local series.
- *Adjustable alt:* spatial 90th-percentile across a state's cells instead of the mean (captures "somewhere extreme"); mean is the default.

## Analyses (mirror the fire chapter, on danger)
1. **Mechanism map** — per-SWT **FFDI-anomaly composite** (gridded, day-of-year climatology, reuse the Step-6 anomaly method) → danger version of the circulation maps.
2. **Propensity (Step-2 analogue)** — seasonally-matched **RR of a multi-state high-danger day** per SWT (+ FDR). Which types raise broad danger.
3. **Synchronisation (key test, Step-4/5 analogue)** — holding the **number of dangerous states fixed (× month)**, stratified label-permutation: does each SWT make **specific state-pairs** (and/or more-dispersed danger via state-centroid pairwise distance) co-occur beyond chance? FDR-corrected. → does danger synchronise where fire didn't?
4. **Extreme days (complementary, `bias-output`)** — seasonally-matched RR of **severe/extreme/catastrophic** FFDI days (any state ≥50 / 75 / 100) per SWT. Operational relevance.

## Compute split (reuses the proven ERA5 Gadi→local pattern)
- **On Gadi** (`module use /g/data/xp65/public/modules; module load conda/analysis3`; xarray+zarr+geopandas; PBS `-l storage=gdata/ia39+gdata/xp65+gdata/<proj>`):
  1. Open the FFDI Zarr lazily (dask), mask to states.
  2. **Artifact A:** per-state **daily area-mean FFDI** series → CSV (`ffdi_state_daily.csv`, ~46 yr × 7 states; both bias-input and bias-output).
  3. **Artifact B:** per-SWT **gridded FFDI-anomaly composite** (coarsened ~0.25°, Australia land) → small NetCDF (`ffdi_swt_composite.nc`).
  rsync both back (small).
- **Locally:** align state series to SWT days, compute monthly-percentile thresholds + high-danger flags, run the **existing Step 2/4/5 permutation machinery** (reuse the code), render the composite map (cartopy + R/ggplot) and the danger RR / synchronisation / extreme-day figures.

## Output / success
- `ffdi_state_daily.csv`, `ffdi_swt_composite.nc` (from Gadi).
- A "Step 8 — FFDI fire danger" section in the notebook: danger-RR table + plot, synchronisation/region-pair result, extreme-day RR, and the FFDI composite map; plus R/ggplot twins.
- **Key result statement:** whether danger synchronises across states under the elevated SWTs (esp. FH-B / WH-A / TH-C), vs the realized-fire "propensity-dominated" finding.

## Scope boundaries (YAGNI)
**In:** state-level FFDI, the 4 analyses, 1979–present, bias-input (+bias-output for extremes). **Out (later):** finer regions (BoM districts / NRM), Total Fire Ban days, weather-objects, continuous-covariance framing, climate-driver/trend attribution, station-FFDI validation.

## Risks
- Zarr schema (var/coord names, time coverage, calendar) unknown until opened on Gadi → verify first, print schema + coverage.
- 0.05° daily 1979– is large → must stay lazy/dask on Gadi; bring back only the two small artifacts. I can't run/verify the Gadi step (user runs it); make it self-checking (print coverage, per-state means, per-SWT day counts).
- State masking at 0.05° near coasts/borders → use land cells only; document cell counts per state.
- Absolute thresholds only meaningful on `bias-output`; percentile work on `bias-input`.
