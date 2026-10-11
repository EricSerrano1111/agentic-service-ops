"""Brief labels -> the system's route enums, in code (plan.md, "Label mapping").

The system's `Route` (packages/schemas/src/schemas/routing.py) has six values. The brief's
`expected_route` uses the same six strings; the mapping is written out anyway so that a
brief value with no system counterpart fails loudly instead of passing through. No label
is mapped by judgement. Mapping `intent` to the specialists' request schemas is Prompt R's
job, not this module's.
"""

from __future__ import annotations

ROUTE_MAP: dict[str, str] = {
    "reporting": "reporting",
    "sentiment": "sentiment",
    "forecast": "forecast",
    "multi_domain": "multi_domain",
    "ambiguous": "ambiguous",
    "out_of_scope": "out_of_scope",
}

#: What each brief category must route to, when a category fixes the route. `None` means the
#: route is the item's own area (checked against `intent.area`).
CATEGORY_ROUTE: dict[str, str | None] = {
    "clear_reporting": "reporting",
    "clear_sentiment": "sentiment",
    "clear_forecast": "forecast",
    "underspecified": None,
    "ambiguous": "ambiguous",
    "multi_domain": "multi_domain",
    "out_of_scope": "out_of_scope",
    "near_miss": "out_of_scope",
    "technician": "reporting",
    "filtered": None,  # reporting or sentiment, by intent.area
    "unsupported_in_area": None,  # the area it fits, by intent.area
}

#: Categories of the routing "clear" stratum (5 items per area).
CLEAR_CATEGORIES = ("clear_reporting", "clear_sentiment", "clear_forecast")


def system_route(expected_route: str) -> str:
    try:
        return ROUTE_MAP[expected_route]
    except KeyError:
        raise ValueError(f"brief route {expected_route!r} has no system route") from None
