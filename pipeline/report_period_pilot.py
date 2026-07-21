"""Write a compact audit report for the historical-period pilot."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from build import load_all, load_period_links, load_periods

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "period_pilot_summary.md"


def main() -> None:
    periods = load_periods()
    links = load_period_links(periods, load_all())
    kinds = Counter(period.kind for period in periods)
    evidence = Counter(link.evidence for link in links)
    regions = Counter(
        continent
        for period in periods
        for continent in (period.geography.continents or ["unknown"])
    )
    lines = [
        "# Historical-period pilot",
        "",
        f"- Authority records: {len(periods)}",
        f"- Entity-period links: {len(links)}",
        f"- Period kinds: {', '.join(f'{key} {value}' for key, value in sorted(kinds.items()))}",
        f"- Regions: {', '.join(f'{key} {value}' for key, value in sorted(regions.items()))}",
        f"- Link evidence: {', '.join(f'{key} {value}' for key, value in sorted(evidence.items()))}",
        "",
        "## Review rules",
        "",
        "Periods are context records, not polities. `explicit` means the source directly names the",
        "relationship; `derived` means chronology and geography support it; `suggested` is not",
        "publication-ready. No link creates a polity parent/child relationship.",
        "",
        "## Records",
        "",
    ]
    for period in sorted(periods, key=lambda item: (item.start, item.canonical_name)):
        linked = [link.entity_id for link in links if link.period_id == period.id]
        lines.append(
            f"- **{period.canonical_name}** ({period.start}–{period.end}, {period.kind}); "
            f"linked entities: {', '.join(linked) if linked else 'none'}"
        )
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK  wrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
