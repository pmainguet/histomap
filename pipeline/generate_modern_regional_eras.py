"""Data-driven regional-era generator for macro chapters 6-9 (1500-present).
Unlike Task 4 Part A's hand-curated set, this creates a bare continent x
chapter node -- no research, no bespoke naming -- for every combination that
actually has at least one polity in it. Idempotent: rerunning reflects
whatever the dataset currently looks like."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"

# (macro_chapter_id, start, end) -- must match periods/macro_*.yaml Task 3 authored
MODERN_MACRO_CHAPTERS = [
    ("macro_early_modern_connections", 1500, 1800),
    ("macro_industrial_imperial_world", 1800, 1914),
    ("macro_world_wars_reordering", 1914, 1945),
    ("macro_contemporary_world", 1945, 2100),
]


def era_id(continent: str, chapter_id: str) -> str:
    return f"{continent}_{chapter_id.removeprefix('macro_')}_era"


def _overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def combinations_with_polities(
    polities: list[dict], macro_chapters: list[tuple[str, int, int]]
) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for polity in polities:
        continents = (polity.get("geography") or {}).get("continents") or []
        if not continents:
            continue
        p_start = polity["start"]
        p_end = polity.get("end") if polity.get("end") is not None else 2026
        for chapter_id, c_start, c_end in macro_chapters:
            if _overlap(p_start, p_end, c_start, c_end):
                for continent in continents:
                    found.add((continent, chapter_id))
    return found


def build_period(continent: str, chapter_id: str, start: int, end: int) -> dict:
    return {
        "id": era_id(continent, chapter_id),
        "canonical_name": f"{continent.replace('_', ' ').title()}, "
        f"{chapter_id.removeprefix('macro_').replace('_', ' ').title()}",
        "kind": "historical",
        "tier": "regional_era",
        "start": start,
        "end": end,
        "start_confidence": "low",
        "end_confidence": "low",
        "geography": {"continents": [continent]},
        "broader_periods": [chapter_id],
        "successors": [],
        "authority": "Histomap editorial: auto-generated continent x chapter node",
        "external_ids": {},
        "notes": "Auto-generated placeholder -- continent-level grain only, no "
        "historical research. A real sub-continental regional era (added by "
        "hand, the Task 4 Part A way) can replace this once someone wants to "
        "invest that research; see ONTOLOGY.md.",
        "source_urls": [],
    }


def load_polities() -> list[dict]:
    documents = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("timeline_role") == "period":
            continue
        documents.append(document)
    return documents


def main() -> None:
    polities = load_polities()
    combos = combinations_with_polities(polities, MODERN_MACRO_CHAPTERS)
    chapter_ranges = {chapter_id: (start, end) for chapter_id, start, end in MODERN_MACRO_CHAPTERS}
    for continent, chapter_id in sorted(combos):
        start, end = chapter_ranges[chapter_id]
        document = build_period(continent, chapter_id, start, end)
        path = PERIODS_DIR / f"{document['id']}.yaml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"wrote {len(combos)} auto-generated regional-era period files")


if __name__ == "__main__":
    main()
