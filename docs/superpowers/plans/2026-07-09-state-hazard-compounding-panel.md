# State×Hazard Compounding Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the per-state daily hazard-load panel (fire + tc hazard layers, drfa impact layer) and the year-block shuffle null that tests whether severe hazards spatially compound across Australian states beyond independence.

**Architecture:** Pure logic in `scripts/state_panel.py` (panel construction) and `scripts/phase3_compounding/compound_demand.py` (shuffle null + ratios, replacing the current stubs); thin runners write parquet/CSV to `data/derived/`; three R figures via the `rfigs` env. All local, seconds–minutes, **no Gadi**.

**Tech Stack:** pandas 2.x, geopandas 1.1.3 (EPSG:3577 for distances), numpy, pytest; R/ggplot2 via `Rscript` in the `rfigs` conda env (no patchwork/gridExtra/cowplot — facets only).

**Spec:** `docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md` — read §1–§3 before starting any task.

## Global Constraints

- **Language:** internal naming says "hazard load", never "demand". Flags are "high hazard load", never "high demand". DRFA is an impact layer, never on the hazard axis; the co-occurrence test runs on fire and tc only.
- **States:** NSW, VIC, QLD, SA, WA, TAS, NT (exactly 7). ACT folds into NSW (fire: already so in `demand_metrics_daily`; drfa: map "Australian Capital Territory" → NSW).
- **Percentiles:** fire within (state, confidence_tier, calendar month); tc and drfa within (state, calendar month). Use `.rank(pct=True)` — same machinery as `scripts/dli.py::monthly_tier_percentile`, not reimplemented differently.
- **Flag threshold:** `high_load = percentile ≥ 0.95`; sensitivity at 0.90 and 0.975 reported alongside every headline number.
- **TC radius:** 300 km from the state polygon; sensitivity at 200 km and 400 km, reported never tuned. Cyclone intensity = BoM stage code `type == "T"`.
- **Null:** 1,000 shuffles; whole-calendar-year blocks; each state×hazard series shuffled independently; fire years shuffle **within confidence tier**; tc years shuffle across the whole period; seeded (`np.random.default_rng(seed)`).
- **Impact check:** descriptive only, no ratio; 30-day follow-up window with sensitivity at 14 and 60 days; 2006-03-20 onward only.
- **Availability discipline:** every cell NaN outside its source window — fire from `COMPONENT_AVAILABILITY["modis"]` start (2000-11-01; per-state fire metrics are hotspot-era only, so the fire layer is Tier 1–2 and Tier 3 has no fire cells); drfa from `COMPONENT_AVAILABILITY["drfa"]` start (2006-03-20); tc from 1979-01-01. Within a layer's window a missing day means zero activity (fill 0 before ranking). `confidence_tier` carried on every fire row.
- **Face-validity gate (blocking):** Black Summer peak days must show NSW+VIC (SA optional) simultaneously high on fire; TC Yasi (2011-02-02/03) must flag QLD under tc, not fire. `scripts/run_state_panel.py` exits non-zero if the gate fails.
- **Environment:** Python is `/opt/anaconda3/bin/python3`; tests `/opt/anaconda3/bin/python3 -m pytest tests/ -q` must stay green (65 currently passing); parquet checkpoints in `data/derived/` (gitignored); commit + push after each task; commit trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
- **Daily bucketing:** UTC+10 (AEST, no DST) everywhere.
- **Feb 29 / partial years:** the shuffle analysis drops Feb 29 rows and trims each series to complete 365-day calendar years (stated in code docstrings; ~0.07% of days).

---

### Task 1: Per-state fire layer (`state_fire_layer`)

**Files:**
- Create: `scripts/state_panel.py`
- Test: `tests/test_state_panel.py`

**Interfaces:**
- Consumes: `data/derived/demand_metrics_daily.parquet` (columns `date, region, concurrent_burden, ignition_load, growth_load, frp_load, ...`; `region ∈ {AUS, SEAUS, NSW, VIC, QLD, SA, WA, TAS, NT}`; per-state rows exist only on active days from 2000-11 on); `scripts.dli.tier_series(dates)`; `scripts.config.COMPONENT_AVAILABILITY`.
- Produces: `STATES` list, `FIRE_METRICS` list, `FIRE_START` Timestamp, and `state_fire_layer(metrics: pd.DataFrame, end=None) -> pd.DataFrame` with columns `[date, state, state_fire, confidence_tier]` — one row per (day, state) from 2000-11-01 to `end` (default: max date in input).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state_panel.py
import numpy as np
import pandas as pd
import pytest

from scripts.state_panel import FIRE_METRICS, STATES, state_fire_layer


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
    out = state_fire_layer(df, end="2015-01-31")
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
    out = state_fire_layer(df, end="2015-01-31")
    qld_jan = out[(out.state == "QLD") & (out.date.dt.month == 1)
                  & (out.date.dt.year == 2015)]
    assert len(qld_jan) == 31
    active = qld_jan.set_index("date").loc[dates, "state_fire"]
    quiet = qld_jan[~qld_jan.date.isin(dates)]["state_fire"]
    assert active.min() > quiet.max()


def test_fire_layer_covers_all_states_and_carries_tier():
    dates = pd.date_range("2015-01-01", "2015-01-05", freq="D")
    df = _synthetic_metrics(["NSW"], dates, {"NSW": 1.0})
    out = state_fire_layer(df, end="2015-01-05")
    assert set(out.state.unique()) == set(STATES)
    assert out["confidence_tier"].notna().all()
    assert (out.loc[out.date >= "2012-01-01", "confidence_tier"] == 1).all()
    # starts at the hotspot-era start, never before
    assert out.date.min() == pd.Timestamp("2000-11-01")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.state_panel'`

- [ ] **Step 3: Write the implementation**

