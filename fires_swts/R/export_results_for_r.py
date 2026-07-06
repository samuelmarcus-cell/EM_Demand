"""Recompute the Step 2/4/5 result tables (same logic + seeds as Fires_SWTs.ipynb) and
write tidy CSVs for the R/ggplot figures. Run: /opt/anaconda3/bin/python3 export_results_for_r.py"""
import sys, numpy as np, pandas as pd
from statsmodels.stats.multitest import multipletests
from itertools import combinations
sys.path.append("/Users/smar0095/Fires_SWTs/gadi")
from ffdi_core import high_danger_flags, build_danger_daily

DATA = "/Users/smar0095/Fires_SWTs"
OUT  = "/Users/smar0095/Fires_SWTs/R"
MIN_AREA_HA = 1000; MIN_STATES = 2; CAP_DAYS = 60; N_BOOT = 1000
STATE_FOLD = {"ACT": "NSW"}; REGIME_PREFIXES = ["WCT","COL","WH","CH","EH","TH","FH","AM"]
def to_regime(s):
    if isinstance(s, str):
        for p in REGIME_PREFIXES:
            if s.startswith(p): return p
    return "Other"

swt = pd.read_csv(f"{DATA}/SWT_climatology_v20260129.csv", parse_dates=["time"] if False else None)
swt = pd.read_csv(f"{DATA}/SWT_climatology_v20260129.csv")
swt.columns = ["time", "assigned_SWT"][:len(swt.columns)]
swt["time"] = pd.to_datetime(swt["time"])
swt["day"] = swt["time"].dt.normalize(); swt["month"] = swt["time"].dt.month
swt["regime"] = swt["assigned_SWT"].apply(to_regime)
# AUDIT FIX (period-matching): restrict whole analysis to the FFDI overlap (danger exists only
# 1979-2023) so fire & danger RR / pairs are computed on a common period.
_ffd = pd.to_datetime(pd.read_csv(f"{DATA}/ffdi_state_daily.csv", usecols=["date"])["date"])
ANALYSIS_LO, ANALYSIS_HI = max(swt["day"].min(), _ffd.min()), min(swt["day"].max(), _ffd.max())
swt = swt[(swt["day"] >= ANALYSIS_LO) & (swt["day"] <= ANALYSIS_HI)].reset_index(drop=True)
print(f"ANALYSIS PERIOD (FFDI overlap): {ANALYSIS_LO.date()} -> {ANALYSIS_HI.date()}")
swt_min, swt_max = swt["day"].min(), swt["day"].max()

df = pd.read_csv(f"{DATA}/bushfire_events_geo.csv", parse_dates=["ignition_date","extinguish_date"])
df["state"] = df["state"].replace(STATE_FOLD)
AB = [0,100,1_000,5_000,20_000,100_000,np.inf]; AL = ["<100","100-1k","1k-5k","5k-20k","20k-100k",">100k"]
df["abin"] = pd.cut(df["area_ha"], bins=AB, labels=AL)
dr = (df["extinguish_date"] - df["ignition_date"]).dt.days
clean = df["extinguish_date"].notna() & (dr > 0) & (dr <= 365) & (df["area_ha"] > 0)
bm = dr[clean].groupby(df.loc[clean,"abin"], observed=True).median()
dur_map = {l: int(np.clip(round(bm[l]),1,CAP_DAYS)) for l in bm.index}
large = df[(~df["is_jan1"]) & (df["area_ha"]>=MIN_AREA_HA) &
           (df["ignition_date"]>=swt_min) & (df["ignition_date"]<=swt_max)].copy().reset_index(drop=True)
large["dur"] = large["abin"].map(dur_map).astype(int)
dur = large["dur"].values; ig = large["ignition_date"].values.astype("datetime64[D]")
offs = np.concatenate([np.arange(d) for d in dur]).astype("timedelta64[D]")

# ---- Step 2: multi-state RR (regime + SWT) ----
sd = pd.DataFrame({"day": np.repeat(ig,dur)+offs, "state": np.repeat(large["state"].values,dur)}).drop_duplicates()
per = sd.groupby("day")["state"].nunique().rename("n_states")
daily = swt[["day","month","assigned_SWT","regime"]].merge(per, on="day", how="left")
daily["n_states"] = daily["n_states"].fillna(0).astype(int)
daily["fire_day"] = daily["n_states"]>=1; daily["multi_day"] = daily["n_states"]>=MIN_STATES

