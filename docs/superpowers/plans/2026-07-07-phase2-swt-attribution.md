# Phase 2 SWT Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quantify which synoptic weather types (SWTs) are over-represented on high-demand days: per-SWT relative risk with month-matched baselines and moving-block bootstrap confidence intervals.

**Architecture:** Fill in the existing stub `scripts/phase2_attribution/swt_attribution.py`. `attach_swt` joins the daily SWT classification onto the Phase 1 demand panel; `demand_swt_rr` computes RR = P(high-demand | SWT) / P(high-demand | month-matched baseline) with bootstrap CIs; a thin runner writes the RR table to `data/derived/`. All logic is locally testable with synthetic data.

**Tech Stack:** pandas, numpy; pytest. No Gadi needed — the SWT climatology CSV is already local.

## Global Constraints

- Local python is `/opt/anaconda3/bin/python3`. Never pip install.
- SWT climatology: `scripts/config.py::PATHS.swt_climatology` → `~/Fires_SWTs/SWT_climatology_v20260129.csv`. Format: header `time,assigned_SWT`; daily rows from **1952-01-01**; SWT labels look like `WH-A`, `TH-A` (~26,900 rows). Verify the header before coding against it.
- Demand panel: `data/derived/demand_daily_panel.parquet` (Phase 1 output of `scripts/run_dli.py`), columns include `date`, `dli`, `confidence_tier`, subindices `sub_fire/sub_tc/sub_drfa/sub_tfb`, and `n_components_available`.
- "High-demand day" = `dli` at or above the 95th percentile **within its confidence tier** (tiers have different component sets; pooled thresholds would just select Tier-1 days).
- Baselines must be **month-matched**: SWT frequencies are strongly seasonal and so is demand; raw RR without month matching rediscovers "summer is busy".
- Daily series are autocorrelated (fire seasons persist for weeks) → naive iid bootstrap understates CI width. Use a **moving-block bootstrap** (block length 30 days, 1000 resamples).
- Keep all existing tests green: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`.
- Commit after each task; trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`; push after each commit.
- Plain-language updates to the user after each task. Context they care about: the predecessor project (Fires_SWTs) found blocking-high SWTs give RR up to 2.13 for multi-state fire *danger* — the scientific question here is whether the same regimes drive *demand*.

---

### Task 1: `attach_swt`

**Files:**
- Modify: `scripts/phase2_attribution/swt_attribution.py`
- Test: `tests/test_swt_attribution.py`

**Interfaces:**
- Produces: `attach_swt(panel: pd.DataFrame, swt_csv=None) -> pd.DataFrame` — the panel with a new `swt_type` string column (NaN where no SWT classification exists for that date). `swt_csv` defaults to `PATHS.swt_climatology`.

- [ ] **Step 1: Write the failing test**

```python
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phase2_attribution.swt_attribution import attach_swt


def _panel(start="2000-01-01", periods=6):
    dates = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({
        "date": dates,
        "dli": np.linspace(0.1, 0.9, periods),
        "confidence_tier": 2,
    })


def test_attach_swt(tmp_path):
    csv = tmp_path / "swt.csv"
    csv.write_text(
        "time,assigned_SWT\n"
        "2000-01-01,WH-A\n"
        "2000-01-02,TH-A\n"
        "2000-01-03,WH-A\n"
    )
    out = attach_swt(_panel(), csv)
    assert len(out) == 6  # left join: panel rows preserved
    assert out.loc[out.date == "2000-01-01", "swt_type"].item() == "WH-A"
    assert out.loc[out.date == "2000-01-05", "swt_type"].isna().all()
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_swt_attribution.py -q`
Expected: FAIL with `NotImplementedError: Phase 2`

- [ ] **Step 3: Implement.** Replace the `attach_swt` stub body:

```python
def attach_swt(panel, swt_csv=None):
    from scripts.config import PATHS

    swt = pd.read_csv(swt_csv or PATHS.swt_climatology)
    swt["date"] = pd.to_datetime(swt["time"]).dt.normalize()
    swt = swt.rename(columns={"assigned_SWT": "swt_type"})[["date", "swt_type"]]
    swt = swt.drop_duplicates("date")
    return panel.merge(swt, on="date", how="left")
```

