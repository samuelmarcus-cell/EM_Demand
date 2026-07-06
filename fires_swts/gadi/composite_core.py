"""Pure (numpy) compositing core — no ERA5/Gadi I/O, so it is unit-testable locally."""
import numpy as np
import pandas as pd
from scipy.stats import norm

_REF  = pd.date_range("2020-01-01", "2020-12-31")          # leap year -> 366 day-of-year slots
_SLOT = {(t.month, t.day): i for i, t in enumerate(_REF)}

def mmdd_slot(dates):
    """Map each date to a 0..365 day-of-year slot (Feb-29 has its own slot)."""
    dti = pd.DatetimeIndex(dates)
    return np.array([_SLOT[(m, d)] for m, d in zip(dti.month, dti.day)], dtype=int)

def doy_anomaly_composite(field, dates, swt, swt_names):
    """Per-SWT seasonally-adjusted composite.
    field [T,Y,X] (12 UTC daily samples), dates datetime64[D][T], swt str[T].
    Returns mean[K,Y,X], anom[K,Y,X], p[K,Y,X] (two-sided), n[K]."""
    field = np.asarray(field, float)
    T, Y, X = field.shape
    doy = mmdd_slot(dates)
    # NaN-safe day-of-year climatology: a single NaN day must NOT poison a cell's whole slot.
    # Built slot-by-slot (small slices) -- a full nan_to_num(field)/isfinite(field) copy
    # doubled peak RAM and OOM-killed the 16GB Gadi job, so we avoid those big temporaries.
    clim = np.full((366, Y, X), np.nan); cnt = np.zeros((366, Y, X))
    for s in np.unique(doy):
        fs = field[doy == s]                                # ~45 days for this calendar slot
        clim[s] = np.nansum(fs, 0); cnt[s] = np.isfinite(fs).sum(0)
    with np.errstate(invalid="ignore"):
        clim = np.where(cnt > 0, clim / np.maximum(cnt, 1), np.nan)
    K = len(swt_names)
    mean = np.full((K, Y, X), np.nan); anom = np.full((K, Y, X), np.nan)
    p    = np.full((K, Y, X), np.nan); n = np.zeros(K, int)
    swt = np.asarray(swt)
    for k, name in enumerate(swt_names):
        m = swt == name; nk = int(m.sum()); n[k] = nk
        if nk == 0:
            continue
        fm = field[m]                                       # this SWT's days only (hundreds, not all T)
        a = fm - clim[doy[m]]                               # day anomalies, SWT-local (no full [T,Y,X])
        mean[k] = np.nanmean(fm, 0); anom[k] = np.nanmean(a, 0)
        if nk > 1:
            with np.errstate(divide="ignore", invalid="ignore"):
                se = np.nanstd(a, 0, ddof=1) / np.sqrt(np.maximum(np.isfinite(a).sum(0), 1))
                t = np.where(se > 0, anom[k] / se, 0.0)
            p[k] = 2 * norm.sf(np.abs(t))
    return mean, anom, p, n
