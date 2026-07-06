"""Pure logic: per-state high-danger flags + the daily danger frame (no zarr/Gadi I/O)."""
import pandas as pd

def high_danger_flags(state_daily, q=0.90):
    """state_daily: long df [date, state, ffdi]. A state-day is 'hot' if its FFDI is
    >= that state's q-quantile WITHIN its calendar month (self-normalising by state & season)."""
    d = state_daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.month
    thr = d.groupby(["state", "month"])["ffdi"].transform(lambda x: x.quantile(q))
    d["hot"] = d["ffdi"] >= thr
    return d[["date", "state", "month", "ffdi", "hot"]]

def build_danger_daily(flags, swt, min_states=2):
    """flags: output of high_danger_flags. swt: df with [day, month, assigned_SWT, regime].
    Returns the full daily frame over SWT days with #dangerous-states, fire_day, multi_day."""
    hot = flags[flags["hot"]]
    per = hot.groupby("date")["state"].nunique().rename("n_states")
    d = swt.copy()
    d["day"] = pd.to_datetime(d["day"])
    d = d.merge(per, left_on="day", right_index=True, how="left")
    d["n_states"]  = d["n_states"].fillna(0).astype(int)
    d["fire_day"]  = d["n_states"] >= 1
    d["multi_day"] = d["n_states"] >= min_states
    return d