Add `import pandas as pd` at module top (the stub currently has no imports).

- [ ] **Step 4: Run tests** — `/opt/anaconda3/bin/python3 -m pytest tests/ -q` — all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/phase2_attribution/swt_attribution.py tests/test_swt_attribution.py
git commit -m "Implement SWT join onto demand panel"
git push
```

---

### Task 2: high-demand flag + point-estimate RR

**Files:**
- Modify: `scripts/phase2_attribution/swt_attribution.py`
- Test: `tests/test_swt_attribution.py`

**Interfaces:**
- Produces:
  - `flag_high_demand(panel, threshold_pct=0.95) -> pd.Series` (bool, True where `dli >=` the within-`confidence_tier` quantile; False where dli is NaN)
  - `swt_rr_point(df) -> pd.DataFrame` with columns `swt_type, n_days, n_high, rr` — where `df` has `date, swt_type, high` and RR uses a month-matched baseline:

    RR(swt) = [n_high(swt) / n_days(swt)] / [Σ_m n_days(swt, m) · P(high | month=m) / n_days(swt)]

    i.e. observed high-rate under the SWT divided by the high-rate expected if the SWT had no effect beyond its monthly occurrence pattern.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_swt_attribution.py`:

```python
from scripts.phase2_attribution.swt_attribution import flag_high_demand, swt_rr_point


def test_flag_high_demand_within_tier():
    dates = pd.date_range("2000-01-01", periods=40, freq="D")
    panel = pd.DataFrame({
        "date": dates,
        "dli": list(np.linspace(0, 1, 20)) * 2,
        "confidence_tier": [2] * 20 + [1] * 20,
    })
    high = flag_high_demand(panel, threshold_pct=0.95)
    # each tier contributes its own top ~5% (the max value at least)
    assert high[panel.confidence_tier == 2].sum() >= 1
    assert high[panel.confidence_tier == 1].sum() >= 1


def test_swt_rr_point_month_matched():
    # Jan: base high-rate 0.5. SWT "A" only in Jan, always high -> RR 2.
    # SWT "B" only in Jan, never high -> RR 0. Month matching means the
    # July-only SWT "C" (high-rate 0 in a month whose base rate is 0)
    # yields NaN, not a spurious signal.
    rows = []
    for d in pd.date_range("2000-01-01", "2000-01-10"):
        rows.append({"date": d, "swt_type": "A" if d.day <= 5 else "B",
                     "high": d.day <= 5})
    for d in pd.date_range("2000-07-01", "2000-07-05"):
        rows.append({"date": d, "swt_type": "C", "high": False})
    out = swt_rr_point(pd.DataFrame(rows)).set_index("swt_type")
    assert out.loc["A", "rr"] == 2.0
    assert out.loc["B", "rr"] == 0.0
    assert np.isnan(out.loc["C", "rr"])
    assert out.loc["A", "n_days"] == 5 and out.loc["A", "n_high"] == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_swt_attribution.py -q`
Expected: FAIL with `ImportError: cannot import name 'flag_high_demand'`

- [ ] **Step 3: Implement**

```python
def flag_high_demand(panel, threshold_pct=0.95):
    thresh = panel.groupby("confidence_tier")["dli"].transform(
        lambda s: s.quantile(threshold_pct)
    )
    return (panel["dli"] >= thresh).fillna(False)


def swt_rr_point(df):
    d = df.dropna(subset=["swt_type"]).copy()
    d["month"] = d["date"].dt.month
    p_high_month = d.groupby("month")["high"].mean()
    rows = []
    for swt, g in d.groupby("swt_type"):
        n_days = len(g)
        n_high = int(g["high"].sum())
        expected = (g["month"].map(p_high_month)).mean()
        rr = (n_high / n_days) / expected if expected > 0 else float("nan")
        rows.append({"swt_type": swt, "n_days": n_days, "n_high": n_high, "rr": rr})
    return pd.DataFrame(rows).sort_values("rr", ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: Run tests** — `/opt/anaconda3/bin/python3 -m pytest tests/ -q` — all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/phase2_attribution/swt_attribution.py tests/test_swt_attribution.py
git commit -m "Add high-demand flag and month-matched SWT relative risk"
git push
```

