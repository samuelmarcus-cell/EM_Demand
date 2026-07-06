import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.crossval import agreement_stats, compare_daily


def _hotspots(times, sensors, frps):
    return pd.DataFrame(
        {
            "lat": [-35.0] * len(times),
            "lon": [149.0] * len(times),
            "datetime_utc": pd.to_datetime(times, utc=True),
            "frp": frps,
            "sensor": sensors,
        }
    )


def test_compare_daily_alignment_and_overlap():
    # 04:00 UTC = 14:00 AEST same day; 20:00 UTC = 06:00 AEST next day
    firms = _hotspots(
        ["2020-01-01 04:00", "2020-01-01 20:00", "2020-01-02 04:00"],
        ["MODIS", "MODIS", "VIIRS S-NPP"],
        [10.0, 20.0, 5.0],
    )
    dea = _hotspots(
        ["2020-01-01 04:30", "2020-01-02 04:00", "2019-12-25 04:00"],
        ["Terra MODIS", "viirs", "MODIS"],
        [12.0, 6.0, 1.0],
    )
    out = compare_daily(firms, dea).set_index(["date", "family"])
    # overlap starts at the later series start (FIRMS 2020-01-01 local 2020-01-01)
    assert out.index.get_level_values("date").min() == pd.Timestamp("2020-01-01")
    m = out.loc[(pd.Timestamp("2020-01-01"), "MODIS")]
    assert m["n_firms"] == 1 and m["n_dea"] == 1 and m["frp_sum_firms"] == 10.0
    v = out.loc[(pd.Timestamp("2020-01-02"), "VIIRS")]
    assert v["n_firms"] == 1 and v["n_dea"] == 1
    # FIRMS-only local day still present with dea zero-filled
    m2 = out.loc[(pd.Timestamp("2020-01-02"), "MODIS")]
    assert m2["n_firms"] == 1 and m2["n_dea"] == 0


def test_agreement_stats_columns():
    firms = _hotspots(["2020-01-01 04:00", "2020-01-02 04:00"], ["MODIS", "MODIS"], [1.0, 2.0])
    stats = agreement_stats(compare_daily(firms, firms.copy()))
    row = stats.set_index("family").loc["MODIS"]
    assert row["count_ratio_firms_dea"] == 1.0
    assert row["count_pearson"] == 1.0 or pd.isna(row["count_pearson"])
