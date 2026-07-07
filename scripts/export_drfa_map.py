"""Count DRFA activations per LGA and check the name-join against ABS boundaries.

Run: /opt/anaconda3/bin/python3 scripts/export_drfa_map.py
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED, PATHS

EXPORT = DATA_DERIVED.parent / "export"
EXPORT.mkdir(exist_ok=True)

# ── 1. Count DRFA activations per LGA ──────────────────────────────────────
raw = pd.read_csv(PATHS.drfa_locations)

# Filter to LGA-level rows only (exclude SAL suburb/locality rows)
lga_raw = raw[raw["Location_Type"] == "LGA"]
print(f"LGA rows: {len(lga_raw)}, SAL rows: {len(raw) - len(lga_raw)}", flush=True)

lga_col = next(
    c for c in raw.columns if "lga" in c.lower() or "local government" in c.lower()
    or c == "Location_Name"
)
counts = (
    lga_raw.groupby(lga_raw[lga_col].str.strip().str.upper())
    .size()
    .rename("n_activations")
    .reset_index()
    .rename(columns={lga_col: "lga_name"})
)
print(f"Unique DRFA LGAs: {len(counts)}", flush=True)

# ── 2. Load ABS LGA 2025 boundaries ────────────────────────────────────────
print("Loading LGA boundaries ...", flush=True)
bounds = gpd.read_file(PATHS.lga_boundaries)
name_col = next(c for c in bounds.columns if "NAME" in c.upper())
bounds["lga_name"] = bounds[name_col].str.strip().str.upper()

# ── 3. Join check ──────────────────────────────────────────────────────────
matched = counts["lga_name"].isin(bounds["lga_name"])
print(
    f"name join: {matched.mean():.1%} of {len(counts)} DRFA LGAs matched",
    flush=True,
)
if (~matched).any():
    print(
        "unmatched examples:", counts.loc[~matched, "lga_name"].head(15).tolist(),
        flush=True,
    )

# ── 4. Minimal cleanups for known ABS-2025 renames ─────────────────────────
# Moreland (VIC) was renamed Merri-bek; Lower Eyre Peninsula shortened to Lower Eyre.
RENAME_MAP = {
    "MORELAND": "MERRI-BEK",
    "LOWER EYRE PENINSULA": "LOWER EYRE",
}
counts["lga_name"] = counts["lga_name"].replace(RENAME_MAP)

matched_final = counts["lga_name"].isin(bounds["lga_name"])
print(
    f"After rename cleanups: {matched_final.mean():.1%} of {len(counts)} DRFA LGAs matched",
    flush=True,
)
if (~matched_final).any():
    print(
        "Residual unmatched:", counts.loc[~matched_final, "lga_name"].tolist(),
        flush=True,
    )

# ── 5. Export counts ────────────────────────────────────────────────────────
counts.to_csv(EXPORT / "fig_drfa_lga.csv", index=False)
print(f"Wrote {EXPORT / 'fig_drfa_lga.csv'}", flush=True)

# ── 6. Export simplified boundaries ────────────────────────────────────────
# Simplify geometry to ~5 km tolerance so R renders quickly (52 MB shapefile)
bounds_out = bounds[["lga_name", "geometry"]].copy()
bounds_out["geometry"] = bounds_out.geometry.simplify(0.005)
bounds_out.to_file(EXPORT / "lga_boundaries.geojson", driver="GeoJSON")
print(f"Wrote {EXPORT / 'lga_boundaries.geojson'}", flush=True)
