"""Section 5: Demand Load Index v0.2.

Each component is percentile-ranked within its (confidence tier, calendar
month) group — the month grouping removes seasonality, the tier grouping
keeps satellite-era step-changes from contaminating ranks. Components are
then folded into hazard SUBINDICES and the DLI is the equal-weight mean of
the available subindices:

    sub_fire   mean of available fire component percentiles
    sub_tc     max(tc_load_pct, tc_severity_pct)
    sub_drfa   drfa_lga_pct (LGA footprint = demand proxy, not event count)
    sub_tfb    tfb_load_pct
    sub_flood  mean of six AGCD rain-fraction percentiles (1979-present)

Benchmark validation drove this structure: a flat all-component mean diluted
single-hazard events (TC Yasi, 2022 floods) with quiet fire components, and
national fire counts swamped SE-Australia events with routine
northern-savanna burning (hence the SEAUS components). Count-style inputs
(n_tcs_active, n_active_events) saturate from ties — one active TC is
common — so the tc subindex takes the max with severity, and the drfa
subindex uses the LGA footprint. Days keep `n_components_available`;
nothing is NaN-filled silently.

Components (daily):
    fire_burden      concurrent_burden (AUS)     tiers 1-2 (hotspot-based)
    fire_ignitions   ignition_load (AUS)         tiers 1-2
    fire_growth      growth_load (AUS)           tiers 1-2
    fire_intensity   frp_load (AUS)              tiers 1-2
    seaus_burden     concurrent_burden (SEAUS)   tiers 1-2
    seaus_intensity  frp_load (SEAUS)            tiers 1-2
    fire_windows     n_windows_active            tier 3 only (polygon burn windows)
    drfa_load        n_active_events             2006-03-20 ->
    drfa_lga         n_lga_active                2006-03-20 ->
    tfb_load         n_districts (VIC)           1945 ->
    tc_load          n_tcs_active                full period
    tc_severity      tc_max_wind                 full period
    rain1d_area      AGCD AUS area frac > p95    1979 -> (AGCD CSV arrival)
    rain3d_area      AGCD AUS 3-day area frac    1979 ->
    rain7d_area      AGCD AUS 7-day area frac    1979 ->
    seaus_rain1d     AGCD SEAUS area frac > p95  1979 ->
    seaus_rain3d     AGCD SEAUS 3-day area frac  1979 ->
    seaus_rain7d     AGCD SEAUS 7-day area frac  1979 ->
"""

import pandas as pd

from scripts.config import COMPONENT_AVAILABILITY, TIER_BOUNDS

# component -> (source column, availability key or None for always)
_HOTSPOT_COMPONENTS = {
    "fire_burden": "concurrent_burden",
    "fire_ignitions": "ignition_load",
    "fire_growth": "growth_load",
    "fire_intensity": "frp_load",
}


def tier_series(dates: pd.Series) -> pd.Series:
    """Vectorised confidence tier for a datetime series."""
    t1 = pd.Timestamp(TIER_BOUNDS[1][0])
    t2 = pd.Timestamp(TIER_BOUNDS[2][0])
    return pd.Series(3, index=dates.index).where(dates < t2, 2).where(dates < t1, 1)


def monthly_tier_percentile(values: pd.Series, dates: pd.Series) -> pd.Series:
    """Percentile rank (0-1) within (tier, calendar month); NaN passes through."""
    tier = tier_series(dates)
    month = dates.dt.month
    return values.groupby([tier, month]).rank(pct=True)


_RAIN_COLS = [
    "rain1d_area", "rain3d_area", "rain7d_area",
    "seaus_rain1d", "seaus_rain3d", "seaus_rain7d",
]


