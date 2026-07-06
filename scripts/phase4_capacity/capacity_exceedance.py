"""Phase 4: demand vs emergency-management capacity.

Confronts the DLI with capacity-side data (agency resourcing, interstate
deployment records, ADF call-outs, international assistance requests) to
estimate when demand plausibly exceeded capacity, and whether exceedance
frequency/duration is trending. Capacity data sources are not yet secured
— royal-commission exhibits, AFAC deployment records, and annual reports
are candidates; this module defines the target interface only.

Planned interface:
    capacity_proxies(sources_dir) -> daily/seasonal capacity panel
    exceedance_episodes(panel, capacity) -> episodes with severity
    exceedance_trend(episodes) -> trend statistics per tier
"""


def capacity_proxies(sources_dir):
    raise NotImplementedError("Phase 4")


def exceedance_episodes(panel, capacity):
    raise NotImplementedError("Phase 4")


def exceedance_trend(episodes):
    raise NotImplementedError("Phase 4")
