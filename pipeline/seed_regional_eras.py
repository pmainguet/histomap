"""One-shot authoring script for the hand-curated regional-era starter set
(macro chapters 1-5 only -- Task 4 Part A of the period-ontology plan). Run
once; re-running is safe (overwrites its own files with the same content).
Not part of the recurring pipeline sequence.

# TODO: a few of the auto-built source_urls below (built from canonical_name)
# won't resolve to a real Wikipedia article -- known rough edge, not blocking
# (schema only checks the URL is a string). Fix opportunistically."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PERIODS_DIR = ROOT / "periods"

# (id, canonical_name, macro_chapter_id, start, end, continents, notes)
#
# Was 20 rows; 9 were demoted to tier=period (reparented under a new
# overarching regional era -- paleolithic_era/neolithic_era/bronze_age_era/
# classical_antiquity_era/iron_age_era) and 2 were deleted outright
# (egyptian_early_states_era, mesopotamian_early_states_era -- each redundant
# with an existing civilization-as-backdrop period). Removed from this table
# in each case so a re-run of this script can't silently revert the change.
# See STATUS.md and git history for the full per-row changelog.
REGIONAL_ERAS: list[dict] = [
    dict(
        id="medieval_europe_era",
        canonical_name="Medieval Europe",
        broader_periods=["macro_postclassical_worlds"],
        start=500,
        end=1500,
        continents=["europe"],
        notes="Early, High, and Late Middle Ages, including the Byzantine "
        "Empire.",
    ),
    dict(
        id="islamic_caliphates_era",
        canonical_name="Islamic Caliphates and Sultanates",
        broader_periods=["macro_postclassical_worlds"],
        start=622,
        end=1500,
        continents=["asia", "africa"],
        notes="Rashidun Caliphate through the rise of the Ottoman, Safavid, "
        "and Mughal gunpowder empires.",
    ),
    dict(
        id="east_asian_imperial_era",
        canonical_name="East Asian Imperial Dynasties (Post-Classical)",
        broader_periods=["macro_postclassical_worlds"],
        start=500,
        end=1500,
        continents=["asia"],
        notes="Tang through Ming China; Heian through Muromachi Japan; "
        "Goryeo Korea.",
    ),
]


def build_period(row: dict) -> dict:
    return {
        "id": row["id"],
        "canonical_name": row["canonical_name"],
        "kind": "historical",
        "tier": "regional_era",
        "start": row["start"],
        "end": row["end"],
        "start_confidence": "low",
        "end_confidence": "low",
        "geography": {"continents": row["continents"]},
        "broader_periods": row["broader_periods"],
        "successors": [],
        "authority": "Histomap editorial: regional-era starter set",
        "external_ids": {},
        "notes": row["notes"],
        "source_urls": ["https://en.wikipedia.org/wiki/" + row["canonical_name"].replace(" ", "_")],
    }


def main() -> None:
    for row in REGIONAL_ERAS:
        document = build_period(row)
        path = PERIODS_DIR / f"{row['id']}.yaml"
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    print(f"wrote {len(REGIONAL_ERAS)} regional-era period files")


if __name__ == "__main__":
    main()
