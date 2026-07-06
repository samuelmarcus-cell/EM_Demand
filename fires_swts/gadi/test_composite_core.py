"""Run: /opt/anaconda3/bin/python3 gadi/test_composite_core.py  -> prints OK or asserts."""
import numpy as np, pandas as pd
from composite_core import mmdd_slot, doy_anomaly_composite

def test_slot_count():
    d = pd.date_range("2019-01-01", "2021-12-31").values.astype("datetime64[D]")
    s = mmdd_slot(d)
    assert s.min() == 0 and s.max() == 365

def test_recovers_known_offset():
    # synthetic: seasonal cycle + a +5.0 offset injected ONLY on SWT 'A' days.
    # NB: anomalies are relative to the ALL-SWT day-of-year climatology (Barnes'
    # cluster_daily_pert). So with frac(A)=0.2 the clim is shifted up by ~0.2*5;
    # A's anomaly -> positive, B's -> negative, and the COUNT-WEIGHTED sum of
    # anomalies is EXACTLY 0. The recoverable signal is the A-vs-B contrast, which
    # for random assignment equals 5*(1 - 1/Yr) where Yr = number of years
    # (finite-record bias of the climatology estimate).
    n_years = 51
    dates = pd.date_range("1970-01-01", f"{1970+n_years-1}-12-31").values.astype("datetime64[D]")
    T = len(dates); Y, X = 3, 4
    doy = mmdd_slot(dates)
    seasonal = np.cos(2*np.pi*doy/366)[:, None, None] * np.ones((T, Y, X))
    rng = np.random.default_rng(0)
    swt = np.where(rng.random(T) < 0.2, "A", "B")
    field = seasonal + rng.normal(0, 0.1, (T, Y, X))
    field[swt == "A"] += 5.0
    mean, anom, p, n = doy_anomaly_composite(field, dates, swt, ["A", "B"])
    assert n[0] > 100 and n[1] > 100
    # defining invariant of this anomaly: sum_k n_k * anom_k == 0 per grid cell
    assert np.allclose(n[0]*anom[0] + n[1]*anom[1], 0.0, atol=1e-6)
    assert (anom[0] > 0).all() and (anom[1] < 0).all()  # A above clim, B below
    expected_contrast = 5.0 * (1 - 1/n_years)            # ~4.90
    assert np.allclose(anom[0] - anom[1], expected_contrast, atol=0.15)
    assert np.nanmax(p[0]) < 0.01                        # A highly significant
    assert np.nanmin(p[1]) < 0.01                        # B also significantly != 0

def test_nan_field_does_not_poison_anomalies():
    # Regression: the real BARRA-R2 FFDI field carries NaN day-cells. A non-skipna
    # day-of-year climatology let a single NaN poison a cell's whole slot, making
    # EVERY anomaly NaN while the plain per-SWT mean still looked finite. Guard it.
    dates = pd.date_range("2000-01-01", "2009-12-31").values.astype("datetime64[D]")
    T = len(dates); Y, X = 3, 3
    rng = np.random.default_rng(1)
    seas = 1 + 0.5*np.cos(2*np.pi*(pd.DatetimeIndex(dates).dayofyear.to_numpy()-15)/365)
    field = (rng.gamma(2, 5, (T, Y, X)) * seas[:, None, None]).astype(float)
    field[rng.random((T, Y, X)) < 0.05] = np.nan      # scattered missing day-cells
    field[100] = np.nan                                # one wholly-missing day
    swt = np.where(np.arange(T) % 2 == 0, "A", "B")
    mean, anom, p, n = doy_anomaly_composite(field, dates, swt, ["A", "B"])
    assert np.isfinite(mean).all(), "means must survive scattered NaN"
    assert np.isfinite(anom).all(), "anomalies must survive scattered NaN (the bug)"
    assert np.isfinite(p).all()
    assert np.nanmean(np.abs(anom[0])) < 0.5           # climatology-relative -> small

if __name__ == "__main__":
    test_slot_count(); test_recovers_known_offset(); test_nan_field_does_not_poison_anomalies()
    print("OK: composite_core tests passed")
