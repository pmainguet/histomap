"""Pipeline step: suggest a regional_era broader_period for each tier=period
record that doesn't have one yet, by continent + date-range overlap against
every tier=regional_era record. Writes a review queue; does not modify
periods/*.yaml directly."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"
REPORT_PATH = ROOT / "reports" / "regional_era_suggestions.jsonl"
SUMMARY_PATH = ROOT / "reports" / "regional_era_summary.md"


def overlap_years(a: tuple[int, int], b: tuple[int, int]) -> int:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    return max(0, hi - lo)


def rank_candidates(period: dict, candidates: list[dict]) -> list[dict]:
    period_continents = set((period.get("geography") or {}).get("continents") or [])
    period_range = (period["start"], period["end"])
    scored = []
    for candidate in candidates:
        candidate_continents = set((candidate.get("geography") or {}).get("continents") or [])
        if not (period_continents & candidate_continents):
            continue
        candidate_range = (candidate["start"], candidate["end"])
        years = overlap_years(period_range, candidate_range)
        if years <= 0:
            continue
        scored.append((years, candidate["id"], candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [candidate for _years, _id, candidate in scored]


def load_regional_eras() -> list[dict]:
    eras = []
    for path in sorted(PERIODS_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("tier") == "regional_era":
            eras.append(document)
    return eras


def main() -> None:
    regional_eras = load_regional_eras()
    suggestions = []
    unmatched = 0
    for path in sorted(PERIODS_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if document.get("tier", "period") != "period":
            continue
        if document.get("broader_periods"):
            continue  # already linked
        ranked = rank_candidates(document, regional_eras)
        if not ranked:
            unmatched += 1
            continue
        suggestions.append(
            {
                "period_id": document["id"],
                "canonical_name": document["canonical_name"],
                "top_suggestion": ranked[0]["id"],
                "alternatives": [r["id"] for r in ranked[1:3]],
            }
        )
    REPORT_PATH.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in suggestions) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        "# Regional-era suggestions\n\n"
        f"- Suggested: {len(suggestions)}\n"
        f"- Unmatched (no continent+date overlap with any regional era): {unmatched}\n"
        "\nUnmatched periods are not a bug -- after Task 4 Part B, coverage should be "
        "close to complete, but any period whose geography is unset, or whose dates "
        "fall entirely in a gap, will legitimately have no suggestion.\n",
        encoding="utf-8",
    )
    print(f"suggested {len(suggestions)}, unmatched {unmatched}")


if __name__ == "__main__":
    main()
