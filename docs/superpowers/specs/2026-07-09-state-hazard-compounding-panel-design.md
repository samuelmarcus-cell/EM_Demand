# State×hazard compounding panel — design

**Date:** 2026-07-09 · **Status:** for user review · **Depends on:** Phase 1
panel (frozen recipe, no sub_flood) and the per-state fire metrics already in
`demand_metrics_daily`. No Gadi anywhere in this analysis.

## 1. The scientific question

> **Do severe hazards spatially compound across Australian states more often
> than independence predicts — and is cross-hazard compounding (different
> hazards in different states on the same day) a real, beyond-chance
> phenomenon, suggesting connection at the synoptic scale?**

The object of study is **hazard co-occurrence, not demand**. Fire hotspots
and cyclone tracks quantify the hazard, agnostic of exposure and
vulnerability. EM demand is the *motivation* — spatial compounding is what
would strain shared national arrangements — but this panel does not measure
demand and its language never claims to. The exceedance flags are "high
hazard load", never "high demand". (DRFA — the costing of actualised
impact, with exposure and vulnerability baked in — is not a hazard and
never sits on the hazard axis; see §2.)

Falsifiable in both directions, each outcome informative:

- **Same-hazard compounding exceeds chance:** hazard extremes are spatially
  organised beyond state boundaries — the assumption that a stretched state
  can borrow from a quiet neighbour fails on precisely the worst days. This
  is the Australian analogue of Gauthier & Bevacqua (2026, npj Nat. Hazards)
  on hazard-activity series rather than fire-weather indices.
- **Cross-hazard compounding exceeds chance:** *different* hazards cluster
  in time across space, pointing at synoptic-scale organisation (e.g. a
  configuration simultaneously supporting TC activity in the north and fire
  weather in the south). The composites pilot showed the hazard pathways
  have distinct synoptic fingerprints; whether those distinct drivers
  co-occur beyond chance is the open question. Whether co-occurring days
  are one connected configuration or coincidence is the *follow-on*
  composite analysis (out of scope here; this panel decides whether that
  analysis has a subject).
- **Neither exceeds chance:** state hazard loads are effectively
  independent; the compounding framing needs rethinking. Must be known
  before anything is built on top.

**Pre-registered expectations (written before any result):** same-hazard
fire compounding will exceed chance strongly — synoptic systems are larger
than states; this is near-certain and serves as the positive control on the
machinery. Cross-hazard compounding is genuinely uncertain — either outcome
is the finding.

**What it adds over existing results:** the DLI is national. It can say
"the nation is loaded" but not *where* — it cannot distinguish one giant
fire day from three states in trouble at once. This panel is the missing
spatial axis, and the substrate the compounding chapter runs on.

## 2. The panel

One row per (date, state, layer), 1979–present. Seven states: NSW, VIC,
QLD, SA, WA, TAS, NT. ACT hotspots fall inside the NSW series under the
existing state-attribution conventions of `demand_metrics_daily` — stated,
not hidden.

**Hazard layers** (the co-occurrence test runs on these and only these):

- **fire** — per-state analogue of `sub_fire`, from the per-state workload
  metrics already computed in `demand_metrics_daily` (concurrent_burden,
  ignition_load, growth_load, frp_load per state). Each metric is
  percentile-ranked within (state, confidence_tier, calendar month) — the
  project's standard machinery: a 1985 SA day ranks against 1980s SA days,
  never against satellite-era data or another state. `state_fire` = mean of
  available metric percentiles, exactly parallel to the national recipe.
  Border-straddling fires count in both adjacent states' series —
  deliberate: both states' agencies respond to such fires.
- **tc** — a cyclone loads a state on a day when any best-track point that
  day lies within **300 km of that state's coastline** at cyclone intensity.
  Why 300 km: approximately the gale-force radius of a large Australian TC
  and the scale of pre-landfall preparation zones. Sensitivity check at
  200 km and 400 km, reported never tuned. `state_tc` = percentile (within
  state, month) of the max wind among in-range track points that day —
  parallel to the national max-with-severity logic. No tier dimension (the
  best-track record has one era).

**Impact layer** (different in kind; never on the hazard axis):

- **drfa** — count of the state's LGAs newly under DRFA activation,
  percentile-ranked within (state, calendar month). Available 2006– only;
  NaN before, per the availability discipline. Used solely for the §3
  impact check.

**Flags:** `high_load = percentile ≥ 0.95` per state×hazard cell. The 0.95
is inherited from the project-wide convention (DLI high-demand days, SWT
attribution, composite strata all use within-group 95th), not invented
here; sensitivity at 0.90 and 0.975 is reported alongside every headline
number. Daily summary columns: `n_states_fire`, `n_states_tc`,
`n_cells_high`, and `cross_hazard` — True when at least one state is high
on fire and at least one *different* state is high on tc on the same day
(the spatially compounding case). A single state high on both hazards at
once is a different phenomenon (co-located compounding), counted
separately as `multi_hazard_state` and reported descriptively, not tested.

