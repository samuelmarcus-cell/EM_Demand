"""DEA/Geoscience Australia Hotspots loader (secondary source, cross-validation).

USER ACTION REQUIRED: export historic hotspot CSVs from
https://hotspots.dea.ga.gov.au/ (Historic data download) and drop them into
data/raw/dea_hotspots/. Column names vary between exports, so the loader maps
a set of known aliases; extend _ALIASES if a new export differs.

Emits the harmonised hotspot schema shared with the FIRMS loader:
    lat, lon, datetime_utc, frp, sensor, confidence, source
"""

from pathlib import Path

import pandas as pd

from scripts.config import PATHS

_ALIASES = {
    "lat": ["latitude", "lat"],
    "lon": ["longitude", "lon"],
    "datetime_utc": ["datetime", "start_dt", "acq_datetime", "observation_time"],
    "frp": ["power", "frp", "firepower"],
    "sensor": ["sensor", "instrument"],
    "confidence": ["confidence"],
}


def _pick(df: pd.DataFrame, target: str) -> str | None:
    for alias in _ALIASES[target]:
        if alias in df.columns:
            return alias
    return None


def harmonise_dea(df: pd.DataFrame) -> pd.DataFrame:
    """DEA export columns -> harmonised schema (tolerant of alias variations)."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    cols = {t: _pick(df, t) for t in _ALIASES}
    missing = [t for t in ("lat", "lon", "datetime_utc") if cols[t] is None]
    if missing:
        raise ValueError(f"DEA export missing required columns {missing}; got {list(df.columns)}")

    out = pd.DataFrame(
        {
            "lat": df[cols["lat"]].astype(float),
            "lon": df[cols["lon"]].astype(float),
            "datetime_utc": pd.to_datetime(df[cols["datetime_utc"]], utc=True, errors="coerce"),
            "frp": pd.to_numeric(df[cols["frp"]], errors="coerce") if cols["frp"] else pd.NA,
            "sensor": df[cols["sensor"]].astype(str) if cols["sensor"] else "unknown",
            "confidence": df[cols["confidence"]].astype(str) if cols["confidence"] else "unknown",
            "source": "dea",
        }
    )
    return out.dropna(subset=["lat", "lon", "datetime_utc"]).reset_index(drop=True)


def load_dea(dea_dir: Path | None = None) -> pd.DataFrame:
    """Load and harmonise every DEA CSV (plain or zipped) in the DEA directory."""
    dea_dir = Path(dea_dir or PATHS.dea_hotspots_dir)
    files = sorted(p for p in dea_dir.glob("*") if p.suffix.lower() in {".csv", ".zip"})
    if not files:
        raise FileNotFoundError(
            f"No DEA files in {dea_dir}. See module docstring for download instructions."
        )
    out = pd.concat([harmonise_dea(pd.read_csv(p)) for p in files], ignore_index=True)
    return out.drop_duplicates(subset=["lat", "lon", "datetime_utc", "sensor"]).reset_index(drop=True)
