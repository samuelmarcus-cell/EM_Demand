import numpy as np
import pandas as pd
import pytest

from scripts.state_panel import (
    DRFA_START,
    FIRE_METRICS,
    STATES,
    drfa_state_layer,
    load_state_geoms,
    state_burn_window_daily,
    state_fire_layer,
    state_tc_layer,
    tc_state_daily,
)


def _synthetic_metrics(states, dates, scale):
    """One row per (state, date); metric value = day-of-run index × scale[state]."""
    rows = []
    for s in states:
        for i, d in enumerate(dates):
            rows.append({"date": d, "region": s,
                         **{m: (i + 1) * scale[s] for m in FIRE_METRICS}})
    return pd.DataFrame(rows)


def test_fire_percentiles_rank_within_state():
    # Identical *patterns* in NSW and VIC, wildly different magnitudes:
    # within-state ranking must give identical percentiles.
    dates = pd.date_range("2015-01-01", "2015-01-31", freq="D")
    df = _synthetic_metrics(["NSW", "VIC"], dates, {"NSW": 1.0, "VIC": 1000.0})
    out = state_fire_layer(df, _windows([]), end="2015-01-31")
    nsw = out[out.state == "NSW"].set_index("date").loc[dates, "state_fire"]
    vic = out[out.state == "VIC"].set_index("date").loc[dates, "state_fire"]
    assert np.allclose(nsw.values, vic.values)
    # And monotone increasing values -> monotone increasing percentiles
    assert nsw.is_monotonic_increasing


def test_fire_layer_zero_fills_missing_days_within_era():
    # QLD has rows only on 2 days of Jan 2015; the other days must exist
    # with metrics treated as zero (lowest ranks), not be absent.
    dates = pd.to_datetime(["2015-01-10", "2015-01-20"])
    df = _synthetic_metrics(["QLD"], dates, {"QLD": 1.0})
    out = state_fire_layer(df, _windows([]), end="2015-01-31")
    qld_jan = out[(out.state == "QLD") & (out.date.dt.month == 1)
                  & (out.date.dt.year == 2015)]
    assert len(qld_jan) == 31
    active = qld_jan.set_index("date").loc[dates, "state_fire"]
    quiet = qld_jan[~qld_jan.date.isin(dates)]["state_fire"]
    assert active.min() > quiet.max()


def test_fire_layer_covers_all_states_and_carries_tier():
    dates = pd.date_range("2015-01-01", "2015-01-05", freq="D")
    df = _synthetic_metrics(["NSW"], dates, {"NSW": 1.0})
    out = state_fire_layer(df, _windows([]), end="2015-01-05")
    assert set(out.state.unique()) == set(STATES)
    assert out["confidence_tier"].notna().all()
    assert (out.loc[out.date >= "2012-01-01", "confidence_tier"] == 1).all()
    # panel starts at 1979 (tier 3 exists via burn windows), never before
    assert out.date.min() == pd.Timestamp("1979-01-01")


def _windows(rows):
    """rows: list of (window_start, window_end, raw_state_label)."""
    df = pd.DataFrame(
        [{"fire_uid": i, "window_start": a, "window_end": b, "state": st}
         for i, (a, b, st) in enumerate(rows)],
        columns=["fire_uid", "window_start", "window_end", "state"],
    )
    df["window_start"] = pd.to_datetime(df["window_start"])
    df["window_end"] = pd.to_datetime(df["window_end"])
    return df


def test_state_burn_window_daily_counts_and_normalises_states():
    win = _windows([
        ("1994-01-05", "1994-01-10", "NSW (New South Wales)"),
        ("1994-01-08", "1994-01-12", "NSW (New South Wales)"),
        ("1994-01-08", "1994-01-09", "ACT (Australian Capital Territory)"),
        ("1994-01-08", "1994-01-09", "Qld"),
    ])
    out = state_burn_window_daily(win, start="1994-01-01", end="1994-01-31")
    d = out.set_index(["date", "state"])["n_windows_active"]
    assert d.loc[(pd.Timestamp("1994-01-08"), "NSW")] == 3   # 2 NSW + 1 ACT
    assert d.loc[(pd.Timestamp("1994-01-10"), "NSW")] == 2   # end day still active
    assert d.loc[(pd.Timestamp("1994-01-11"), "NSW")] == 1
    assert d.loc[(pd.Timestamp("1994-01-08"), "QLD")] == 1
    assert d.loc[(pd.Timestamp("1994-01-20"), "NSW")] == 0
    assert "ACT" not in out["state"].values


def test_fire_layer_tier3_scores_on_burn_windows():
    # No hotspot metrics at all; a tier-3 burst of windows in NSW must
    # out-rank quiet NSW January days.
    win = _windows([("1994-01-05", "1994-01-15", "NSW (New South Wales)")] * 5)
    df = _synthetic_metrics(["NSW"], pd.date_range("2015-01-01", "2015-01-02"), {"NSW": 1.0})
    out = state_fire_layer(df, win, end="2015-01-31")
    t3 = out[(out.state == "NSW") & (out.confidence_tier == 3)
             & (out.date.dt.year == 1994) & (out.date.dt.month == 1)]
    busy = t3[t3.date.between("1994-01-05", "1994-01-15")]["state_fire"]
    quiet = t3[~t3.date.between("1994-01-05", "1994-01-15")]["state_fire"]
    assert busy.min() > quiet.max()
    # tier-3 rows never score on hotspot metrics, tier-1/2 rows never on windows
    t12 = out[(out.state == "NSW") & (out.confidence_tier != 3)]
    assert t12["date"].min() == pd.Timestamp("2000-11-01")


