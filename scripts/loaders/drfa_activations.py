"""DRFA activation loader + end-date attachment from donor catalogues.

Input: drfa_activation_history_by_location CSV (LGA-level rows, no end dates),
       plus two end-date donor catalogues:
         - ICA historical catastrophe master (Event Start/Finish, best coverage)
         - AIDR disaster mapper xlsx (Start/End Date, mostly point records)
Output: event-level table (one row per AGRN) with end dates and provenance
        (end_date_source in {ica, aidr, assumed}).
"""

import re

import pandas as pd

from scripts.config import ASSUMED_DURATION_DAYS, HAZARD_CLASS_TOKENS, PATHS

_STOPWORDS = {
    "the", "and", "of", "to", "in", "a", "an", "new", "south", "wales", "queensland",
    "victoria", "victorian", "tasmania", "tasmanian", "australia", "australian",
    "western", "northern", "territory", "nsw", "qld", "vic", "tas", "wa", "sa", "nt",
    "act", "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "flooding", "floods", "flood",
    "bushfires", "bushfire", "fires", "fire", "storm", "storms", "cyclone", "severe",
    "weather", "event", "events", "associated", "with",
}

_STATE_ABBREV = {
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "VIC": "Victoria",
    "TAS": "Tasmania",
    "WA": "Western Australia",
    "SA": "South Australia",
    "NT": "Northern Territory",
    "ACT": "Australian Capital Territory",
    "SEQ": "Queensland",
}

# Donor hazard label -> hazard class. Unmapped labels (Transport, Earthquake,
# Man-made, ...) never match DRFA events.
_DONOR_HAZARD_CLASS = {
    "bushfire": "fire",
    "flood": "flood",
    "cyclone": "tc",
    "storm": "storm",
    "hail": "storm",
    "tornado": "storm",
}

_WILDCARD_ZONES = {"national", "australia wide", "offshore"}


def hazard_classes(hazard_type: str) -> set:
    """Map a DRFA hazard_type string to hazard classes {fire, flood, tc, storm, other}."""
    if not isinstance(hazard_type, str) or not hazard_type.strip():
        return {"other"}
    found = set()
    for cls, tokens in HAZARD_CLASS_TOKENS.items():
        if any(tok.lower() in hazard_type.lower() for tok in tokens):
            found.add(cls)
    return found or {"other"}


def assumed_duration(classes: set) -> int:
    """Assumed duration (days) = max over hazard classes present."""
    return max(ASSUMED_DURATION_DAYS[c] for c in classes)


def load_drfa_locations(path=None) -> pd.DataFrame:
    """Raw LGA-level DRFA activation rows with parsed dates."""
    df = pd.read_csv(path or PATHS.drfa_locations)
    df["disaster_start_date"] = pd.to_datetime(df["disaster_start_date"])
    return df


def drfa_events(locations: pd.DataFrame) -> pd.DataFrame:
    """Collapse LGA rows to one row per AGRN event."""
    ev = (
        locations.groupby("agrn")
        .agg(
            event_name=("event_name", "first"),
            hazard_type=("hazard_type", "first"),
            start_date=("disaster_start_date", "min"),
            states=("STATE", lambda s: sorted(set(s))),
            n_lga=("Location_code", "nunique"),
        )
        .reset_index()
    )
    ev["hazard_classes"] = ev["hazard_type"].map(hazard_classes)
    return ev


def load_aidr(path=None) -> pd.DataFrame:
    """AIDR disaster mapper events with start/end dates."""
    df = pd.read_excel(path or PATHS.aidr_mapper, sheet_name="Disaster Mapper Data")
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={"Event": "event", "Start Date": "start_date", "End Date": "end_date"})
    # AIDR includes pre-1900 historical events whose dates overflow ns-datetime
    # arithmetic — coerce to ns and drop anything before 1900 (we only need 1979+).
    for col in ("start_date", "end_date"):
        df[col] = pd.to_datetime(df[col], errors="coerce").astype("datetime64[ns]")
    df = df.dropna(subset=["start_date"])
    return df[df["start_date"] >= pd.Timestamp("1900-01-01")]


