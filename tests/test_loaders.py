import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.loaders.hotspots_firms import harmonise_firms
from scripts.loaders.tfb_vic import parse_districts, parse_span, tfb_daily_panel


def test_firms_harmonise_and_snpp_filter():
    df = pd.DataFrame(
        {
            "latitude": [-37.1, -36.5, -35.0],
            "longitude": [145.2, 148.0, 149.0],
            "acq_date": ["2020-01-04", "2020-01-04", "2020-01-04"],
            "acq_time": [312, 1450, 1450],
            "frp": [55.2, 12.0, 8.0],
            "confidence": ["80", "n", "n"],
            "instrument": ["MODIS", "VIIRS", "VIIRS"],
            "satellite": ["Terra", "N", "1"],  # "1" = NOAA-20, must be dropped
        }
    )
    out = harmonise_firms(df)
    assert len(out) == 2
    assert set(out["sensor"]) == {"MODIS_TERRA", "VIIRS_SNPP"}
    assert out["datetime_utc"].iloc[0] == pd.Timestamp("2020-01-04 03:12", tz="UTC")
    assert list(out.columns) == ["lat", "lon", "datetime_utc", "frp", "sensor", "confidence", "source"]


def test_parse_districts_overlapping_names():
    found, whole = parse_districts(
        "Mallee, Wimmera, North Central, Central (includes Melbourne and Geelong) and West and South Gippsland"
    )
    assert whole is False
    assert set(found) == {"Mallee", "Wimmera", "North Central", "Central", "West and South Gippsland"}
    # "South West" must NOT be claimed out of "West and South Gippsland"
    assert "South West" not in found


def test_parse_districts_whole_state():
    found, whole = parse_districts("the whole State of Victoria")
    assert whole is True
    assert len(found) == 9


def test_parse_span():
    s, e = parse_span("11/03/2026 00:01 - 11/03/2026 23:59")
    assert s == pd.Timestamp("2026-03-11 00:01")
    assert e == pd.Timestamp("2026-03-11 23:59")
    # cross-midnight legacy form
    s, e = parse_span("26/12/1945 00:00 - 27/12/1945 00:00")
    assert (e - s).days == 1


def test_tfb_daily_panel():
    dec = pd.DataFrame(
        {
            "districts": [["Mallee", "Wimmera"], ["Central"]],
            "whole_state": [False, False],
            "n_districts": [2, 1],
            "start": pd.to_datetime(["2020-01-01 00:01", "2020-01-01 06:00"]),
            "end": pd.to_datetime(["2020-01-01 23:59", "2020-01-02 12:00"]),
        }
    )
    panel = tfb_daily_panel(dec, start="2019-12-31", end="2020-01-03").set_index("date")
    assert bool(panel.loc["2019-12-31", "tfb_vic"]) is False
    assert panel.loc["2020-01-01", "n_districts"] == 2  # max across declarations
    assert bool(panel.loc["2020-01-02", "tfb_vic"]) is True
    assert bool(panel.loc["2020-01-03", "tfb_vic"]) is False


def test_tc_daily_panel():
    from scripts.loaders.tc_besttrack import tc_daily_panel

    tracks = pd.DataFrame(
        {
            "tc_id": ["AU1_01U"] * 2 + ["AU1_02U"],
            "name": ["Yasi", "Yasi", "Noname"],
            "datetime_utc": pd.to_datetime(
                ["2011-02-01 18:00", "2011-02-02 06:00", "2011-02-02 06:00"], utc=True
            ),
            "lat": [-17.0, -17.5, -20.0],
            "lon": [147.0, 146.0, 120.0],
            "max_wind_spd": [60.0, 65.0, None],
        }
    )
    panel = tc_daily_panel(tracks, start="2011-01-31", end="2011-02-03").set_index("date")
    # 18:00 UTC Feb 1 = 04:00 AEST Feb 2 -> both points land on Feb 2 local
    assert bool(panel.loc["2011-01-31", "tc_active"]) is False
    assert panel.loc["2011-02-02", "n_tcs_active"] == 2
    assert panel.loc["2011-02-02", "tc_max_wind"] == 65.0
    assert panel.loc["2011-01-31", "tc_max_wind"] == 0.0
    assert panel.loc["2011-02-02", "tc_names"] == ["Yasi"]  # placeholders excluded
    assert panel.loc["2011-02-03", "tc_names"] == []
