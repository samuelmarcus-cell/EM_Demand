# Running the FFDI extract on Gadi

## 1. Put these files in one Gadi dir (e.g. /g/data/gb02/sm5259/ffdi/)
`ffdi_extract.py`, `composite_core.py`, `ffdi_core.py`, `aus_states.geojson`,
`SWT_climatology_v20260129.csv`, `ffdi_extract.pbs`

(Requires `ia39` membership — you have it.)

## 2. Dry run first (one year — prints the Zarr schema; cheap)
```
module use /g/data/xp65/public/modules && module load conda/analysis3
cd /g/data/gb02/sm5259/ffdi/
python3 ffdi_extract.py --start 2000-01 --end 2000-12 --out_csv t.csv --out_nc t.nc
```
- Read the printed **"=== Zarr schema ==="**: confirm the FFDI variable name and the lat/lon
  coordinate names the script auto-detected (line `using var=... lat=... lon=...`).
- If wrong, re-run adding `--var <name> --lat <name> --lon <name>`.
- Check **"cells per state"** are all > 0 and **"aligned days"** ≈ 365. Then delete `t.csv t.nc`.

## 3. Full run
```
qsub ffdi_extract.pbs          # ~5-15 SU (4 cpu x ~1h x 2; single-pass read). 4cpu/16GB normal.
qstat -u $USER
# If the composite step OOMs: raise --coarsen (e.g. 10 -> 0.5deg) in the .pbs python line,
# or bump to ncpus=8/mem=32GB. Storage of outputs is ~40 MB.
```
Outputs land in the run dir: `ffdi_state_daily.csv`, `ffdi_swt_composite.nc`, `ffdi_extract.o<id>`.

## 4. Copy results to your laptop (run ON your laptop, single line each)
```
rsync -vP sm5259@gadi-dm.nci.org.au:/g/data/gb02/sm5259/ffdi/ffdi_state_daily.csv /Users/smar0095/Fires_SWTs/
rsync -vP sm5259@gadi-dm.nci.org.au:/g/data/gb02/sm5259/ffdi/ffdi_swt_composite.nc /Users/smar0095/Fires_SWTs/
```
Then re-run notebook **Step 8** — it auto-detects the real files over the synthetic placeholders.

## (optional) Bias-corrected extremes pass
For the absolute-threshold (FFDI >=50/75/100) extreme-day analysis, repeat with the bias-OUTPUT zarr:
```
python3 ffdi_extract.py \
  --zarr /g/data/ia39/ncra/fire/bias-output/ffdi/AUST-05i_BOM_ERA5_historical_hres_BARRAR2_v1_day_FFDI.zarr \
  --out_csv ffdi_state_daily_biascorr.csv --out_nc ffdi_swt_composite_biascorr.nc
```
