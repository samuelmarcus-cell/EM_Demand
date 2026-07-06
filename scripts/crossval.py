"""FIRMS vs DEA hotspot cross-validation (design decision 4).

Both loaders emit the same schema, so validation compares daily national
hotspot counts and FRP sums over the overlap period, per sensor family
(MODIS / VIIRS S-NPP). Agreement is summarised as Pearson and Spearman
correlations of the daily series; the point is to confirm the FIRMS record
underpinning tiers 1-2 is not idiosyncratic before tier decisions bake in.
"""

import pandas as pd

_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)  # AEST daily bucketing, as elsewhere


def _family(sensor: pd.Series) -> pd.Series:
    s = sensor.str.upper()
    return pd.Series("other", index=sensor.index).where(
        ~s.str.contains("MODIS"), "MODIS"
    ).where(~s.str.contains("VIIRS"), "VIIRS")


def daily_by_sensor(hotspots: pd.DataFrame, source: str) -> pd.DataFrame:
    """Daily national count + FRP sum per sensor family: date, family, n, frp_sum."""
    h = hotspots.copy()
    h["date"] = (h["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET).dt.normalize()
    h["family"] = _family(h["sensor"].astype(str))
    out = (
        h.groupby(["date", "family"])
        .agg(n=("lat", "size"), frp_sum=("frp", "sum"))
        .reset_index()
    )
    out["source"] = source
    return out


def compare_daily(firms: pd.DataFrame, dea: pd.DataFrame) -> pd.DataFrame:
    """Join the two daily series on (date, family) over their overlap period."""
    f = daily_by_sensor(firms, "firms")
    d = daily_by_sensor(dea, "dea")
    start = max(f["date"].min(), d["date"].min())
    end = min(f["date"].max(), d["date"].max())
    merged = pd.merge(
        f[f["date"].between(start, end)],
        d[d["date"].between(start, end)],
        on=["date", "family"],
        how="outer",
        suffixes=("_firms", "_dea"),
    ).fillna({"n_firms": 0, "n_dea": 0, "frp_sum_firms": 0.0, "frp_sum_dea": 0.0})
    return merged.sort_values(["family", "date"]).reset_index(drop=True)


def agreement_stats(compared: pd.DataFrame) -> pd.DataFrame:
    """Per sensor family: n days, count/FRP correlations, mean count ratio."""
    rows = []
    for fam, g in compared.groupby("family"):
        rows.append(
            {
                "family": fam,
                "n_days": len(g),
                "count_pearson": g["n_firms"].corr(g["n_dea"]),
                "count_spearman": g["n_firms"].corr(g["n_dea"], method="spearman"),
                "frp_pearson": g["frp_sum_firms"].corr(g["frp_sum_dea"]),
                "count_ratio_firms_dea": g["n_firms"].sum() / max(g["n_dea"].sum(), 1),
            }
        )
    return pd.DataFrame(rows)