def simultaneity_rr(level_col, fdr=False, seed=0, n_boot=N_BOOT, daily_df=None):
    d = daily if daily_df is None else daily_df; codes, items = pd.factorize(d[level_col], sort=True); K=len(items)
    month = d["month"].values; mm = d["multi_day"].values
    mfrac = np.bincount(codes[mm], minlength=K)/mm.sum()
    g = d.groupby(level_col, observed=True)
    desc = pd.DataFrame({"n_days":g.size().reindex(items),"n_fire":g["fire_day"].sum().reindex(items),
                         "n_multi":g["multi_day"].sum().reindex(items)})
    desc["p_multi"]=desc["n_multi"]/desc["n_days"]; desc["sync"]=desc["n_multi"]/desc["n_fire"].replace(0,np.nan)
    rng=np.random.default_rng(seed); midx={m:np.where(month==m)[0] for m in np.unique(month)}
    mc=pd.Series(month[mm]).value_counts().to_dict(); boot=np.empty((n_boot,K))
    for i in range(n_boot):
        s=np.concatenate([codes[rng.choice(midx[m],size=n,replace=True)] for m,n in mc.items()])
        bg=np.bincount(s,minlength=K)/s.size
        with np.errstate(divide="ignore",invalid="ignore"): boot[i]=np.where(bg>0,mfrac/bg,np.nan)
    rr=np.nanmean(boot,axis=0); lo=np.nanpercentile(boot,2.5,axis=0); hi=np.nanpercentile(boot,97.5,axis=0)
    frac=np.where(rr>1,np.nanmean(boot<=1,axis=0),np.nanmean(boot>=1,axis=0)); pv=np.minimum(2*frac,1.0)
    res=desc.reset_index().rename(columns={"index":level_col})
    res["RR_mean"],res["CI_low"],res["CI_high"],res["pval"]=rr,lo,hi,pv
    if fdr: res["sig_fdr"],_,_,_=multipletests(np.clip(res["pval"],1e-4,1),0.05,method="fdr_bh")
    return res.sort_values("RR_mean",ascending=False)

simultaneity_rr("regime").to_csv(f"{OUT}/regime_rr.csv", index=False)
simultaneity_rr("assigned_SWT", fdr=True).to_csv(f"{OUT}/swt_rr.csv", index=False)

# ---- Step 4: spatial spread (distance) with fire_key surrogate fix ----
large["fire_key"] = large["fire_id"].where(large["fire_id"].notna(), "na_"+large.index.astype(str))
active = pd.DataFrame({"day":np.repeat(ig,dur)+offs,"fire_key":np.repeat(large["fire_key"].values,dur),
    "lat":np.repeat(large["lat"].values,dur),"lon":np.repeat(large["lon"].values,dur),
    "state":np.repeat(large["state"].values,dur)})
fire_day = active.groupby(["day","fire_key"],as_index=False).agg(lat=("lat","mean"),lon=("lon","mean"),state=("state","first"))
R=6371.0
def mpw(lat,lon):
    la,lo=np.radians(lat),np.radians(lon); dla=la[:,None]-la[None,:]; dlo=lo[:,None]-lo[None,:]
    a=np.sin(dla/2)**2+np.cos(la)[:,None]*np.cos(la)[None,:]*np.sin(dlo/2)**2
    return (2*R*np.arcsin(np.sqrt(np.clip(a,0,1))))[np.triu_indices(len(lat),k=1)].mean()
gg=fire_day.groupby("day"); sync=gg.agg(n_fires=("fire_key","size"),n_states=("state","nunique"))
md=sync.index[sync["n_fires"]>=2]
dist={d:mpw(g["lat"].values,g["lon"].values) for d,g in fire_day[fire_day["day"].isin(md)].groupby("day")}
sync["mean_dist_km"]=sync.index.map(dist)
sync=sync.reset_index().merge(swt[["day","month","assigned_SWT"]],on="day",how="left")
sync2=sync[(sync["n_fires"]>=2)&sync["assigned_SWT"].notna()].copy()

