# Running the ERA5 SWT composites on Gadi

## 1. Put these 4 files in one Gadi working dir
e.g. `/g/data/<PROJECT>/<user>/swt_comp/`

- `era5_swt_composites.py`
- `composite_core.py`
- `read_era5.py`        (copy from `Australian_synoptic_weather_types/utils/read_era5.py`)
- `SWT_climatology_v20260129.csv`

(also copy `era5_swt_composites.pbs` there)

## 2. Find your project + fill the placeholders
```
nci_account              # lists your projects + SU balances; pick one WITH a compute allocation
```
Replace every `<PROJECT>` in `era5_swt_composites.pbs` — in BOTH `-P <PROJECT>` and
`-l storage=...gdata/<PROJECT>`. (rt52 = ERA5 data, xp65 = the conda env, <PROJECT> = where you write output.)

## 3. Cheap dry run first (~1 SU, one year)
```
module use /g/data/xp65/public/modules && module load conda/analysis3
cd /g/data/<PROJECT>/<user>/swt_comp/
python3 era5_swt_composites.py --start 1990-01 --end 1990-12 --out test.nc
```
Expect: per-field progress lines, `aligned days: ~365`, and `wrote test.nc`. Sanity-check
`test.nc` looks reasonable (e.g. `ncdump -h test.nc`), then delete it.

## 4. Full run via PBS
```
qsub era5_swt_composites.pbs     # prints a job id like 12345678.gadi-pbs
qstat -u $USER                   # watch status; stdout+stderr -> era5_swt_comp.o<id>
```
Estimated cost: ~5-20 SU (2 cpus x a few hours x 2 SU/cpu-hr on the `normal` queue).

## 5. Copy the result back to your laptop  (run THIS command ON YOUR LAPTOP)
```
rsync -vP <user>@gadi-dm.nci.org.au:/g/data/<PROJECT>/<user>/swt_comp/era5_swt_composites.nc \
      /Users/smar0095/Fires_SWTs/
```
Then in `Fires_SWTs.ipynb` Step 6, change `NC` from the `_SYNTH.nc` test file to
`era5_swt_composites.nc` and re-run the plotting cell.
