"""Section 4: explode DRFA events into a daily national activation panel.

Output columns per date: n_active_events, n_jurisdictions_active,
n_hazard_types_active, hazard flags (fire/flood/tc/storm/other),
drfa_available.
"""

import pandas as pd

from scripts.config import component_available

HAZARD_FLAG_COLS = ["hazard_fire", "hazard_flood", "hazard_tc", "hazard_storm", "hazard_other"]


def explode_events_daily(events: pd.DataFrame) -> pd.DataFrame:
    """One row per (event, active day). Requires start_date, end_date, states, hazard_classes."""
    rows = []
    for _, ev in events.iterrows():
        for day in pd.date_range(ev["start_date"], ev["end_date"], freq="D"):
            rows.append(
                {
                    "date": day,
                    "agrn": ev["agrn"],
                    "states": tuple(ev["states"]),
                    "hazard_classes": frozenset(ev["hazard_classes"]),
                    "end_date_source": ev["end_date_source"],
                }
            )
    return pd.DataFrame(rows)


def daily_panel(events: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Daily national activation panel over [start, end] (defaults to event span)."""
    ed = explode_events_daily(events)
    start = pd.Timestamp(start) if start else ed["date"].min()
    end = pd.Timestamp(end) if end else ed["date"].max()
    idx = pd.date_range(start, end, freq="D", name="date")

    grouped = ed.groupby("date")
    panel = pd.DataFrame(index=idx)
    panel["n_active_events"] = grouped["agrn"].nunique()
    panel["n_jurisdictions_active"] = grouped["states"].agg(
        lambda col: len(set().union(*col))
    )
    panel["n_hazard_types_active"] = grouped["hazard_classes"].agg(
        lambda col: len(frozenset().union(*col))
    )
    for cls in ["fire", "flood", "tc", "storm", "other"]:
        panel[f"hazard_{cls}"] = grouped["hazard_classes"].agg(
            lambda col, c=cls: any(c in h for h in col)
        )

    panel["n_active_events"] = panel["n_active_events"].fillna(0).astype(int)
    panel["n_jurisdictions_active"] = panel["n_jurisdictions_active"].fillna(0).astype(int)
    panel["n_hazard_types_active"] = panel["n_hazard_types_active"].fillna(0).astype(int)
    for c in HAZARD_FLAG_COLS:
        panel[c] = panel[c].astype("boolean").fillna(False).astype(bool)

    panel["drfa_available"] = [component_available("drfa", d) for d in panel.index]
    return panel.reset_index()