def spread_permutation(value_col, dsync, n_bins=5, B=N_BOOT, seed=0):
    d=dsync.dropna(subset=[value_col,"assigned_SWT"]).reset_index(drop=True); val=d[value_col].to_numpy(float)
    codes,items=pd.factorize(d["assigned_SWT"],sort=True); K=len(items); n_k=np.bincount(codes,minlength=K).astype(float)
    nb=pd.qcut(d["n_fires"],q=n_bins,duplicates="drop"); strat=d["month"].astype(str)+"|"+nb.astype(str)
    strata=[np.where(strat.values==s)[0] for s in strat.unique()]
    obs=np.bincount(codes,weights=val,minlength=K)/np.where(n_k>0,n_k,np.nan); rng=np.random.default_rng(seed); boot=np.empty((B,K))
    for b in range(B):
        pm=codes.copy()
        for idx in strata: pm[idx]=codes[idx][rng.permutation(idx.size)]
        boot[b]=np.bincount(pm,weights=val,minlength=K)/np.where(n_k>0,n_k,np.nan)
    nmean=np.nanmean(boot,axis=0); ge=np.mean(boot>=obs,axis=0); le=np.mean(boot<=obs,axis=0)
    res=pd.DataFrame({"assigned_SWT":items,"n_days":n_k.astype(int),"obs":obs,"null_mean":nmean,
        "excess":obs-nmean,"pval":np.minimum(2*np.minimum(ge,le),1.0)})
    res["sig_fdr"],_,_,_=multipletests(np.clip(res["pval"],1e-4,1),0.05,method="fdr_bh")
    return res.sort_values("excess",ascending=False)
spread_permutation("mean_dist_km", sync2).to_csv(f"{OUT}/step4_distance.csv", index=False)

# ---- Step 5: region-pair co-occurrence (headline SWTs) ----
STATES=["NSW","VIC","QLD","SA","WA","TAS","NT"]
sdall=pd.DataFrame({"day":np.repeat(ig,dur)+offs,"state":np.repeat(large["state"].values,dur)}).drop_duplicates()
burn=sdall.assign(v=1).pivot_table(index="day",columns="state",values="v",fill_value=0).reindex(columns=STATES,fill_value=0)
burn["n_states"]=burn.sum(axis=1)
burn=burn.reset_index().merge(swt[["day","month","assigned_SWT"]],on="day",how="left")
pair_days=burn[(burn["n_states"]>=2)&burn["assigned_SWT"].notna()].copy()
PAIRS=list(combinations(STATES,2)); Sarr=pair_days[STATES].to_numpy()
pidx=[(STATES.index(a),STATES.index(b)) for a,b in PAIRS]
M=np.stack([Sarr[:,i]*Sarr[:,j] for i,j in pidx],axis=1).astype(float)
d=pair_days.reset_index(drop=True); codes,items=pd.factorize(d["assigned_SWT"],sort=True); K,P=len(items),len(PAIRS)
n_k=np.bincount(codes,minlength=K).astype(float)
strat=d["month"].astype(str)+"|"+d["n_states"].astype(str); strata=[np.where(strat.values==s)[0] for s in strat.unique()]
obs=np.zeros((K,P)); np.add.at(obs,codes,M); obs/=n_k[:,None]
rng=np.random.default_rng(0); ge=np.zeros((K,P)); le=np.zeros((K,P)); ssum=np.zeros((K,P))
for b in range(N_BOOT):
    pm=codes.copy()
    for idx in strata: pm[idx]=codes[idx][rng.permutation(idx.size)]
    rate=np.zeros((K,P)); np.add.at(rate,pm,M); rate/=n_k[:,None]; ge+=rate>=obs; le+=rate<=obs; ssum+=rate
nm=ssum/N_BOOT; pv=np.minimum(2*np.minimum(ge,le)/N_BOOT,1.0)
rows=[(items[si],f"{PAIRS[pi][0]}-{PAIRS[pi][1]}",int(n_k[si]),obs[si,pi],nm[si,pi],obs[si,pi]-nm[si,pi],pv[si,pi])
      for si in range(K) for pi in range(P)]
