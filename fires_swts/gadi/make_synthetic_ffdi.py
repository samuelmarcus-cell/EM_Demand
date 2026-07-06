"""Synthetic ffdi_state_daily.csv + ffdi_swt_composite.nc so Step 8 builds without Gadi."""
import numpy as np, pandas as pd
from netCDF4 import Dataset
D = "/Users/smar0095/Fires_SWTs"
dates = pd.date_range("1979-01-01", "2024-12-31")
rng = np.random.default_rng(0)
seas = 1 + 0.6 * np.cos(2 * np.pi * (dates.dayofyear - 15) / 365)      # summer-peaked
rows = []
for s in ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT"]:
    rows.append(pd.DataFrame({"date": dates.date, "state": s,
                              "ffdi": np.clip(rng.gamma(2, 5, len(dates)) * seas, 0, None)}))
pd.concat(rows, ignore_index=True).to_csv(f"{D}/ffdi_state_daily.csv", index=False)
# gridded composite (same schema as real)
swt = ["FH-B", "WH-A", "TH-C", "WCT-B", "AM-A"]; lat = np.arange(-44, -9, 0.25); lon = np.arange(112, 154, 0.25)
K, Y, X = len(swt), len(lat), len(lon)
nc = Dataset(f"{D}/ffdi_swt_composite.nc", "w")
nc.createDimension("swt", K); nc.createDimension("lat", Y); nc.createDimension("lon", X)
v = nc.createVariable("swt", str, ("swt",)); [v.__setitem__(i, s) for i, s in enumerate(swt)]
nc.createVariable("lat", "f4", ("lat",))[:] = lat; nc.createVariable("lon", "f4", ("lon",))[:] = lon
nc.createVariable("ffdi_mean", "f4", ("swt", "lat", "lon"))[:] = 5 + rng.normal(0, 3, (K, Y, X))
nc.createVariable("ffdi_anom", "f4", ("swt", "lat", "lon"))[:] = rng.normal(0, 2, (K, Y, X))
nc.createVariable("ffdi_p", "f4", ("swt", "lat", "lon"))[:] = rng.random((K, Y, X))
nc.createVariable("n_days", "i4", ("swt",))[:] = rng.integers(400, 2000, K)
nc.close(); print("wrote synthetic ffdi_state_daily.csv + ffdi_swt_composite.nc")
