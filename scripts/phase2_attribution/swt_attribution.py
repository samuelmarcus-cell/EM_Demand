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


def demand_swt_rr(panel, dli_threshold_pct=0.95):
    raise NotImplementedError("Phase 2")
