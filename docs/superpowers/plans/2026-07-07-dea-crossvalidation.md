# FIRMS vs DEA Cross-Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the FIRMS hotspot record underpinning DLI tiers 1–2 against Geoscience Australia's independent DEA hotspot archive (design decision 4: daily national count + FRP-sum correlation over the overlap period).

**Architecture:** Stream the 1.26 GB `all-data-csv.zip` in chunks into a filtered parquet checkpoint (MODIS/VIIRS rows, hotspot era only), then run the existing `scripts/crossval.py` comparison against `hotspots_firms.parquet`. All comparison logic already exists and is tested; this plan adds the chunked archive extraction and wires the runner to the checkpoint.

**Tech Stack:** pandas, pyarrow (ParquetWriter for append-style writing), zipfile stdlib.

## Global Constraints

- Read `CLAUDE.md` at repo root first — working rules and environment traps apply to every task.
- Python is `/opt/anaconda3/bin/python3`. 17 GB RAM: never read the zip or its CSVs whole.
- PRECONDITION: the user must have placed `all-data-csv.zip` in `data/raw/dea_hotspots/`. If absent, STOP and tell the user (this is their download; see `scripts/loaders/hotspots_dea.py` docstring).
- Harmonised hotspot schema (must match FIRMS): `lat, lon, datetime_utc (tz=UTC), frp (float), sensor, confidence, source`.
- FIRMS VIIRS is S-NPP only (design decision 3): the DEA VIIRS series must be restricted to S-NPP for a like-for-like comparison, if the archive identifies the satellite.
- Tests green before and after every task: `/opt/anaconda3/bin/python3 -m pytest tests/ -q` (42 passing at time of writing).
- Commit after each task; trailer `Co-Authored-By: Claude <model> <noreply@anthropic.com>`; push.

---

### Task 1: Inspect the archive (no code changes)

**Files:** none (read-only investigation)

**Interfaces:**
- Produces: the actual member list and column names of the DEA archive, recorded in the Task 2 alias table. Later tasks assume the aliases below; this task confirms or corrects them.

- [ ] **Step 1: Confirm the zip is present**

Run: `ls -lh ~/EM_Demand/data/raw/dea_hotspots/`
Expected: `all-data-csv.zip` ≈ 1.26 GB. If missing, STOP — user action required.

- [ ] **Step 2: List members and peek at columns without extracting**

Run:
```bash
cd ~/EM_Demand && /opt/anaconda3/bin/python3 - <<'EOF'
import zipfile, pandas as pd
zf = zipfile.ZipFile("data/raw/dea_hotspots/all-data-csv.zip")
names = zf.namelist()
print(len(names), "members:", names[:10])
csvs = [n for n in names if n.lower().endswith(".csv")]
with zf.open(csvs[0]) as fh:
    head = pd.read_csv(fh, nrows=5)
print(list(head.columns))
print(head.to_string())
EOF
```
Expected: one or more CSV members; columns including latitude/longitude, a UTC datetime, power/FRP, sensor, and (hopefully) satellite. Record the exact column names.

- [ ] **Step 3: Check the alias map covers the real columns**

Compare the printed columns against `_ALIASES` in `scripts/loaders/hotspots_dea.py`
(current targets: lat, lon, datetime_utc, frp, sensor, confidence). If a
required column (lat/lon/datetime) has a name not in the alias list, add the
new alias in Task 2's harmoniser update. If there is a satellite column, note
its exact name for Task 2 (expected: `satellite`).

---

### Task 2: Harmoniser update + chunked archive extraction

**Files:**
- Modify: `scripts/loaders/hotspots_dea.py`
- Test: `tests/test_hotspots_dea.py` (create)

**Interfaces:**
- Consumes: `harmonise_dea(df)` (exists), `PATHS.dea_hotspots_dir` from `scripts.config`.
- Produces: `extract_dea_archive(zip_path, out_path, chunksize=1_000_000, min_date="2000-11-01") -> int` (rows written). Output parquet columns: `lat (float), lon (float), datetime_utc (timestamp UTC), frp (float), sensor (str), satellite (str), confidence (str), source (str)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hotspots_dea.py`:

