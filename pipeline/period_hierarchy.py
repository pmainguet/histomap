"""Read-side query layer over the period tier hierarchy (periods/*.yaml +
period_links.yaml + polities/*.yaml). This is what a future timeline UI/API
should import instead of re-deriving broader_periods/period_links traversal
itself."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"
POLITIES_DIR = ROOT / "polities"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"


class PeriodHierarchy:
    def __init__(
        self, periods: list[dict], period_links: list[dict], polities: list[dict]
    ) -> None:
        self._periods = {p["id"]: p for p in periods}
        self._children: dict[str, list[str]] = {}
        for period in periods:
            for parent_id in period.get("broader_periods") or []:
                self._children.setdefault(parent_id, []).append(period["id"])
        for parent_id, child_ids in self._children.items():
            child_ids.sort(key=lambda cid: self._periods[cid]["start"])
        self._direct_links: dict[str, list[str]] = {}
        for link in period_links:
            self._direct_links.setdefault(link["period_id"], []).append(link["entity_id"])
        self._polities = {p["id"]: p for p in polities}

    def ancestors(self, period_id: str) -> list[str]:
        period = self._periods[period_id]  # KeyError on unknown id, by design
        chain: list[str] = []
        seen = {period_id}
        current = period
        while current.get("broader_periods"):
            parent_id = current["broader_periods"][0]
            if parent_id in seen:
                raise ValueError(f"broader_periods cycle detected at {parent_id!r}")
            seen.add(parent_id)
            chain.append(parent_id)
            current = self._periods[parent_id]
        return list(reversed(chain))

    def children(self, period_id: str) -> list[str]:
        return list(self._children.get(period_id, []))

    def entities_under(self, period_id: str) -> list[str]:
        entities: set[str] = set(self._direct_links.get(period_id, []))
        stack = list(self._children.get(period_id, []))
        seen_periods = {period_id}
        while stack:
            current_id = stack.pop()
            if current_id in seen_periods:
                continue
            seen_periods.add(current_id)
            entities.update(self._direct_links.get(current_id, []))
            stack.extend(self._children.get(current_id, []))
        return list(entities)

    def top_entities(self, period_id: str, limit: int) -> list[str]:
        entity_ids = self.entities_under(period_id)

        def sort_key(entity_id: str) -> tuple[float, str]:
            polity = self._polities.get(entity_id, {})
            return (-polity.get("prominence_score", 0), entity_id)

        return sorted(entity_ids, key=sort_key)[:limit]

    def macro_chapters(self) -> list[str]:
        chapters = [p for p in self._periods.values() if p.get("tier") == "macro_chapter"]
        chapters.sort(key=lambda p: p["start"])
        return [p["id"] for p in chapters]


def load() -> PeriodHierarchy:
    periods = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ]
    period_links = (
        yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8"))
        if PERIOD_LINKS_PATH.exists()
        else []
    ) or []
    polities = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(POLITIES_DIR.glob("*.yaml"))
    ]
    return PeriodHierarchy(periods=periods, period_links=period_links, polities=polities)


if __name__ == "__main__":
    hierarchy = load()
    total_entities = 0
    for chapter_id in hierarchy.macro_chapters():
        count = len(hierarchy.entities_under(chapter_id))
        total_entities += count
        top = hierarchy.top_entities(chapter_id, limit=3)
        print(f"{chapter_id}: {count} linked entities, top 3: {top}")
    if total_entities == 0:
        print(
            "\nAll counts are 0 -- expected today. The 117 pre-existing periods aren't "
            "linked into the tier hierarchy yet (see reports/regional_era_suggestions.jsonl "
            "and reports/period_link_suggestions.jsonl -- both are human-review queues, "
            "never auto-applied). This will fill in as those queues get worked."
        )
