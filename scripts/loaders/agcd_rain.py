"""AGCD daily rainfall loader — national and SE Australia fractions (1979–present).

Source: Australian Gridded Climate Data (AGCD) aggregated daily rainfall.
Each row represents a day with rainfall accumulations at 1, 3, and 7-day spans,
computed as area fractions (0–1) of Australia and SE Australia (SEAUS) grid
points exceeding within-month wet-day 95th percentile.

AGCD days end at 09:00 local time (09:00 each region's local LT; varies across
the ~45° longitude span). The project's fixed UTC+10 bucket is ~9 hours ahead,
so AGCD day N aligns approximately with UTC+10 day N–1 late (09:00–00:00 local
= 23:00–14:00 UTC+10). This offset is accepted and documented; AGCD is
preprocessed on Gadi, so no local alignment is performed here.

The loader validates that all rain columns are in [0, 1] (NaN is allowed for
missing days outside the CSV's coverage window). Outside the CSV coverage,
all rain columns are NaN (availability discipline).
"""

import pandas as pd

from scripts.config import PATHS


def load_agcd_rain(path=None) -> pd.DataFrame:
    """Load AGCD daily rainfall CSV and validate rain fractions.

    Parameters
    ----------
    path : str or Path, optional
        Path to agcd_rain_daily.csv. If None, uses PATHS.agcd_rain_daily.

    Returns
    -------
    pd.DataFrame
        Columns: date (datetime64[ns]), rain1d_area, rain3d_area, rain7d_area,
        seaus_rain1d, seaus_rain3d, seaus_rain7d (all float).
        Outside the CSV's date coverage, rain columns are NaN.

    Raises
    ------
    ValueError
        If any rain column contains a value outside [0, 1] (NaN is allowed).
    """
    df = pd.read_csv(path or PATHS.agcd_rain_daily)

    # Parse date column to datetime64[ns].
    df["date"] = pd.to_datetime(df["date"])

    # Expected columns.
    rain_cols = ["rain1d_area", "rain3d_area", "rain7d_area", "seaus_rain1d", "seaus_rain3d", "seaus_rain7d"]

    # Validate that all rain columns exist.
    for col in rain_cols:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    # Validate rain fractions: all values must be in [0, 1], NaN is allowed.
    for col in rain_cols:
        valid_mask = df[col].notna()
        if valid_mask.any():
            out_of_range = (df.loc[valid_mask, col] < 0) | (df.loc[valid_mask, col] > 1)
            if out_of_range.any():
                raise ValueError(
                    f"Column {col} contains values outside [0, 1]: "
                    f"{df.loc[out_of_range, col].values}"
                )

    # Return with expected column order: date + rain columns.
    return df[["date"] + rain_cols]
