"""Section 6: analysis-ready CSV exports (data/export/).

    demand_daily_panel.csv   wide daily panel: components, percentiles,
                             subindices, dli, confidence_tier
    dli_components_long.csv  tidy long: date, tier, component, value, pct
    demand_metrics_daily.csv region-day fire demand metrics (already tidy)
    dli_top50_days.csv       top 50 DLI days per tier

R reads these directly (no R run here). Floats rounded to 4 dp to keep
files small; NaN written as empty string (R reads as NA).
"""

import pandas as pd

from scripts.config import DATA_DERIVED

EXPORT_DIR = DATA_DERIVED.parent / "export"


def tidy_components(panel: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (date, component) with raw value and percentile."""
    pct_cols = [c for c in panel.columns if c.endswith("_pct")]
    components = [c.removesuffix("_pct") for c in pct_cols]
    value = panel.melt(
        id_vars=["date", "confidence_tier"], value_vars=components,
        var_name="component", value_name="value",
    )
    pct = panel.melt(id_vars=["date"], value_vars=pct_cols, value_name="pct")
    value["pct"] = pct["pct"].values  # melt preserves column-major order
    return value.sort_values(["date", "component"]).reset_index(drop=True)


def _write(df: pd.DataFrame, name: str) -> None:
    df.to_csv(EXPORT_DIR / name, index=False, float_format="%.4f")
    print(f"  {name}: {len(df)} rows", flush=True)


def write_exports(panel: pd.DataFrame, metrics: pd.DataFrame, top50: pd.DataFrame) -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    _write(panel, "demand_daily_panel.csv")
    _write(tidy_components(panel), "dli_components_long.csv")
    _write(metrics, "demand_metrics_daily.csv")
    _write(top50, "dli_top50_days.csv")
