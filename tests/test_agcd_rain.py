import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.loaders.agcd_rain import load_agcd_rain

CSV = """date,rain1d_area,rain3d_area,rain7d_area,seaus_rain1d,seaus_rain3d,seaus_rain7d
1979-01-01,0.01,0.02,0.03,0.0,0.0,0.0
1979-01-02,0.10,0.12,0.15,0.20,0.25,0.30
"""


def test_load_agcd_rain(tmp_path):
    p = tmp_path / "agcd_rain_daily.csv"
    p.write_text(CSV)
    df = load_agcd_rain(p)
    assert list(df.columns) == [
        "date",
        "rain1d_area",
        "rain3d_area",
        "rain7d_area",
        "seaus_rain1d",
        "seaus_rain3d",
        "seaus_rain7d",
    ]
    assert df["date"].dtype.kind == "M"
    assert df["rain3d_area"].iloc[1] == 0.12


def test_load_agcd_rain_rejects_bad_fraction(tmp_path):
    p = tmp_path / "agcd_rain_daily.csv"
    p.write_text(CSV.replace("0.30", "1.30"))
    with pytest.raises(ValueError):
        load_agcd_rain(p)
