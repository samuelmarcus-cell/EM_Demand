"""Victorian Total Fire Ban loader — district-level declarations 1945–present.

Source: CFA TFB history export (UTF-16-LE, one header line above the column
row). Each row is a declaration with a district list and a datetime span.
Outputs a declaration table and a daily panel: tfb_vic, n_districts,
tfb_whole_state.

Revoked districts are parsed and retained but NOT subtracted from the daily
flag in v0 — a revocation still implies the day began under declared TFB.
"""

import re

import pandas as pd

from scripts.config import PATHS

# Current CFA fire weather districts. Longest-first matching matters:
# "West and South Gippsland" must consume its text before "South West" is
# tried, and "North Central" before "Central".
VIC_DISTRICTS = [
    "West and South Gippsland",
    "Northern Country",
    "East Gippsland",
    "North Central",
    "South West",
    "North East",
    "Wimmera",
    "Central",
    "Mallee",
]

# Pre-2009 legacy district names appearing in the historical record. Matched
# like current districts but kept under their own names (no spatial mapping
# is attempted; n_districts simply counts them).
LEGACY_DISTRICTS = ["North Western", "Eastern"]

_WHOLE_STATE = re.compile(r"whole\s+state", re.IGNORECASE)


def parse_districts(text: str) -> tuple[list, bool]:
    """District string -> (matched districts, whole_state flag).

    Whole-state declarations return all districts. Unmatched leftovers (e.g.
    historical district names) yield an empty match list — callers should
    treat n_districts as a lower bound on those rows.
    """
    if not isinstance(text, str) or not text.strip():
        return [], False
    if _WHOLE_STATE.search(text):
        return list(VIC_DISTRICTS), True
    remaining, found = text, []
    for d in sorted(VIC_DISTRICTS + LEGACY_DISTRICTS, key=len, reverse=True):
        if d.lower() in remaining.lower():
            found.append(d)
            idx = remaining.lower().index(d.lower())
            remaining = remaining[:idx] + remaining[idx + len(d):]
    return found, False


def parse_span(span: str) -> tuple:
    """'11/03/2026 00:01 - 11/03/2026 23:59' -> (start, end) Timestamps."""
    parts = re.split(r"\s*[-–]\s*(?=\d{1,2}/)", str(span).strip(), maxsplit=1)
    start = pd.to_datetime(parts[0].strip(), dayfirst=True)
    end = pd.to_datetime(parts[1].strip(), dayfirst=True) if len(parts) > 1 else start
    return start, end


def load_tfb_declarations(path=None) -> pd.DataFrame:
    """Declaration-level table with parsed districts and datetime spans."""
    df = pd.read_csv(path or PATHS.tfb_history, encoding="utf-16-le", skiprows=1)
    df.columns = [c.strip() for c in df.columns]
    parsed = df["Declared district(s)"].map(parse_districts)
    spans = df["Declared date and time"].map(parse_span)
    out = pd.DataFrame(
        {
            "declared_raw": df["Declared district(s)"],
            "districts": [p[0] for p in parsed],
            "whole_state": [p[1] for p in parsed],
            "revoked_raw": df["Revoked district(s)"],
            "start": [s[0] for s in spans],
            "end": [s[1] for s in spans],
        }
    )
    out["n_districts"] = out["districts"].map(len)
    out["unparsed"] = (out["n_districts"] == 0) & ~out["whole_state"]
    return out


def tfb_daily_panel(declarations: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """Daily panel: date, tfb_vic, n_districts (max across declarations),
    tfb_whole_state."""
    rows = []
    for _, d in declarations.iterrows():
        for day in pd.date_range(d["start"].normalize(), d["end"].normalize(), freq="D"):
            rows.append({"date": day, "n_districts": d["n_districts"], "whole_state": d["whole_state"]})
    daily = pd.DataFrame(rows).groupby("date").agg(
        n_districts=("n_districts", "max"), tfb_whole_state=("whole_state", "any")
    )

    start = pd.Timestamp(start) if start else daily.index.min()
    end = pd.Timestamp(end) if end else daily.index.max()
    idx = pd.date_range(start, end, freq="D", name="date")
    panel = daily.reindex(idx)
    panel["tfb_vic"] = panel["n_districts"].notna()
    panel["n_districts"] = panel["n_districts"].fillna(0).astype(int)
    panel["tfb_whole_state"] = panel["tfb_whole_state"].astype("boolean").fillna(False).astype(bool)
    return panel.reset_index()[["date", "tfb_vic", "n_districts", "tfb_whole_state"]]