def load_ica(path=None) -> pd.DataFrame:
    """ICA historical normalised catastrophe master with parsed start/finish dates.

    Date-parsing recipe (2-digit-year fix) follows the aus-disaster app's load_ica.
    """
    df = pd.read_csv(path or PATHS.ica_catastrophes)
    df.columns = [c.strip() for c in df.columns]
    df["Event Start"] = pd.to_datetime(df["Event Start"], format="%d-%b-%y", errors="coerce")
    df["Event Finish"] = pd.to_datetime(df["Event Finish"], format="%d-%b-%y", errors="coerce")
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    mask = df["Event Start"].dt.year > df["Year"] + 1
    df.loc[mask, "Event Start"] -= pd.DateOffset(years=100)
    df.loc[mask, "Event Finish"] -= pd.DateOffset(years=100)
    return df.dropna(subset=["Event Start"])


_MONTHS = {
    m.lower(): i + 1
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"]
    )
}

# "(22 February - 5 April 2022)" | "(25 December 2021 - 3 January 2022)"
_RANGE_FULL = re.compile(
    r"\(\s*(\d{1,2})\s+([A-Za-z]+)\s*(\d{4})?\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*\)"
)
# "(1-4 February 2022)"
_RANGE_SAME_MONTH = re.compile(
    r"\(\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*\)"
)


def parse_name_date_range(event_name: str):
    """Extract (start, end) from an official date range embedded in the event name.

    Handles "(22 February - 5 April 2022)" and "(1-4 February 2022)" forms.
    Open-ended ranges ("... onwards") and month-only names return None.
    """
    name = str(event_name)
    m = _RANGE_FULL.search(name)
    if m:
        d1, mon1, y1, d2, mon2, y2 = m.groups()
        if mon1.lower() in _MONTHS and mon2.lower() in _MONTHS:
            end = pd.Timestamp(int(y2), _MONTHS[mon2.lower()], int(d2))
            y1 = int(y1) if y1 else (int(y2) if _MONTHS[mon1.lower()] <= _MONTHS[mon2.lower()] else int(y2) - 1)
            start = pd.Timestamp(y1, _MONTHS[mon1.lower()], int(d1))
            if end >= start:
                return start, end
    m = _RANGE_SAME_MONTH.search(name)
    if m:
        d1, d2, mon, y = m.groups()
        if mon.lower() in _MONTHS and int(d2) >= int(d1):
            return (
                pd.Timestamp(int(y), _MONTHS[mon.lower()], int(d1)),
                pd.Timestamp(int(y), _MONTHS[mon.lower()], int(d2)),
            )
    return None


