import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.demand_metrics import (
    _mean_pairwise_km,
    build_fire_days,
    daily_metrics,
    demand_metrics_panel,
    fire_seasons,
    region_filter,
)


def _fire_days():
    return pd.DataFrame(
        {
            "fire_uid": ["A", "A", "A", "B", "C"],
            "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04", "2020-01-02", "2020-06-15"]),
            "n_hotspots": [10, 25, 5, 3, 4],
            "frp_sum": [100.0, 250.0, 50.0, 30.0, 8.0],
            "lat": [-37.0, -37.0, -37.0, -36.0, -35.0],
            "lon": [148.0, 148.0, 148.0, 147.0, 138.0],
            "state": ["VIC", "VIC", "VIC", "VIC", "SA"],
        }
    )


def test_build_fire_days_centroid_and_agg():
    matches = pd.DataFrame(
        {
            "hotspot_idx": [0, 1, 2],
            "fire_uid": ["F", "F", "G"],
            "date_local": pd.to_datetime(["2020-01-01"] * 3),
            "frp": [10.0, 20.0, 5.0],
        }
    )
    coords = pd.DataFrame({"lat": [-37.0, -38.0, -20.0], "lon": [148.0, 149.0, 130.0]})
    fd = build_fire_days(matches, coords)
    f = fd.set_index("fire_uid").loc["F"]
    assert f["n_hotspots"] == 2 and f["frp_sum"] == 30.0
    assert f["lat"] == -37.5 and f["lon"] == 148.5


def test_fire_seasons_cumulative_share():
    fd = pd.DataFrame(
        {
            "state": ["VIC"] * 4,
            "date": pd.to_datetime(["2020-01-15", "2021-01-20", "2020-02-10", "2020-07-01"]),
            "frp_sum": [60.0, 15.0, 20.0, 5.0],
        }
    )
    seasons = fire_seasons(fd, frp_share=0.80)
    assert seasons["VIC"] == {1, 2}  # Jan 75% -> +Feb 95% >= 80%; July excluded


def test_mean_pairwise_km():
    assert np.isnan(_mean_pairwise_km(np.array([-37.0]), np.array([148.0])))
    # ~1 degree of latitude ~= 111 km
    d = _mean_pairwise_km(np.array([-37.0, -38.0]), np.array([148.0, 148.0]))
    assert 105 < d < 118


def test_daily_metrics_growth_ignition_unseasonal():
    m = daily_metrics(_fire_days(), seasons={"VIC": {1, 2}, "SA": {1}}).set_index("date")
    d1, d2 = m.loc["2020-01-01"], m.loc["2020-01-02"]
    assert d1["concurrent_burden"] == 1 and d2["concurrent_burden"] == 2
    assert d1["ignition_load"] == 1 and d2["ignition_load"] == 1
    assert d1["growth_load"] == 10  # new fire contributes full count
    assert d2["growth_load"] == 15 + 3  # A grew 10->25, B new with 3
    # A skipped Jan 3: Jan 4 growth compares to 0, not stale Jan 2 count
    assert m.loc["2020-01-04", "growth_load"] == 5
    assert np.isnan(d1["dispersion_km"]) and d2["dispersion_km"] > 0
    # June fire in SA (season = Jan only) is out of season
    assert m.loc["2020-06-15", "unseasonal_hotspots"] == 4
    assert d1["unseasonal_hotspots"] == 0


def test_region_filter_and_panel():
    fd = _fire_days()
    assert len(region_filter(fd, "SA")) == 1
    assert len(region_filter(fd, "SEAUS")) == 4  # SA fire at lon 138 is outside bbox
    panel = demand_metrics_panel(fd, seasons={"VIC": {1}, "SA": {1}}, regions=["AUS", "VIC", "SA"])
    assert set(panel["region"]) == {"AUS", "VIC", "SA"}
    aus = panel[panel["region"] == "AUS"]
    assert aus["concurrent_burden"].max() == 2