pair_res=pd.DataFrame(rows,columns=["assigned_SWT","pair","n_days","obs","null_mean","excess","pval"])
HEAD=["FH-B","WH-A","TH-C","WCT-B"]; sub=pair_res[pair_res.assigned_SWT.isin(HEAD)].copy()
sub["sig_fdr"],_,_,_=multipletests(np.clip(sub["pval"],1e-4,1),0.05,method="fdr_bh")
sub.to_csv(f"{OUT}/step5_pairs.csv", index=False)

# ---- Step 8: DANGER multi-state RR + DANGER region-pairs (BARRA-R2 FFDI) ----
ffdi = pd.read_csv(f"{DATA}/ffdi_state_daily.csv")
flags = high_danger_flags(ffdi, q=0.90)
ddaily = build_danger_daily(flags, swt[["day","month","assigned_SWT","regime"]], min_states=MIN_STATES)
# AUDIT regression guard: fire (daily) and danger (ddaily) MUST share one period for a fair comparison
assert daily["day"].min() == ddaily["day"].min() and daily["day"].max() == ddaily["day"].max(), \
    f"period mismatch: fire {daily['day'].min().date()}..{daily['day'].max().date()} vs danger {ddaily['day'].min().date()}..{ddaily['day'].max().date()}"
simultaneity_rr("assigned_SWT", fdr=True, daily_df=ddaily).to_csv(f"{OUT}/swt_danger_rr.csv", index=False)

hot = flags[flags["hot"]].assign(v=1)
burnd = hot.pivot_table(index="date",columns="state",values="v",fill_value=0).reindex(columns=STATES,fill_value=0)
burnd["n_states"]=burnd.sum(axis=1)
burnd=burnd.reset_index().rename(columns={"date":"day"}); burnd["day"]=pd.to_datetime(burnd["day"])
burnd=burnd.merge(swt[["day","month","assigned_SWT"]],on="day",how="left")
pdays=burnd[(burnd["n_states"]>=2)&burnd["assigned_SWT"].notna()].copy()
Sd=pdays[STATES].to_numpy(); Md=np.stack([Sd[:,i]*Sd[:,j] for i,j in pidx],axis=1).astype(float)
dd=pdays.reset_index(drop=True); cz,iz=pd.factorize(dd["assigned_SWT"],sort=True); Kz=len(iz)
nz=np.bincount(cz,minlength=Kz).astype(float)
stz=dd["month"].astype(str)+"|"+dd["n_states"].astype(str); strataz=[np.where(stz.values==s)[0] for s in stz.unique()]
obz=np.zeros((Kz,P)); np.add.at(obz,cz,Md); obz/=nz[:,None]
rng=np.random.default_rng(0); gez=np.zeros((Kz,P)); lez=np.zeros((Kz,P)); ssz=np.zeros((Kz,P))
for b in range(N_BOOT):
    pm=cz.copy()
    for idx in strataz: pm[idx]=cz[idx][rng.permutation(idx.size)]
    rate=np.zeros((Kz,P)); np.add.at(rate,pm,Md); rate/=nz[:,None]; gez+=rate>=obz; lez+=rate<=obz; ssz+=rate
nmz=ssz/N_BOOT; pvz=np.minimum(2*np.minimum(gez,lez)/N_BOOT,1.0)
rowz=[(iz[si],f"{PAIRS[pi][0]}-{PAIRS[pi][1]}",int(nz[si]),obz[si,pi],nmz[si,pi],obz[si,pi]-nmz[si,pi],pvz[si,pi])
      for si in range(Kz) for pi in range(P)]
pres=pd.DataFrame(rowz,columns=["assigned_SWT","pair","n_days","obs","null_mean","excess","pval"])
subz=pres[pres.assigned_SWT.isin(HEAD)].copy()
subz["sig_fdr"],_,_,_=multipletests(np.clip(subz["pval"],1e-4,1),0.05,method="fdr_bh")
subz.to_csv(f"{OUT}/step8_danger_pairs.csv", index=False)

print("wrote: regime_rr, swt_rr, step4_distance, step5_pairs, swt_danger_rr, step8_danger_pairs ->", OUT)
