import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.satellite_clusters import cluster_season, cluster_unmatched, season_of


def test_season_of():
    t = pd.to_datetime(["2019-12-31", "2020-01-01", "2020-06-30", "2020-07-01"]).to_series()
    assert season_of(t).tolist() == [2019, 2019, 2019, 2020]


def test_cluster_season_space_and_time_gates():
    # cluster A: 4 points within 2 km / same day; B: 4 points 100 km away;
    # C: same place as A but 10 days later -> separate cluster; one lone point.
    x = [0, 1, 2, 1, 100, 101, 102, 101, 0, 1, 2, 1, 500]
    y = [0, 1, 0, 2, 0, 1, 0, 2, 0, 1, 0, 2, 500]
    t = [0, 0, 0.1, 0.1, 0, 0, 0.1, 0.1, 10, 10, 10.1, 10.1, 0]
    labels = cluster_season(np.array(x, float), np.array(y, float), np.array(t, float))
    a, b, c = labels[0], labels[4], labels[8]
    assert len({a, b, c}) == 3 and min(a, b, c) >= 0
    assert list(labels[:4]) == [a] * 4
    assert list(labels[4:8]) == [b] * 4
    assert list(labels[8:12]) == [c] * 4
    assert labels[12] == -1  # isolated point is noise


def test_cluster_unmatched_ids_and_noise_drop():
    base = pd.Timestamp("2020-01-04 03:00", tz="UTC")
    df = pd.DataFrame(
        {
            "lat": [-37.0, -37.005, -37.01, -20.0],
            "lon": [148.0, 148.005, 148.01, 130.0],
            "datetime_utc": [base, base, base + pd.Timedelta("1h"), base],
            "frp": [1.0, 2.0, 3.0, 4.0],
        },
        index=[10, 11, 12, 13],
    )
    out = cluster_unmatched(df)
    assert len(out) == 3  # lone NT point dropped as noise
    assert out["fire_uid"].nunique() == 1
    assert out["fire_uid"].iloc[0].startswith("SAT_2019_")
    assert set(out["hotspot_idx"]) == {10, 11, 12}
    assert (out["date_local"] == pd.Timestamp("2020-01-04")).all()


def test_cluster_unmatched_seasons_disjoint():
    pts = {
        "lat": [-37.0, -37.005, -37.01] * 2,
        "lon": [148.0, 148.005, 148.01] * 2,
        "datetime_utc": (
            [pd.Timestamp("2020-01-04 03:00", tz="UTC")] * 3
            + [pd.Timestamp("2020-09-04 03:00", tz="UTC")] * 3
        ),
        "frp": [1.0] * 6,
    }
    out = cluster_unmatched(pd.DataFrame(pts))
    ids = set(out["fire_uid"])
    assert len(ids) == 2
    assert any(i.startswith("SAT_2019_") for i in ids) and any(i.startswith("SAT_2020_") for i in ids)
