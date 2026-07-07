# State and territory flood data layers — inventory (2026-07-07)

Research input for the flood component of the DLI (v0.2 candidate). The
question that matters most here: which jurisdictions publish **dated
historical flood extents** (usable to validate a rainfall-based flood proxy),
versus only design-likelihood (e.g. 1% AEP) planning layers.

National context: Geoscience Australia's Australian Flood Studies Database
(eCat 79139, National Flood Risk Information Project) catalogues council
flood studies and inundation maps nationally, but coverage is patchy and
temporally it records studies, not events.

## Summary table

| Jurisdiction | Dataset / layer | Custodian | Content | Access | Licence | Dated historical extents? |
|---|---|---|---|---|---|---|
| NSW | NSW Flood Data Portal (via SEED) | NSW SES / DCCEEW | ~2,300+ council flood-study outputs, design extents, risk plans | SHP/TAB; WFS for EPI-Flood; portal login for some — flooddata.ses.nsw.gov.au | CC-BY 4.0 | **Partial** — council-submitted study outputs, few discrete event layers |
| VIC | Victoria Flood Database (VFD): Historical + Statistical extents | DEECA / EMV | 26 layers: modelled 1–500 yr ARI extents, observed/historical event extents, contours, levees | SHP/TAB/GDB/WMS/WFS — discover.data.vic.gov.au | CC-BY 4.0 | **YES** — named event extents (Oct 2022 flood is a standalone dataset; `Historic_extents` aggregates events) |
| QLD | Flood Extent Series + Historical Flood Map Series | Dept of Resources / QRA | Dated inundation polygons for real events **1893–2025**; scanned map series 1893–1974 | SHP/TAB/FGDB/KMZ/GPKG/WMS/REST — data.qld.gov.au, FloodCheck | CC-BY 4.0 | **YES** — the standout: explicitly dated events (2011, 2012, 2013, 2017, 2019, …) |
| SA | WaterConnect Flood Awareness Map + PlanSA hazard mapping | DEW / State Planning Commission | Design-event extents from studies; statewide hazard mapping in progress (2026 code amendment) | Portal (FAM); WMS via SAPPA; limited bulk download | CC-BY 4.0 (site); varies | **NO** — modelled/design only |
| WA | FPM Historical Extent of Flooding (DWER-123) + Historical Floodplain Area (DWER-124) | DWER | Historical flood extents for named events (Warmun 2011, Perth 2017, York 2021–22, Fitzroy 2023) + design floodway/fringe layers (DWER-014–023) | SHP/GDB/GPKG/GeoJSON/WMS/WFS/REST (login for download) — catalogue.data.wa.gov.au | Custom acceptance licence | **YES** — named, dated events; sparser in remote regions |
| TAS | Flood Inundation Extent Models (LISTmap) | NRE Tas / Hydro Tas / TasWater | Modelled extents, flood + dam-break scenarios at 0.5/1/2% AEP | Vector download via LISTmap — thelist.tas.gov.au | CC-BY 3.0 AU | **Unclear** — needs per-layer metadata review |
| NT | Floodplain Maps — NT (NTLIS) | DIPL / DENR | Modelled 1% AEP extents + peak contours for select towns; storm-surge for Gulf communities | PDF + spatial packages — data.nt.gov.au / NTLIS | Not stated | **NO** — design only, town-by-town |
| ACT | 1% AEP Flood Extent Model | EPSDD | 1% AEP extent + depth for all ACT catchments (LiDAR-verified) | SHP/GeoJSON/KML/WMS/WFS/REST — data.act.gov.au / ACTmapi | CC-BY 4.0 | **NO** — design only |

## Implications for the flood component design

- **Validation set (dated events): QLD ≫ VIC ≈ WA.** QLD's Flood Extent
  Series alone (1893–2025, CC-BY, GIS-ready) gives a dated event archive to
  validate the AGCD rainfall proxy against, the same role DEA Hotspots
  played for FIRMS. VIC (Oct 2022 + Historic_extents) and WA (DWER-123/124)
  add south-east and west coverage.
- **Exposure weighting:** the design-likelihood layers (all jurisdictions +
  GA Flood Studies DB) can define "flood-prone AND populated" masks so the
  rainfall proxy counts rain where it can actually generate demand.
- **No jurisdiction offers a daily flood time series** — the daily engine
  must be AGCD rainfall (decision 2026-07-07: national + SEAUS box
  aggregation, mirroring the fire component design).

## Links

- NSW: <https://flooddata.ses.nsw.gov.au/> · <https://datasets.seed.nsw.gov.au/dataset/flood-data-portal>
- VIC: <https://discover.data.vic.gov.au/dataset/victoria-flood-database-statistical-extents-for-1-to-500-years-floods> · <https://discover.data.vic.gov.au/dataset/victorian-flood-history-october-2022-event-public>
- QLD: <https://www.data.qld.gov.au/dataset/flood-extent-series> · <https://www.data.qld.gov.au/dataset/historical-flood-map-series-queensland> · <https://floodcheck.information.qld.gov.au/>
- SA: <https://www.waterconnect.sa.gov.au/Systems/FAM/SitePages/Home.aspx> · <https://plan.sa.gov.au/our_planning_system/programs_and_initiatives/hazard_mapping_project>
- WA: <https://catalogue.data.wa.gov.au/dataset/fpm-historical-extent-of-flooding> · <https://catalogue.data.wa.gov.au/dataset/fpm-historical-floodplain-area>
- TAS: <https://maps.thelist.tas.gov.au/listmap/app/list/map>
- NT: <https://nt.gov.au/environment/water/water-in-the-nt/flooding-and-storm-surge/floodplain>
- ACT: <https://www.data.act.gov.au/dataset/1-percent-AEP-Flood/5w26-48wz/data> · <https://actmapi-actgov.opendata.arcgis.com/search?tags=flood>
- GA Flood Studies DB (eCat 79139): <https://researchdata.edu.au/natural-hazards-australian-studies-database/3412581>
