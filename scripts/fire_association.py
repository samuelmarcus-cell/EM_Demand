"""Section 2: hotspot -> fire-polygon association.

Spatially joins FIRMS hotspots to National Historical Bushfire Extents
footprints (buffered HOTSPOT_BUFFER_KM in EPSG:3577) with a temporal gate
around each fire's plausible burn window:

    window_start = ignition - HOTSPOT_TEMPORAL_GATE_DAYS
    window_end   = coalesce(extinguish, capture, ignition + 21d) + gate

Fires without a usable ignition date (missing or OLE-null) cannot be gated
and are excluded from association — they remain in the Tier-3 polygon record.
Jan-1 ignition dates are retained but flagged (often placeholders).

Multi-matches (overlapping agency captures of the same fire) are resolved by
keeping, per hotspot, the match with the tightest temporal window, then the
smallest area.

Daily bucketing uses a fixed UTC+10 offset (AEST) so a burning local day is
not split across two UTC dates by the afternoon/overnight overpass pair.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from scripts.config import (
    HOTSPOT_BUFFER_KM,
    HOTSPOT_TEMPORAL_GATE_DAYS,
    OLE_NULL_DATE,
    PATHS,
)

_ALBERS = "EPSG:3577"
_GDB_LAYERS = ["National_Historical_Bushfire_Extents_v4", "NT_Historical_Bushfire_Extents_v1"]
_ASSUMED_FIRE_DAYS = 21
_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)  # AEST, fixed (no DST) for daily bucketing


def _clean_date(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_localize(None)
    out[out == pd.Timestamp(OLE_NULL_DATE)] = pd.NaT
    out[out < pd.Timestamp("1900-01-01")] = pd.NaT
    return out


def temporal_windows(df: pd.DataFrame, gate_days: int = HOTSPOT_TEMPORAL_GATE_DAYS) -> pd.DataFrame:
    """Attach window_start/window_end/window_days; drop rows with no ignition date."""
    df = df.copy()
    ign = _clean_date(df["ignition_date"])
    ext = _clean_date(df["extinguish_date"])
    cap = _clean_date(df["capture_date"]) if "capture_date" in df else pd.Series(pd.NaT, index=df.index)

    df["ignition_date"] = ign
    end = ext.fillna(cap).fillna(ign + pd.Timedelta(days=_ASSUMED_FIRE_DAYS))
    end = end.where(end >= ign)  # guard against extinguish/capture typos before ignition
    end = end.fillna(ign + pd.Timedelta(days=_ASSUMED_FIRE_DAYS))

    gate = pd.Timedelta(days=gate_days)
    df["window_start"] = ign - gate
    df["window_end"] = end + gate
    df["window_days"] = (df["window_end"] - df["window_start"]).dt.days
    df["jan1_ignition"] = (ign.dt.month == 1) & (ign.dt.day == 1)
    return df[ign.notna()].copy()


def load_fire_polygons(
    gdb_path: Path | None = None, min_window_end: str = "2000-11-01"
) -> gpd.GeoDataFrame:
    """Buffered, windowed fire polygons in EPSG:3577 for the hotspot era.

    Only fires whose temporal window ends on/after min_window_end (start of
    the MODIS record) are kept — earlier fires can never match a hotspot.
    """
    gdb_path = Path(gdb_path or PATHS.fire_polygons_gdb)
    parts = []
    for layer in _GDB_LAYERS:
        g = gpd.read_file(
            gdb_path,
            layer=layer,
            columns=["fire_id", "fire_name", "ignition_date", "capture_date", "extinguish_date", "area_ha", "state"],
        )
        g["layer"] = layer
        parts.append(g)
    fires = pd.concat(parts, ignore_index=True)
    fires["fire_uid"] = fires["layer"].str.split("_").str[0] + "_" + fires.index.astype(str)

    fires = temporal_windows(fires)
    fires = fires[fires["window_end"] >= pd.Timestamp(min_window_end)].copy()

    fires = fires.to_crs(_ALBERS)
    fires["geometry"] = fires.geometry.simplify(100).buffer(HOTSPOT_BUFFER_KM * 1000)
    return fires.reset_index(drop=True)


def dedupe_matches(pairs: pd.DataFrame) -> pd.DataFrame:
    """One fire per hotspot: tightest temporal window, then smallest area."""
    return (
        pairs.sort_values(["window_days", "area_ha"])
        .drop_duplicates(subset="hotspot_idx", keep="first")
        .reset_index(drop=True)
    )


def associate_hotspots(hotspots: pd.DataFrame, fires: gpd.GeoDataFrame) -> pd.DataFrame:
    """Match hotspots to fires, chunked by month.

    hotspots: harmonised schema (lat, lon, datetime_utc, frp, ...).
    fires: output of load_fire_polygons (buffered, EPSG:3577).
    Returns one row per matched hotspot: hotspot_idx, fire_uid, date_local,
    frp, state.
    """
    hs = hotspots.reset_index(drop=True)
    t_naive = hs["datetime_utc"].dt.tz_localize(None)
    month = t_naive.dt.to_period("M")

    results = []
    for m, idx in hs.groupby(month).groups.items():
        m_start, m_end = m.start_time, m.end_time
        cand = fires[(fires["window_start"] <= m_end) & (fires["window_end"] >= m_start)]
        if cand.empty:
            continue
        chunk = hs.loc[idx]
        pts = gpd.GeoDataFrame(
            {"hotspot_idx": idx, "t": t_naive.loc[idx].values, "frp": chunk["frp"].values},
            geometry=gpd.points_from_xy(chunk["lon"], chunk["lat"], crs="EPSG:4326"),
        ).to_crs(_ALBERS)
        joined = gpd.sjoin(
            pts,
            cand[["fire_uid", "window_start", "window_end", "window_days", "area_ha", "state", "geometry"]],
            predicate="within",
            how="inner",
        )
        gated = joined[(joined["t"] >= joined["window_start"]) & (joined["t"] <= joined["window_end"])]
        if gated.empty:
            continue
        results.append(
            dedupe_matches(
                pd.DataFrame(gated.drop(columns="geometry"))[
                    ["hotspot_idx", "fire_uid", "t", "frp", "window_days", "area_ha", "state"]
                ]
            )
        )

    if not results:
        return pd.DataFrame(columns=["hotspot_idx", "fire_uid", "date_local", "frp", "state"])
    out = pd.concat(results, ignore_index=True)
    out["date_local"] = (out["t"] + _LOCAL_UTC_OFFSET).dt.normalize()
    return out[["hotspot_idx", "fire_uid", "date_local", "frp", "state"]]


def fire_daily_table(matches: pd.DataFrame) -> pd.DataFrame:
    """Per-fire-per-day aggregation: fire_id, date, n_hotspots, frp_sum, state."""
    agg = (
        matches.groupby(["fire_uid", "date_local", "state"], dropna=False)
        .agg(n_hotspots=("hotspot_idx", "size"), frp_sum=("frp", "sum"))
        .reset_index()
        .rename(columns={"fire_uid": "fire_id", "date_local": "date"})
    )
    return agg.sort_values(["date", "fire_id"]).reset_index(drop=True)
