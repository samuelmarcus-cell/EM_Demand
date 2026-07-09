"""Per-state hazard-load layers for the state×hazard compounding panel.

Everything here measures HAZARD LOAD — the activity of the hazard itself,
agnostic of exposure and vulnerability — never demand. DRFA is an impact
layer, kept off the hazard axis. Spec:
docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md
"""

import pandas as pd
import geopandas as gpd

from scripts.config import COMPONENT_AVAILABILITY, PATHS
from scripts.dli import tier_series

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]
FIRE_METRICS = ["concurrent_burden", "ignition_load", "growth_load", "frp_load"]
FIRE_START = pd.Timestamp("1979-01-01")   # tier 3 fire = polygon burn windows
HOTSPOT_START = pd.Timestamp(COMPONENT_AVAILABILITY["modis"][0])  # 2000-11-01


def normalise_state(raw: pd.Series) -> pd.Series:
    """Normalise messy gdb state labels ("WA (Western Australia)", "Qld",
    "ACT (...)") to the panel's 7 abbreviations; ACT folds into NSW."""
    abbrev = raw.astype(str).str.split(" ").str[0].str.upper()
    return abbrev.replace({"ACT": "NSW"})


def _per_state_daily(df, value_cols, states, idx, fill=0.0):
    """Reindex each state's series to the full daily index, filling gaps.

    Within a layer's availability window a missing day means zero
    activity (project rule), hence the fill.
    """
    frames = []
    for state in states:
        s = (
            df[df["state"] == state]
            .set_index("date")[value_cols]
            .reindex(idx)
            .fillna(fill)
            .reset_index()
        )
        s["state"] = state
        frames.append(s)
    return pd.concat(frames, ignore_index=True)


