"""Real test of the ACTUAL masking function (imports it, doesn't paraphrase it).
Run from gadi/: /opt/anaconda3/bin/python3 test_weather_objects.py
Catches lat/lon argument-order swaps via known inland cities."""
import numpy as np
from weather_objects_extract import state_label_array

GEO = "aus_states.geojson"

def test_counts_and_known_cities():
    lat = np.arange(-44, -9 + 1e-6, 0.5); lon = np.arange(112, 154 + 1e-6, 0.5)
    m = state_label_array(lat, lon, GEO)                       # call the REAL function, (lat, lon) order
    assert m.shape == (len(lat), len(lon)), m.shape
    cnt = {s: int((m == s).sum()) for s in ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]}
    assert all(v > 0 for v in cnt.values()), cnt               # every state present
    assert cnt["WA"] == max(cnt.values()), cnt                 # WA biggest
    assert cnt["TAS"] == min(cnt.values()), cnt                # TAS smallest

    def state_at(la, lo):
        i = int(np.argmin(np.abs(lat - la))); j = int(np.argmin(np.abs(lon - lo)))
        return m[i, j]
    # deep-interior points -> safe at 0.5deg; a lat/lon swap sends these off-continent (NaN/wrong state)
    cases = {(-33, 147): "NSW", (-26, 122): "WA", (-20, 133): "NT",
             (-22, 144): "QLD", (-30, 135): "SA", (-37, 144): "VIC"}
    for (la, lo), want in cases.items():
        got = state_at(la, lo)
        assert got == want, f"point(lat={la},lon={lo}) -> {got}, expected {want}"

def test_end_to_end_presence():
    """Real pipeline (assign_weatherfeature_coords -> state_label_array -> state_daily_presence)
    on a synthetic global feature file with a front planted over NSW on day 3 only."""
    import xarray as xr
    from weather_objects_extract import assign_weatherfeature_coords, state_label_array, state_daily_presence
    T, ny, nx = 72, 361, 720
    ds = xr.Dataset({"FRONT": (("time", "y", "x"), np.zeros((T, ny, nx), "i1"))})
    ds = ds.assign_coords(time=("time", np.array("2010-01-01", dtype="datetime64[h]") + np.arange(T)))
    ds = assign_weatherfeature_coords(ds)
    day3 = ds.time.dt.day == 3
    box = (ds.longitude >= 147) & (ds.longitude <= 150) & (ds.latitude >= -33) & (ds.latitude <= -31)
    ds["FRONT"] = ds["FRONT"].where(~(day3 & box), 1)
    sub = ds.sel(latitude=slice(-55, -9), longitude=slice(110, 155)).load()
    smask = state_label_array(sub.latitude.values, sub.longitude.values, GEO)
    df = state_daily_presence(sub["FRONT"].values, sub["time"].values, smask, ["NSW", "WA"])
    nsw = df[df.state == "NSW"].sort_values("date")["present"].tolist()
    wa = df[df.state == "WA"].sort_values("date")["present"].tolist()
    assert nsw == [0, 0, 1], nsw      # front over NSW only on day 3
    assert wa == [0, 0, 0], wa        # never over WA

def test_select_files():
    """select_files returns only the requested years' monthly files, in order."""
    import os, shutil, tempfile
    from weather_objects_extract import select_files
    tmpdir = tempfile.mkdtemp(prefix="wxobj_seltest_")          # portable: mac AND Gadi
    try:
        for y in (2009, 2010, 2011):
            d = f"{tmpdir}/fronts/cdf.850hPa/{y}"; os.makedirs(d)
            for m in range(1, 13):
                open(f"{d}/F{y}_{m:02d}.nc", "w").close()
        fs = select_files(tmpdir, "fronts/cdf.850hPa", "F", 2010, 2010)
        assert len(fs) == 12 and all("/2010/" in f for f in fs), fs
        two = select_files(tmpdir, "fronts/cdf.850hPa", "F", 2010, 2011)
        assert len(two) == 24 and two == sorted(two), two
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    test_counts_and_known_cities()
    test_end_to_end_presence()
    test_select_files()
    print("OK: weather-object tests passed (masking, city checks, end-to-end presence, file selection)")