```python
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.loaders.hotspots_dea import extract_dea_archive, harmonise_dea


def _dea_csv(rows):
    df = pd.DataFrame(
        rows,
        columns=["latitude", "longitude", "datetime", "power", "sensor", "satellite", "confidence"],
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def test_harmonise_carries_satellite_and_float_frp():
    out = harmonise_dea(
        pd.DataFrame(
            {"latitude": [-35.0], "longitude": [149.0], "datetime": ["2020-01-01T04:00:00Z"],
             "power": [12.5], "sensor": ["MODIS"], "satellite": ["TERRA"], "confidence": [80]}
        )
    )
    assert out.loc[0, "satellite"] == "TERRA"
    assert out["frp"].dtype == float
    assert out.loc[0, "source"] == "dea"


def test_extract_dea_archive_filters(tmp_path):
    zpath = tmp_path / "all-data-csv.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("part1.csv", _dea_csv([
            (-35.0, 149.0, "2020-01-01T04:00:00Z", 10.0, "MODIS", "AQUA", 80),
            (-35.0, 149.0, "1999-05-01T04:00:00Z", 10.0, "MODIS", "TERRA", 80),  # pre hotspot era
            (-35.0, 149.0, "2020-01-01T04:00:00Z", 10.0, "AVHRR", "NOAA-18", 80),  # wrong sensor
        ]))
        zf.writestr("part2.csv", _dea_csv([
            (-20.0, 130.0, "2021-06-01T02:00:00Z", 5.0, "VIIRS", "SUOMI NPP", 90),
        ]))
    out = tmp_path / "hotspots_dea.parquet"
    n = extract_dea_archive(zpath, out, chunksize=2)
    got = pd.read_parquet(out)
    assert n == len(got) == 2  # era + sensor filters applied
    assert set(got["satellite"]) == {"AQUA", "SUOMI NPP"}
    assert got["datetime_utc"].dt.tz is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/test_hotspots_dea.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_dea_archive'` (and the satellite assertion fails against the current harmoniser).

- [ ] **Step 3: Implement**

In `scripts/loaders/hotspots_dea.py`:

(a) add the satellite alias to `_ALIASES`:
```python
_ALIASES = {
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon"],
    "datetime_utc": ["datetime", "start_dt", "acq_datetime", "observation_time"],
    "frp": ["power", "frp", "firepower"],
    "sensor": ["sensor", "instrument"],
    "satellite": ["satellite", "satellite_name"],
    "confidence": ["confidence"],
}
```

(b) in `harmonise_dea`, change the frp/sensor lines and add satellite, so the
output frame is built as:
```python
    out = pd.DataFrame(
        {
            "lat": df[cols["lat"]].astype(float),
            "lon": df[cols["lon"]].astype(float),
            "datetime_utc": pd.to_datetime(df[cols["datetime_utc"]], utc=True, errors="coerce"),
            "frp": pd.to_numeric(df[cols["frp"]], errors="coerce") if cols["frp"] else float("nan"),
            "sensor": df[cols["sensor"]].astype(str) if cols["sensor"] else "unknown",
            "satellite": df[cols["satellite"]].astype(str) if cols["satellite"] else "unknown",
            "confidence": df[cols["confidence"]].astype(str) if cols["confidence"] else "unknown",
            "source": "dea",
        }
    )
```

(c) append the extraction function:
```python
def extract_dea_archive(zip_path, out_path, chunksize=1_000_000, min_date="2000-11-01",
                        verbose=False) -> int:
    """Stream the DEA all-data zip into a filtered parquet checkpoint.

    Keeps MODIS/VIIRS rows in the hotspot era only (the DLI never uses
    other sensors). Chunked because the archive does not fit in memory.
    Returns the number of rows written.
    """
    import zipfile

    import pyarrow as pa
    import pyarrow.parquet as pq

    min_ts = pd.Timestamp(min_date, tz="UTC")
    writer, total = None, 0
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        for name in members:
            with zf.open(name) as fh:
                for chunk in pd.read_csv(fh, chunksize=chunksize, low_memory=False):
                    h = harmonise_dea(chunk)
                    fam = h["sensor"].str.upper()
                    h = h[(h["datetime_utc"] >= min_ts)
                          & (fam.str.contains("MODIS") | fam.str.contains("VIIRS"))]
                    if h.empty:
                        continue
                    table = pa.Table.from_pandas(h, preserve_index=False)
                    if writer is None:
                        writer = pq.ParquetWriter(out_path, table.schema)
                    writer.write_table(table)
                    total += len(h)
                    if verbose:
                        print(f"    {name}: +{len(h)} (total {total})", flush=True)
    if writer is not None:
        writer.close()
    return total
```

- [ ] **Step 4: Run the full suite**

Run: `/opt/anaconda3/bin/python3 -m pytest tests/ -q`
Expected: all pass (42 existing + 2 new). If `test_crossval.py` or the DEA
tests fail on schema, fix before proceeding — do not skip.

- [ ] **Step 5: Commit**

```bash
git add scripts/loaders/hotspots_dea.py tests/test_hotspots_dea.py
git commit -m "Add chunked DEA archive extraction with satellite column"
git push
```

---

### Task 3: Run the extraction (heavy step)

**Files:**
- Create: `scripts/run_dea_extract.py`

