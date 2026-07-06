"""Phase 2: attribute high-demand days to synoptic weather types (SWTs).

Joins the daily DLI panel (Phase 1 output, `demand_daily_panel.parquet`)
to the SWT daily classification (`~/Fires_SWTs/SWT_climatology_v20260129.csv`)
and asks: which SWTs are over-represented on high-demand days, per tier and
per season? Follows the Fires_SWTs relative-risk framework (RR of a
high-DLI day conditional on SWT, with bootstrap CIs), but with demand — not
fire occurrence — as the outcome variable.

Planned interface:
    attach_swt(panel, swt_csv) -> panel + swt_type column
    demand_swt_rr(panel, dli_threshold_pct=0.95) -> per-SWT RR table
"""


def attach_swt(panel, swt_csv):
    raise NotImplementedError("Phase 2")


def demand_swt_rr(panel, dli_threshold_pct=0.95):
    raise NotImplementedError("Phase 2")
