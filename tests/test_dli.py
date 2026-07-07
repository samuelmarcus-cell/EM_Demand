import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.dli import assemble_components, compute_dli, monthly_tier_percentile, tier_series
from scripts.fire_association import burn_window_daily


def test_tier_series():
    d = pd.to_datetime(["1985-06-01", "2000-10-31", "2000-11-01", "2011-12-31", "2012-01-01"]).to_series()
    assert tier_series(d).tolist() == [3, 3, 2, 2, 1]


def test_monthly_tier_percentile_removes_seasonality():
    dates = pd.to_datetime(["2015-01-01", "2015-01-02", "2016-01-01", "2015-06-01", "2015-06-02"]).to_series()
    vals = pd.Series([10.0, 30.0, 20.0, 1.0, 2.0])
    dates.index = vals.index
    pct = monthly_tier_percentile(vals, dates)
    # January group ranks among Januaries only
    assert pct.iloc[1] == 1.0 and pct.iloc[0] == pytest_approx(1 / 3)
    # June winter values rank within June despite being tiny absolutely
    assert pct.iloc[4] == 1.0


def pytest_approx(x):
    import pytest

    return pytest.approx(x)


def test_burn_window_daily():
    w = pd.DataFrame(
        {
            "window_start": pd.to_datetime(["1983-02-14", "1983-02-15"]),
            "window_end": pd.to_datetime(["1983-02-17", "1983-02-15"]),
        }
    )
    d = burn_window_daily(w, start="1983-02-13", end="1983-02-19").set_index("date")
    assert d.loc["1983-02-13", "n_windows_active"] == 0
    assert d.loc["1983-02-15", "n_windows_active"] == 2
    assert d.loc["1983-02-17", "n_windows_active"] == 1  # end day still active
    assert d.loc["1983-02-18", "n_windows_active"] == 0


_RAIN_COLS = [
    "rain1d_area", "rain3d_area", "rain7d_area",
    "seaus_rain1d", "seaus_rain3d", "seaus_rain7d",
]


def _panels():
    dm = pd.DataFrame(
        {
            "region": ["AUS", "AUS", "SEAUS"],
            "date": pd.to_datetime(["2015-01-01", "2015-01-02", "2015-01-01"]),
            "concurrent_burden": [5, 10, 2],
            "ignition_load": [1, 2, 1],
            "growth_load": [3.0, 6.0, 1.0],
            "frp_load": [100.0, 200.0, 50.0],
        }
    )
    bw = pd.DataFrame(
        {"date": pd.to_datetime(["1983-02-16", "2015-01-01"]), "n_windows_active": [40, 99]}
    )
    drfa = pd.DataFrame(
        {"date": pd.to_datetime(["2015-01-01"]), "n_active_events": [4], "n_lga_active": [25]}
    )
    tfb = pd.DataFrame({"date": pd.to_datetime(["1983-02-16", "2015-01-01"]), "n_districts": [9, 0]})
    tc = pd.DataFrame(
        {"date": pd.to_datetime(["2015-01-02"]), "n_tcs_active": [1], "tc_max_wind": [65.0]}
    )
    return dm, bw, drfa, tfb, tc


def _rain_panel():
    """Minimal rain panel: two days with valid rain fractions."""
    dates = pd.to_datetime(["2015-01-01", "2015-01-02"])
    data = {
        "date": dates,
        "rain1d_area": [0.1, 0.8],
        "rain3d_area": [0.2, 0.7],
        "rain7d_area": [0.15, 0.6],
        "seaus_rain1d": [0.05, 0.9],
        "seaus_rain3d": [0.1, 0.85],
        "seaus_rain7d": [0.12, 0.75],
    }
    return pd.DataFrame(data)


