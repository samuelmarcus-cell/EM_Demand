import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase2_attribution.swt_attribution import attach_swt


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
