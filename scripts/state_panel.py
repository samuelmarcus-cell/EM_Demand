"""Per-state hazard-load layers for the state×hazard compounding panel.

Everything here measures HAZARD LOAD — the activity of the hazard itself,
agnostic of exposure and vulnerability — never demand. DRFA is an impact
layer, kept off the hazard axis. Spec:
docs/superpowers/specs/2026-07-09-state-hazard-compounding-panel-design.md
"""

import pandas as pd
import geopandas as gpd

from scripts.config import COMPONENT_AVAILABILITY, PATHS
from scripts.dli import tier_series
from scripts.loaders.drfa_activations import load_drfa_locations

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]
FIRE_METRICS = ["concurrent_burden", "ignition_load", "growth_load", "frp_load"]
FIRE_START = pd.Timestamp("1979-01-01")   # tier 3 fire = polygon burn windows
HOTSPOT_START = pd.Timestamp(COMPONENT_AVAILABILITY["modis"][0])  # 2000-11-01


def normalise_state(raw: pd.Series) -> pd.Series:
    """Normalise messy gdb state labels ("WA (Western Australia)", "Qld",
    "ACT (...)") to the panel's 7 abbreviations; ACT folds into NSW."""
    abbrev = raw.astype(str).str.split(" ").str[0].str.upper()
    return abbrev.replace({"ACT": "NSW"})


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


def state_burn_window_daily(windows: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Per-state daily count of active polygon burn windows.

    Same sweep-line logic and +1-day end convention as the national
    burn_window_daily in scripts/fire_association.py. This is the Tier-3
    fire-activity signal: no satellite record before Nov 2000, so daily
    fire activity is the count of mapped fires whose window covers the day.
    Returns [date, state, n_windows_active] on the full daily grid.
    """
    w = windows.dropna(subset=["window_start", "window_end"]).copy()
    w["state"] = normalise_state(w["state"])
    w = w[w["state"].isin(STATES)]
    start = pd.Timestamp(start) if start is not None else FIRE_START
    end = pd.Timestamp(end) if end is not None else w["window_end"].max()
    idx = pd.date_range(start, end, freq="D", name="date")
    frames = []
    for state in STATES:
        g = w[w["state"] == state]
        starts = g["window_start"].dt.normalize().value_counts()
        # +1 day: a window ending on day D is still active on D
        ends = (g["window_end"].dt.normalize() + pd.Timedelta(days=1)).value_counts()
        active = starts.sub(ends, fill_value=0).sort_index().cumsum()
        s = (active.reindex(idx, method="ffill").fillna(0).astype(int)
             .rename("n_windows_active").reset_index())
        s["state"] = state
        frames.append(s)
    return pd.concat(frames, ignore_index=True)


def state_fire_layer(metrics: pd.DataFrame, windows: pd.DataFrame,
                     end=None) -> pd.DataFrame:
    """Per-state fire hazard-load percentiles, 1979-present.

    Mirrors the frozen national sub_fire recipe per tier: Tier 3
    (1979 - 2000-10-31) scores on the per-state burn-window count only;
    Tiers 1-2 score on the mean of the per-state hotspot-metric
    percentiles, re-ranked within group so the final score is itself a
    percentile. Every ranking is within (state, confidence_tier, calendar
    month) — the project's standard machinery — so tier-3 values never
    rank against satellite-era values, and a >=0.95 flag means "top 5% of
    days" in every tier. Returns [date, state, state_fire, confidence_tier].
    """
    df = metrics[metrics["region"].isin(STATES)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"region": "state"})
    end = pd.Timestamp(end) if end is not None else df["date"].max()

    # Tiers 1-2: hotspot metrics on the hotspot-era grid
    idx12 = pd.date_range(HOTSPOT_START, end, freq="D", name="date")
    hot = _per_state_daily(df, FIRE_METRICS, STATES, idx12)
    hot["confidence_tier"] = tier_series(hot["date"])
    keys = [hot["state"], hot["confidence_tier"], hot["date"].dt.month]
    pct = pd.DataFrame(
        {m: hot.groupby(keys)[m].rank(pct=True) for m in FIRE_METRICS}
    )
    hot["state_fire"] = pct.mean(axis=1)
    # Re-rank the combined score so state_fire is itself a within-group
    # percentile. A mean of four percentiles rarely clears 0.95 (all four
    # metrics must spike at once), which flagged satellite-era days at
    # roughly half the tier-3 rate and hid Black Summer from the
    # descriptive outputs (amendment 2026-07-10, user-approved). Ranking
    # the mean makes the >=0.95 flag mean "top 5% of days" in every tier —
    # the project-wide high-demand-day convention. Tier 3 needs no re-rank:
    # its single input is already a percentile, and ranking a percentile
    # within the same group is the identity.
    hot["state_fire"] = hot.groupby(keys)["state_fire"].rank(pct=True)

    # Tier 3: burn-window counts on the pre-hotspot grid
    bw = state_burn_window_daily(
        windows, start=FIRE_START, end=HOTSPOT_START - pd.Timedelta(days=1)
    )
    bw["confidence_tier"] = 3
    bw["state_fire"] = bw.groupby([bw["state"], bw["date"].dt.month])[
        "n_windows_active"
    ].rank(pct=True)

    cols = ["date", "state", "state_fire", "confidence_tier"]
    return (
        pd.concat([bw[cols], hot[cols]], ignore_index=True)
        .sort_values(["state", "date"])
        .reset_index(drop=True)
    )


# --- Tropical cyclone layer ---

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


# --- DRFA impact layer ---

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


# --- Panel assembly and daily summary ---

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
    Fire-dependent columns (n_states_fire, n_cells_high, cross_hazard,
    multi_hazard_state) are NaN before FIRE_START; they cannot be asserted
    without fire data.
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
    # Use nullable boolean dtype to allow pd.NA assignment
    out["cross_hazard"] = ((n_f > 0) & (n_t > 0) & ~only_same_single).astype("boolean")
    out["multi_hazard_state"] = (both > 0).astype("boolean")

    # Mask fire-dependent columns before FIRE_START (defensive; required if
    # panel has tc rows earlier than fire data availability)
    before_fire_start = idx < FIRE_START
    out.loc[before_fire_start, "n_states_fire"] = pd.NA
    out.loc[before_fire_start, "n_cells_high"] = pd.NA
    out.loc[before_fire_start, "cross_hazard"] = pd.NA
    out.loc[before_fire_start, "multi_hazard_state"] = pd.NA

    return out
