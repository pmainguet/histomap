"""One-off remediation for ROADMAP.md's geography-gaps item: a handful of
`present_countries` entries use an ambiguous or simply wrong ISO code --
fixed by hand-mapping each specific record to its real modern-day country
code(s), rather than adding a blanket `historical_regions.py` table entry
for a code that doesn't mean one thing.

- **SU** (the Soviet Union's own historic ISO code) genuinely spans many
  different modern regions (Central Asia, West Asia, Eastern Europe, ...)
  depending on which constituent republic a record represents -- unlike YU
  (added to `historical_regions.py` directly; every YU-tagged record in this
  dataset really is Yugoslavia/a Yugoslav successor), a single "SU" table
  entry would be wrong for most of the records that carry it. Most
  SU-tagged Soviet republics already resolve fine via their OWN modern
  country code sitting alongside SU in `present_countries` (e.g. Georgian
  SSR: `[GE, SU]`) -- these are not touched. Only the 4 records left with
  SU as their SOLE, unresolved code (see STATUS.md) get corrected here.
- **CS** is doubly overloaded in real-world ISO history: it meant
  Czechoslovakia 1993-2003, then was reused for Serbia and Montenegro
  2003-2006. `second_czechoslovak_republic` (1938-1939, predating both eras)
  is the one record left with a bare, unresolved "CS" needing a real fix.
- `kingdom_of_tonga` was mistagged `TV` (Tuvalu) instead of `TO` (Tonga) --
  a real data bug found live while investigating this same country-code
  gap, fixed here as a bonus since it was already being looked at directly.

Locks `geography` via `manual_overrides` after fixing -- these are
hand-verified corrections for records where Wikidata's own P17 chain keeps
resolving to the ambiguous/wrong code, so an unguarded future
`pipeline.enrich_geography` re-run (its main pass overwrites unlocked
geography unconditionally) would otherwise silently revert them. Also fills
`continents` directly from the corrected country code(s), via the same
reverse ISO2 -> continents index `enrich_geography.py`'s own
`backfill_continents_from_present_countries()` uses, rather than depending
on run order between the two scripts.

Idempotent -- re-running only touches a record whose `present_countries`
doesn't already match the correction.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"

CORRECTIONS: dict[str, list[str]] = {
    # Soviet-era records left with only the ambiguous "SU" -- corrected to
    # the modern country their own historical territory actually maps to.
    "khorezm_socialist_soviet_republic": ["UZ"],
    "moldavian_soviet_socialist_republic": ["MD"],
    "socialist_soviet_republic_of_armenia": ["AM"],
    "socialist_soviet_republic_of_georgia": ["GE"],
    # The one record left with a bare, unresolved "CS".
    "second_czechoslovak_republic": ["CZ", "SK"],
    # Real data bug: TV (Tuvalu) instead of TO (Tonga).
    "kingdom_of_tonga": ["TO"],
}


def main() -> dict[str, int]:
    # Imported locally (not at module level) so a test can patch
    # pipeline.seed_present_countries_from_name.load_iso2_to_continents and
    # have it actually take effect -- a top-level import here would bind
    # the name into this module's own namespace at import time instead.
    from pipeline.seed_present_countries_from_name import load_iso2_to_continents

    iso2_to_continents = load_iso2_to_continents()
    fixed = 0
    for polity_id, countries in CORRECTIONS.items():
        path = POLITIES_DIR / f"{polity_id}.yaml"
        if not path.exists():
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        geography = document.get("geography") or {}
        if geography.get("present_countries") == countries:
            continue
        geography["present_countries"] = countries
        continents = sorted({c for code in countries for c in iso2_to_continents.get(code, [])})
        if continents:
            geography["continents"] = continents
        document["geography"] = geography
        manual_overrides = set(document.get("manual_overrides", []))
        manual_overrides.add("geography")
        document["manual_overrides"] = sorted(manual_overrides)
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        fixed += 1
    return {"fixed": fixed}


if __name__ == "__main__":
    result = main()
    print(f"fixed: {result['fixed']}")