---

### Task 3: moving-block bootstrap CIs + `demand_swt_rr`

**Files:**
- Modify: `scripts/phase2_attribution/swt_attribution.py`
- Test: `tests/test_swt_attribution.py`

**Interfaces:**
- Produces: `demand_swt_rr(panel, dli_threshold_pct=0.95, n_boot=1000, block_days=30, seed=0) -> pd.DataFrame` with columns `swt_type, n_days, n_high, rr, rr_lo, rr_hi` (2.5/97.5 bootstrap percentiles). Panel must already carry `swt_type` (from `attach_swt`). Rows with NaN dli or NaN swt_type are excluded.

Bootstrap scheme: resample the *daily time series* in contiguous blocks of `block_days` (circular moving-block: start indices drawn uniformly, wrap allowed via `np.take(..., mode="wrap")` on positional indices), recompute `swt_rr_point` on each resample, take percentile CIs per SWT. Blocks preserve the multi-week persistence of both fire seasons and synoptic regimes.

- [ ] **Step 1: Write the failing test**

```python
from scripts.phase2_attribution.swt_attribution import demand_swt_rr


def test_demand_swt_rr_columns_and_ci_order():
    rng = np.random.default_rng(0)
    dates = pd.date_range("2000-01-01", periods=400, freq="D")
    swt = rng.choice(["A", "B"], size=400)
    dli = rng.uniform(0, 0.8, size=400)
    dli[swt == "A"] += 0.2  # A days genuinely run hotter
    panel = pd.DataFrame({
        "date": dates, "dli": dli, "confidence_tier": 2, "swt_type": swt,
    })
    out = demand_swt_rr(panel, n_boot=50, block_days=10, seed=1)
    assert list(out.columns) == ["swt_type", "n_days", "n_high", "rr", "rr_lo", "rr_hi"]
    a = out.set_index("swt_type").loc["A"]
    assert a["rr_lo"] <= a["rr"] <= a["rr_hi"]
    assert a["rr"] > 1.0  # enriched SWT detected


def test_demand_swt_rr_reproducible():
    dates = pd.date_range("2000-01-01", periods=200, freq="D")
    panel = pd.DataFrame({
        "date": dates,
        "dli": np.tile(np.linspace(0, 1, 20), 10),
        "confidence_tier": 2,
        "swt_type": np.tile(["A"] * 10 + ["B"] * 10, 10),
    })
    o1 = demand_swt_rr(panel, n_boot=20, block_days=10, seed=7)
    o2 = demand_swt_rr(panel, n_boot=20, block_days=10, seed=7)
    pd.testing.assert_frame_equal(o1, o2)
```

- [ ] **Step 2: Run to verify failure**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_swt_attribution.py -q`
Expected: FAIL — `demand_swt_rr` still raises `NotImplementedError`.

- [ ] **Step 3: Implement.** Replace the `demand_swt_rr` stub:

```python
import numpy as np


def demand_swt_rr(panel, dli_threshold_pct=0.95, n_boot=1000, block_days=30, seed=0):
    d = panel.dropna(subset=["dli", "swt_type"]).sort_values("date").reset_index(drop=True)
    d["high"] = flag_high_demand(d, dli_threshold_pct)
    base = d[["date", "swt_type", "high"]]
    point = swt_rr_point(base)

    rng = np.random.default_rng(seed)
    n = len(base)
    n_blocks = int(np.ceil(n / block_days))
    boot_rrs = {s: [] for s in point["swt_type"]}
    for _ in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        pos = (starts[:, None] + np.arange(block_days)[None, :]).ravel()[:n] % n
        sample = base.iloc[pos].reset_index(drop=True)
        rr_b = swt_rr_point(sample).set_index("swt_type")["rr"]
        for s in boot_rrs:
            boot_rrs[s].append(rr_b.get(s, np.nan))

    point["rr_lo"] = [np.nanpercentile(boot_rrs[s], 2.5) for s in point["swt_type"]]
    point["rr_hi"] = [np.nanpercentile(boot_rrs[s], 97.5) for s in point["swt_type"]]
    return point[["swt_type", "n_days", "n_high", "rr", "rr_lo", "rr_hi"]]
