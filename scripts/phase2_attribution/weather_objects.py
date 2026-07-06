"""Phase 2: weather-object presence on high-demand days (Gadi).

Composites weather objects (fronts, lows, highs — TFB_Objects pipeline) on
top-DLI days. Composite domain per design decision 7: lon 105-180E, lat
45-8S; presence measured within regional boxes, never whole-domain flags
(they saturate). Requires Gadi (project gb02, env xp65) and
`assign_weatherfeature_coords` for the object files; run via qsub only —
see gadi/phase2_objects.pbs.

Planned interface:
    object_presence_daily(objects_dir, region_boxes) -> daily presence panel
    composite_top_days(panel, presence, n_days=50) -> per-object composites
"""


def object_presence_daily(objects_dir, region_boxes):
    raise NotImplementedError("Phase 2 (Gadi)")


def composite_top_days(panel, presence, n_days=50):
    raise NotImplementedError("Phase 2 (Gadi)")
