"""Build the state×hazard load panel and daily summary.

Blocking face-validity gate (spec §4): Black Summer must show NSW+VIC
simultaneously high on fire; TC Yasi must flag QLD under tc, not fire.
Exits 1 on gate failure — nothing downstream is interpretable then.
"""

import sys

import pandas as pd

from scripts.config import DATA_DERIVED
from scripts.fire_association import load_polygon_windows
from scripts.loaders.drfa_activations import load_drfa_locations
from scripts.loaders.tc_besttrack import load_tc_tracks
from scripts.state_panel import (
    HIGH_LOAD_THRESHOLD,
    assemble_panel,
    daily_summary,
    drfa_state_layer,
    load_state_geoms,
    state_fire_layer,
    state_tc_layer,
    tc_state_daily,
)

print("Building per-state fire layer (tier 3 = burn windows) ...", flush=True)
metrics = pd.read_parquet(DATA_DERIVED / "demand_metrics_daily.parquet")
fire = state_fire_layer(metrics, load_polygon_windows())

print("Building tc layer (300 km, + 200/400 km sensitivity) ...", flush=True)
tracks = load_tc_tracks()
states_gdf = load_state_geoms()
tc = state_tc_layer(tc_state_daily(tracks, states_gdf, radius_km=300.0))
for r in (200.0, 400.0):
    alt = state_tc_layer(tc_state_daily(tracks, states_gdf, radius_km=r))
    tc[f"state_tc_r{int(r)}"] = alt["state_tc"].values  # same (date,state) order

print("Building drfa impact layer ...", flush=True)
drfa = drfa_state_layer(load_drfa_locations())

panel = assemble_panel(fire, tc, drfa)
for r in (200, 400):
    panel[f"pct_r{r}"] = pd.NA
    tc_mask = panel["layer"] == "tc"
    # Key TC radius sensitivity by (date, state) to ensure correct alignment
    tc_lookup = tc.set_index(["date", "state"])[f"state_tc_r{r}"]
    panel_tc_idx = pd.MultiIndex.from_arrays(
        [panel.loc[tc_mask, "date"], panel.loc[tc_mask, "state"]],
        names=["date", "state"]
    )
    panel.loc[tc_mask, f"pct_r{r}"] = tc_lookup.loc[panel_tc_idx].values

summary = daily_summary(panel)
panel.to_parquet(DATA_DERIVED / "state_hazard_panel.parquet")
summary.reset_index().rename(columns={"index": "date"}).to_parquet(
    DATA_DERIVED / "state_hazard_summary.parquet")
print(f"Panel rows: {len(panel):,}; summary days: {len(summary):,}", flush=True)

# ---- face-validity gate (blocking) ----
def high_states(layer, days):
    sub = panel[(panel.layer == layer) & panel.date.isin(pd.to_datetime(days))]
    return set(sub[sub.pct >= HIGH_LOAD_THRESHOLD].state)

bs_days = pd.date_range("2019-12-28", "2020-01-06", freq="D")
bs_fire = high_states("fire", bs_days)
yasi_days = ["2011-02-02", "2011-02-03"]
yasi_tc = high_states("tc", yasi_days)
yasi_fire = high_states("fire", yasi_days)

print("\n=== Face-validity gate ===")
print(f"Black Summer 2019-12-28..2020-01-06, states high on fire: {sorted(bs_fire)}")
print(f"TC Yasi 2011-02-02/03, states high on tc: {sorted(yasi_tc)}")
print(f"TC Yasi 2011-02-02/03, states high on fire: {sorted(yasi_fire)}")

ok = True
if not {"NSW", "VIC"} <= bs_fire:
    print("FAIL: Black Summer must show NSW+VIC high on fire"); ok = False
if "QLD" not in yasi_tc:
    print("FAIL: Yasi must flag QLD under tc"); ok = False
if "QLD" in yasi_fire:
    print("FAIL: Yasi flagged QLD under FIRE — attribution is wrong"); ok = False
print("GATE PASSED" if ok else "GATE FAILED")
sys.exit(0 if ok else 1)