```

Note the resampled rows keep their **original dates** — that is intentional: month-matching inside `swt_rr_point` must use each day's real calendar month.

- [ ] **Step 4: Run tests** — `/opt/anaconda3/bin/python3 -m pytest tests/ -q` — all pass. (The 50-resample test takes a few seconds; that's fine.)

- [ ] **Step 5: Commit**

```bash
git add scripts/phase2_attribution/swt_attribution.py tests/test_swt_attribution.py
git commit -m "Add block-bootstrap CIs to SWT demand relative risk"
git push
```

---

### Task 4: runner + real-data sanity check

**Files:**
- Create: `scripts/run_phase2_swt.py`

**Interfaces:**
- Consumes: `data/derived/demand_daily_panel.parquet`, `attach_swt`, `demand_swt_rr`.
- Produces: `data/derived/swt_demand_rr.csv` (+ per-tier variants) and a printed table.

- [ ] **Step 1: Write the runner**

```python
"""Phase 2: SWT attribution of high-demand days.

Reads the Phase 1 demand panel, joins the SWT daily classification, and
writes per-SWT relative-risk tables (all-period and per confidence tier).

Outputs (data/derived/):
    swt_demand_rr.csv         all days with an SWT classification
    swt_demand_rr_tier{t}.csv per confidence tier
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED
from scripts.phase2_attribution.swt_attribution import attach_swt, demand_swt_rr

panel = pd.read_parquet(
    DATA_DERIVED / "demand_daily_panel.parquet",
    columns=["date", "dli", "confidence_tier"],
)
panel = attach_swt(panel)
n_swt = panel["swt_type"].notna().sum()
print(f"panel: {len(panel):,} days, {n_swt:,} with SWT", flush=True)

rr = demand_swt_rr(panel)
rr.round(3).to_csv(DATA_DERIVED / "swt_demand_rr.csv", index=False)
print("\nAll days:\n" + rr.round(2).to_string(index=False), flush=True)

for t, g in panel.groupby("confidence_tier"):
    rr_t = demand_swt_rr(g)
    rr_t.round(3).to_csv(DATA_DERIVED / f"swt_demand_rr_tier{t}.csv", index=False)
    print(f"\nTier {t}:\n" + rr_t.round(2).to_string(index=False), flush=True)
```

- [ ] **Step 2: Run it**

Run: `/opt/anaconda3/bin/python3 scripts/run_phase2_swt.py`
Expected runtime: a few minutes (1000 bootstraps × 4 tables; `swt_rr_point` on ~17k rows is cheap). If it drags past ~10 min, rerun in the background with a log per CLAUDE.md rule 5 — do not reduce `n_boot` for the saved outputs.

- [ ] **Step 3: Sanity-check the output** (do this yourself before reporting):
  - Every SWT label in the CSV matches the climatology's label set (e.g. `WH-A`, `TH-A` style).
  - `n_days` sums to roughly the number of classified days per table.
  - RRs are mostly within ~0.3–3; CIs bracket the point estimate.
  - Context: Fires_SWTs found blocking-high types reached RR ≈ 2.13 for multi-state fire *danger*. Comparable or larger enrichment for demand is plausible; wildly larger (RR > 5 with tight CIs) suggests a bug (check the month-matching and the tier threshold).

- [ ] **Step 4: Commit + report**

```bash
git add scripts/run_phase2_swt.py
git commit -m "Add Phase 2 SWT attribution runner"
git push
```

Then report to the user in plain language: which weather types are over-represented on high-demand days, with RR and CI, and how that compares to the Fires_SWTs danger result. Update CLAUDE.md "Current status" (Phase 2 SWT attribution: done, results file paths).
