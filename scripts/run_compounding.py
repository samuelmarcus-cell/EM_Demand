"""Spatial hazard-load compounding: excess ratios + impact check.

Reads state_hazard_panel.parquet; writes compounding_ratios.csv,
compounding_null_samples.csv, compounding_impact_check.csv,
state_cooccurrence.csv, compound_days_top.csv; prints plain-language
tables. Headline = flag threshold 0.95, radius 300 km; sensitivity grid
reported alongside, never tuned.
"""

import pandas as pd

from scripts.config import DATA_DERIVED, TIER_BOUNDS
from scripts.phase3_compounding.compound_demand import (
    complete_years, excess_ratios, impact_followup,
)
from scripts.state_panel import DRFA_START, STATES

panel = pd.read_parquet(DATA_DERIVED / "state_hazard_panel.parquet")
panel["date"] = pd.to_datetime(panel["date"])


def high_frame(layer, threshold, pct_col="pct"):
    sub = panel[panel.layer == layer]
    wide = sub.pivot_table(index="date", columns="state", values=pct_col,
                           aggfunc="first").reindex(columns=STATES)
    return wide >= threshold


tier1_start = pd.Timestamp(TIER_BOUNDS[1][0]).year  # 2012
tier2_start = pd.Timestamp(TIER_BOUNDS[2][0]).year  # 2000 (from 2000-11-01)


def fire_group(y):
    """Year -> shuffle group. Years only swap within their confidence tier
    so data-era artefacts cannot fake a signal. Year 2000 mixes tier 3
    (Jan-Oct) and tier 2 (Nov-Dec): it gets its own singleton group and
    never swaps."""
    if y < tier2_start:
        return 3
    if y == tier2_start:
        return 0  # singleton: the mixed tier-boundary year stays in place
    return 1 if y >= tier1_start else 2


all_ratios, all_samples = [], []
for thr in (0.95, 0.90, 0.975):
    for radius, pct_col in [(300, "pct"), (200, "pct_r200"), (400, "pct_r400")]:
        fire = high_frame("fire", thr)
        tc = high_frame("tc", thr, pct_col)
        fire_cy = complete_years(fire)
        fire_year_groups = {int(y): fire_group(int(y))
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
ratios.to_csv(DATA_DERIVED / "compounding_ratios.csv", index=False)
samples.to_csv(DATA_DERIVED / "compounding_null_samples.csv", index=False)

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
impact.to_csv(DATA_DERIVED / "compounding_impact_check.csv", index=False)

# ---- figure data: state co-occurrence matrix + top compound days ----
cooc = []
for hazard, frame in [("fire", fire95), ("tc", tc95)]:
    f = frame.fillna(False)
    for a in STATES:
        for b in STATES:
            cooc.append({"hazard": hazard, "state_a": a, "state_b": b,
                         "n_days": int((f[a] & f[b]).sum())})
pd.DataFrame(cooc).to_csv(DATA_DERIVED / "state_cooccurrence.csv", index=False)

summary = pd.read_parquet(DATA_DERIVED / "state_hazard_summary.parquet")
summary["date"] = pd.to_datetime(summary["date"])
top = summary.nlargest(30, "n_cells_high")["date"]
top_cells = panel[panel.date.isin(top) & panel.layer.isin(["fire", "tc"])
                  & (panel.pct >= 0.95)]
top_cells[["date", "state", "layer", "pct"]].to_csv(
    DATA_DERIVED / "compound_days_top.csv", index=False)

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
