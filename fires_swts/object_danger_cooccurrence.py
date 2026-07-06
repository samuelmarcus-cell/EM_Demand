"""Step 9: do multi-state fire-DANGER days coincide with weather objects (fronts/anticyclones)?
Merges object_presence_daily.csv (from gadi/weather_objects_extract.py) onto the danger frame and
tests, per headline SWT, whether object presence is ELEVATED on multi-state danger days vs that
SWT's other days (month-stratified label permutation, FDR over object x SWT).

Run (real):       /opt/anaconda3/bin/python3 object_danger_cooccurrence.py
Self-test:        /opt/anaconda3/bin/python3 object_danger_cooccurrence.py --synthetic
"""
import argparse, sys, numpy as np, pandas as pd
from statsmodels.stats.multitest import multipletests
sys.path.append("/Users/smar0095/Fires_SWTs/gadi")
from ffdi_core import high_danger_flags, build_danger_daily

DATA = "/Users/smar0095/Fires_SWTs"
HEAD = ["FH-B", "WH-A", "TH-C"]
OBJECTS = ["front850", "front700", "anticyclone", "cyclone"]
N_PERM = 1000

def danger_frame():
    swt = pd.read_csv(f"{DATA}/SWT_climatology_v20260129.csv")
    swt.columns = ["time", "assigned_SWT"][:len(swt.columns)]
    swt["day"] = pd.to_datetime(swt["time"]).dt.normalize(); swt["month"] = swt["day"].dt.month
    swt["regime"] = swt["assigned_SWT"].str.split("-").str[0]
    ffdi = pd.read_csv(f"{DATA}/ffdi_state_daily.csv")
    flags = high_danger_flags(ffdi, q=0.90)
    return build_danger_daily(flags, swt[["day", "month", "assigned_SWT", "regime"]], min_states=2)

def make_synthetic(dd, seed=0):
    """Plant a signal: front850 & anticyclone are MORE present on FH-B multi-state danger days."""
    rng = np.random.default_rng(seed); rows = []
    for s in ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]:
        for o in OBJECTS:
            base = 0.30
            boosted = (dd["assigned_SWT"].eq("FH-B") & dd["multi_day"]
                       & (o in ("front850", "anticyclone")))
            p = np.where(boosted, 0.75, base)
            rows.append(pd.DataFrame({"date": dd["day"], "state": s, "object": o,
                                      "present": (rng.random(len(dd)) < p).astype(int)}))
    return pd.concat(rows, ignore_index=True)

def obj_day_table(pres):
    """Collapse to one row per day: 'object present somewhere over Australia that day'."""
    pres = pres.copy(); pres["date"] = pd.to_datetime(pres["date"]).dt.normalize()
    anyst = pres.groupby(["date", "object"])["present"].max().reset_index()
    wide = anyst.pivot(index="date", columns="object", values="present").reset_index()
    return wide.rename(columns={"date": "day"})

def cooccur_test(merged, seed=0):
    rng = np.random.default_rng(seed); recs = []
    for k in HEAD:
        sub = merged[merged["assigned_SWT"].eq(k)].copy()
        mult = sub["multi_day"].to_numpy(bool)
        if mult.sum() < 10:
            continue
        months = sub["month"].to_numpy()
        strata = [np.where(months == m)[0] for m in np.unique(months)]
        for o in OBJECTS:
            if o not in sub:
                continue
            present = sub[o].to_numpy(float)
            obs = present[mult].mean()
            null = np.empty(N_PERM)
            for b in range(N_PERM):
                pm = mult.copy()
                for idx in strata:                       # permute multi-day labels within month
                    pm[idx] = mult[idx][rng.permutation(idx.size)]
                null[b] = present[pm].mean()
            p = (np.sum(null >= obs) + 1) / (N_PERM + 1)  # one-sided: object elevated on danger days
            recs.append({"SWT": k, "object": o, "n_multi": int(mult.sum()),
                         "rate_danger": obs, "rate_null": null.mean(), "excess": obs - null.mean(), "pval": p})
    res = pd.DataFrame(recs)
    res["sig_fdr"], _, _, _ = multipletests(res["pval"], 0.05, method="fdr_bh")
    return res.sort_values(["SWT", "excess"], ascending=[True, False])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--presence", default=f"{DATA}/object_presence_daily.csv")
    a = ap.parse_args()
    dd = danger_frame()
    if a.synthetic:
        pres = make_synthetic(dd); print("[synthetic] planted: front850 & anticyclone up on FH-B multi-days")
    else:
        pres = pd.read_csv(a.presence)
    merged = dd.merge(obj_day_table(pres), on="day", how="inner")
    print(f"merged days with object data: {len(merged):,} "
          f"({merged['day'].min().date()}..{merged['day'].max().date()})")
    res = cooccur_test(merged)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    print(res.to_string(index=False))
    res.to_csv(f"{DATA}/R/step9_object_cooccurrence.csv", index=False)
    print("\nwrote R/step9_object_cooccurrence.csv")

if __name__ == "__main__":
    main()
