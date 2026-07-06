"""BoM tropical cyclone best-track loader (IDCKMSTM0S.csv, 1906-present).

Source: http://www.bom.gov.au/clim_data/IDCKMSTM0S.csv (3 header lines above
the column row). TM timestamps are UTC. Emits track points:
    tc_id, name, datetime_utc, lat, lon, central_pres, max_wind_spd, type

and a daily panel of TC activity in the Australian region:
    date, tc_active, n_tcs_active, tc_names
"""

import pandas as pd

from scripts.config import PATHS

_USECOLS = ["NAME", "DISTURBANCE_ID", "TM", "TYPE", "LAT", "LON", "CENTRAL_PRES", "MAX_WIND_SPD"]
_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)


def load_tc_tracks(path=None) -> pd.DataFrame:
    """Track-point table from the BoM best-track CSV."""
    df = pd.read_csv(path or PATHS.bom_tc_dir / "IDCKMSTM0S.csv", skiprows=3, usecols=_USECOLS)
    out = pd.DataFrame(
        {
            "tc_id": df["DISTURBANCE_ID"].str.strip(),
            "name": df["NAME"].str.strip().str.title(),
            "datetime_utc": pd.to_datetime(df["TM"], utc=True, errors="coerce"),
            "lat": pd.to_numeric(df["LAT"], errors="coerce"),
            "lon": pd.to_numeric(df["LON"], errors="coerce"),
            "central_pres": pd.to_numeric(df["CENTRAL_PRES"], errors="coerce"),
            "max_wind_spd": pd.to_numeric(df["MAX_WIND_SPD"], errors="coerce"),
            "type": df["TYPE"].str.strip(),
        }
    )
    return out.dropna(subset=["datetime_utc", "lat", "lon"]).reset_index(drop=True)


def tc_daily_panel(tracks: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Daily panel: tc_active, n_tcs_active, tc_names (local AEST dates)."""
    t = tracks.copy()
    t["date"] = (t["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET).dt.normalize()
    daily = t.groupby("date").agg(
        n_tcs_active=("tc_id", "nunique"),
        tc_names=("name", lambda s: sorted(set(s) - {"Unnamed", "Noname"})),
    )

    start = pd.Timestamp(start) if start else daily.index.min()
    end = pd.Timestamp(end) if end else daily.index.max()
    idx = pd.date_range(start, end, freq="D", name="date")
    panel = daily.reindex(idx)
    panel["tc_active"] = panel["n_tcs_active"].notna()
    panel["n_tcs_active"] = panel["n_tcs_active"].fillna(0).astype(int)
    panel["tc_names"] = panel["tc_names"].apply(lambda v: v if isinstance(v, list) else [])
    return panel.reset_index()[["date", "tc_active", "n_tcs_active", "tc_names"]]