## 3. The statistical test — shuffle null

Adapted from Gauthier & Bevacqua's spatial-shuffle design:

1. **Observed:** historical frequencies of the daily count of
   simultaneously high cells — days with ≥2, ≥3, … states high on fire;
   same for tc; frequency of cross-hazard days.
2. **Null (1,000 shuffles):** each state×hazard series has its **years
   shuffled independently** of the other states'. Fire series shuffle
   within confidence tier (so data-era artefacts cannot fake a signal);
   tc series shuffle across the whole period (single-era record, §2).
   Each series keeps its own seasonality (a shuffled year is a whole
   calendar year) and its own within-season persistence; the only thing
   destroyed is whether states' bad periods line up in time.
3. **Result:** excess ratios — "days with ≥3 states under high fire load
   occur N× more often than under independence" — with uncertainty from
   the null spread (report the null's 2.5th–97.5th percentile band). One
   ratio per compounding type (fire, tc, cross-hazard) × threshold
   sensitivity.

**Why whole-year shuffling:** day-shuffling destroys persistence and makes
the null trivially easy to beat; month-shuffling cuts ENSO years in half.
Year blocks are the conservative choice — a climate driver that
synchronises whole seasons across states partly survives in the null, so
the excess that remains is same-day/synoptic-scale organisation, not
shared climate background. Consequence, stated up front: the headline
ratios are underestimates of total co-occurrence. That is the right
direction to err.

**Impact check (descriptive only, no ratio):** compare the frequency of
multi-state DRFA activation in the 30 days following panel-flagged
multi-state hazard days vs following quiet days (2006– only). If hazard
compounding never manifests in actualised impact, that is evidence against
the panel's relevance and is reported either way. The 30-day window
reflects DRFA's known days-to-weeks lag; sensitivity at 14 and 60 days.

## 4. Code, outputs, figures

House pattern — pure logic in importable modules, thin runners, unit tests:

- `scripts/state_panel.py` — pure functions: per-state fire percentiles,
  TC-to-state attribution, DRFA state rollup, flags, daily summary.
- `scripts/phase3_compounding/compound_demand.py` — replaces the current
  NotImplemented stubs: year-block shuffle null, excess ratios, impact
  check. Internal naming says "hazard load", not "demand", per §1.
- `scripts/run_state_panel.py` → `data/derived/state_hazard_panel.parquet`;
  `scripts/run_compounding.py` → `data/derived/compounding_ratios.csv` +
  plain-language result table printed.
- All local, fast (seconds–minutes). **No Gadi.**

Figures (`R/compounding.R`, house style; README updated):
- `fig_compounding_null.png` — observed vs null distributions of
  simultaneous state counts, one panel per compounding type (headline).
- `fig_state_cooccurrence.png` — state×state high-load co-occurrence
  matrix.
- `fig_compound_days_timeline.png` — timeline strip of top compound days
  labelled with state and hazard.

**Face-validity gate on delivery (blocking):** Black Summer days must show
NSW+VIC(+SA) simultaneously high on fire; TC Yasi (Feb 2011) must flag QLD
under tc, not fire. If the panel cannot recover the landmark events,
nothing downstream is interpretable.

## 5. Testing & validation

- Unit tests on synthetic data with known answers: perfectly synchronised
  state series → ratio ≫ 1; independently generated series → ratio ≈ 1
  (the null machinery must prove itself on signal-free data); TC
  attribution against known landfalls (Yasi→QLD, Tracy→NT, Vance→WA).
- Percentile machinery reused from `scripts/dli.py` where possible, not
  reimplemented.
- Availability discipline: every cell NaN outside its source window;
  `confidence_tier` carried on every fire row.

## 6. Out of scope

Trend-over-time claims (tier boundaries make them treacherous — parked,
not denied); the follow-on composite analysis of cross-hazard days (own
design, contingent on this panel finding such days exceed chance); any
change to the frozen DLI recipe; temporal/sequential compounding
(Richardson-style season overlap); flood (component abandoned 2026-07-09;
no flood layer is possible and none is faked).

## 7. Replication note

Per the project's standing rule, the implementation and writeup must let
the user rebuild this analysis himself: every threshold above carries its
justification (0.95 inherited; 300 km gale radius; year-block shuffle
conservatism), every alternative considered is recorded with the reason
for rejection, and the runners print plain-language tables rather than
bare statistics.