def state_burn_window_daily(windows: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Per-state daily count of active polygon burn windows.

    Same sweep-line logic and +1-day end convention as the national
    burn_window_daily in scripts/fire_association.py. This is the Tier-3
    fire-activity signal: no satellite record before Nov 2000, so daily
    fire activity is the count of mapped fires whose window covers the day.
    Returns [date, state, n_windows_active] on the full daily grid.
    """
    w = windows.dropna(subset=["window_start", "window_end"]).copy()
    w["state"] = normalise_state(w["state"])
    w = w[w["state"].isin(STATES)]
    start = pd.Timestamp(start) if start is not None else FIRE_START
    end = pd.Timestamp(end) if end is not None else w["window_end"].max()
    idx = pd.date_range(start, end, freq="D", name="date")
    frames = []
    for state in STATES:
        g = w[w["state"] == state]
        starts = g["window_start"].dt.normalize().value_counts()
        # +1 day: a window ending on day D is still active on D
        ends = (g["window_end"].dt.normalize() + pd.Timedelta(days=1)).value_counts()
        active = starts.sub(ends, fill_value=0).sort_index().cumsum()
        s = (active.reindex(idx, method="ffill").fillna(0).astype(int)
             .rename("n_windows_active").reset_index())
        s["state"] = state
        frames.append(s)
    return pd.concat(frames, ignore_index=True)


def state_fire_layer(metrics: pd.DataFrame, windows: pd.DataFrame,
                     end=None) -> pd.DataFrame:
    """Per-state fire hazard-load percentiles, 1979-present.

    Mirrors the frozen national sub_fire recipe per tier: Tier 3
    (1979 - 2000-10-31) scores on the per-state burn-window count only;
    Tiers 1-2 score on the mean of the per-state hotspot-metric
    percentiles. Every percentile is ranked within (state,
    confidence_tier, calendar month) — the project's standard machinery —
    so tier-3 values never rank against satellite-era values.
    Returns columns [date, state, state_fire, confidence_tier].
    """
    df = metrics[metrics["region"].isin(STATES)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"region": "state"})
    end = pd.Timestamp(end) if end is not None else df["date"].max()

    # Tiers 1-2: hotspot metrics on the hotspot-era grid
    idx12 = pd.date_range(HOTSPOT_START, end, freq="D", name="date")
    hot = _per_state_daily(df, FIRE_METRICS, STATES, idx12)
    hot["confidence_tier"] = tier_series(hot["date"])
    keys = [hot["state"], hot["confidence_tier"], hot["date"].dt.month]
    pct = pd.DataFrame(
        {m: hot.groupby(keys)[m].rank(pct=True) for m in FIRE_METRICS}
    )
    hot["state_fire"] = pct.mean(axis=1)

    # Tier 3: burn-window counts on the pre-hotspot grid
    bw = state_burn_window_daily(
        windows, start=FIRE_START, end=HOTSPOT_START - pd.Timedelta(days=1)
    )
    bw["confidence_tier"] = 3
    bw["state_fire"] = bw.groupby([bw["state"], bw["date"].dt.month])[
        "n_windows_active"
    ].rank(pct=True)

    cols = ["date", "state", "state_fire", "confidence_tier"]
    return (
        pd.concat([bw[cols], hot[cols]], ignore_index=True)
        .sort_values(["state", "date"])
        .reset_index(drop=True)
    )


# --- Tropical cyclone layer ---

# ~gale-force radius of a large Australian TC and the scale of pre-landfall
# preparation zones (spec §2). Sensitivity at 200/400 km, reported never tuned.
TC_RADIUS_KM = 300.0
TC_START = pd.Timestamp(COMPONENT_AVAILABILITY["tc_besttrack"][0])
_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)


def load_state_geoms(path=None) -> gpd.GeoDataFrame:
    """State polygons in GDA94 Australian Albers (EPSG:3577, metres)."""
    gdf = gpd.read_file(path or PATHS.aus_states_geojson)
    return gdf.to_crs(3577)


def tc_state_daily(tracks: pd.DataFrame, states_gdf: gpd.GeoDataFrame,
                   radius_km: float = TC_RADIUS_KM) -> pd.DataFrame:
    """Daily max in-range wind per state from cyclone-intensity track points.

    A point loads a state when it lies within radius_km of the state's
    polygon and the system is at cyclone intensity (BoM stage code
    type == "T"). A point can load several states at once — deliberate:
    both states' agencies respond. Returns rows only for (date, state)
    with at least one in-range point: [date, state, tc_max_wind].
    """
    t = tracks[tracks["type"] == "T"].copy()
    t["date"] = (t["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET).dt.normalize()
    pts = gpd.GeoDataFrame(
        t[["date", "max_wind_spd"]],
        geometry=gpd.points_from_xy(t["lon"], t["lat"], crs=4326),
    ).to_crs(3577)
    hits = gpd.sjoin(
        pts, states_gdf[["state", "geometry"]],
        predicate="dwithin", distance=radius_km * 1000.0,
    )
    return (
        hits.groupby(["date", "state"], as_index=False)
        .agg(tc_max_wind=("max_wind_spd", "max"))
    )


def state_tc_layer(tc_daily: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Per-state tc percentiles: within (state, calendar month) rank of the
    daily max in-range wind, parallel to the national max-with-severity
    logic. Days with no in-range cyclone (and in-range points with
    unrecorded wind) rank as 0 wind, so they can never fake severity.
    No tier dimension — the best-track record has one era (spec §2).
    Returns [date, state, state_tc, tc_max_wind].
    """
    start = pd.Timestamp(start) if start is not None else TC_START
    end = pd.Timestamp(end) if end is not None else tc_daily["date"].max()
    idx = pd.date_range(start, end, freq="D", name="date")
    out = _per_state_daily(tc_daily, ["tc_max_wind"], STATES, idx)
    out["state_tc"] = out.groupby([out["state"], out["date"].dt.month])[
        "tc_max_wind"
    ].rank(pct=True)
    return out[["date", "state", "state_tc", "tc_max_wind"]]