# --- Tropical cyclone tests ---


def _track_points(rows):
    """rows: list of (utc_timestamp_str, lat, lon, wind, type)."""
    return pd.DataFrame(
        [{"tc_id": "AU000000", "name": "Test",
          "datetime_utc": pd.Timestamp(ts, tz="UTC"),
          "lat": lat, "lon": lon, "central_pres": 980.0,
          "max_wind_spd": wind, "type": typ}
         for ts, lat, lon, wind, typ in rows]
    )


@pytest.fixture(scope="module")
def states_gdf():
    return load_state_geoms()


def test_tc_point_off_qld_coast_loads_qld_only(states_gdf):
    # ~100 km east of Townsville: inside 300 km of QLD, far from all others
    tracks = _track_points([("2011-02-02 12:00", -19.0, 148.0, 60.0, "T")])
    out = tc_state_daily(tracks, states_gdf)
    assert set(out["state"]) == {"QLD"}
    assert out["tc_max_wind"].iloc[0] == 60.0


def test_tc_point_mid_tasman_loads_nothing(states_gdf):
    tracks = _track_points([("2011-02-02 12:00", -35.0, 160.0, 60.0, "T")])
    out = tc_state_daily(tracks, states_gdf)
    assert out.empty


def test_tc_border_point_loads_both_states(states_gdf):
    # Just off the NT/WA border coast (~ -14.5, 129.0): within 300 km of both
    tracks = _track_points([("2011-02-02 12:00", -14.0, 129.0, 40.0, "T")])
    out = tc_state_daily(tracks, states_gdf)
    assert {"NT", "WA"} <= set(out["state"])


def test_non_cyclone_intensity_points_excluded(states_gdf):
    tracks = _track_points([("2011-02-02 12:00", -19.0, 148.0, 60.0, "L")])
    out = tc_state_daily(tracks, states_gdf)
    assert out.empty


def test_state_tc_layer_full_grid_and_percentiles():
    daily = pd.DataFrame({
        "date": pd.to_datetime(["2011-02-02"]),
        "state": ["QLD"], "tc_max_wind": [60.0],
    })
    out = state_tc_layer(daily, start="2011-01-01", end="2011-02-28")
    assert len(out) == 59 * len(STATES)
    qld_feb2 = out[(out.state == "QLD") & (out.date == "2011-02-02")]
    # only nonzero wind in the (QLD, Feb) group -> top rank
    assert qld_feb2["state_tc"].iloc[0] == 1.0
    # a state with no TC ever must never reach the 0.95 flag
    assert (out[out.state == "TAS"]["state_tc"] < 0.95).all()


# --- real-data landmark attribution (spec §5; loads the BoM best-track CSV) ---

@pytest.mark.parametrize("day,name_year,state,wind_floor", [
    ("2011-02-03", "Yasi 2011", "QLD", 30.0),
    ("1974-12-25", "Tracy 1974", "NT", 30.0),
    ("1999-03-22", "Vance 1999", "WA", 30.0),
])
def test_landmark_tc_attribution(states_gdf, day, name_year, state, wind_floor):
    from scripts.loaders.tc_besttrack import load_tc_tracks
    out = tc_state_daily(load_tc_tracks(), states_gdf)
    row = out[(out["date"] == day) & (out["state"] == state)]
    assert not row.empty, f"{name_year} did not load {state} on {day}"
    assert row["tc_max_wind"].iloc[0] >= wind_floor


# --- DRFA impact layer tests ---


def _locations(rows):
    """rows: list of (start_date, full_state_name, location_code)."""
    return pd.DataFrame(
        [{"disaster_start_date": pd.Timestamp(d), "STATE": st, "Location_code": lc,
          "agrn": 1, "event_name": "x", "hazard_type": "Flood"}
         for d, st, lc in rows]
    )


def test_drfa_counts_unique_new_lgas_per_state_day():
    loc = _locations([
        ("2011-01-10", "Queensland", "LGA1"),
        ("2011-01-10", "Queensland", "LGA2"),
        ("2011-01-10", "Queensland", "LGA2"),   # duplicate LGA -> counted once
        ("2011-01-10", "New South Wales", "LGA9"),
    ])
    out = drfa_state_layer(loc, end="2011-01-31")
    day = out[out.date == "2011-01-10"].set_index("state")
    assert day.loc["QLD", "drfa_new_lgas"] == 2
    assert day.loc["NSW", "drfa_new_lgas"] == 1
    assert day.loc["VIC", "drfa_new_lgas"] == 0


def test_drfa_act_folds_into_nsw():
    loc = _locations([
        ("2011-01-10", "Australian Capital Territory", "LGA_ACT"),
        ("2011-01-10", "New South Wales", "LGA_NSW"),
    ])
    out = drfa_state_layer(loc, end="2011-01-31")
    day = out[out.date == "2011-01-10"].set_index("state")
    assert day.loc["NSW", "drfa_new_lgas"] == 2
    assert "ACT" not in out["state"].values


def test_drfa_layer_starts_at_availability_window():
    loc = _locations([("2011-01-10", "Queensland", "LGA1")])
    out = drfa_state_layer(loc, end="2011-01-31")
    assert out.date.min() == DRFA_START
