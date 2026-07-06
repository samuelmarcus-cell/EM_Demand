"""Phase 2: SWT attribution of high-demand days.

Reads the Phase 1 demand panel, joins the SWT daily classification, and
writes per-SWT relative-risk tables (all-period and per confidence tier).

Outputs (data/derived/):
    swt_demand_rr.csv         all days with an SWT classification
    swt_demand_rr_tier{t}.csv per confidence tier
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.phase2_attribution.swt_attribution import attach_swt, demand_swt_rr

panel = pd.read_parquet(
    DATA_DERIVED / "demand_daily_panel.parquet",
    columns=["date", "dli", "confidence_tier"],
)
panel = attach_swt(panel)
n_swt = panel["swt_type"].notna().sum()
print(f"panel: {len(panel):,} days, {n_swt:,} with SWT", flush=True)

rr = demand_swt_rr(panel)
rr.round(3).to_csv(DATA_DERIVED / "swt_demand_rr.csv", index=False)
print("\nAll days:\n" + rr.round(2).to_string(index=False), flush=True)

for t, g in panel.groupby("confidence_tier"):
    rr_t = demand_swt_rr(g)
    rr_t.round(3).to_csv(DATA_DERIVED / f"swt_demand_rr_tier{t}.csv", index=False)
    print(f"\nTier {t}:\n" + rr_t.round(2).to_string(index=False), flush=True)
