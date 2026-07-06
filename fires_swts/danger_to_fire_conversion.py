"""Step 10: danger->fire CONVERSION by SWT (ignition-based + season-controlled).
Of the multi-state DANGER days under each SWT, how often did a large fire actually break out -
MORE than that SWT's seasonal timing alone would imply?

Ignition-based (not persistent footprints) removes the persistence inflation; a month-stratified
permutation removes the "this SWT just happens in peak summer" confound. In-hand data only.

Run: /opt/anaconda3/bin/python3 danger_to_fire_conversion.py
"""
import sys, numpy as np, pandas as pd
from statsmodels.stats.multitest import multipletests
sys.path.append("/Users/smar0095/Fires_SWTs/gadi")
from ffdi_core import high_danger_flags, build_danger_daily

DATA = "/Users/smar0095/Fires_SWTs"
MIN_AREA_HA, MIN_STATES, N_PERM = 1000, 2, 2000
HEAD = ["FH-B", "WH-A", "TH-C", "WCT-B"]
STATE_FOLD = {"ACT": "NSW"}; REGIME_PREFIXES = ["WCT","COL","WH","CH","EH","TH","FH","AM"]
def to_regime(s):
    if isinstance(s, str):
        for p in REGIME_PREFIXES:
            if s.startswith(p): return p
    return "Other"

# ---- SWT (one type per day) ----
swt = pd.read_csv(f"{DATA}/SWT_climatology_v20260129.csv")
swt.columns = ["time", "assigned_SWT"][:len(swt.columns)]
swt["time"] = pd.to_datetime(swt["time"])
swt["day"] = swt["time"].dt.normalize(); swt["month"] = swt["time"].dt.month
swt["regime"] = swt["assigned_SWT"].apply(to_regime)
swt_min, swt_max = swt["day"].min(), swt["day"].max()

# ---- IGNITION-based fire: distinct states with a large-fire IGNITION that day ----
df = pd.read_csv(f"{DATA}/bushfire_events_geo.csv", parse_dates=["ignition_date","extinguish_date"])
df["state"] = df["state"].replace(STATE_FOLD)
large = df[(~df["is_jan1"]) & (df["area_ha"] >= MIN_AREA_HA) &
           (df["ignition_date"] >= swt_min) & (df["ignition_date"] <= swt_max)].copy()
large["day"] = large["ignition_date"].dt.normalize()
ign = large.groupby("day")["state"].nunique().rename("n_ign_states")
fire = swt[["day", "assigned_SWT", "month"]].merge(ign, on="day", how="left")
fire["n_ign_states"] = fire["n_ign_states"].fillna(0).astype(int)
fire["ig_any"]   = fire["n_ign_states"] >= 1          # any large fire started that day
fire["ig_multi"] = fire["n_ign_states"] >= MIN_STATES # >=2 states started a large fire that day

# ---- DANGER multi-state day frame ----
ffdi = pd.read_csv(f"{DATA}/ffdi_state_daily.csv")
flags = high_danger_flags(ffdi, q=0.90)
dd = build_danger_daily(flags, swt[["day","month","assigned_SWT","regime"]], min_states=MIN_STATES)
dang = dd[["day","assigned_SWT","multi_day"]].rename(columns={"multi_day":"dang_multi"})

# ---- merge, restrict to FFDI overlap, keep only multi-state DANGER days ----
lo, hi = pd.to_datetime(ffdi["date"]).min(), pd.to_datetime(ffdi["date"]).max()
m = fire.merge(dang, on=["day","assigned_SWT"], how="inner")
m = m[(m["day"] >= lo) & (m["day"] <= hi)]
g = m[m["dang_multi"]].reset_index(drop=True)
print(f"overlap {lo.date()}..{hi.date()}; multi-state danger days = {len(g):,}")
print(f"overall P(any large ignition | multi-danger) = {g['ig_any'].mean():.3f} | "
      f"P(>=2-state ignition | multi-danger) = {g['ig_multi'].mean():.3f}\n")

def season_controlled(outcome):
    """Per-SWT conversion among multi-danger days vs month-stratified null (shuffle outcome within
    month). lift = observed / expected-given-its-season; p two-sided; FDR over SWTs with n>=20."""
    y = g[outcome].to_numpy(float); months = g["month"].to_numpy()
    codes, items = pd.factorize(g["assigned_SWT"], sort=True); K = len(items)
    n_k = np.bincount(codes, minlength=K).astype(float)
    obs = np.bincount(codes, weights=y, minlength=K) / np.where(n_k > 0, n_k, np.nan)
    strata = [np.where(months == mo)[0] for mo in np.unique(months)]
    rng = np.random.default_rng(0); boot = np.empty((N_PERM, K))
    for b in range(N_PERM):
        ys = y.copy()
        for idx in strata: ys[idx] = y[idx][rng.permutation(idx.size)]
        boot[b] = np.bincount(codes, weights=ys, minlength=K) / np.where(n_k > 0, n_k, np.nan)
    exp = np.nanmean(boot, axis=0)
    ge = np.mean(boot >= obs, axis=0); le = np.mean(boot <= obs, axis=0)
    res = pd.DataFrame({"assigned_SWT": items, "n_danger_multi": n_k.astype(int),
                        "conversion": obs, "expected_season": exp,
                        "lift": obs / np.where(exp > 0, exp, np.nan),
                        "pval": np.minimum(2*np.minimum(ge, le), 1.0)})
    res = res[res["n_danger_multi"] >= 20].copy()
    res["sig_fdr"], _, _, _ = multipletests(res["pval"], 0.05, method="fdr_bh")
    return res.sort_values("lift", ascending=False)

pd.set_option("display.float_format", lambda x: f"{x:.3f}")
for outcome, label in [("ig_any", "ANY large ignition"), ("ig_multi", ">=2-state ignition")]:
    res = season_controlled(outcome)
    print(f"=== Conversion to {label} | multi-state danger, season-controlled (FDR) ===")
    print(res.to_string(index=False))
    print(f"  -> elevated beyond season & FDR-sig: " +
          (", ".join(f"{r.assigned_SWT}({r.lift:.2f})" for r in res[(res.lift>1)&res.sig_fdr].itertuples()) or "none"))
    print(f"  -> headline SWTs: " +
          ", ".join(f"{r.assigned_SWT} lift={r.lift:.2f} p={r.pval:.3f}"
                    for r in res[res.assigned_SWT.isin(HEAD)].itertuples()) + "\n")
    res.to_csv(f"{DATA}/R/step10_conversion_{outcome}.csv", index=False)
print("wrote R/step10_conversion_ig_any.csv, R/step10_conversion_ig_multi.csv")
