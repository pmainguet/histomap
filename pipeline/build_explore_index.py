"""Build-time step: precompute explore_index.json (the World zoom level's
data) from the period hierarchy. Server-served as a static file, same
pattern as periods.json/period_links.json -- no per-request computation."""

from __future__ import annotations

from pipeline.period_hierarchy import PeriodHierarchy


def build_explore_index(
    polities: list[dict], periods: list[dict], period_links: list[dict], top_n: int = 3
) -> list[dict]:
    hierarchy = PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)
    polities_by_id = {p["id"]: p for p in polities}
    entries = []
    for chapter_id in hierarchy.macro_chapters():
        chapter = next(p for p in periods if p["id"] == chapter_id)
        entity_ids = hierarchy.entities_under(chapter_id)
        top_ids = hierarchy.top_entities(chapter_id, limit=top_n)
        entries.append(
            {
                "id": chapter_id,
                "canonical_name": chapter["canonical_name"],
                "start": chapter["start"],
                "end": chapter["end"],
                "entity_count": len(entity_ids),
                "top_entities": [
                    {
                        "id": eid,
                        "canonical_name": polities_by_id[eid]["canonical_name"],
                        "start": polities_by_id[eid]["start"],
                        "end": polities_by_id[eid].get("end"),
                    }
                    for eid in top_ids
                ],
            }
        )
    return entries
