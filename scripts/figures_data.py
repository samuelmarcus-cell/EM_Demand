"""Tidy data exports for R/ggplot figures (compute here, render in R)."""

import pandas as pd

_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)  # AEST, as everywhere else

BENCHMARKS = {
    "Ash Wednesday": "1983-02-16",
    "NSW Jan 1994": "1994-01-08",
    "VIC Dandenongs Jan 1997": "1997-01-21",
    "Canberra fires 2003": "2003-01-18",
    "Black Saturday": "2009-02-07",
    "TC Yasi": "2011-02-02",
    "TAS Dunalley 2013": "2013-01-04",
    "NSW Blue Mtns Oct 2013": "2013-10-17",
    "TAS fires Jan 2016": "2016-01-20",
    "QLD Deepwater Nov 2018": "2018-11-28",
    "Black Summer peak": "2020-01-04",
    "East-coast floods 2022": "2022-02-28",
}


def hotspots_for_days(hotspots: pd.DataFrame, days) -> pd.DataFrame:
    """Hotspots whose AEST local day is in `days` -> date, lat, lon, frp."""
    local_day = (hotspots["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET).dt.normalize()
    wanted = pd.to_datetime(pd.Index(days))
    keep = local_day.isin(wanted)
    out = hotspots.loc[keep, ["lat", "lon", "frp"]].copy()
    out.insert(0, "date", local_day[keep].values)
    return out.reset_index(drop=True)


def benchmark_table(panel: pd.DataFrame, benchmarks: dict) -> pd.DataFrame:
    """Per benchmark event: DLI, tier, and within-tier percentile on the peak day."""
    p = panel.set_index("date")
    rows = []
    for name, day in benchmarks.items():
        row = p.loc[pd.Timestamp(day)]
        tier = int(row["confidence_tier"])
        in_tier = p[p["confidence_tier"] == tier]["dli"]
        rows.append({
            "name": name,
            "date": pd.Timestamp(day),
            "dli": float(row["dli"]),
            "confidence_tier": tier,
            "pct": float((in_tier < row["dli"]).mean()),
        })
    return pd.DataFrame(rows)
