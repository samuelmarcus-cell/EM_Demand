"""Section 2b: cluster polygon-unmatched hotspots into satellite-only fires.

ST-DBSCAN via the standard embedding trick: time is scaled into a third
spatial axis at (DBSCAN_EPS_KM / DBSCAN_TEMPORAL_DAYS) km per day, then plain
DBSCAN with eps = DBSCAN_EPS_KM runs on (x, y, t'). A point within 5 km and
2 days of a core point joins its cluster.

Clustering runs per fire-season (Jul-Jun) so label spaces stay small and
memory bounded; fires spanning the mid-winter season boundary split into two
clusters, which is acceptable for a demand index. Noise points (label -1) are
isolated single detections and are dropped from the fire table.

Cluster IDs are "SAT_<season>_<label>" to keep them disjoint from polygon
fire_uids.
"""

import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.cluster import DBSCAN

from scripts.config import DBSCAN_EPS_KM, DBSCAN_TEMPORAL_DAYS

_TO_ALBERS = Transformer.from_crs("EPSG:4326", "EPSG:3577", always_xy=True)
_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)
_MIN_SAMPLES = 3


def season_of(t: pd.Series) -> pd.Series:
    """Fire-season label (year of the July that starts it), from naive local time."""
    return t.dt.year.where(t.dt.month >= 7, t.dt.year - 1)


def cluster_season(x_km, y_km, t_days, eps_km=DBSCAN_EPS_KM, eps_days=DBSCAN_TEMPORAL_DAYS):
    """DBSCAN labels for one season's points (arrays in km / fractional days)."""
    scale = eps_km / eps_days
    X = np.column_stack([x_km, y_km, np.asarray(t_days) * scale])
    return DBSCAN(eps=eps_km, min_samples=_MIN_SAMPLES, algorithm="ball_tree", n_jobs=-1).fit_predict(X)


def cluster_unmatched(hotspots: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """Label unmatched hotspots with satellite-only cluster IDs.

    hotspots: harmonised schema rows (lat, lon, datetime_utc, frp).
    Returns matched-format rows for clustered points: hotspot_idx, fire_uid,
    date_local, frp, state=NA.
    """
    hs = hotspots.copy()
    t_local = hs["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET
    hs["season"] = season_of(t_local)
    x, y = _TO_ALBERS.transform(hs["lon"].values, hs["lat"].values)
    hs["x_km"], hs["y_km"] = np.asarray(x) / 1000, np.asarray(y) / 1000
    epoch = t_local.min().normalize()
    hs["t_days"] = (t_local - epoch) / pd.Timedelta(days=1)
    hs["date_local"] = t_local.dt.normalize()

    parts = []
    for season, grp in hs.groupby("season"):
        if verbose:
            print(f"    season {season}: {len(grp)} points", flush=True)
        labels = cluster_season(grp["x_km"].values, grp["y_km"].values, grp["t_days"].values)
        clustered = grp[labels >= 0].copy()
        clustered["fire_uid"] = [f"SAT_{season}_{l}" for l in labels[labels >= 0]]
        parts.append(clustered)

    if not parts:
        return pd.DataFrame(columns=["hotspot_idx", "fire_uid", "date_local", "frp", "state"])
    out = pd.concat(parts)
    out["hotspot_idx"] = out.index
    out["state"] = pd.NA
    return out[["hotspot_idx", "fire_uid", "date_local", "frp", "state"]].reset_index(drop=True)
