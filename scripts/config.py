"""Central configuration for EM_Demand. All paths, domains, periods, tiers."""

import os
from dataclasses import dataclass, field
from pathlib import Path

RUN_CONTEXT = os.environ.get("EM_DEMAND_CONTEXT", "local")  # "local" | "gadi"

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_DERIVED = REPO_ROOT / "data" / "derived"

_ONEDRIVE = Path.home() / "Library/CloudStorage/OneDrive-MonashUniversity/PhD/Disaster_Data"
_FIRES_SWTS = Path.home() / "Fires_SWTs"


@dataclass(frozen=True)
class Paths:
    drfa_locations: Path = _ONEDRIVE / "drfa_activation_history_by_location_2026_march_19.csv"
    aidr_mapper: Path = _ONEDRIVE / "AIDR_disaster_mapper_data.xlsx"
    ica_catastrophes: Path = _ONEDRIVE / "ICA-Historical-Normalised-Catastrophe-Master-Updated-2026_02.csv"
    tfb_history: Path = Path.home() / "Downloads/TFBsHistory_20260706123204.csv"
    fire_polygons_geo: Path = REPO_ROOT / "fires_swts" / "bushfire_events_geo.csv"
    fire_polygons_gdb: Path = _FIRES_SWTS / "Bushfire Extents - Historical (2025).gdb"
    swt_climatology: Path = REPO_ROOT / "fires_swts" / "SWT_climatology_v20260129.csv"
    aus_states_geojson: Path = REPO_ROOT / "fires_swts" / "gadi" / "aus_states.geojson"
    firms_dir: Path = DATA_RAW / "firms"          # USER ACTION: FIRMS archive CSVs
    dea_hotspots_dir: Path = DATA_RAW / "dea_hotspots"
    bom_tc_dir: Path = DATA_RAW / "bom_tc"
    agcd_rain_daily: Path = DATA_RAW / "agcd" / "agcd_rain_daily.csv"
    lga_boundaries: Path = _ONEDRIVE / "LGA_2025_AUST_GDA2020/LGA_2025_AUST_GDA2020.shp"


PATHS = Paths()

# Analysis period: panel runs to today with per-component availability flags.
PERIOD_START = "1979-01-01"

# Confidence tiers (satellite-driven boundaries).
TIER_BOUNDS = {
    1: ("2012-01-01", None),          # VIIRS S-NPP + MODIS
    2: ("2000-11-01", "2011-12-31"),  # MODIS only
    3: ("1979-01-01", "2000-10-31"),  # polygon burn-windows only
}

# Component availability windows (None = open-ended).
COMPONENT_AVAILABILITY = {
    "drfa": ("2006-03-20", None),
    "ffdi": ("1979-01-01", "2023-12-31"),
    "tfb_vic": ("1945-01-01", None),
    "modis": ("2000-11-01", None),
    "viirs_snpp": ("2012-01-01", None),
    "tc_besttrack": ("1979-01-01", None),
    "fire_polygons": ("1979-01-01", None),
    "agcd_rain": ("1979-01-01", None),
}

# Phase 2 composite domain: all-Australia + Tasman (covers NZ approach).
# NEVER use whole-domain presence flags — they saturate at continental scale.
COMPOSITE_DOMAIN = {"lon_min": 105.0, "lon_max": 180.0, "lat_min": -45.0, "lat_max": -8.0}

# SE Australia subset bbox (matches TFB_Objects study region).
SE_AUS_BBOX = {"lon_min": 140.0, "lon_max": 154.0, "lat_min": -39.0, "lat_max": -28.0}

# Assumed event durations (days) where AIDR end date unavailable, by hazard class.
ASSUMED_DURATION_DAYS = {"fire": 21, "flood": 14, "tc": 7, "storm": 3, "other": 3}

# Hazard-type token -> hazard class. Tokens are substrings of the DRFA hazard_type field.
HAZARD_CLASS_TOKENS = {
    "fire": ["Bushfire"],
    "flood": ["Flood", "Rainfall"],
    "tc": ["Cyclone", "Low/tropical low", "Tropical low", "Trough/monsoonal trough"],
    "storm": ["Storm", "Thunderstorm", "Tornado", "Hailstorm", "Storm surge"],
}

# Data hygiene sentinels.
OLE_NULL_DATE = "1899-12-30"   # OLE/Excel epoch null — flag, never treat as real
JAN1_PLACEHOLDER_FLAG = True   # Jan-1 ignition dates are often placeholders — flag, don't drop

# Hotspot association parameters (Section 2).
HOTSPOT_BUFFER_KM = 1.5
HOTSPOT_TEMPORAL_GATE_DAYS = 3
DBSCAN_EPS_KM = 5.0
DBSCAN_TEMPORAL_DAYS = 2

# Gadi context.
GADI = {
    "project": "gb02",
    "user_gdata": "/g/data/gb02/sm5259/EM_Demand",
    "storage_flags": "gdata/if69+gdata/su28+gdata/gb02+gdata/xp65+gdata/ia39+gdata/rt52+gdata/zv2",
    "ffdi_zarr": "/g/data/ia39/ncra/fire/bias-input/ffdi/"
                 "AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr",
    "weather_objects": "/g/data/if69/cj0591/GC26_energy_synoptics/data/weatherfeatures.era5/",
    "era5_hourly": "/g/data/rt52/era5/",
    "era5_daily_1deg": "/g/data/su28/ERA5/daily",
    "wxsyslib": "/g/data/gb02/mb0427/WxSysLib",
}


def tier_for_date(date) -> int:
    """Confidence tier (1/2/3) for a datetime-like date."""
    import pandas as pd
    d = pd.Timestamp(date)
    if d >= pd.Timestamp(TIER_BOUNDS[1][0]):
        return 1
    if d >= pd.Timestamp(TIER_BOUNDS[2][0]):
        return 2
    return 3


def component_available(component: str, date) -> bool:
    """True if a component is available on the given date."""
    import pandas as pd
    start, end = COMPONENT_AVAILABILITY[component]
    d = pd.Timestamp(date)
    if d < pd.Timestamp(start):
        return False
    return end is None or d <= pd.Timestamp(end)
