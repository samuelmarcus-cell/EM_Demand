import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase2_attribution.swt_attribution import (
    attach_swt,
    demand_swt_rr,
    flag_high_demand,
    swt_rr_point,
)


def _panel(start="2000-01-01", periods=6):
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "date": dates,
        "dli": np.linspace(0.1, 0.9, periods),
        "confidence_tier": 2,
    })


def test_attach_swt(tmp_path):
    csv = tmp_path / "swt.csv"
    csv.write_text(
        "time,assigned_SWT\n"
        "2000-01-01,WH-A\n"
        "2000-01-02,TH-A\n"
        "2000-01-03,WH-A\n"
    )
    out = attach_swt(_panel(), csv)
    assert len(out) == 6  # left join: panel rows preserved
    assert out.loc[out.date == "2000-01-01", "swt_type"].item() == "WH-A"
    assert out.loc[out.date == "2000-01-05", "swt_type"].isna().all()


def test_flag_high_demand_within_tier():
    dates = pd.date_range("2000-01-01", periods=40, freq="D")
    panel = pd.DataFrame({
        "date": dates,
        "dli": list(np.linspace(0, 1, 20)) * 2,
        "confidence_tier": [2] * 20 + [1] * 20,
    })
    high = flag_high_demand(panel, threshold_pct=0.95)
    # each tier contributes its own top ~5% (the max value at least)
    assert high[panel.confidence_tier == 2].sum() >= 1
    assert high[panel.confidence_tier == 1].sum() >= 1


def test_swt_rr_point_month_matched():
    # Jan: base high-rate 0.5. SWT "A" only in Jan, always high -> RR 2.
    # SWT "B" only in Jan, never high -> RR 0. Month matching means the
    # July-only SWT "C" (high-rate 0 in a month whose base rate is 0)
    # yields NaN, not a spurious signal.
    rows = []
    for d in pd.date_range("2000-01-01", "2000-01-10"):
        rows.append({"date": d, "swt_type": "A" if d.day <= 5 else "B",
                     "high": d.day <= 5})
    for d in pd.date_range("2000-07-01", "2000-07-05"):
        rows.append({"date": d, "swt_type": "C", "high": False})
    out = swt_rr_point(pd.DataFrame(rows)).set_index("swt_type")
    assert out.loc["A", "rr"] == 2.0
    assert out.loc["B", "rr"] == 0.0
    assert np.isnan(out.loc["C", "rr"])
    assert out.loc["A", "n_days"] == 5 and out.loc["A", "n_high"] == 5


def test_demand_swt_rr_columns_and_ci_order():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2000-01-01", periods=400, freq="D")
    swt = rng.choice(["A", "B"], size=400)
    dli = rng.uniform(0, 0.8, size=400)
    dli[swt == "A"] += 0.2  # A days genuinely run hotter
    panel = pd.DataFrame({
        "date": dates, "dli": dli, "confidence_tier": 2, "swt_type": swt,
    })
    out = demand_swt_rr(panel, n_boot=50, block_days=10, seed=1)
    assert list(out.columns) == ["swt_type", "n_days", "n_high", "rr", "rr_lo", "rr_hi"]
    a = out.set_index("swt_type").loc["A"]
    assert a["rr_lo"] <= a["rr"] <= a["rr_hi"]
    assert a["rr"] > 1.0  # enriched SWT detected


def test_demand_swt_rr_reproducible():
    dates = pd.date_range("2000-01-01", periods=200, freq="D")
    panel = pd.DataFrame({
        "date": dates,
        "dli": np.tile(np.linspace(0, 1, 20), 10),
        "confidence_tier": 2,
        "swt_type": np.tile(["A"] * 10 + ["B"] * 10, 10),
    })
    o1 = demand_swt_rr(panel, n_boot=20, block_days=10, seed=7)
    o2 = demand_swt_rr(panel, n_boot=20, block_days=10, seed=7)
    pd.testing.assert_frame_equal(o1, o2)