```python
# scripts/state_panel.py
"""Per-state hazard-load layers for the state×hazard compounding panel.

Everything here measures HAZARD LOAD — the activity of the hazard itself,
agnostic of exposure and vulnerability — never demand. DRFA is an impact
layer, kept off the hazard axis. Spec:
docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md
"""

import pandas as pd

from scripts.config import COMPONENT_AVAILABILITY
from scripts.dli import tier_series

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]
FIRE_METRICS = ["concurrent_burden", "ignition_load", "growth_load", "frp_load"]
# Per-state fire metrics exist only in the hotspot era (Tiers 1-2); the
# fire layer is NaN-by-absence before this date (availability discipline).
FIRE_START = pd.Timestamp(COMPONENT_AVAILABILITY["modis"][0])


def _per_state_daily(df, value_cols, states, idx, fill=0.0):
    """Reindex each state's series to the full daily index, filling gaps.

    Within a layer's availability window a missing day means zero
    activity (project rule), hence the fill.
    """
    frames = []
    for state in states:
        s = (
            df[df["state"] == state]
            .set_index("date")[value_cols]
            .reindex(idx)
            .fillna(fill)
            .reset_index()
        )
        s["state"] = state
        frames.append(s)
    return pd.concat(frames, ignore_index=True)


def state_fire_layer(metrics: pd.DataFrame, end=None) -> pd.DataFrame:
    """Per-state fire hazard-load percentiles.

    Each metric is percentile-ranked within (state, confidence_tier,
    calendar month) — the project's standard machinery; state_fire is the
    mean of available metric percentiles, exactly parallel to the frozen
    national sub_fire recipe.
    Returns columns [date, state, state_fire, confidence_tier].
    """
    df = metrics[metrics["region"].isin(STATES)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"region": "state"})
    end = pd.Timestamp(end) if end is not None else df["date"].max()
    idx = pd.date_range(FIRE_START, end, freq="D", name="date")
    out = _per_state_daily(df, FIRE_METRICS, STATES, idx)

    out["confidence_tier"] = tier_series(out["date"])
    keys = [out["state"], out["confidence_tier"], out["date"].dt.month]
    pct = pd.DataFrame(
        {m: out.groupby(keys)[m].rank(pct=True) for m in FIRE_METRICS}
    )
    out["state_fire"] = pct.mean(axis=1)
    return out[["date", "state", "state_fire", "confidence_tier"]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: 3 passed. Then run the whole suite: `/opt/anaconda3/bin/python3 -m pytest tests/ -q` — expected: 68 passed (65 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/state_panel.py tests/test_state_panel.py
git commit -m "feat: per-state fire hazard-load layer for compounding panel

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 2: TC-to-state attribution (`tc_state_daily`, `state_tc_layer`)

**Files:**
- Modify: `scripts/state_panel.py` (append)
- Test: `tests/test_state_panel.py` (append)

**Interfaces:**
- Consumes: `scripts.loaders.tc_besttrack.load_tc_tracks()` → DataFrame `[tc_id, name, datetime_utc, lat, lon, central_pres, max_wind_spd, type]` (type "T" = cyclone intensity; winds m/s; timestamps UTC); `PATHS.aus_states_geojson` (`fires_swts/gadi/aus_states.geojson`, EPSG:4326, columns `[state, geometry]`, state values already NSW/VIC/QLD/SA/WA/TAS/NT).
- Produces:
  - `load_state_geoms(path=None) -> gpd.GeoDataFrame` in EPSG:3577 (metres).
  - `tc_state_daily(tracks, states_gdf, radius_km=300.0) -> pd.DataFrame` `[date, state, tc_max_wind]` — rows only where ≥1 in-range cyclone-intensity point.
  - `state_tc_layer(tc_daily, start="1979-01-01", end=None) -> pd.DataFrame` `[date, state, state_tc, tc_max_wind]` — full daily grid, no-TC days rank as 0 wind.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_state_panel.py`:

```python
from scripts.state_panel import load_state_geoms, state_tc_layer, tc_state_daily


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: new tests FAIL with `ImportError: cannot import name 'tc_state_daily'`; Task 1 tests still pass.

- [ ] **Step 3: Write the implementation**

Append to `scripts/state_panel.py`:

```python
import geopandas as gpd

from scripts.config import PATHS

# ~gale-force radius of a large Australian TC and the scale of pre-landfall
# preparation zones (spec §2). Sensitivity at 200/400 km, reported never tuned.
TC_RADIUS_KM = 300.0
TC_START = pd.Timestamp(COMPONENT_AVAILABILITY["tc_besttrack"][0])
_LOCAL_UTC_OFFSET = pd.Timedelta(hours=10)


def load_state_geoms(path=None) -> gpd.GeoDataFrame:
    """State polygons in GDA94 Australian Albers (EPSG:3577, metres)."""
    gdf = gpd.read_file(path or PATHS.aus_states_geojson)
    return gdf.to_crs(3577)


def tc_state_daily(tracks: pd.DataFrame, states_gdf: gpd.GeoDataFrame,
                   radius_km: float = TC_RADIUS_KM) -> pd.DataFrame:
    """Daily max in-range wind per state from cyclone-intensity track points.

    A point loads a state when it lies within radius_km of the state's
    polygon and the system is at cyclone intensity (BoM stage code
    type == "T"). A point can load several states at once — deliberate:
    both states' agencies respond. Returns rows only for (date, state)
    with at least one in-range point: [date, state, tc_max_wind].
    """
    t = tracks[tracks["type"] == "T"].copy()
    t["date"] = (t["datetime_utc"].dt.tz_localize(None) + _LOCAL_UTC_OFFSET).dt.normalize()
    pts = gpd.GeoDataFrame(
        t[["date", "max_wind_spd"]],
        geometry=gpd.points_from_xy(t["lon"], t["lat"], crs=4326),
    ).to_crs(3577)
    hits = gpd.sjoin(
        pts, states_gdf[["state", "geometry"]],
        predicate="dwithin", distance=radius_km * 1000.0,
    )
    return (
        hits.groupby(["date", "state"], as_index=False)
        .agg(tc_max_wind=("max_wind_spd", "max"))
    )


