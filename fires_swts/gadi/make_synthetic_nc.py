"""Make a synthetic era5_swt_composites.nc with the real schema so plotting can be built now.
Uses netCDF4 (not xarray) so it works in the local env where dask metadata is broken."""
import numpy as np
from netCDF4 import Dataset

swt_names = ["FH-B", "WH-A", "TH-C", "WCT-B", "AM-A", "CH-A"]   # subset incl. headline 4 is fine
lat = np.arange(-60, -4, 1.0); lon = np.arange(80, 181, 1.0)
K, Y, X = len(swt_names), len(lat), len(lon)
rng = np.random.default_rng(0)

out = "/Users/smar0095/Fires_SWTs/era5_swt_composites_SYNTH.nc"
nc = Dataset(out, "w")
nc.createDimension("swt", K); nc.createDimension("lat", Y); nc.createDimension("lon", X)
vswt = nc.createVariable("swt", str, ("swt",))
for i, s in enumerate(swt_names):
    vswt[i] = s
nc.createVariable("lat", "f4", ("lat",))[:] = lat
nc.createVariable("lon", "f4", ("lon",))[:] = lon
for f, base in [("msl", 101300.0), ("z500", 5500.0), ("u850", 0.0), ("v850", 0.0), ("t850", 273.0)]:
    nc.createVariable(f"{f}_mean", "f4", ("swt", "lat", "lon"))[:] = base + rng.normal(0, 50, (K, Y, X))
    nc.createVariable(f"{f}_anom", "f4", ("swt", "lat", "lon"))[:] = rng.normal(0, 20, (K, Y, X))
    nc.createVariable(f"{f}_p",    "f4", ("swt", "lat", "lon"))[:] = rng.random((K, Y, X))
nc.createVariable("n_days", "i4", ("swt",))[:] = rng.integers(150, 400, K)
nc.close()
print("wrote", out)
