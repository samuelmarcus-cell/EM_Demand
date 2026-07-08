"""Assign each high-demand day to its dominant-hazard stratum (pilot composites).

Selection: within-tier DLI >= 95th percentile (same flag_high_demand as the
Phase 2 SWT attribution, so the two analyses use identical day populations).
Stratum: argmax of the hazard subindices — no tuned threshold. sub_tfb folds
into fire (a total fire ban is a fire-danger decision). sub_drfa maps to
'drfa-led', which is a funding activation, not a hazard: composited
descriptively, excluded from the hypothesis test (see spec §2).

Margin: difference between the top two per-STRATUM scores, where the fire
score = max(sub_fire, sub_tfb). Folding first means a sub_fire/sub_tfb
near-tie (both fire) is not reported as hazard ambiguity. Ties across strata
resolve to the first stratum in STRATUM_OF order (nanargmax is deterministic).
"""
import numpy as np
import pandas as pd

from scripts.phase2_attribution.swt_attribution import flag_high_demand

STRATUM_OF = {
    "sub_fire": "fire",
    "sub_tfb": "fire",
    "sub_tc": "tc",
    "sub_flood": "flood",
    "sub_drfa": "drfa-led",
}


def assign_strata(panel, threshold_pct=0.95):
    """Return DataFrame(date, stratum, margin) for within-tier high-DLI days.

    Days whose subindices are all NaN are excluded (no basis for assignment).
    margin is NaN when fewer than two strata have a score that day.
    """
    d = panel.dropna(subset=["dli"]).copy()
    high = d[flag_high_demand(d, threshold_pct)]

    scores = {}
    for col, stratum in STRATUM_OF.items():
        if col not in high.columns:
            continue
        v = high[col].to_numpy(float)
        scores[stratum] = np.fmax(scores[stratum], v) if stratum in scores else v
    sc = pd.DataFrame(scores, index=high.index)

    valid = sc.notna().any(axis=1)
    high, sc = high[valid], sc[valid]

    arr = sc.to_numpy(float)
    stratum = sc.columns.to_numpy()[np.nanargmax(arr, axis=1)]
    ranked = np.sort(np.where(np.isnan(arr), -np.inf, arr), axis=1)
    top2 = ranked[:, -2]
    margin = np.where(np.isfinite(top2), ranked[:, -1] - top2, np.nan)

    return pd.DataFrame(
        {"date": high["date"].to_numpy(), "stratum": stratum, "margin": margin}
    ).reset_index(drop=True)
