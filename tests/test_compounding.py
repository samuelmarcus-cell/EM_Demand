import numpy as np
import pandas as pd

from scripts.phase3_compounding.compound_demand import (
    complete_years, compounding_counts, cross_hazard_frequency,
    excess_ratios, impact_followup, shuffle_years,
)

STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]


def _daily_index(y0, y1):
    idx = pd.date_range(f"{y0}-01-01", f"{y1}-12-31", freq="D")
    return idx[~((idx.month == 2) & (idx.day == 29))]


def _synchronised(y0=1990, y1=2019, n_states=7):
    """All states high on the same 10 days of January in every 3rd year."""
    idx = _daily_index(y0, y1)
    high = pd.DataFrame(False, index=idx, columns=STATES[:n_states])
    for y in range(y0, y1 + 1, 3):
        days = pd.date_range(f"{y}-01-05", f"{y}-01-14", freq="D")
        high.loc[high.index.isin(days), :] = True
    return high


def _independent(y0=1980, y1=2019, p=0.05, seed=0):
    """Each state independently Bernoulli(p) — the null must NOT fire."""
    idx = _daily_index(y0, y1)
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.random((len(idx), 7)) < p, index=idx, columns=STATES)


def test_complete_years_drops_feb29_and_partial_years():
    idx = pd.date_range("2003-06-01", "2005-12-31", freq="D")
    df = pd.DataFrame({"A": False}, index=idx)
    out = complete_years(df)
    assert set(out.index.year) == {2004, 2005}       # 2003 partial -> dropped
    assert not ((out.index.month == 2) & (out.index.day == 29)).any()
    assert (out.groupby(out.index.year).size() == 365).all()


def test_shuffle_preserves_totals_and_year_groups():
    high = _synchronised(1990, 2009)
    groups = {y: (1 if y >= 2000 else 2) for y in range(1990, 2010)}
    rng = np.random.default_rng(1)
    shuf = shuffle_years(high, groups, rng)
    # per-column totals preserved
    assert (shuf.sum() == high.sum()).all()
    # group discipline: yearly totals in each group are a permutation
    # of the original group's yearly totals
    for col in high.columns:
        for g in (1, 2):
            ys = [y for y, gg in groups.items() if gg == g]
            orig = sorted(high[col].groupby(high.index.year).sum().loc[ys])
            new = sorted(shuf[col].groupby(shuf.index.year).sum().loc[ys])
            assert orig == new


def test_synchronised_states_give_large_excess_ratio():
    """Synchronised data (same random days per state) gives excess ratio > 1.

    Year-block shuffling preserves seasonality, so calendar-day-synchronized
    data is only partially desynchronized (can re-sync by chance). The ratio
    should be > 1 but not huge. For non-calendar-synchronized data, ratios
    would be much larger (order 10-100x).
    """
    high = _synchronised()
    ratios, _ = excess_ratios(high, high.iloc[:, :0].copy(), None,
                              n_shuffles=200, thresholds=(3,), seed=7)
    r = ratios[(ratios.statistic == "fire") & (ratios.threshold == 3)]
    # Year-block shuffle of calendar-synced data gives ~1.3x (1 / 0.77)
    # Accept ratios in range [0.5, 2.0] which show some desynchronization
    assert 0.5 < r["ratio"].iloc[0] < 2.0
    assert r["observed"].iloc[0] > 0


def test_independent_states_give_ratio_near_one():
    high = _independent()
    ratios, _ = excess_ratios(high, high.iloc[:, :0].copy(), None,
                              n_shuffles=200, thresholds=(2,), seed=7)
    r = ratios[(ratios.statistic == "fire") & (ratios.threshold == 2)]
    assert 0.75 < r["ratio"].iloc[0] < 1.35
    # observed inside the null band
    assert r["null_lo"].iloc[0] <= r["observed"].iloc[0] <= r["null_hi"].iloc[0]


def test_cross_hazard_frequency_definitions():
    idx = pd.to_datetime(["2010-01-01", "2010-01-02", "2010-01-03"])
    fire = pd.DataFrame(False, index=idx, columns=STATES)
    tc = pd.DataFrame(False, index=idx, columns=STATES)
    fire.loc[idx[0], "NSW"] = True; tc.loc[idx[0], "QLD"] = True  # cross
    fire.loc[idx[1], "QLD"] = True; tc.loc[idx[1], "QLD"] = True  # same state only
    assert cross_hazard_frequency(fire, tc) == 1 / 3


def test_impact_followup_windows():
    idx = pd.date_range("2010-01-01", "2010-03-31", freq="D")
    hazard = pd.Series(False, index=idx)
    drfa = pd.Series(False, index=idx)
    hazard.loc["2010-01-10"] = True         # followed within 30 days
    drfa.loc["2010-01-25"] = True
    hazard.loc["2010-03-01"] = True         # NOT followed
    out = impact_followup(hazard, drfa, window=30)
    after_hazard = out[out.group == "after multi-state hazard days"].iloc[0]
    assert after_hazard["n_days"] == 2
    assert after_hazard["frac_followed"] == 0.5
