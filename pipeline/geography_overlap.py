"""Shared geography- and date-overlap helpers used by the suggestion queues
(suggest_period_links.py, suggest_regional_eras.py) and by
build_explore_tree.py. Historical_region overlap (finer-grained, ~23 regions)
is preferred over continent overlap (7 regions) when both sides have
historical_regions set -- continent-only matching produces low-quality
matches for broad continents (e.g. an Iraqi caliphate matching a Chinese
empire purely because both share the "asia" tag). Falls back to continent
overlap when either side lacks historical_regions -- most of the dataset
still does."""

from __future__ import annotations


def overlap_years(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Years of overlap between two [start, end) ranges; 0 if disjoint or touching."""
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0, hi - lo)


def geography_matches(source_geo: dict, candidate_geo: dict) -> bool:
    """Historical_region overlap when both sides have it (tighter, preferred);
    continent overlap otherwise. An empty candidate continents list means
    deliberately global (a macro chapter) -- always eligible; see ONTOLOGY.md's
    tier-scoped geography-emptiness rule."""
    candidate_continents = set(candidate_geo.get("continents") or [])
    if not candidate_continents:
        return True
    source_regions = set(source_geo.get("historical_regions") or [])
    candidate_regions = set(candidate_geo.get("historical_regions") or [])
    if source_regions and candidate_regions:
        return bool(source_regions & candidate_regions)
    source_continents = set(source_geo.get("continents") or [])
    return bool(source_continents & candidate_continents)
