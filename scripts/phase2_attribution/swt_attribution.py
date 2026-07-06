"""Phase 2: attribute high-demand days to synoptic weather types (SWTs).

Joins the daily DLI panel (Phase 1 output, `demand_daily_panel.parquet`)
to the SWT daily classification (`~/Fires_SWTs/SWT_climatology_v20260129.csv`)
and asks: which SWTs are over-represented on high-demand days, per tier and
per season? Follows the Fires_SWTs relative-risk framework (RR of a
high-DLI day conditional on SWT, with bootstrap CIs), but with demand — not
fire occurrence — as the outcome variable.

Interface:
    attach_swt(panel, swt_csv) -> panel + swt_type column
    flag_high_demand(panel, threshold_pct) -> bool Series (within-tier threshold)
    swt_rr_point(df) -> per-SWT RR table (month-matched baseline)
    demand_swt_rr(panel, ...) -> RR table with moving-block bootstrap CIs
"""

import numpy as np
import pandas as pd


def attach_swt(panel, swt_csv=None):
    from scripts.config import PATHS

    swt = pd.read_csv(swt_csv or PATHS.swt_climatology)
    swt["date"] = pd.to_datetime(swt["time"]).dt.normalize()
    swt = swt.rename(columns={"assigned_SWT": "swt_type"})[["date", "swt_type"]]
    swt = swt.drop_duplicates("date")
    return panel.merge(swt, on="date", how="left")


def flag_high_demand(panel, threshold_pct=0.95):
    thresh = panel.groupby("confidence_tier")["dli"].transform(
        lambda s: s.quantile(threshold_pct)
    )
    return (panel["dli"] >= thresh).fillna(False)


def swt_rr_point(df):
    """Per-SWT relative risk of a high-demand day, month-matched baseline.

    RR = observed high-rate under the SWT / high-rate expected if the SWT
    had no effect beyond its monthly occurrence pattern.
    """
    d = df.dropna(subset=["swt_type"]).copy()
    d["month"] = d["date"].dt.month
    p_high_month = d.groupby("month")["high"].mean()
    rows = []
    for swt, g in d.groupby("swt_type"):
        n_days = len(g)
        n_high = int(g["high"].sum())
        expected = (g["month"].map(p_high_month)).mean()
        rr = (n_high / n_days) / expected if expected > 0 else float("nan")
        rows.append({"swt_type": swt, "n_days": n_days, "n_high": n_high, "rr": rr})
    return pd.DataFrame(rows).sort_values("rr", ascending=False).reset_index(drop=True)


def demand_swt_rr(panel, dli_threshold_pct=0.95):
    raise NotImplementedError("Phase 2")
