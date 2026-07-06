import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.drfa_panel import daily_panel, explode_events_daily
from scripts.loaders.drfa_activations import (
    assumed_duration,
    attach_end_dates,
    donor_catalogue_from_aidr,
    donor_catalogue_from_ica,
    hazard_classes,
)


def _events():
    return pd.DataFrame(
        {
            "agrn": [1, 2],
            "event_name": ["Eastern Australia flooding: February 2022", "Perth Hills bushfire: Feb 2021"],
            "hazard_type": ["Flood", "Bushfire"],
            "start_date": pd.to_datetime(["2022-02-22", "2021-02-01"]),
            "states": [["New South Wales", "Queensland"], ["Western Australia"]],
            "hazard_classes": [{"flood"}, {"fire"}],
        }
    )


def test_hazard_classes():
    assert hazard_classes("Flood, Storm") == {"flood", "storm"}
    assert hazard_classes("Cyclone, Flood, Storm surge") == {"tc", "flood", "storm"}
    assert hazard_classes("Earthquake") == {"other"}
    assert hazard_classes(None) == {"other"}


def test_assumed_duration_takes_max():
    assert assumed_duration({"flood", "storm"}) == 14
    assert assumed_duration({"fire", "tc"}) == 21


def _aidr_donors(**overrides):
    base = {
        "event": ["Eastern Australia Flooding"],
        "Category": ["Flood"],
        "Zone": ["New South Wales"],
        "start_date": pd.to_datetime(["2022-02-23"]),
        "end_date": pd.to_datetime(["2022-04-05"]),
    }
    base.update(overrides)
    return donor_catalogue_from_aidr(pd.DataFrame(base))


def test_aidr_match_and_fallback():
    out = attach_end_dates(_events(), _aidr_donors())
    matched = out[out["agrn"] == 1].iloc[0]
    assert matched["end_date_source"] == "aidr"
    assert matched["end_date"] == pd.Timestamp("2022-04-05")
    fallback = out[out["agrn"] == 2].iloc[0]
    assert fallback["end_date_source"] == "assumed"
    assert fallback["end_date"] == pd.Timestamp("2021-02-01") + pd.Timedelta(days=21)


def test_class_mismatch_no_match():
    out = attach_end_dates(_events(), _aidr_donors(Category=["Bushfire"]))
    assert out[out["agrn"] == 1].iloc[0]["end_date_source"] == "assumed"


def test_state_mismatch_no_match():
    out = attach_end_dates(_events(), _aidr_donors(Zone=["Western Australia"]))
    assert out[out["agrn"] == 1].iloc[0]["end_date_source"] == "assumed"


def test_national_zone_matches():
    out = attach_end_dates(_events(), _aidr_donors(Zone=["National"]))
    assert out[out["agrn"] == 1].iloc[0]["end_date_source"] == "aidr"


def test_end_before_start_falls_back():
    out = attach_end_dates(
        _events(),
        _aidr_donors(start_date=pd.to_datetime(["2022-02-20"]), end_date=pd.to_datetime(["2022-02-10"])),
    )
    row = out[out["agrn"] == 1].iloc[0]
    assert row["end_date_source"] == "assumed"
    assert row["end_date"] > row["start_date"]


def test_ica_donor_preferred_over_aidr_on_tie():
    ica = donor_catalogue_from_ica(
        pd.DataFrame(
            {
                "Event Name": ["Eastern Australia Flooding"],
                "Event Start": pd.to_datetime(["2022-02-23"]),
                "Event Finish": pd.to_datetime(["2022-04-08"]),
                "Type": ["Flood"],
                "State": ["NSW, QLD"],
            }
        )
    )
    donors = pd.concat([ica, _aidr_donors()], ignore_index=True)
    out = attach_end_dates(_events(), donors)
    row = out[out["agrn"] == 1].iloc[0]
    assert row["end_date_source"] == "ica"
    assert row["end_date"] == pd.Timestamp("2022-04-08")


def test_name_range_beats_donors():
    ev = _events()
    ev.loc[ev["agrn"] == 1, "event_name"] = (
        "AGRN 1011 - South East Queensland Rainfall and Flooding (22 February - 5 April 2022)"
    )
    out = attach_end_dates(ev, _aidr_donors())
    row = out[out["agrn"] == 1].iloc[0]
    assert row["end_date_source"] == "name"
    assert row["end_date"] == pd.Timestamp("2022-04-05")


def test_name_range_same_month():
    from scripts.loaders.drfa_activations import parse_name_date_range

    assert parse_name_date_range("Tropical Low and Flooding (1-4 February 2022)") == (
        pd.Timestamp("2022-02-01"),
        pd.Timestamp("2022-02-04"),
    )
    assert parse_name_date_range("Cross-year event (25 December - 3 January 2022)") == (
        pd.Timestamp("2021-12-25"),
        pd.Timestamp("2022-01-03"),
    )
    assert parse_name_date_range("NSW Severe Weather (22 February 2022 onwards)") is None
    assert parse_name_date_range("Queensland floods: mid-January 2008") is None


def test_ica_point_record_excluded():
    ica = donor_catalogue_from_ica(
        pd.DataFrame(
            {
                "Event Name": ["East Coast Floods"],
                "Event Start": pd.to_datetime(["2022-02-22"]),
                "Event Finish": pd.to_datetime(["2022-02-22"]),  # zero duration
                "Type": ["Flood"],
                "State": ["NSW"],
            }
        )
    )
    out = attach_end_dates(_events(), ica)
    assert out[out["agrn"] == 1].iloc[0]["end_date_source"] == "assumed"


def test_daily_panel_counts():
    ev = _events()
    ev["end_date"] = ev["start_date"] + pd.Timedelta(days=5)
    ev["end_date_source"] = "assumed"
    panel = daily_panel(ev)
    d = panel.set_index("date")
    # 2021-02-03: only event 2 (WA fire)
    assert d.loc["2021-02-03", "n_active_events"] == 1
    assert d.loc["2021-02-03", "n_jurisdictions_active"] == 1
    assert bool(d.loc["2021-02-03", "hazard_fire"]) is True
    assert bool(d.loc["2021-02-03", "hazard_flood"]) is False
    # 2022-02-24: only event 1 (NSW+QLD flood)
    assert d.loc["2022-02-24", "n_jurisdictions_active"] == 2
    assert d.loc["2022-02-24", "n_hazard_types_active"] == 1
    # gap day between events
    assert d.loc["2021-06-01", "n_active_events"] == 0
    # availability flag
    assert bool(d.loc["2021-02-03", "drfa_available"]) is True


def test_explode_row_count():
    ev = _events()
    ev["end_date"] = ev["start_date"] + pd.Timedelta(days=2)
    ev["end_date_source"] = "assumed"
    assert len(explode_events_daily(ev)) == 6  # 2 events x 3 days
