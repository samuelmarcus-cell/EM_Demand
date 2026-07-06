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
