"""NASA FIRMS archive hotspot loader (primary source).

USER ACTION REQUIRED: request archive downloads at
https://firms.modaps.eosdis.nasa.gov/download/
  - MODIS C6.1, Australia, 2000-11-01 -> present
  - VIIRS S-NPP 375 m (SUOMI VIIRS C2), Australia, 2012-01-20 -> present
Drop the delivered CSVs (zipped or not, any filenames) into data/raw/firms/.

Emits the harmonised hotspot schema shared with the DEA loader:
    lat, lon, datetime_utc, frp, sensor, confidence, source
"""

import zipfile
from pathlib import Path

import pandas as pd

from scripts.config import PATHS

_USECOLS = ["latitude", "longitude", "acq_date", "acq_time", "frp", "confidence", "instrument", "satellite"]

# VIIRS is restricted to S-NPP for a consistent Tier-1 record (see design doc).
# FIRMS encodes S-NPP inconsistently: archive files use instrument="SNPP",
# satellite="SNPP"; NRT files use instrument="VIIRS", satellite="N".
_SNPP_SATELLITES = {"N", "SNPP", "SUOMI NPP", "SUOMI-NPP", "SUOMI_NPP", "NPP"}
_MODIS_SATELLITES = {"TERRA", "AQUA", "T", "A"}


def harmonise_firms(df: pd.DataFrame) -> pd.DataFrame:
    """FIRMS archive columns -> harmonised schema. Drops non-S-NPP VIIRS rows."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    instrument = df["instrument"].astype(str).str.upper().str.strip()
    satellite = df["satellite"].astype(str).str.upper().str.strip()

    is_viirs = instrument.str.startswith("VIIRS") | instrument.eq("SNPP")
    keep = (instrument.eq("MODIS") & satellite.isin(_MODIS_SATELLITES)) | (
        is_viirs & satellite.isin(_SNPP_SATELLITES)
    )
    df = df[keep].copy()
    instrument, satellite = instrument[keep], satellite[keep]

    time_str = df["acq_time"].astype(int).astype(str).str.zfill(4)
    sat_full = satellite.replace({"T": "TERRA", "A": "AQUA"})
    sensor = ("MODIS_" + sat_full).where(instrument.eq("MODIS"), "VIIRS_SNPP")
    out = pd.DataFrame(
        {
            "lat": df["latitude"].astype(float),
            "lon": df["longitude"].astype(float),
            "datetime_utc": pd.to_datetime(
                df["acq_date"].astype(str) + " " + time_str.str[:2] + ":" + time_str.str[2:],
                utc=True,
            ),
            "frp": pd.to_numeric(df["frp"], errors="coerce"),
            "sensor": sensor,
            "confidence": df["confidence"].astype(str),
            "source": "firms",
        }
    )
    return out.dropna(subset=["lat", "lon", "datetime_utc"]).reset_index(drop=True)


def _read_csvs(path: Path):
    """Yield raw DataFrames from a CSV file or every CSV member of a zip.

    FIRMS delivery zips contain fire_archive_*.csv + fire_nrt_*.csv (recent
    weeks not yet in standard processing) + Readme.txt; both CSVs are loaded
    and the archive/NRT overlap is removed by the caller's dedupe.
    """
    if path.suffix.lower() == ".csv":
        yield pd.read_csv(path, usecols=_USECOLS)
        return
    with zipfile.ZipFile(path) as zf:
        for member in zf.namelist():
            if member.lower().endswith(".csv"):
                with zf.open(member) as f:
                    yield pd.read_csv(f, usecols=_USECOLS)


def load_firms(firms_dir: Path | None = None) -> pd.DataFrame:
    """Load and harmonise every FIRMS CSV (plain or zipped) in the FIRMS directory."""
    firms_dir = Path(firms_dir or PATHS.firms_dir)
    files = sorted(p for p in firms_dir.glob("*") if p.suffix.lower() in {".csv", ".zip"})
    if not files:
        raise FileNotFoundError(
            f"No FIRMS files in {firms_dir}. See module docstring for download instructions."
        )
    parts = [harmonise_firms(raw) for p in files for raw in _read_csvs(p)]
    out = pd.concat(parts, ignore_index=True)
    return out.drop_duplicates(subset=["lat", "lon", "datetime_utc", "sensor"]).reset_index(drop=True)
