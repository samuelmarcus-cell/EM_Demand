"""Phase 3: compound and sequential demand episodes.

Uses the Phase 1 subindices (sub_fire, sub_tc, sub_drfa, sub_tfb) to
identify days and multi-week episodes where demand stacks across hazards
(concurrent compounding: e.g. Jan 2013 fires + TC Narelle) or across time
(sequential compounding: recovery from one event overlapping response to
the next, via DRFA event windows). Outputs an episode table with duration,
hazard mix, peak DLI, and inter-episode recovery gaps.

Planned interface:
    demand_episodes(panel, dli_threshold_pct=0.90, min_gap_days=7) -> episodes
    hazard_cooccurrence(panel) -> subindex joint-exceedance matrix
    recovery_gaps(episodes) -> gap distribution per region/era
"""


def demand_episodes(panel, dli_threshold_pct=0.90, min_gap_days=7):
    raise NotImplementedError("Phase 3")


def hazard_cooccurrence(panel):
    raise NotImplementedError("Phase 3")


def recovery_gaps(episodes):
    raise NotImplementedError("Phase 3")