def _tokens(name: str) -> set:
    words = re.findall(r"[a-z]+", str(name).lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _zone_states(zone: str):
    """AIDR Zone -> set of full state names, or None for national/wildcard zones."""
    parts = [p.strip().title().replace("  ", " ") for p in str(zone).split(",")]
    if any(p.lower() in _WILDCARD_ZONES for p in parts):
        return None
    return {p for p in parts if p}


def _ica_states(state: str):
    """ICA State field ('QLD, NSW', 'NSW and SEQ', 'SA, Vic') -> set of full names.

    Returns None (wildcard) when no known abbreviation is found.
    """
    found = {
        _STATE_ABBREV[m.upper()]
        for m in re.findall(r"[A-Za-z]+", str(state))
        if m.upper() in _STATE_ABBREV
    }
    return found or None


def donor_catalogue_from_aidr(aidr: pd.DataFrame) -> pd.DataFrame:
    """Standardise AIDR to donor columns: event, start_date, end_date, _class, _states, donor."""
    d = aidr.dropna(subset=["end_date"]).copy()
    d["_class"] = d["Category"].map(lambda c: _DONOR_HAZARD_CLASS.get(str(c).strip().lower()))
    d["_states"] = d["Zone"].map(_zone_states)
    d["donor"] = "aidr"
    return d[["event", "start_date", "end_date", "_class", "_states", "donor"]]


def donor_catalogue_from_ica(ica: pd.DataFrame) -> pd.DataFrame:
    """Standardise ICA to donor columns."""
    d = ica.dropna(subset=["Event Finish"]).copy()
    d = d.rename(columns={"Event Name": "event", "Event Start": "start_date", "Event Finish": "end_date"})
    d["_class"] = d["Type"].map(lambda c: _DONOR_HAZARD_CLASS.get(str(c).strip().lower()))
    d["_states"] = d["State"].map(_ica_states)
    d["donor"] = "ica"
    return d[["event", "start_date", "end_date", "_class", "_states", "donor"]]


_DONOR_PRIORITY = {"ica": 0, "aidr": 1}


def attach_end_dates(
    events: pd.DataFrame,
    donors: pd.DataFrame,
    max_start_diff_days: int = 14,
) -> pd.DataFrame:
    """Attach end dates to DRFA events from a pooled donor catalogue.

    Priority cascade per event:
    1. "name" — an official date range embedded in the DRFA event name itself
       (e.g. "(22 February - 5 April 2022)") is authoritative.
    2. Donor match: candidates = donor events with a compatible hazard class,
       an overlapping state (wildcard/national donors match anything), and a
       start date within ±max_start_diff_days. Best candidate = smallest
       start-date gap, then name-token Jaccard, then donor priority (ICA over
       AIDR). Point records (end == start) are excluded — they carry no
       duration information, so the assumed window is better.
    3. "assumed" — start + per-hazard-class duration.

    Adds columns end_date, end_date_source ("name" | "ica" | "aidr" |
    "assumed"), donor_event.
    """
    donors = donors[donors["end_date"] > donors["start_date"]].copy()
    donors = donors[donors["_class"].notna()]
    donors["_tokens"] = donors["event"].map(_tokens)

    out = events.copy()
    end_dates, sources, matched_names = [], [], []
    for _, ev in out.iterrows():
        named = parse_name_date_range(ev["event_name"])
        if named is not None and named[1] >= ev["start_date"]:
            end_dates.append(named[1])
            sources.append("name")
            matched_names.append(None)
            continue
        cand = donors[
            ((donors["start_date"] - ev["start_date"]).abs().dt.days <= max_start_diff_days)
            & donors["_class"].isin(ev["hazard_classes"])
        ]
        ev_states, ev_tok = set(ev["states"]), _tokens(ev["event_name"])
        best_key, best_row = None, None
        for _, c in cand.iterrows():
            if c["_states"] is not None and not (c["_states"] & ev_states):
                continue
            gap = abs((c["start_date"] - ev["start_date"]).days)
            union = ev_tok | c["_tokens"]
            jac = len(ev_tok & c["_tokens"]) / len(union) if union else 0.0
            key = (gap, -jac, _DONOR_PRIORITY[c["donor"]])
            if best_key is None or key < best_key:
                best_key, best_row = key, c
        if best_row is not None:
            end_dates.append(best_row["end_date"])
            sources.append(best_row["donor"])
            matched_names.append(best_row["event"])
        else:
            end_dates.append(ev["start_date"] + pd.Timedelta(days=assumed_duration(ev["hazard_classes"])))
            sources.append("assumed")
            matched_names.append(None)

    out["end_date"] = end_dates
    out["end_date_source"] = sources
    out["donor_event"] = matched_names
    # Guard against donor end dates that precede the DRFA start (bad match or data error).
    bad = out["end_date"] < out["start_date"]
    out.loc[bad, "end_date"] = out.loc[bad].apply(
        lambda r: r["start_date"] + pd.Timedelta(days=assumed_duration(r["hazard_classes"])), axis=1
    )
    out.loc[bad, "end_date_source"] = "assumed"
    return out


def load_drfa_events_with_end_dates(drfa_path=None, aidr_path=None, ica_path=None) -> pd.DataFrame:
    """Full pipeline: locations -> events -> pooled ICA+AIDR end dates."""
    locations = load_drfa_locations(drfa_path)
    events = drfa_events(locations)
    donors = pd.concat(
        [donor_catalogue_from_ica(load_ica(ica_path)), donor_catalogue_from_aidr(load_aidr(aidr_path))],
        ignore_index=True,
    )
    return attach_end_dates(events, donors)
