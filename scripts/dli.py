"""Section 5: Demand Load Index v0.

DLI v0 (design decision 6): each component is percentile-ranked within its
(confidence tier, calendar month) group — the month grouping removes
seasonality, the tier grouping keeps satellite-era step-changes from
contaminating ranks — then the DLI is the equal-weight mean of available
component percentiles. Days keep `n_components_available`; nothing is
NaN-filled silently.

Components (daily, national):
    fire_burden      concurrent_burden   tiers 1-2 (hotspot-based)
    fire_ignitions   ignition_load       tiers 1-2
    fire_growth      growth_load         tiers 1-2
    fire_intensity   frp_load            tiers 1-2
    fire_windows     n_windows_active    tier 3 only (polygon burn windows)
    drfa_load        n_active_events     2006-03-20 ->
    tfb_load         n_districts (VIC)   1945 ->
    tc_load          n_tcs_active        full period
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


def assemble_components(
    demand_metrics: pd.DataFrame,
    burn_windows: pd.DataFrame,
    drfa_panel: pd.DataFrame,
    tfb_panel: pd.DataFrame,
    tc_panel: pd.DataFrame,
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
    for comp, col in _HOTSPOT_COMPONENTS.items():
        s = aus[col].reindex(idx)
        # hotspot era only; within it, a missing day means zero fire activity
        s = s.fillna(0).where(tier <= 2)
        out[comp] = s

    out["fire_windows"] = (
        burn_windows.set_index("date")["n_windows_active"].reindex(idx).fillna(0).where(tier == 3)
    )
    out["drfa_load"] = _masked(drfa_panel, "n_active_events", idx, "drfa")
    out["tfb_load"] = _masked(tfb_panel, "n_districts", idx, "tfb_vic")
    out["tc_load"] = tc_panel.set_index("date")["n_tcs_active"].reindex(idx).fillna(0)
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
    out["dli"] = ranks.mean(axis=1, skipna=True)
    out["confidence_tier"] = tier_series(dates)
    return pd.concat([components, out], axis=1).reset_index()
