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
            (5.4, 114.7, "2020-01-01T04:00:00Z", 10.0, "MODIS", "TERRA", 80),  # Borneo, outside AUS
        ]))
        zf.writestr("part2.csv", _dea_csv([
            (-20.0, 130.0, "2021-06-01T02:00:00Z", 5.0, "VIIRS", "SUOMI NPP", 90),
        ]))
    out = tmp_path / "hotspots_dea.parquet"
    n = extract_dea_archive(zpath, out, chunksize=2)
    got = pd.read_parquet(out)
    assert n == len(got) == 2  # era + sensor + bbox filters applied
    assert set(got["satellite"]) == {"AQUA", "SUOMI NPP"}
    assert got["datetime_utc"].dt.tz is not None