**Interfaces:**
- Consumes: `extract_dea_archive` from Task 2.
- Produces: `data/derived/hotspots_dea.parquet` (checkpoint used by Task 4).

- [ ] **Step 1: Write the runner**

Create `scripts/run_dea_extract.py`:
```python
"""Extract MODIS/VIIRS rows from the DEA all-data zip to a parquet checkpoint."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.config import DATA_DERIVED, PATHS
from scripts.loaders.hotspots_dea import extract_dea_archive

t0 = time.time()
n = extract_dea_archive(
    PATHS.dea_hotspots_dir / "all-data-csv.zip",
    DATA_DERIVED / "hotspots_dea.parquet",
    verbose=True,
)
print(f"{n} rows written in {time.time()-t0:.0f}s", flush=True)
```

- [ ] **Step 2: Run it in the background with a log**

Run (background): `cd ~/EM_Demand && /opt/anaconda3/bin/python3 scripts/run_dea_extract.py > data/derived/dea_extract.log 2>&1`
Expect 5–30 min for 1.26 GB. Monitor the log for progress lines and
`Traceback|Error|Killed|MemoryError`. If killed (OOM), halve `chunksize` and
rerun — do not load differently.

- [ ] **Step 3: Sanity-check the checkpoint**

```bash
cd ~/EM_Demand && /opt/anaconda3/bin/python3 - <<'EOF'
import pandas as pd
d = pd.read_parquet("data/derived/hotspots_dea.parquet", columns=["datetime_utc", "sensor", "satellite"])
print(len(d), "rows,", d.datetime_utc.min(), "->", d.datetime_utc.max())
print(d.sensor.value_counts().head())
print(d.satellite.value_counts().head(8))
EOF
```
Expected: millions of rows, span ≈ 2000-11 → near-present, MODIS + VIIRS only.
If the satellite column is all "unknown", note it — Task 4 then compares all-VIIRS
and must record that caveat in the printed output.

- [ ] **Step 4: Commit the runner**

```bash
git add scripts/run_dea_extract.py
git commit -m "Add DEA archive extraction runner"
git push
```

---

### Task 4: Wire the checkpoint into the comparison and run it

**Files:**
- Modify: `scripts/run_crossval.py`

**Interfaces:**
- Consumes: `data/derived/hotspots_dea.parquet`; `compare_daily`, `agreement_stats` from `scripts/crossval.py` (unchanged).
- Produces: `data/derived/crossval_daily.parquet` + printed agreement table.

- [ ] **Step 1: Replace the DEA load in `scripts/run_crossval.py`**

Replace the `dea = load_dea()` block with:
```python
dea_pq = DATA_DERIVED / "hotspots_dea.parquet"
if dea_pq.exists():
    dea = pd.read_parquet(dea_pq)
else:
    from scripts.loaders.hotspots_dea import load_dea
    dea = load_dea()

# like-for-like with FIRMS: VIIRS restricted to S-NPP where identifiable
if "satellite" in dea and not (dea["satellite"] == "unknown").all():
    is_viirs = dea["sensor"].str.upper().str.contains("VIIRS")
    dea = dea[~is_viirs | dea["satellite"].str.upper().str.contains("NPP")]
else:
    print("WARNING: DEA satellite unidentified — VIIRS comparison includes all platforms", flush=True)
```
(keep the existing imports; drop the now-unused top-level `load_dea` import)

- [ ] **Step 2: Run the comparison**

Run: `cd ~/EM_Demand && /opt/anaconda3/bin/python3 scripts/run_crossval.py`
Expected output: DEA row count + span, overlap span, then the per-family table
from `agreement_stats` (family, n_days, count_pearson, count_spearman,
frp_pearson, count_ratio_firms_dea).

- [ ] **Step 3: Judge the result against the acceptance gate**

Acceptance: MODIS `count_spearman ≥ 0.90` over the overlap. VIIRS should be
similar if S-NPP filtering worked. `count_ratio_firms_dea` between ~0.5 and ~2
is fine (different processing versions differ in absolute counts; rank
agreement is what protects the percentile-based DLI). If below gate:
investigate before touching anything downstream — check tz handling, sensor
family assignment, and whether DEA coverage has gaps (plot annual counts per
source). Report findings to the user either way; do NOT "fix" the DLI in this plan.

- [ ] **Step 4: Record and commit**

Paste the agreement table into the "Current status" section of `CLAUDE.md`
(one line: date + MODIS/VIIRS Spearman values), then:
```bash
git add scripts/run_crossval.py CLAUDE.md
git commit -m "Run FIRMS vs DEA cross-validation from the archive checkpoint"
git push
```
Finally, tell the user in plain language what the correlations mean for the
trustworthiness of tiers 1–2.
