# Weather-object presence over Australia (fronts / anticyclones / cyclones)

Builds a daily per-state "was this weather object over the state?" flag from the 21CW ERA5
weather-feature catalogues, to test co-occurrence with multi-state fire DANGER (Step 9).

Load recipe mirrors the GC26_energy_synoptics demand notebook (Michael Barnes' group);
state masking uses our own `aus_states.geojson` (7 states), not cj0591's 5-state scratch mask.

## Data (you already read these via ARE jupyter-root, so access is fine)
- Features: `/g/data/if69/cj0591/GC26_energy_synoptics/data/weatherfeatures.era5/`
  (alt copy: `/g/data/su28/weatherfeatures.era5/`)
- Objects used: `fronts/cdf.850hPa` & `cdf.700hPa` (var `FRONT`), `maxcl/cdf` anticyclones (`FLAG`),
  `mincl/cdf` cyclones (`INPUT`). WCB is in the catalogue too but left out (less fire-relevant).

## Files to put in one Gadi dir (e.g. /g/data/gb02/sm5259/wxobj/)
`weather_objects_extract.py`, `aus_states.geojson`, `weather_objects_extract.pbs`

## 1. Dry run first (one year — cheap; confirms paths + grid + cells-per-state)
```
module use /g/data/xp65/public/modules && module load conda/analysis3
cd /g/data/gb02/sm5259/wxobj/
python3 weather_objects_extract.py --start 2010-01 --end 2010-12 --out t.csv
```
Check the printed `cells/state` are all > 0 (WA biggest ~924, TAS smallest ~30) and that each
object loads. If a path is wrong, pass `--datadir /g/data/su28/weatherfeatures.era5`. Then `rm t.csv`.

## 2. Full run (1979-2023)
```
qsub weather_objects_extract.pbs
qstat -u $USER
```
Output `object_presence_daily.csv` (~few MB): columns `date, state, object, present` (present = 1
if the object was over that state at ANY sub-daily step that day).

## 3. Back to laptop, then analyse
```
rsync -vP sm5259@gadi-dm.nci.org.au:/g/data/gb02/sm5259/wxobj/object_presence_daily.csv /Users/smar0095/Fires_SWTs/
```
Then locally: `python3 object_danger_cooccurrence.py` (merges onto the danger frame, tests whether
multi-state DANGER days under FH-B/WH-A/TH-C coincide with fronts/anticyclones more than chance).
