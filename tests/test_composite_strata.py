import numpy as np
import pandas as pd
import pytest

from scripts.composite_strata import STRATUM_OF, assign_strata


def make_panel(n=100):
    """Synthetic single-tier panel: dli ramps 0->1 so the top-5% days are rows 95-99."""
    return pd.DataFrame(
        {
            "date": pd.date_range("2015-01-01", periods=n),
            "dli": np.linspace(0, 1, n),
            "confidence_tier": 1,
            "sub_fire": 0.1,
            "sub_tfb": 0.1,
            "sub_tc": 0.1,
            "sub_drfa": 0.1,
        }
    )


def test_only_high_demand_days_selected():
    out = assign_strata(make_panel())
    assert len(out) == 5  # rows 95-99 of the 0..1 ramp
    assert out["date"].min() == pd.Timestamp("2015-04-06")


def test_argmax_assigns_dominant_hazard():
    df = make_panel()
    df.loc[99, "sub_tc"] = 0.9
    df.loc[98, "sub_fire"] = 0.9
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "tc"    # row 99
    assert s[pd.Timestamp("2015-04-09")] == "fire"  # row 98


def test_tfb_folds_into_fire_and_margin_uses_stratum_scores():
    df = make_panel()
    df.loc[99, ["sub_tfb", "sub_fire", "sub_tc"]] = [0.95, 0.5, 0.6]
    out = assign_strata(df).set_index("date")
    row = out.loc[pd.Timestamp("2015-04-10")]
    assert row["stratum"] == "fire"
    # fire score = max(0.5, 0.95); runner-up stratum is tc (0.6), NOT sub_fire
    assert row["margin"] == pytest.approx(0.95 - 0.6)


def test_flood_column_absent_is_fine():
    out = assign_strata(make_panel())  # no sub_flood column
    assert set(out["stratum"]) <= {"fire", "tc", "drfa-led"}


def test_flood_column_used_when_present():
    df = make_panel()
    df["sub_flood"] = 0.1
    df.loc[99, "sub_flood"] = 0.99
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "flood"


def test_all_nan_subindices_day_is_excluded():
    df = make_panel()
    df.loc[99, ["sub_fire", "sub_tfb", "sub_tc", "sub_drfa"]] = np.nan
    out = assign_strata(df)
    assert pd.Timestamp("2015-04-10") not in set(out["date"])
    assert len(out) == 4


def test_partial_nan_ignored():
    df = make_panel()
    df.loc[99, "sub_tc"] = np.nan
    df.loc[99, "sub_drfa"] = 0.8
    s = assign_strata(df).set_index("date")["stratum"]
    assert s[pd.Timestamp("2015-04-10")] == "drfa-led"


def test_margin_nan_when_single_stratum_scored():
    df = make_panel()
    df.loc[99, ["sub_tfb", "sub_tc", "sub_drfa"]] = np.nan
    out = assign_strata(df).set_index("date")
    assert np.isnan(out.loc[pd.Timestamp("2015-04-10"), "margin"])


def test_strata_to_composite_min_days():
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "gadi" / "demand_composites.py"
    spec = importlib.util.spec_from_file_location("demand_composites", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    days = pd.DataFrame(
        {
            "date": pd.date_range("2015-01-01", periods=40),
            "stratum": ["fire"] * 30 + ["tc"] * 10,
        }
    )
    assert mod.strata_to_composite(days) == ["fire"]
    assert mod.strata_to_composite(days, min_days=10) == ["fire", "tc"]
