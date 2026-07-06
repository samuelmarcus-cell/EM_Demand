import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_for_r import tidy_components


def test_tidy_components_alignment():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2015-01-01", "2015-01-02"]),
            "confidence_tier": [1, 1],
            "fire_burden": [5.0, 10.0],
            "fire_burden_pct": [0.5, 1.0],
            "tc_load": [0.0, np.nan],
            "tc_load_pct": [0.25, np.nan],
            "dli": [0.4, 0.9],
        }
    )
    out = tidy_components(panel)
    assert len(out) == 4  # 2 days x 2 components
    row = out[(out["date"] == "2015-01-02") & (out["component"] == "fire_burden")].iloc[0]
    assert row["value"] == 10.0 and row["pct"] == 1.0
    row = out[(out["date"] == "2015-01-02") & (out["component"] == "tc_load")].iloc[0]
    assert np.isnan(row["value"]) and np.isnan(row["pct"])
    assert set(out.columns) == {"date", "confidence_tier", "component", "value", "pct"}
