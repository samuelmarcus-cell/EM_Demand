"""Spatial hazard-load compounding: year-block shuffle null + excess ratios.

Measures HAZARD LOAD co-occurrence across states — never demand (spec §1).
Method: Gauthier & Bevacqua (2026, npj Nat. Hazards) spatial-shuffle design
adapted to whole-calendar-year blocks (docs/phase3_methods_notes.md).
Year blocks are the conservative choice: a climate driver synchronising
whole seasons partly survives in the null, so the excess that remains is
same-day/synoptic-scale organisation. Headline ratios are therefore
underestimates of total co-occurrence — the right direction to err.
"""

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365  # Feb 29 dropped by complete_years


def complete_years(high: pd.DataFrame) -> pd.DataFrame:
    """Drop Feb 29 rows and trim to complete 365-day calendar years.

    Whole-year shuffling needs equal-length year blocks; partial first/last
    years and leap days (~0.07% of days) are excluded from observed AND
    null alike, so nothing is biased.
    """
    df = high[~((high.index.month == 2) & (high.index.day == 29))]
    counts = df.groupby(df.index.year).size()
    keep = counts[counts == DAYS_PER_YEAR].index
    return df[df.index.year.isin(keep)].sort_index()


def _grouped_permutation(years: np.ndarray, year_groups, rng) -> np.ndarray:
    """Permutation of year positions; swaps stay within year_groups labels."""
    idx = np.arange(len(years))
    if year_groups is None:
        return rng.permutation(idx)
    out = idx.copy()
    labels = np.array([year_groups[int(y)] for y in years])
    for g in np.unique(labels):
        sel = np.where(labels == g)[0]
        out[sel] = sel[rng.permutation(len(sel))]
    return out


def shuffle_years(high: pd.DataFrame, year_groups, rng) -> pd.DataFrame:
    """Independently permute each column's calendar years.

    Each series keeps its own seasonality (a shuffled year is a whole
    calendar year) and within-season persistence; only the alignment of
    states' bad periods in time is destroyed. year_groups (e.g. year ->
    confidence tier for fire) restricts swaps to within-group so data-era
    artefacts cannot fake a signal; None = whole-period shuffle (tc).
    Input must already be complete_years output.
    """
    years = np.array(sorted(set(high.index.year)))
    n_years = len(years)
    out = {}
    for col in high.columns:
        arr = high[col].to_numpy().reshape(n_years, DAYS_PER_YEAR)
        perm = _grouped_permutation(years, year_groups, rng)
        out[col] = arr[perm].ravel()
    return pd.DataFrame(out, index=high.index)


def compounding_counts(high: pd.DataFrame, thresholds=(2, 3, 4)) -> dict:
    """Fraction of days with >=k states simultaneously under high load."""
    n = high.sum(axis=1)
    return {k: float((n >= k).mean()) for k in thresholds}


def cross_hazard_frequency(fire_high: pd.DataFrame,
                           tc_high: pd.DataFrame) -> float:
    """Fraction of days with >=1 state high on fire AND a DIFFERENT state
    high on tc (the spatially compounding case, spec §2). Computed on the
    intersection of the two layers' dates."""
    common = fire_high.index.intersection(tc_high.index)
    f, t = fire_high.loc[common], tc_high.loc[common]
    cols = f.columns.intersection(t.columns)
    n_f, n_t = f.sum(axis=1), t.sum(axis=1)
    both = (f[cols] & t[cols]).sum(axis=1)
    only_same_single = (n_f == 1) & (n_t == 1) & (both == 1)
    return float(((n_f > 0) & (n_t > 0) & ~only_same_single).mean())


def excess_ratios(fire_high, tc_high, fire_year_groups, n_shuffles=1000,
                  thresholds=(2, 3, 4), seed=42):
    """Observed vs shuffle-null frequencies of spatial compounding.

    Returns (ratios, null_samples):
      ratios: statistic ('fire'|'tc'|'cross'), threshold, observed,
              null_mean, null_lo, null_hi (2.5/97.5 pct), ratio,
              ratio_lo, ratio_hi.
      null_samples: long frame (statistic, threshold, shuffle, frequency)
              for the null-distribution figure.
    An empty tc_high (zero columns) skips tc and cross statistics — used
    by the synthetic single-hazard tests.
    """
    rng = np.random.default_rng(seed)
    fire_high = complete_years(fire_high)
    have_tc = tc_high.shape[1] > 0
    if have_tc:
        tc_high = complete_years(tc_high)

    obs = {("fire", k): v for k, v in
           compounding_counts(fire_high, thresholds).items()}
    if have_tc:
        obs.update({("tc", k): v for k, v in
                    compounding_counts(tc_high, thresholds).items()})
        obs[("cross", 1)] = cross_hazard_frequency(fire_high, tc_high)

    null = {key: [] for key in obs}
    for i in range(n_shuffles):
        f = shuffle_years(fire_high, fire_year_groups, rng)
        if have_tc:
            t = shuffle_years(tc_high, None, rng)
        for k, v in compounding_counts(f, thresholds).items():
            null[("fire", k)].append(v)
        if have_tc:
            for k, v in compounding_counts(t, thresholds).items():
                null[("tc", k)].append(v)
            null[("cross", 1)].append(cross_hazard_frequency(f, t))

    rows, samples = [], []
    for key, o in obs.items():
        arr = np.asarray(null[key])
        mean = arr.mean()
        lo, hi = np.percentile(arr, [2.5, 97.5])
        rows.append({
            "statistic": key[0], "threshold": key[1], "observed": o,
            "null_mean": mean, "null_lo": lo, "null_hi": hi,
            "ratio": o / mean if mean > 0 else np.inf,
            "ratio_lo": o / hi if hi > 0 else np.inf,
            "ratio_hi": o / lo if lo > 0 else np.inf,
        })
        samples.extend(
            {"statistic": key[0], "threshold": key[1], "shuffle": i,
             "frequency": v} for i, v in enumerate(arr)
        )
    return pd.DataFrame(rows), pd.DataFrame(samples)


def impact_followup(hazard_multi: pd.Series, drfa_multi: pd.Series,
                    window: int = 30) -> pd.DataFrame:
    """Descriptive impact check (spec §3): frequency of >=1 multi-state
    DRFA-activation day within `window` days AFTER multi-state hazard days
    vs after quiet days. No ratio, no test — reported either way.
    Both series boolean, daily, aligned (2006- caller's responsibility).
    """
    common = hazard_multi.index.intersection(drfa_multi.index)
    h, d = hazard_multi.loc[common], drfa_multi.loc[common]
    # followed[t] = any drfa_multi in (t, t+window]
    followed = (
        d.iloc[::-1].rolling(window, min_periods=1).max().iloc[::-1]
        .shift(-1)
    )
    df = pd.DataFrame({"hazard": h, "followed": followed}).dropna()
    rows = []
    for label, mask in [("after multi-state hazard days", df.hazard),
                        ("after quiet days", ~df.hazard)]:
        sub = df[mask]
        rows.append({"group": label, "window_days": window,
                     "n_days": int(len(sub)),
                     "frac_followed": float(sub["followed"].mean())
                     if len(sub) else float("nan")})
    return pd.DataFrame(rows)
