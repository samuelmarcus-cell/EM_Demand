"""Run: /opt/anaconda3/bin/python3 gadi/test_ffdi_core.py"""
import numpy as np, pandas as pd
from ffdi_core import high_danger_flags, build_danger_daily

def _synth():
    dates = pd.date_range("1990-01-01", "2009-12-31")
    rng = np.random.default_rng(0)
    rows = []
    for st in ["NSW", "VIC", "SA"]:
        ffdi = rng.gamma(2, 5, len(dates))
        rows.append(pd.DataFrame({"date": dates, "state": st, "ffdi": ffdi}))
    return pd.concat(rows, ignore_index=True)

def test_flag_rate_is_about_10pct():
    f = high_danger_flags(_synth(), q=0.90)
    # >= monthly 90th pctile -> ~10% of each state's days flagged
    rate = f.groupby("state")["hot"].mean()
    assert (rate.between(0.08, 0.13)).all(), rate.to_dict()

def test_build_danger_daily_counts():
    f = high_danger_flags(_synth(), q=0.90)
    swt = pd.DataFrame({"day": pd.date_range("1990-01-01", "2009-12-31")})
    swt["month"] = swt["day"].dt.month; swt["assigned_SWT"] = "X"; swt["regime"] = "X"
    d = build_danger_daily(f, swt, min_states=2)
    assert len(d) == len(swt)
    assert d["n_states"].max() <= 3 and d["n_states"].min() >= 0
    assert (d["multi_day"] == (d["n_states"] >= 2)).all()

if __name__ == "__main__":
    test_flag_rate_is_about_10pct(); test_build_danger_daily_counts()
    print("OK: ffdi_core tests passed")