def test_assemble_components_availability_masking():
    rain = _rain_panel()
    comp = assemble_components(*_panels(), rain, start="1983-01-01", end="2015-01-02").loc[
        ["1983-02-16", "2005-01-01", "2015-01-01"]
    ]
    d83, d05, d15 = comp.iloc[0], comp.iloc[1], comp.iloc[2]
    # Tier 3: hotspot components NaN, windows present; DRFA pre-2006 NaN
    assert np.isnan(d83["fire_burden"]) and d83["fire_windows"] == 40
    assert np.isnan(d83["drfa_load"]) and np.isnan(d83["drfa_lga"]) and d83["tfb_load"] == 9
    assert np.isnan(d83["seaus_burden"])
    # Tier 2 day: hotspot metrics 0-filled (no fires = zero), windows masked
    assert d05["fire_burden"] == 0 and d05["seaus_burden"] == 0 and np.isnan(d05["fire_windows"])
    assert np.isnan(d05["drfa_load"])  # before 2006-03-20
    # Tier 1 day: everything live
    assert d15["fire_burden"] == 5 and d15["drfa_load"] == 4 and d15["tc_load"] == 0


def test_assemble_components_rain_columns():
    """Rain columns are reindexed without fillna; days outside CSV are NaN."""
    rain = _rain_panel()
    comp = assemble_components(*_panels(), rain, start="1983-01-01", end="2015-01-02")
    # 2015-01-01 has rain data — values must match
    assert comp.loc["2015-01-01", "rain1d_area"] == pytest_approx(0.1)
    assert comp.loc["2015-01-01", "seaus_rain7d"] == pytest_approx(0.12)
    # 2015-01-02 has rain data
    assert comp.loc["2015-01-02", "rain1d_area"] == pytest_approx(0.8)
    # 1983-02-16 is outside the CSV coverage — must be NaN (no fillna)
    for c in _RAIN_COLS:
        assert np.isnan(comp.loc["1983-02-16", c]), f"Expected NaN for {c} on 1983-02-16"


def test_compute_dli_counts_and_mean():
    rain = _rain_panel()
    comp = assemble_components(*_panels(), rain, start="1983-01-01", end="2015-01-02")
    dli = compute_dli(comp).set_index("date")
    d83 = dli.loc["1983-02-16"]
    assert d83["confidence_tier"] == 3
    # available in 1983: fire_windows, tfb, tc_load, tc_severity — not hotspot or drfa or rain
    assert d83["n_components_available"] == 4
    assert 0 <= d83["dli"] <= 1
    # 1983: sub_drfa unavailable, sub_flood unavailable (no rain data), other three present
    assert np.isnan(d83["sub_drfa"]) and not np.isnan(d83["sub_fire"])
    assert np.isnan(d83["sub_flood"])
    d15 = dli.loc["2015-01-02"]
    assert d15["n_components_available"] == 17  # 11 non-rain + 6 rain cols
    # tc subindex is the max of load and severity percentiles
    assert d15["sub_tc"] == max(d15["tc_load_pct"], d15["tc_severity_pct"])
    assert 0 <= d15["dli"] <= 1
    # sub_flood is the mean of the six rain rank columns
    assert not np.isnan(d15["sub_flood"])
    expected_flood = np.mean([d15[f"{c}_pct"] for c in _RAIN_COLS])
    assert d15["sub_flood"] == pytest_approx(expected_flood)


def test_sub_flood_nan_when_all_rain_nan():
    """sub_flood must be NaN when all six rain columns are NaN (pre-CSV coverage)."""
    rain = _rain_panel()
    comp = assemble_components(*_panels(), rain, start="1983-01-01", end="2015-01-02")
    dli = compute_dli(comp).set_index("date")
    # 1983-02-16: no rain coverage → all rain ranks NaN → sub_flood NaN
    d83 = dli.loc["1983-02-16"]
    assert np.isnan(d83["sub_flood"]), "sub_flood must be NaN when all rain columns are NaN"
    # DLI on that day should still be valid (from other 3 subindices)
    assert not np.isnan(d83["dli"])


def test_dli_includes_sub_flood_in_mean():
    """dli averages five subindices where available; sub_flood included on rainy days."""
    rain = _rain_panel()
    comp = assemble_components(*_panels(), rain, start="2015-01-01", end="2015-01-02")
    dli = compute_dli(comp).set_index("date")
    d15 = dli.loc["2015-01-02"]
    # All five subindices available; dli = mean of sub_fire, sub_tc, sub_drfa, sub_tfb, sub_flood
    sub_cols = ["sub_fire", "sub_tc", "sub_drfa", "sub_tfb", "sub_flood"]
    sub_vals = [d15[c] for c in sub_cols if not np.isnan(d15[c])]
    assert d15["dli"] == pytest_approx(np.mean(sub_vals))
