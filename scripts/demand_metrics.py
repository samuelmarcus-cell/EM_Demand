"""Section 3: daily fire demand metrics from the per-fire-per-day record.

Inputs are the Section 2 match tables (polygon + satellite-only) joined back
to hotspot coordinates. Metric definitions (v0):

    concurrent_burden  distinct fires active on the day
    ignition_load      fires whose first observed day is that day
    growth_load        sum over fires of max(0, n_hotspots - previous day's
                       n_hotspots); a fire's first day contributes its full
                       count (escalation, not steady burning, drives demand)
    frp_load           total FRP (MW) across active fires
    dispersion_km      mean pairwise great-circle distance between active
                       fire centroids (Fires_SWTs Step 4 port); NaN if <2
    n_states_active    distinct states with active fire
    unseasonal_hotspots  hotspots in states outside their climatological
                       fire season (see fire_seasons)

Regions: AUS (national), each state, SEAUS (SE_AUS_BBOX). Metrics are
computed identically on the region-filtered fire-day table.
"""

import numpy as np
import pandas as pd

from scripts.config import SE_AUS_BBOX

_EARTH_R_KM = 6371.0


def build_fire_days(matches: pd.DataFrame, hotspot_coords: pd.DataFrame) -> pd.DataFrame:
    """Per-fire-per-day table with centroid and hotspot stats.

    matches: concatenated polygon + satellite match rows
             (hotspot_idx, fire_uid, date_local, frp).
    hotspot_coords: lat/lon indexed like hotspots_firms.parquet.
    """
    m = matches.merge(
        hotspot_coords[["lat", "lon"]], left_on="hotspot_idx", right_index=True, how="left"
    )
    return (
        m.groupby(["fire_uid", "date_local"])
        .agg(
            n_hotspots=("hotspot_idx", "size"),
            frp_sum=("frp", "sum"),
            lat=("lat", "mean"),
            lon=("lon", "mean"),
        )
        .reset_index()
        .rename(columns={"date_local": "date"})
    )


def assign_states(fire_days: pd.DataFrame, states_geojson_path) -> pd.DataFrame:
    """Attach a state to each fire-day by centroid point-in-polygon.

    Coastal/offshore centroids that miss every state polygon get the nearest
    state (sjoin_nearest), so no fire-day is silently dropped from per-state
    metrics.
    """
    import geopandas as gpd

    states = gpd.read_file(states_geojson_path)
    pts = gpd.GeoDataFrame(
        fire_days,
        geometry=gpd.points_from_xy(fire_days["lon"], fire_days["lat"], crs="EPSG:4326"),
    )
    joined = gpd.sjoin(pts, states, predicate="within", how="left").drop(columns="index_right")
    missing = joined["state"].isna()
    if missing.any():
        near = gpd.sjoin_nearest(
            pts.loc[missing].to_crs("EPSG:3577"), states.to_crs("EPSG:3577"), how="left"
        )
        near = near[~near.index.duplicated()]
        joined.loc[missing, "state"] = near["state"]
    return pd.DataFrame(joined.drop(columns="geometry"))


def fire_seasons(fire_days: pd.DataFrame, frp_share: float = 0.80) -> dict:
    """Per-state fire-season months from FRP climatology.

    For each state, months are ranked by their share of total FRP and taken
    until cumulative share >= frp_share. Applied to all tiers (design
    decision 5).
    """
    df = fire_days.copy()
    df["month"] = df["date"].dt.month
    seasons = {}
    for state, grp in df.groupby("state"):
        by_month = grp.groupby("month")["frp_sum"].sum().sort_values(ascending=False)
        cum = by_month.cumsum() / by_month.sum()
        n_keep = int((cum < frp_share).sum()) + 1
        seasons[state] = set(by_month.index[:n_keep])
    return seasons


def _mean_pairwise_km(lat: np.ndarray, lon: np.ndarray) -> float:
    """Mean great-circle distance over all centroid pairs (NaN if <2)."""
    n = len(lat)
    if n < 2:
        return np.nan
    la, lo = np.radians(lat), np.radians(lon)
    i, j = np.triu_indices(n, k=1)
    d = np.arccos(
        np.clip(
            np.sin(la[i]) * np.sin(la[j]) + np.cos(la[i]) * np.cos(la[j]) * np.cos(lo[i] - lo[j]),
            -1.0,
            1.0,
        )
    )
    return float(d.mean() * _EARTH_R_KM)


def daily_metrics(fire_days: pd.DataFrame, seasons: dict, region: str = "AUS") -> pd.DataFrame:
    """Daily metric panel for one region's fire-day table."""
    df = fire_days.sort_values(["fire_uid", "date"]).copy()

    prev = df.groupby("fire_uid")["n_hotspots"].shift(1)
    prev_date = df.groupby("fire_uid")["date"].shift(1)
    # growth resets when a fire skips a day: compare against 0, not stale counts
    prev = prev.where(prev_date == df["date"] - pd.Timedelta(days=1), 0).fillna(0)
    df["growth"] = (df["n_hotspots"] - prev).clip(lower=0)
    df["is_ignition"] = df.groupby("fire_uid").cumcount() == 0
    df["out_of_season"] = [
        m not in seasons.get(s, set()) for s, m in zip(df["state"], df["date"].dt.month)
    ]

    daily = df.groupby("date").agg(
        concurrent_burden=("fire_uid", "nunique"),
        ignition_load=("is_ignition", "sum"),
        growth_load=("growth", "sum"),
        frp_load=("frp_sum", "sum"),
        n_states_active=("state", "nunique"),
    )
    daily["unseasonal_hotspots"] = (
        df[df["out_of_season"]].groupby("date")["n_hotspots"].sum().reindex(daily.index).fillna(0).astype(int)
    )
    disp = df.groupby("date").apply(
        lambda g: _mean_pairwise_km(g["lat"].values, g["lon"].values), include_groups=False
    )
    daily["dispersion_km"] = disp
    daily["region"] = region
    return daily.reset_index()


def region_filter(fire_days: pd.DataFrame, region: str) -> pd.DataFrame:
    """Subset the fire-day table to a region: AUS, a state code, or SEAUS."""
    if region == "AUS":
        return fire_days
    if region == "SEAUS":
        b = SE_AUS_BBOX
        return fire_days[
            fire_days["lon"].between(b["lon_min"], b["lon_max"])
            & fire_days["lat"].between(b["lat_min"], b["lat_max"])
        ]
    return fire_days[fire_days["state"] == region]


def demand_metrics_panel(fire_days: pd.DataFrame, seasons: dict, regions=None) -> pd.DataFrame:
    """Long-format daily metrics across regions."""
    regions = regions or ["AUS", "SEAUS", "NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]
    parts = [
        daily_metrics(sub, seasons, region=r)
        for r in regions
        if len(sub := region_filter(fire_days, r))
    ]
    return pd.concat(parts, ignore_index=True)
