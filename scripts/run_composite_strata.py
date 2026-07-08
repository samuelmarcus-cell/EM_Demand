"""Write the stratum-label file for the Gadi composite job, and print the
stratum counts + top-two-margin evidence the compounding panel will need.

Output: data/derived/demand_stratum_days.csv (date,stratum)
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.composite_strata import assign_strata
from scripts.config import DATA_DERIVED

panel = pd.read_parquet(DATA_DERIVED / "demand_daily_panel.parquet")
days = assign_strata(panel)

out = DATA_DERIVED / "demand_stratum_days.csv"
days[["date", "stratum"]].to_csv(out, index=False, date_format="%Y-%m-%d")
print(f"wrote {out} ({len(days)} high-demand days)", flush=True)

counts = days["stratum"].value_counts()
print("\nStratum counts (n < 30 reported but NOT composited):", flush=True)
for s, n in counts.items():
    note = "" if n >= 30 else "   [n<30 — not composited]"
    print(f"  {s:>9}: {n}{note}", flush=True)

print("\nTop-two margin distribution (per-stratum scores):", flush=True)
q = days["margin"].quantile([0.05, 0.25, 0.5, 0.75, 0.95])
print(q.round(3).to_string(), flush=True)

print("\n20 smallest margins (near-ties — evidence for the future "
      "compound-day definition):", flush=True)
near = days.nsmallest(20, "margin")[["date", "stratum", "margin"]]
print(near.assign(margin=near["margin"].round(4)).to_string(index=False),
      flush=True)
