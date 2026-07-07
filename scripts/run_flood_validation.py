"""Flood-event validation diagnostic.

Loads demand_daily_panel.parquet and, for each event in docs/flood_event_days.csv,
prints sub_flood, its within-tier percentile (same method as run_dli.py benchmark
loop), and the six rain component percentile columns.

Guard: if sub_flood is absent from the panel (the AGCD rain CSV has not yet been
fetched and run_dli.py re-run), a clear message is printed and the script exits
with code 1.

NOTE: As of 2026-07-07 this run is DEFERRED — the AGCD rain CSV is still being
computed on Gadi.  Re-run after fetching the CSV and rebuilding the panel with
run_dli.py.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED

EVENTS_CSV = Path(__file__).resolve().parents[1] / "docs" / "flood_event_days.csv"

# Six rain-component percentile columns produced by dli.py
_RAIN_PCT_COLS = [
    "rain1d_area_pct",
    "rain3d_area_pct",
    "rain7d_area_pct",
    "seaus_rain1d_pct",
    "seaus_rain3d_pct",
    "seaus_rain7d_pct",
]


def main() -> None:
    panel = pd.read_parquet(DATA_DERIVED / "demand_daily_panel.parquet")

    # Guard: sub_flood must be present
    if "sub_flood" not in panel.columns:
        print(
            "ERROR: sub_flood is absent from demand_daily_panel.parquet.\n"
            "Re-run scripts/run_dli.py after fetching the AGCD rain CSV from Gadi\n"
            "to rebuild the panel with the flood component.",
            flush=True,
        )
        sys.exit(1)

    events = pd.read_csv(EVENTS_CSV, comment="#", parse_dates=["date"])
    p = panel.set_index("date")

    print("Flood-event validation:", flush=True)
    print(
        f"  {'Event':<26s} {'Date':<12s} {'tier':>4s}  "
        f"{'sub_flood':>9s}  {'sub_flood_pct':>13s}  "
        + "  ".join(f"{c:>16s}" for c in _RAIN_PCT_COLS),
        flush=True,
    )

    for _, row in events.iterrows():
        name = row["name"]
        day = row["date"]

        if day not in p.index:
            print(f"  {name:<26s} {str(day.date()):<12s} -- date not in panel", flush=True)
            continue

        event_row = p.loc[day]
        tier = int(event_row["confidence_tier"])

        # Within-tier percentile of sub_flood (mirrors run_dli.py benchmark loop)
        in_tier = p[p["confidence_tier"] == tier]["sub_flood"]
        sf_val = event_row["sub_flood"]
        sf_pct = (in_tier < sf_val).mean()

        # Rain component percentile values
        rain_vals = [
            f"{event_row[c]:.4f}" if c in event_row.index and pd.notna(event_row[c]) else "   NaN"
            for c in _RAIN_PCT_COLS
        ]

        print(
            f"  {name:<26s} {str(day.date()):<12s} {tier:>4d}  "
            f"{sf_val:>9.4f}  {sf_pct:>13.4f}  "
            + "  ".join(f"{v:>16s}" for v in rain_vals),
            flush=True,
        )


if __name__ == "__main__":
    main()
