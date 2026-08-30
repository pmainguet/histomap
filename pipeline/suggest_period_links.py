"""Pipeline step: suggest a period_links.yaml entry for global/regional-tier
polities that don't have one yet. Writes a review queue; does not modify
period_links.yaml directly.

Geography match prefers historical_region overlap (finer-grained, ~23 regions)
over continent overlap (7 regions) when both sides have historical_regions set
-- continent-only matching was producing low-quality suggestions for broad
continents (e.g. abbasid_caliphate matched to chinese_empire_period purely
because both share the "asia" tag). Falls back to continent overlap when
either side lacks historical_regions -- most of the dataset still does."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.geography_overlap import geography_matches

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PERIODS_DIR = ROOT / "periods"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"
REPORT_PATH = ROOT / "reports" / "period_link_suggestions.jsonl"
SUMMARY_PATH = ROOT / "reports" / "period_link_suggestion_summary.md"

TIER_SPECIFICITY = {"period": 0, "regional_era": 1, "macro_chapter": 2}


def in_scope(polity: dict) -> bool:
    if polity.get("visibility_override") == "global":
        return True
    return polity.get("visibility_tier") in {"global", "regional"}


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return max(0, hi - lo)


def best_period_for_polity(polity: dict, periods: list[dict]) -> dict | None:
    polity_geo = polity.get("geography") or {}
    polity_range = (polity["start"], polity.get("end") if polity.get("end") is not None else 2026)
    candidates = []
    for period in periods:
        if not geography_matches(polity_geo, period.get("geography") or {}):
            continue
        period_range = (period["start"], period["end"])
        years = _overlap(polity_range, period_range)
        if years <= 0:
            continue
        specificity = TIER_SPECIFICITY.get(period.get("tier", "period"), 0)
        candidates.append((specificity, -years, period["id"], period))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def load_periods() -> list[dict]:
    return [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ]


def load_linked_polity_ids() -> set[str]:
    if not PERIOD_LINKS_PATH.exists():
        return set()
    links = yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8")) or []
    return {link["entity_id"] for link in links}


def main() -> None:
    periods = load_periods()
    already_linked = load_linked_polity_ids()
    suggestions = []
    in_scope_count = 0
    unmatched = 0
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        polity = yaml.safe_load(path.read_text(encoding="utf-8"))
        if polity.get("timeline_role") == "period":
            continue
        if not in_scope(polity):
            continue
        in_scope_count += 1
        if polity["id"] in already_linked:
            continue
        best = best_period_for_polity(polity, periods)
        if best is None:
            unmatched += 1
            continue
        suggestions.append(
            {
                "entity_id": polity["id"],
                "canonical_name": polity["canonical_name"],
                "suggested_period_id": best["id"],
                "suggested_tier": best.get("tier", "period"),
            }
        )
    REPORT_PATH.write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in suggestions) + "\n",
        encoding="utf-8",
    )
    SUMMARY_PATH.write_text(
        "# Polity to period-link suggestions\n\n"
        f"- In-scope polities (global/regional tier or visibility_override): {in_scope_count}\n"
        f"- Already linked: {in_scope_count - len(suggestions) - unmatched}\n"
        f"- Suggested: {len(suggestions)}\n"
        f"- Unmatched (no geography/date overlap with any period): {unmatched}\n",
        encoding="utf-8",
    )
    print(f"in-scope {in_scope_count}, suggested {len(suggestions)}, unmatched {unmatched}")


if __name__ == "__main__":
    main()