def assemble_components(
    demand_metrics: pd.DataFrame,
    burn_windows: pd.DataFrame,
    drfa_panel: pd.DataFrame,
    tfb_panel: pd.DataFrame,
    tc_panel: pd.DataFrame,
    rain_panel: pd.DataFrame,
    start="1979-01-01",
    end=None,
) -> pd.DataFrame:
    """Daily national component table, NaN where unavailable."""
    end = pd.Timestamp(end) if end else max(
        demand_metrics["date"].max(), drfa_panel["date"].max(), tc_panel["date"].max()
    )
    idx = pd.date_range(start, end, freq="D", name="date")
    out = pd.DataFrame(index=idx)
    tier = tier_series(out.index.to_series())

    aus = demand_metrics[demand_metrics["region"] == "AUS"].set_index("date")
    seaus = demand_metrics[demand_metrics["region"] == "SEAUS"].set_index("date")
    for comp, (src, col) in {
        **{c: (aus, col) for c, col in _HOTSPOT_COMPONENTS.items()},
        "seaus_burden": (seaus, "concurrent_burden"),
        "seaus_intensity": (seaus, "frp_load"),
    }.items():
        # hotspot era only; within it, a missing day means zero fire activity
        out[comp] = src[col].reindex(idx).fillna(0).where(tier <= 2)

    out["fire_windows"] = (
        burn_windows.set_index("date")["n_windows_active"].reindex(idx).fillna(0).where(tier == 3)
    )
    out["drfa_load"] = _masked(drfa_panel, "n_active_events", idx, "drfa")
    out["drfa_lga"] = _masked(drfa_panel, "n_lga_active", idx, "drfa")
    out["tfb_load"] = _masked(tfb_panel, "n_districts", idx, "tfb_vic")
    tc = tc_panel.set_index("date")
    out["tc_load"] = tc["n_tcs_active"].reindex(idx).fillna(0)
    out["tc_severity"] = tc["tc_max_wind"].reindex(idx).fillna(0)

    # Rain columns: reindex only — no fillna (NaN outside CSV coverage is correct).
    rain = rain_panel.set_index("date")
    for c in _RAIN_COLS:
        out[c] = rain[c].reindex(idx)

    return out


def _masked(panel: pd.DataFrame, col: str, idx, availability_key: str) -> pd.Series:
    a_start, a_end = COMPONENT_AVAILABILITY[availability_key]
    s = panel.set_index("date")[col].reindex(idx).fillna(0).astype(float)
    s[idx < pd.Timestamp(a_start)] = pd.NA
    if a_end is not None:
        s[idx > pd.Timestamp(a_end)] = pd.NA
    return s


def compute_dli(components: pd.DataFrame) -> pd.DataFrame:
    """Percentile-rank components and average into the DLI."""
    dates = components.index.to_series()
    ranks = pd.DataFrame(
        {c: monthly_tier_percentile(components[c].astype(float), dates) for c in components},
        index=components.index,
    )
    out = ranks.add_suffix("_pct")
    out["n_components_available"] = ranks.notna().sum(axis=1)
    fire_cols = list(_HOTSPOT_COMPONENTS) + ["seaus_burden", "seaus_intensity", "fire_windows"]
    rain_cols = _RAIN_COLS
    subs = pd.DataFrame(
        {
            "sub_fire": ranks[fire_cols].mean(axis=1, skipna=True),
            "sub_tc": ranks[["tc_load", "tc_severity"]].max(axis=1, skipna=True),
            "sub_drfa": ranks["drfa_lga"],
            "sub_tfb": ranks["tfb_load"],
            "sub_flood": ranks[rain_cols].mean(axis=1, skipna=True),
        }
    )
    # sub_flood must be NaN when all rain ranks are NaN (skipna=True with all-NaN row = NaN).
    all_rain_nan = ranks[rain_cols].isna().all(axis=1)
    subs.loc[all_rain_nan, "sub_flood"] = float("nan")
    out[subs.columns] = subs
    out["dli"] = subs.mean(axis=1, skipna=True)
    out["confidence_tier"] = tier_series(dates)
    return pd.concat([components, out], axis=1).reset_index()