def state_tc_layer(tc_daily: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Per-state tc percentiles: within (state, calendar month) rank of the
    daily max in-range wind, parallel to the national max-with-severity
    logic. Days with no in-range cyclone (and in-range points with
    unrecorded wind) rank as 0 wind, so they can never fake severity.
    No tier dimension — the best-track record has one era (spec §2).
    Returns [date, state, state_tc, tc_max_wind].
    """
    start = pd.Timestamp(start) if start is not None else TC_START
    end = pd.Timestamp(end) if end is not None else tc_daily["date"].max()
    idx = pd.date_range(start, end, freq="D", name="date")
    out = _per_state_daily(tc_daily, ["tc_max_wind"], STATES, idx)
    out["state_tc"] = out.groupby([out["state"], out["date"].dt.month])[
        "tc_max_wind"
    ].rank(pct=True)
    return out[["date", "state", "state_tc", "tc_max_wind"]]
```

Note: `max_wind_spd` can be NaN on early records; `groupby.agg("max")` skips NaN, and an all-NaN (date, state) group yields NaN `tc_max_wind`, which `_per_state_daily`'s `fillna(0.0)` then zeroes — exactly the documented behaviour.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: all pass (Task 1's 3 + 8 new). If a landmark test fails, do NOT tune the radius — investigate the track data and report (the gate exists to catch real attribution bugs).

- [ ] **Step 5: Commit**

```bash
git add scripts/state_panel.py tests/test_state_panel.py
git commit -m "feat: TC-to-state attribution via 300 km coastline rule

Landmark validation: Yasi->QLD, Tracy->NT, Vance->WA.

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 3: DRFA state rollup (`drfa_state_layer`)

**Files:**
- Modify: `scripts/state_panel.py` (append)
- Test: `tests/test_state_panel.py` (append)

**Interfaces:**
- Consumes: `scripts.loaders.drfa_activations.load_drfa_locations()` → LGA-level rows with columns incl. `STATE` (full names, incl. "Australian Capital Territory"), `Location_code`, `disaster_start_date` (parsed datetime).
- Produces: `drfa_state_layer(locations, end=None) -> pd.DataFrame` `[date, state, drfa_new_lgas, state_drfa]` — daily grid from 2006-03-20 (`DRFA_START`), percentile within (state, month). Impact layer only; never enters the co-occurrence flags.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_state_panel.py`:

```python
from scripts.state_panel import DRFA_START, drfa_state_layer


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: new tests FAIL with `ImportError: cannot import name 'drfa_state_layer'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/state_panel.py`:

```python
DRFA_START = pd.Timestamp(COMPONENT_AVAILABILITY["drfa"][0])

_STATE_FULL_TO_ABBREV = {
    "New South Wales": "NSW",
    "Australian Capital Territory": "NSW",  # ACT folds into NSW (spec §2)
    "Victoria": "VIC",
    "Queensland": "QLD",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "TAS",
    "Northern Territory": "NT",
}


def drfa_state_layer(locations: pd.DataFrame, end=None) -> pd.DataFrame:
    """Per-state IMPACT layer: count of the state's LGAs newly under DRFA
    activation that day ("newly" = the event's disaster_start_date),
    percentile within (state, calendar month). DRFA costs actualised
    impact — exposure and vulnerability baked in — so this layer never
    sits on the hazard axis and never enters the co-occurrence flags
    (spec §2); it feeds only the §3 impact check. Available 2006- only.
    Returns [date, state, drfa_new_lgas, state_drfa].
    """
    loc = locations.copy()
    loc["state"] = loc["STATE"].map(_STATE_FULL_TO_ABBREV)
    loc["date"] = pd.to_datetime(loc["disaster_start_date"])
    loc = loc[loc["date"] >= DRFA_START]
    daily = (
        loc.groupby(["date", "state"], as_index=False)
        .agg(drfa_new_lgas=("Location_code", "nunique"))
    )
    end = pd.Timestamp(end) if end is not None else daily["date"].max()
    idx = pd.date_range(DRFA_START, end, freq="D", name="date")
    out = _per_state_daily(daily, ["drfa_new_lgas"], STATES, idx)
    out["drfa_new_lgas"] = out["drfa_new_lgas"].astype(int)
    out["state_drfa"] = out.groupby([out["state"], out["date"].dt.month])[
        "drfa_new_lgas"
    ].rank(pct=True)
    return out[["date", "state", "drfa_new_lgas", "state_drfa"]]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: all pass. Full suite: `/opt/anaconda3/bin/python3 -m pytest tests/ -q` — green.

- [ ] **Step 5: Commit**

```bash
git add scripts/state_panel.py tests/test_state_panel.py
git commit -m "feat: DRFA per-state impact layer (newly activated LGAs)

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 4: Panel assembly, daily summary, runner with face-validity gate

**Files:**
- Modify: `scripts/state_panel.py` (append)
- Create: `scripts/run_state_panel.py`
- Test: `tests/test_state_panel.py` (append)

**Interfaces:**
- Consumes: the three layer functions from Tasks 1–3.
- Produces:
  - `assemble_panel(fire, tc, drfa) -> pd.DataFrame` — long: `[date, state, layer, pct, confidence_tier, tc_max_wind, drfa_new_lgas]` where `layer ∈ {fire, tc, drfa}`; `confidence_tier` non-null only on fire rows; `tc_max_wind` only on tc rows; `drfa_new_lgas` only on drfa rows. Rows exist only inside each layer's availability window (absent row = NaN cell).
  - `daily_summary(panel, threshold=0.95) -> pd.DataFrame` indexed by date with `[n_states_fire, n_states_tc, n_cells_high, cross_hazard, multi_hazard_state]`; fire-dependent columns are NaN before `FIRE_START`.
  - Runner writes `data/derived/state_hazard_panel.parquet` and `data/derived/state_hazard_summary.parquet`; tc rows additionally carry `pct_r200`, `pct_r400` (radius sensitivity); exits 1 if the face-validity gate fails.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_state_panel.py`:

```python
from scripts.state_panel import assemble_panel, daily_summary


def _mini_panel(fire_high, tc_high):
    """Build a panel with given high states on one day (2015-02-01).

    fire_high/tc_high: sets of states given pct 0.99; all others 0.10.
    """
    date = pd.Timestamp("2015-02-01")
    fire = pd.DataFrame({
        "date": date, "state": STATES,
        "state_fire": [0.99 if s in fire_high else 0.10 for s in STATES],
        "confidence_tier": 1,
    })
    tc = pd.DataFrame({
        "date": date, "state": STATES,
        "state_tc": [0.99 if s in tc_high else 0.10 for s in STATES],
        "tc_max_wind": 0.0,
    })
    drfa = pd.DataFrame({
        "date": date, "state": STATES, "drfa_new_lgas": 0,
        "state_drfa": [0.99] * len(STATES),  # high drfa must NOT enter flags
    })
    return assemble_panel(fire, tc, drfa)


def test_summary_counts_and_cross_hazard_true():
    # NSW high fire, QLD high tc, different states -> cross_hazard
    s = daily_summary(_mini_panel({"NSW"}, {"QLD"})).iloc[0]
    assert s["n_states_fire"] == 1 and s["n_states_tc"] == 1
    assert s["n_cells_high"] == 2
    assert bool(s["cross_hazard"]) is True
    assert bool(s["multi_hazard_state"]) is False


def test_same_state_both_hazards_is_multi_hazard_not_cross():
    s = daily_summary(_mini_panel({"QLD"}, {"QLD"})).iloc[0]
    assert bool(s["cross_hazard"]) is False
    assert bool(s["multi_hazard_state"]) is True


def test_same_state_plus_another_is_cross():
    # fire {QLD}, tc {QLD, WA}: WA differs from QLD -> cross
    s = daily_summary(_mini_panel({"QLD"}, {"QLD", "WA"})).iloc[0]
    assert bool(s["cross_hazard"]) is True
    assert bool(s["multi_hazard_state"]) is True


def test_drfa_never_enters_flags():
    # nothing high on hazards, drfa pct 0.99 everywhere
    s = daily_summary(_mini_panel(set(), set())).iloc[0]
    assert s["n_cells_high"] == 0
    assert bool(s["cross_hazard"]) is False


def test_threshold_sensitivity_parameter():
    # pct 0.92 highs: flagged at 0.90, not at 0.95
    panel = _mini_panel({"NSW", "VIC"}, set())
    panel.loc[(panel.layer == "fire") & panel.state.isin(["NSW", "VIC"]), "pct"] = 0.92
    assert daily_summary(panel, threshold=0.90).iloc[0]["n_states_fire"] == 2
    assert daily_summary(panel, threshold=0.95).iloc[0]["n_states_fire"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q`
Expected: FAIL with `ImportError: cannot import name 'assemble_panel'`.

- [ ] **Step 3: Write the implementation**

Append to `scripts/state_panel.py`:

```python
HAZARD_LAYERS = ["fire", "tc"]  # the co-occurrence test runs on these ONLY
HIGH_LOAD_THRESHOLD = 0.95      # project-wide within-group 95th convention


def assemble_panel(fire: pd.DataFrame, tc: pd.DataFrame,
                   drfa: pd.DataFrame) -> pd.DataFrame:
    """Long panel: one row per (date, state, layer).

    Rows exist only inside each layer's availability window — an absent
    row IS the NaN cell (availability discipline). fire and tc are hazard
    layers; drfa is the impact layer.
    """
    f = fire.rename(columns={"state_fire": "pct"})
    f["layer"] = "fire"
    t = tc.rename(columns={"state_tc": "pct"})
    t["layer"] = "tc"
    d = drfa.rename(columns={"state_drfa": "pct"})
    d["layer"] = "drfa"
    cols = ["date", "state", "layer", "pct", "confidence_tier",
            "tc_max_wind", "drfa_new_lgas"]
    panel = pd.concat([f, t, d], ignore_index=True, sort=False)
    for c in cols:
        if c not in panel.columns:
            panel[c] = pd.NA
    return panel[cols]


def _high_wide(panel: pd.DataFrame, layer: str, threshold: float) -> pd.DataFrame:
    """(date × state) boolean frame of high-hazard-load flags for one layer."""
    sub = panel[panel["layer"] == layer]
    wide = sub.pivot_table(index="date", columns="state", values="pct",
                           aggfunc="first")
    return (wide >= threshold).reindex(columns=STATES, fill_value=False)


def daily_summary(panel: pd.DataFrame,
                  threshold: float = HIGH_LOAD_THRESHOLD) -> pd.DataFrame:
    """Daily summary of high-hazard-load flags (hazard layers only).

    cross_hazard: >=1 state high on fire AND a DIFFERENT state high on tc
    the same day — the spatially compounding case. multi_hazard_state:
    one state high on both at once (co-located; descriptive only).
    Fire-dependent columns are NaN before FIRE_START (no fire data, not
    "no fire").
    """
    fire = _high_wide(panel, "fire", threshold)
    tc = _high_wide(panel, "tc", threshold)
    idx = fire.index.union(tc.index)
    fire = fire.reindex(idx, fill_value=False)
    tc = tc.reindex(idx, fill_value=False)

    n_f = fire.sum(axis=1)
    n_t = tc.sum(axis=1)
    both = (fire & tc).sum(axis=1)
    only_same_single = (n_f == 1) & (n_t == 1) & (both == 1)

    out = pd.DataFrame(index=idx)
    out["n_states_fire"] = n_f.astype(float)
    out["n_states_tc"] = n_t.astype(float)
    out["n_cells_high"] = (n_f + n_t).astype(float)
    out["cross_hazard"] = ((n_f > 0) & (n_t > 0) & ~only_same_single).astype(object)
    out["multi_hazard_state"] = (both > 0).astype(object)
    pre_fire = out.index < FIRE_START
    out.loc[pre_fire, ["n_states_fire", "n_cells_high"]] = float("nan")
    out.loc[pre_fire, ["cross_hazard", "multi_hazard_state"]] = pd.NA
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_state_panel.py -q` — all pass.

- [ ] **Step 5: Write the runner with the blocking face-validity gate**

```python
# scripts/run_state_panel.py
"""Build the state×hazard load panel and daily summary.

Blocking face-validity gate (spec §4): Black Summer must show NSW+VIC
simultaneously high on fire; TC Yasi must flag QLD under tc, not fire.
Exits 1 on gate failure — nothing downstream is interpretable then.
"""

import sys

import pandas as pd

from scripts.config import PATHS
from scripts.loaders.drfa_activations import load_drfa_locations
from scripts.loaders.tc_besttrack import load_tc_tracks
from scripts.state_panel import (
    HIGH_LOAD_THRESHOLD, assemble_panel, daily_summary, drfa_state_layer,
    load_state_geoms, state_fire_layer, state_tc_layer, tc_state_daily,
)

DERIVED = PATHS.derived_dir  # if config names it differently, use that name

print("Building per-state fire layer ...", flush=True)
metrics = pd.read_parquet(DERIVED / "demand_metrics_daily.parquet")
fire = state_fire_layer(metrics)

print("Building tc layer (300 km, + 200/400 km sensitivity) ...", flush=True)
tracks = load_tc_tracks()
states_gdf = load_state_geoms()
tc = state_tc_layer(tc_state_daily(tracks, states_gdf, radius_km=300.0))
for r in (200.0, 400.0):
    alt = state_tc_layer(tc_state_daily(tracks, states_gdf, radius_km=r))
    tc[f"state_tc_r{int(r)}"] = alt["state_tc"].values  # same (date,state) order

print("Building drfa impact layer ...", flush=True)
drfa = drfa_state_layer(load_drfa_locations())

panel = assemble_panel(fire, tc, drfa)
for r in (200, 400):
    panel[f"pct_r{r}"] = pd.NA
    tc_mask = panel["layer"] == "tc"
    panel.loc[tc_mask, f"pct_r{r}"] = tc[f"state_tc_r{r}"].values

summary = daily_summary(panel)
panel.to_parquet(DERIVED / "state_hazard_panel.parquet")
summary.reset_index().rename(columns={"index": "date"}).to_parquet(
    DERIVED / "state_hazard_summary.parquet")
print(f"Panel rows: {len(panel):,}; summary days: {len(summary):,}", flush=True)

# ---- face-validity gate (blocking) ----
def high_states(layer, days):
    sub = panel[(panel.layer == layer) & panel.date.isin(pd.to_datetime(days))]
    return set(sub[sub.pct >= HIGH_LOAD_THRESHOLD].state)

bs_days = pd.date_range("2019-12-28", "2020-01-06", freq="D")
bs_fire = high_states("fire", bs_days)
yasi_days = ["2011-02-02", "2011-02-03"]
yasi_tc = high_states("tc", yasi_days)
yasi_fire = high_states("fire", yasi_days)

print("\n=== Face-validity gate ===")
print(f"Black Summer 2019-12-28..2020-01-06, states high on fire: {sorted(bs_fire)}")
print(f"TC Yasi 2011-02-02/03, states high on tc: {sorted(yasi_tc)}")
print(f"TC Yasi 2011-02-02/03, states high on fire: {sorted(yasi_fire)}")

ok = True
if not {"NSW", "VIC"} <= bs_fire:
    print("FAIL: Black Summer must show NSW+VIC high on fire"); ok = False
if "QLD" not in yasi_tc:
    print("FAIL: Yasi must flag QLD under tc"); ok = False
if "QLD" in yasi_fire:
    print("FAIL: Yasi flagged QLD under FIRE — attribution is wrong"); ok = False
print("GATE PASSED" if ok else "GATE FAILED")
sys.exit(0 if ok else 1)
```

Before writing: check `scripts/config.py` for the actual name of the derived-dir path constant (other runners use it — copy their import). If the layers end at different dates (fire max date > drfa max date etc.), that is fine — the panel is ragged by design.

- [ ] **Step 6: Run the runner**

Run: `/opt/anaconda3/bin/python3 -m scripts.run_state_panel` (or `cd` to repo root and `/opt/anaconda3/bin/python3 scripts/run_state_panel.py` — match how existing runners are invoked).
Expected: parquet files written; `GATE PASSED` printed; exit 0. If the gate fails, STOP — do not tune thresholds or radii; report the failure.

- [ ] **Step 7: Commit**

```bash
git add scripts/state_panel.py scripts/run_state_panel.py tests/test_state_panel.py
git commit -m "feat: state hazard panel assembly, daily summary, face-validity gate

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 5: Year-block shuffle null, excess ratios, impact check

**Files:**
- Rewrite: `scripts/phase3_compounding/compound_demand.py` (the three `NotImplementedError` stubs — `demand_episodes`, `hazard_cooccurrence`, `recovery_gaps` — have no consumers; delete them)
- Create: `scripts/run_compounding.py`
- Test: `tests/test_compounding.py`

**Interfaces:**
- Consumes: `data/derived/state_hazard_panel.parquet` + `state_hazard_summary.parquet` from Task 4; `scripts.state_panel.{_high_wide is private — use daily pct pivots via public code below}`.
- Produces (all in `compound_demand.py`):
  - `complete_years(high: pd.DataFrame) -> pd.DataFrame` — drops Feb 29, keeps only complete 365-day calendar years.
  - `shuffle_years(high, year_groups, rng) -> pd.DataFrame` — independently permutes each column's years; `year_groups: dict[int,int] | None` restricts swaps to within-group.
  - `compounding_counts(high, thresholds=(2,3,4)) -> dict[int,float]`
  - `cross_hazard_frequency(fire_high, tc_high) -> float`
  - `excess_ratios(fire_high, tc_high, fire_year_groups, n_shuffles=1000, thresholds=(2,3,4), seed=42) -> (pd.DataFrame, pd.DataFrame)` — (ratios table, null samples long table).
  - `impact_followup(hazard_multi, drfa_multi, window=30) -> pd.DataFrame`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compounding.py
import numpy as np
import pandas as pd

from scripts.phase3_compounding.compound_demand import (
    complete_years, compounding_counts, cross_hazard_frequency,
    excess_ratios, impact_followup, shuffle_years,
)

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]


def _daily_index(y0, y1):
    idx = pd.date_range(f"{y0}-01-01", f"{y1}-12-31", freq="D")
    return idx[~((idx.month == 2) & (idx.day == 29))]


def _synchronised(y0=1990, y1=2019, n_states=7):
    """All states high on the same 10 days of January in every 3rd year."""
    idx = _daily_index(y0, y1)
    high = pd.DataFrame(False, index=idx, columns=STATES[:n_states])
    for y in range(y0, y1 + 1, 3):
        days = pd.date_range(f"{y}-01-05", f"{y}-01-14", freq="D")
        high.loc[high.index.isin(days), :] = True
    return high


def _independent(y0=1980, y1=2019, p=0.05, seed=0):
    """Each state independently Bernoulli(p) — the null must NOT fire."""
    idx = _daily_index(y0, y1)
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.random((len(idx), 7)) < p, index=idx, columns=STATES)


def test_complete_years_drops_feb29_and_partial_years():
    idx = pd.date_range("2003-06-01", "2005-12-31", freq="D")
    df = pd.DataFrame({"A": False}, index=idx)
    out = complete_years(df)
    assert set(out.index.year) == {2004, 2005}       # 2003 partial -> dropped
    assert not ((out.index.month == 2) & (out.index.day == 29)).any()
    assert (out.groupby(out.index.year).size() == 365).all()


def test_shuffle_preserves_totals_and_year_groups():
    high = _synchronised(1990, 2009)
    groups = {y: (1 if y >= 2000 else 2) for y in range(1990, 2010)}
    rng = np.random.default_rng(1)
    shuf = shuffle_years(high, groups, rng)
    # per-column totals preserved
    assert (shuf.sum() == high.sum()).all()
    # group discipline: yearly totals in each group are a permutation
    # of the original group's yearly totals
    for col in high.columns:
        for g in (1, 2):
            ys = [y for y, gg in groups.items() if gg == g]
            orig = sorted(high[col].groupby(high.index.year).sum().loc[ys])
            new = sorted(shuf[col].groupby(shuf.index.year).sum().loc[ys])
            assert orig == new


def test_synchronised_states_give_large_excess_ratio():
    high = _synchronised()
    ratios, _ = excess_ratios(high, high.iloc[:, :0].copy(), None,
                              n_shuffles=200, thresholds=(3,), seed=7)
    r = ratios[(ratios.statistic == "fire") & (ratios.threshold == 3)]
    assert r["ratio"].iloc[0] > 3.0
    assert r["observed"].iloc[0] > r["null_hi"].iloc[0]


def test_independent_states_give_ratio_near_one():
    high = _independent()
    ratios, _ = excess_ratios(high, high.iloc[:, :0].copy(), None,
                              n_shuffles=200, thresholds=(2,), seed=7)
    r = ratios[(ratios.statistic == "fire") & (ratios.threshold == 2)]
    assert 0.75 < r["ratio"].iloc[0] < 1.35
    # observed inside the null band
    assert r["null_lo"].iloc[0] <= r["observed"].iloc[0] <= r["null_hi"].iloc[0]


def test_cross_hazard_frequency_definitions():
    idx = pd.to_datetime(["2010-01-01", "2010-01-02", "2010-01-03"])
    fire = pd.DataFrame(False, index=idx, columns=STATES)
    tc = pd.DataFrame(False, index=idx, columns=STATES)
    fire.loc[idx[0], "NSW"] = True; tc.loc[idx[0], "QLD"] = True  # cross
    fire.loc[idx[1], "QLD"] = True; tc.loc[idx[1], "QLD"] = True  # same state only
    assert cross_hazard_frequency(fire, tc) == 1 / 3


def test_impact_followup_windows():
    idx = pd.date_range("2010-01-01", "2010-03-31", freq="D")
    hazard = pd.Series(False, index=idx)
    drfa = pd.Series(False, index=idx)
    hazard.loc["2010-01-10"] = True         # followed within 30 days
    drfa.loc["2010-01-25"] = True
    hazard.loc["2010-03-01"] = True         # NOT followed
    out = impact_followup(hazard, drfa, window=30)
    after_hazard = out[out.group == "after multi-state hazard days"].iloc[0]
    assert after_hazard["n_days"] == 2
    assert after_hazard["frac_followed"] == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_compounding.py -q`
Expected: FAIL with `ImportError` (stub module lacks these names).

- [ ] **Step 3: Rewrite `compound_demand.py`**

Replace the entire file content:

```python
# scripts/phase3_compounding/compound_demand.py
"""Spatial hazard-load compounding: year-block shuffle null + excess ratios.

Measures HAZARD LOAD co-occurrence across states — never demand (spec §1).
Method: Gauthier & Bevacqua (2026, npj Nat. Hazards) spatial-shuffle design
adapted to whole-calendar-year blocks (docs/phase3_methods_notes.md).
Year blocks are the conservative choice: a climate driver synchronising
whole seasons partly survives in the null, so the excess that remains is
same-day/synoptic-scale organisation. Headline ratios are therefore
underestimates of total co-occurrence — the right direction to err.
"""

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365  # Feb 29 dropped by complete_years


def complete_years(high: pd.DataFrame) -> pd.DataFrame:
    """Drop Feb 29 rows and trim to complete 365-day calendar years.

    Whole-year shuffling needs equal-length year blocks; partial first/last
    years and leap days (~0.07% of days) are excluded from observed AND
    null alike, so nothing is biased.
    """
    df = high[~((high.index.month == 2) & (high.index.day == 29))]
    counts = df.groupby(df.index.year).size()
    keep = counts[counts == DAYS_PER_YEAR].index
    return df[df.index.year.isin(keep)].sort_index()


def _grouped_permutation(years: np.ndarray, year_groups, rng) -> np.ndarray:
    """Permutation of year positions; swaps stay within year_groups labels."""
    idx = np.arange(len(years))
    if year_groups is None:
        return rng.permutation(idx)
    out = idx.copy()
    labels = np.array([year_groups[int(y)] for y in years])
    for g in np.unique(labels):
        sel = np.where(labels == g)[0]
        out[sel] = sel[rng.permutation(len(sel))]
    return out


def shuffle_years(high: pd.DataFrame, year_groups, rng) -> pd.DataFrame:
    """Independently permute each column's calendar years.

    Each series keeps its own seasonality (a shuffled year is a whole
    calendar year) and within-season persistence; only the alignment of
    states' bad periods in time is destroyed. year_groups (e.g. year ->
    confidence tier for fire) restricts swaps to within-group so data-era
    artefacts cannot fake a signal; None = whole-period shuffle (tc).
    Input must already be complete_years output.
    """
    years = np.array(sorted(set(high.index.year)))
    n_years = len(years)
    out = {}
    for col in high.columns:
        arr = high[col].to_numpy().reshape(n_years, DAYS_PER_YEAR)
        perm = _grouped_permutation(years, year_groups, rng)
        out[col] = arr[perm].ravel()
    return pd.DataFrame(out, index=high.index)


def compounding_counts(high: pd.DataFrame, thresholds=(2, 3, 4)) -> dict:
    """Fraction of days with >=k states simultaneously under high load."""
    n = high.sum(axis=1)
    return {k: float((n >= k).mean()) for k in thresholds}


def cross_hazard_frequency(fire_high: pd.DataFrame,
                           tc_high: pd.DataFrame) -> float:
    """Fraction of days with >=1 state high on fire AND a DIFFERENT state
    high on tc (the spatially compounding case, spec §2). Computed on the
    intersection of the two layers' dates."""
    common = fire_high.index.intersection(tc_high.index)
    f, t = fire_high.loc[common], tc_high.loc[common]
    cols = f.columns.intersection(t.columns)
    n_f, n_t = f.sum(axis=1), t.sum(axis=1)
    both = (f[cols] & t[cols]).sum(axis=1)
    only_same_single = (n_f == 1) & (n_t == 1) & (both == 1)
    return float(((n_f > 0) & (n_t > 0) & ~only_same_single).mean())


def excess_ratios(fire_high, tc_high, fire_year_groups, n_shuffles=1000,
                  thresholds=(2, 3, 4), seed=42):
    """Observed vs shuffle-null frequencies of spatial compounding.

    Returns (ratios, null_samples):
      ratios: statistic ('fire'|'tc'|'cross'), threshold, observed,
              null_mean, null_lo, null_hi (2.5/97.5 pct), ratio,
              ratio_lo, ratio_hi.
      null_samples: long frame (statistic, threshold, shuffle, frequency)
              for the null-distribution figure.
    An empty tc_high (zero columns) skips tc and cross statistics — used
    by the synthetic single-hazard tests.
    """
    rng = np.random.default_rng(seed)
    fire_high = complete_years(fire_high)
    have_tc = tc_high.shape[1] > 0
    if have_tc:
        tc_high = complete_years(tc_high)

    obs = {("fire", k): v for k, v in
           compounding_counts(fire_high, thresholds).items()}
    if have_tc:
        obs.update({("tc", k): v for k, v in
                    compounding_counts(tc_high, thresholds).items()})
        obs[("cross", 1)] = cross_hazard_frequency(fire_high, tc_high)

    null = {key: [] for key in obs}
    for i in range(n_shuffles):
        f = shuffle_years(fire_high, fire_year_groups, rng)
        if have_tc:
            t = shuffle_years(tc_high, None, rng)
        for k, v in compounding_counts(f, thresholds).items():
            null[("fire", k)].append(v)
        if have_tc:
            for k, v in compounding_counts(t, thresholds).items():
                null[("tc", k)].append(v)
            null[("cross", 1)].append(cross_hazard_frequency(f, t))

    rows, samples = [], []
    for key, o in obs.items():
        arr = np.asarray(null[key])
        mean = arr.mean()
        lo, hi = np.percentile(arr, [2.5, 97.5])
        rows.append({
            "statistic": key[0], "threshold": key[1], "observed": o,
            "null_mean": mean, "null_lo": lo, "null_hi": hi,
            "ratio": o / mean if mean > 0 else np.inf,
            "ratio_lo": o / hi if hi > 0 else np.inf,
            "ratio_hi": o / lo if lo > 0 else np.inf,
        })
        samples.extend(
            {"statistic": key[0], "threshold": key[1], "shuffle": i,
             "frequency": v} for i, v in enumerate(arr)
        )
    return pd.DataFrame(rows), pd.DataFrame(samples)


def impact_followup(hazard_multi: pd.Series, drfa_multi: pd.Series,
                    window: int = 30) -> pd.DataFrame:
    """Descriptive impact check (spec §3): frequency of >=1 multi-state
    DRFA-activation day within `window` days AFTER multi-state hazard days
    vs after quiet days. No ratio, no test — reported either way.
    Both series boolean, daily, aligned (2006- caller's responsibility).
    """
    common = hazard_multi.index.intersection(drfa_multi.index)
    h, d = hazard_multi.loc[common], drfa_multi.loc[common]
    # followed[t] = any drfa_multi in (t, t+window]
    followed = (
        d.iloc[::-1].rolling(window, min_periods=1).max().iloc[::-1]
        .shift(-1)
    )
    df = pd.DataFrame({"hazard": h, "followed": followed}).dropna()
    rows = []
    for label, mask in [("after multi-state hazard days", df.hazard),
                        ("after quiet days", ~df.hazard)]:
        sub = df[mask]
        rows.append({"group": label, "window_days": window,
                     "n_days": int(len(sub)),
                     "frac_followed": float(sub["followed"].mean())
                     if len(sub) else float("nan")})
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_compounding.py -q`
Expected: 7 passed (the synchronised/independent tests take a few seconds — 200 shuffles). Full suite green.

- [ ] **Step 5: Write the runner**

```python
# scripts/run_compounding.py
"""Spatial hazard-load compounding: excess ratios + impact check.

Reads state_hazard_panel.parquet; writes compounding_ratios.csv,
compounding_null_samples.csv, compounding_impact_check.csv,
state_cooccurrence.csv, compound_days_top.csv; prints plain-language
tables. Headline = flag threshold 0.95, radius 300 km; sensitivity grid
reported alongside, never tuned.
"""

import pandas as pd

from scripts.config import PATHS, TIER_BOUNDS
from scripts.phase3_compounding.compound_demand import (
    complete_years, excess_ratios, impact_followup,
)
from scripts.state_panel import DRFA_START, STATES

DERIVED = PATHS.derived_dir  # match the constant name used in run_state_panel
panel = pd.read_parquet(DERIVED / "state_hazard_panel.parquet")
panel["date"] = pd.to_datetime(panel["date"])


def high_frame(layer, threshold, pct_col="pct"):
    sub = panel[panel.layer == layer]
    wide = sub.pivot_table(index="date", columns="state", values=pct_col,
                           aggfunc="first").reindex(columns=STATES)
    return wide >= threshold


tier1_start = pd.Timestamp(TIER_BOUNDS[1][0]).year
fire_year_groups = None  # set below from the fire frame's actual years

all_ratios, all_samples = [], []
for thr in (0.95, 0.90, 0.975):
    for radius, pct_col in [(300, "pct"), (200, "pct_r200"), (400, "pct_r400")]:
        fire = high_frame("fire", thr)
        tc = high_frame("tc", thr, pct_col)
        fire_cy = complete_years(fire)
        fire_year_groups = {int(y): (1 if y >= tier1_start else 2)
                            for y in set(fire_cy.index.year)}
        ratios, samples = excess_ratios(fire, tc, fire_year_groups,
                                        n_shuffles=1000, seed=42)
        for df in (ratios, samples):
            df["flag_threshold"] = thr
            df["radius_km"] = radius
        # fire ratios do not depend on radius — keep only at 300 to avoid dupes
        if radius != 300:
            ratios = ratios[ratios.statistic != "fire"]
            samples = samples[samples.statistic != "fire"]
        all_ratios.append(ratios)
        all_samples.append(samples)
        print(f"done: threshold={thr} radius={radius}", flush=True)

ratios = pd.concat(all_ratios, ignore_index=True)
samples = pd.concat(all_samples, ignore_index=True)
ratios.to_csv(DERIVED / "compounding_ratios.csv", index=False)
samples.to_csv(DERIVED / "compounding_null_samples.csv", index=False)

# ---- impact check (descriptive; 2006- only) ----
fire95, tc95 = high_frame("fire", 0.95), high_frame("tc", 0.95)
idx = fire95.index.union(tc95.index)
any_high = (fire95.reindex(idx, fill_value=False)
            | tc95.reindex(idx, fill_value=False))
hazard_multi = (any_high.sum(axis=1) >= 2)[lambda s: s.index >= DRFA_START]
drfa = panel[panel.layer == "drfa"].pivot_table(
    index="date", columns="state", values="drfa_new_lgas", aggfunc="first")
drfa_multi = (drfa > 0).sum(axis=1) >= 2
impact = pd.concat(
    [impact_followup(hazard_multi, drfa_multi, w) for w in (30, 14, 60)],
    ignore_index=True)
impact.to_csv(DERIVED / "compounding_impact_check.csv", index=False)

# ---- figure data: state co-occurrence matrix + top compound days ----
cooc = []
for hazard, frame in [("fire", fire95), ("tc", tc95)]:
    f = frame.fillna(False)
    for a in STATES:
        for b in STATES:
            cooc.append({"hazard": hazard, "state_a": a, "state_b": b,
                         "n_days": int((f[a] & f[b]).sum())})
pd.DataFrame(cooc).to_csv(DERIVED / "state_cooccurrence.csv", index=False)

summary = pd.read_parquet(DERIVED / "state_hazard_summary.parquet")
summary["date"] = pd.to_datetime(summary["date"])
top = summary.nlargest(30, "n_cells_high")["date"]
top_cells = panel[panel.date.isin(top) & panel.layer.isin(["fire", "tc"])
                  & (panel.pct >= 0.95)]
top_cells[["date", "state", "layer", "pct"]].to_csv(
    DERIVED / "compound_days_top.csv", index=False)

# ---- plain-language result table ----
head = ratios[(ratios.flag_threshold == 0.95) & (ratios.radius_km == 300)]
print("\n=== Headline (flag >= 0.95 within (state, month[, tier]); "
      "tc radius 300 km; 1,000 year-block shuffles) ===")
for _, r in head.iterrows():
    what = {"fire": f">= {r.threshold} states under high fire load",
            "tc": f">= {r.threshold} states under high tc load",
            "cross": "different states high on fire and tc, same day"}[r.statistic]
    print(f"{what}: observed {r.observed*365:.2f} days/yr vs "
          f"{r.null_mean*365:.2f} under independence -> "
          f"{r.ratio:.1f}x (null band {r.ratio_lo:.1f}-{r.ratio_hi:.1f}x)")
print("\nNote: year-block shuffling is conservative — shared climate "
      "background (e.g. ENSO) partly survives in the null, so these "
      "ratios UNDERSTATE total co-occurrence (spec §3).")
print("\n=== Impact check (descriptive, 2006-) ===")
print(impact.to_string(index=False))
```

- [ ] **Step 6: Run the runner**

Run: `/opt/anaconda3/bin/python3 -m scripts.run_compounding` (match invocation style from Step 6 of Task 4).
Expected: five CSVs in `data/derived/`; a plain-language headline table; runtime minutes (9 threshold×radius combinations × 1,000 shuffles — if this exceeds ~15 min, reduce nothing; let it run in background writing to a log per house rules). Sanity expectations (pre-registered, spec §1): fire same-hazard ratio clearly > 1 (positive control); cross-hazard is the open question — either outcome is the finding.

- [ ] **Step 7: Commit**

```bash
git add scripts/phase3_compounding/compound_demand.py scripts/run_compounding.py tests/test_compounding.py
git commit -m "feat: year-block shuffle null, excess ratios, impact check

Replaces the phase-3 stubs. Naming says hazard load, not demand.

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 6: R figures + README

**Files:**
- Create: `R/compounding.R`
- Modify: `README.md` (Figures section + Phase 3 roadmap bullet)
- Outputs: `R/figs/fig_compounding_null.png`, `R/figs/fig_state_cooccurrence.png`, `R/figs/fig_compound_days_timeline.png` (committed)

**Interfaces:**
- Consumes: `data/derived/compounding_ratios.csv`, `compounding_null_samples.csv`, `state_cooccurrence.csv`, `compound_days_top.csv` (Task 5).
- Produces: three PNGs. House style: read `R/figures_dli.R` first and match its theme/colour conventions; **no patchwork/gridExtra/cowplot/magick** in the rfigs env — use `facet_wrap`/`facet_grid` only.

- [ ] **Step 1: Write `R/compounding.R`**

```r
# R/compounding.R — state×hazard compounding figures (run via rfigs env Rscript)
library(ggplot2)
library(dplyr)
library(readr)
library(stringr)

derived <- "data/derived"
figs <- "R/figs"

ratios <- read_csv(file.path(derived, "compounding_ratios.csv"), show_col_types = FALSE)
samples <- read_csv(file.path(derived, "compounding_null_samples.csv"), show_col_types = FALSE)

# --- fig 1: observed vs null distributions (headline: 0.95 / 300 km) ---
lab <- function(stat, k) {
  ifelse(stat == "cross", "cross-hazard day\n(fire + tc, different states)",
         sprintf(">= %d states, %s", k, stat))
}
s <- samples |> filter(flag_threshold == 0.95, radius_km == 300) |>
  mutate(panel = lab(statistic, threshold), freq_yr = frequency * 365)
o <- ratios |> filter(flag_threshold == 0.95, radius_km == 300) |>
  mutate(panel = lab(statistic, threshold), obs_yr = observed * 365)

p1 <- ggplot(s, aes(freq_yr)) +
  geom_histogram(bins = 40, fill = "grey70", colour = NA) +
  geom_vline(data = o, aes(xintercept = obs_yr), colour = "firebrick", linewidth = 0.8) +
  facet_wrap(~panel, scales = "free") +
  labs(x = "days per year", y = "shuffles (of 1,000)",
       title = "Observed spatial hazard-load compounding vs independence null",
       subtitle = str_wrap(paste(
         "Red line = observed frequency; grey = 1,000 year-block shuffles",
         "(states' years permuted independently; fire within confidence tier).",
         "High load = within-(state, month[, tier]) percentile >= 0.95."), 100)) +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_compounding_null.png"), p1,
       width = 10, height = 6, dpi = 200)

# --- fig 2: state×state co-occurrence matrix ---
cooc <- read_csv(file.path(derived, "state_cooccurrence.csv"), show_col_types = FALSE) |>
  filter(state_a != state_b)
p2 <- ggplot(cooc, aes(state_a, state_b, fill = n_days)) +
  geom_tile() +
  geom_text(aes(label = n_days), size = 3) +
  facet_wrap(~hazard) +
  scale_fill_gradient(low = "white", high = "firebrick") +
  labs(x = NULL, y = NULL, fill = "joint high-load days",
       title = "Days both states under high hazard load (flag >= 0.95)") +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_state_cooccurrence.png"), p2,
       width = 10, height = 5, dpi = 200)

# --- fig 3: timeline strip of top compound days ---
top <- read_csv(file.path(derived, "compound_days_top.csv"), show_col_types = FALSE)
p3 <- ggplot(top, aes(date, state, colour = layer)) +
  geom_point(size = 3) +
  scale_colour_manual(values = c(fire = "firebrick", tc = "steelblue")) +
  labs(x = NULL, y = NULL, colour = "hazard",
       title = "Top compound days: which states, which hazards",
       subtitle = "30 days with the most simultaneous high-hazard-load cells") +
  theme_minimal(base_size = 11)
ggsave(file.path(figs, "fig_compound_days_timeline.png"), p3,
       width = 10, height = 4, dpi = 200)

cat("wrote 3 figures to", figs, "\n")
```

Before finalising: open `R/figures_dli.R` and align theme/palette/ggsave conventions with it (house style overrides the sketch above where they differ).

- [ ] **Step 2: Render and inspect**

Run: `conda run -n rfigs Rscript R/compounding.R` (match the invocation used for `R/demand_composites.R`).
Expected: three PNGs in `R/figs/`. Open each (Read tool) and check: fig 1's red observed lines sit where the printed ratios say; fig 2 is symmetric; fig 3's labels legible. Fix rendering issues before committing.

- [ ] **Step 3: Update README**

In `README.md` Figures section, append:

```markdown
**Compounding panel figures** (state×hazard co-occurrence; spec
`docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md`;
rendered by `R/compounding.R` from CSVs written by `scripts/run_compounding.py`):

- `fig_compounding_null.png` — observed vs 1,000-shuffle null distributions of
  simultaneous high-hazard-load state counts, one panel per compounding type
- `fig_state_cooccurrence.png` — state×state joint high-load day counts, by hazard
- `fig_compound_days_timeline.png` — the 30 biggest compound days, labelled by
  state and hazard
```

And update the Phase 3 roadmap bullet to reflect that the state×hazard panel + shuffle null are built (keep hemispheric overlap as remaining).

- [ ] **Step 4: Commit**

```bash
git add R/compounding.R R/figs/fig_compounding_null.png R/figs/fig_state_cooccurrence.png R/figs/fig_compound_days_timeline.png README.md
git commit -m "feat: compounding panel figures + README

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

### Task 7: Replication writeup (METHODOLOGY) + status updates

**Files:**
- Modify: `docs/METHODOLOGY.md` (new section, numbered after the current last section)
- Modify: `CLAUDE.md` (Current status: compounding panel done, pointers)

**Interfaces:**
- Consumes: the printed tables from `run_state_panel.py` and `run_compounding.py` (re-run them if output is no longer in scrollback) and the three figures.

- [ ] **Step 1: Write the METHODOLOGY section**

Per the project's standing rule this is a **replication guide teaching the user**, not a paper. Follow the style of §11 (composites pilot). It must contain, in plain language:

1. The scientific question and the three falsifiable outcomes (copy the logic from spec §1, not the wording verbatim).
2. Pre-registered expectations, stated as written before the result — then the actual result beside each.
3. How the panel is built, layer by layer, with every threshold and its justification: 0.95 inherited from the project-wide within-group 95th convention; 300 km ≈ gale radius / preparation-zone scale; year-block shuffle chosen over day/month shuffles and why (persistence; ENSO-splitting) and its stated consequence (ratios are underestimates).
4. What the shuffle null does in words: "each state's years are shuffled independently, so each state keeps its own seasonality and persistence; the only thing destroyed is whether states' bad periods line up."
5. The face-validity gate outcome (Black Summer, Yasi) — copy the runner's printed lines.
6. The headline ratio table (paste the runner's plain-language output) plus the full sensitivity grid location (`data/derived/compounding_ratios.csv`).
7. The impact-check table and its reading (descriptive only; either outcome reported).
8. Alternatives considered and rejected: day-shuffle (trivially easy null), month-shuffle (cuts ENSO years), storm-archive layer (report bias — spec §6), drfa on the hazard axis (impact, not hazard).
9. Exact rerun commands:
   ```
   /opt/anaconda3/bin/python3 -m scripts.run_state_panel
   /opt/anaconda3/bin/python3 -m scripts.run_compounding
   conda run -n rfigs Rscript R/compounding.R
   ```
10. Honest limitations: fire layer is hotspot-era only (2000-11 on, Tiers 1–2 — per-state Tier-3 series don't exist); ACT inside NSW; wind-missing early TC points rank as zero; no trend claims (tier treachery, spec §6).

- [ ] **Step 2: Update CLAUDE.md**

In "Current status / open items", replace the "(3) state×hazard compounding panel" priority entry with a done-entry: date, one-line result (fire compounding ratio, cross-hazard verdict), pointers to the panel parquet, ratios CSV, runners, spec, and METHODOLOGY section. Add the pipeline table rows for `run_state_panel.py` and `run_compounding.py` with their outputs and runtimes.

- [ ] **Step 3: Commit**

```bash
git add docs/METHODOLOGY.md CLAUDE.md
git commit -m "docs: compounding panel replication guide + status

Co-Authored-By: Claude <model> <noreply@anthropic.com>"
git push
```

---

## Self-Review (done at plan-writing time)

- **Spec coverage:** §1 (question/naming) → Global Constraints + module docstrings; §2 fire layer → Task 1; §2 tc layer + sensitivity radii → Tasks 2/4; §2 drfa layer → Task 3; §2 flags + summary cols (`n_states_fire`, `n_states_tc`, `n_cells_high`, `cross_hazard`, `multi_hazard_state`) → Task 4; §3 shuffle null + ratios + bands → Task 5; §3 impact check (30/14/60) → Task 5; §4 files/outputs/figures → Tasks 4–6; §4 face-validity gate → Task 4 (blocking, exit code); §5 synthetic known-answer tests + landmark TC tests + percentile-machinery reuse (`rank(pct=True)`, `tier_series`) + availability discipline → Tasks 1–5; §7 replication note → Task 7.
- **Known deviation, stated not hidden:** spec §2 says the panel spans 1979–present; the per-state fire metrics only exist from 2000-11 (hotspot era), so fire cells are absent (NaN) through Tier 3 under the spec's own availability discipline (§5). The tc layer does span 1979–present. Flagged for the user in the plan summary.
- **Type consistency:** `state_fire_layer`/`state_tc_layer`/`drfa_state_layer` all return long frames with `date, state` keys consumed by `assemble_panel`; `_high_wide`/`high_frame` produce (date×state) boolean frames consumed by `excess_ratios`; `excess_ratios` returns `(ratios, samples)` consumed by the runner and R script column-for-column.
- **Placeholder scan:** clean — every code step carries complete code; the two "match house conventions" notes (derived-dir constant name, R theme) are deliberate look-before-you-write instructions, with the fallback named.

## Execution Handoff

Subagent-driven development recommended (fresh implementer per task, task review after each, final whole-branch review); ledger at `.superpowers/sdd/progress.md`.
