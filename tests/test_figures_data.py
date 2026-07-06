import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.figures_data import benchmark_table, hotspots_for_days


def test_hotspots_for_days_aest_bucketing():
    hs = pd.DataFrame({
        "lat": [-35.0, -36.0, -20.0],
        "lon": [149.0, 145.0, 130.0],
        # 20:00 UTC = 06:00 AEST NEXT day; 04:00 UTC = 14:00 AEST same day
        "datetime_utc": pd.to_datetime(
            ["2009-02-06 20:00", "2009-02-07 04:00", "2009-03-01 04:00"], utc=True),
        "frp": [10.0, 20.0, 5.0],
    })
    out = hotspots_for_days(hs, ["2009-02-07"])
    assert len(out) == 2  # both land on local 2009-02-07; March row excluded
    assert set(out.columns) == {"date", "lat", "lon", "frp"}
    assert (out["date"] == pd.Timestamp("2009-02-07")).all()


def test_benchmark_table_within_tier_pct():
    dates = pd.date_range("2009-01-01", periods=10, freq="D")
    panel = pd.DataFrame({
        "date": dates,
        "dli": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        "confidence_tier": 2,
    })
    out = benchmark_table(panel, {"Test event": "2009-01-10"})
    assert set(out.columns) == {"name", "date", "dli", "confidence_tier", "pct"}
    row = out.iloc[0]
    assert row["name"] == "Test event"
    assert row["pct"] == 0.9  # 9 of 10 tier-2 days are below it
    assert row["confidence_tier"] == 2
