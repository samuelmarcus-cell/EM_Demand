import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.fire_association import (
    associate_hotspots,
    dedupe_matches,
    fire_daily_table,
    temporal_windows,
)

_ALBERS = "EPSG:3577"


def _square_around(lon, lat, half_km):
    pt = gpd.GeoSeries(gpd.points_from_xy([lon], [lat]), crs="EPSG:4326").to_crs(_ALBERS)
    x, y = pt.x.iloc[0], pt.y.iloc[0]
    h = half_km * 1000
    return Polygon([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)])


def _fires():
    return gpd.GeoDataFrame(
        {
            "fire_uid": ["F1", "F2"],
            "window_start": pd.to_datetime(["2020-01-01", "2019-12-01"]),
            "window_end": pd.to_datetime(["2020-01-10", "2020-02-28"]),
            "window_days": [9, 89],
            "area_ha": [100.0, 50000.0],
            "state": ["VIC", "VIC"],
        },
        geometry=[_square_around(148.0, -37.0, 5), _square_around(148.0, -37.0, 20)],
        crs=_ALBERS,
    )


def _hotspots():
    return pd.DataFrame(
        {
            "lat": [-37.0, -37.0, -30.0],
            "lon": [148.0, 148.0, 120.0],
            "datetime_utc": pd.to_datetime(
                ["2020-01-04 03:00", "2020-01-20 03:00", "2020-01-04 03:00"], utc=True
            ),
            "frp": [10.0, 20.0, 5.0],
        }
    )


def test_temporal_windows_cascade_and_filters():
    df = pd.DataFrame(
        {
            "ignition_date": ["2020-01-05", "2020-01-05", "2020-01-05", None, "1899-12-30"],
            "extinguish_date": ["2020-01-20", None, None, "2020-02-01", "2020-02-01"],
            "capture_date": [None, "2020-01-10", None, None, None],
        }
    )
    out = temporal_windows(df, gate_days=3)
    assert len(out) == 3  # missing and OLE-null ignition dropped
    ends = out["window_end"].tolist()
    assert ends[0] == pd.Timestamp("2020-01-23")  # extinguish + gate
    assert ends[1] == pd.Timestamp("2020-01-13")  # capture + gate
    assert ends[2] == pd.Timestamp("2020-01-29")  # ignition + 21d + gate
    assert (out["window_start"] == pd.Timestamp("2020-01-02")).all()


def test_temporal_windows_end_before_ignition_falls_back():
    df = pd.DataFrame(
        {
            "ignition_date": ["2020-01-05"],
            "extinguish_date": ["2019-06-01"],  # typo: before ignition
            "capture_date": [None],
        }
    )
    out = temporal_windows(df, gate_days=0)
    assert out["window_end"].iloc[0] == pd.Timestamp("2020-01-26")  # ignition + 21d


def test_temporal_windows_jan1_flag():
    df = pd.DataFrame(
        {"ignition_date": ["2020-01-01", "2020-02-05"], "extinguish_date": [None, None], "capture_date": [None, None]}
    )
    out = temporal_windows(df)
    assert out["jan1_ignition"].tolist() == [True, False]


def test_dedupe_prefers_tight_window_then_small_area():
    pairs = pd.DataFrame(
        {
            "hotspot_idx": [0, 0, 1, 1],
            "fire_uid": ["A", "B", "C", "D"],
            "window_days": [9, 89, 10, 10],
            "area_ha": [100.0, 5.0, 200.0, 50.0],
        }
    )
    out = dedupe_matches(pairs)
    assert out.set_index("hotspot_idx")["fire_uid"].to_dict() == {0: "A", 1: "D"}


def test_associate_and_daily_table():
    matches = associate_hotspots(_hotspots(), _fires())
    # hotspot 0: inside both, gated into F1 (tight window); hotspot 1: only F2's
    # window covers Jan 20; hotspot 2: far away, unmatched.
    assert len(matches) == 2
    m = matches.set_index("hotspot_idx")
    assert m.loc[0, "fire_uid"] == "F1"
    assert m.loc[1, "fire_uid"] == "F2"
    assert m.loc[0, "date_local"] == pd.Timestamp("2020-01-04")  # 03:00 UTC -> 13:00 AEST same day

    daily = fire_daily_table(matches)
    assert list(daily.columns) == ["fire_id", "date", "state", "n_hotspots", "frp_sum"]
    assert daily.loc[daily["fire_id"] == "F1", "frp_sum"].iloc[0] == 10.0


def test_associate_local_date_rollover():
    hs = pd.DataFrame(
        {
            "lat": [-37.0],
            "lon": [148.0],
            "datetime_utc": pd.to_datetime(["2020-01-04 15:00"], utc=True),  # 01:00 AEST Jan 5
            "frp": [1.0],
        }
    )
    matches = associate_hotspots(hs, _fires())
    assert matches["date_local"].iloc[0] == pd.Timestamp("2020-01-05")
