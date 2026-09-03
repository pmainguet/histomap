"""One-off fix for ROADMAP.md's geography-gaps item: two name clusters
among the still-gapped records that no existing signal can resolve --
neither has a usable P17 chain, direct P30 claim, or centroid (confirmed
exhausted, see STATUS.md), and neither matches
`seed_present_countries_from_name.py`'s demonym table ("taifa" and "saxe"
aren't country/demonym words, they're a polity-type title and a dynastic
name respectively).

- Every remaining **"Taifa of *"** record (11th-century Iberia, the petty
  kingdoms al-Andalus fragmented into after the Caliphate of Cordoba's
  collapse) -- all but one are Spain; Taifa of Tavira sits on the Algarve
  coast, now Portugal. Verified by hand against each record's own Wikidata
  label, not guessed from the name pattern alone.
- Every remaining **"Saxe-*"** record (the Ernestine Saxon duchies,
  present-day Germany).

Locks `geography` via `manual_overrides` -- same reasoning as
`fix_ambiguous_country_codes.py`: these are hand-verified, not re-derivable
from any automated signal, so an unguarded future `pipeline.enrich_geography`
re-run would otherwise leave them as-is anyway (no P17/P30/centroid to
overwrite them WITH), but locking documents the correction is deliberate.

Idempotent -- re-running only touches a record whose `present_countries`
doesn't already match.
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"

CORRECTIONS: dict[str, list[str]] = {
    "taifa_of_arjona": ["ES"],
    "taifa_of_constantina_and_hornachuelos": ["ES"],
    "taifa_of_guadix_and_baza": ["ES"],
    "taifa_of_huesca": ["ES"],
    "taifa_of_jaen": ["ES"],
    "taifa_of_lorca_q104192614": ["ES"],
    "taifa_of_mallorca_q104178598": ["ES"],
    "taifa_of_menorca": ["ES"],
    "taifa_of_murcia_q921067": ["ES"],
    "taifa_of_murviedro_and_sagunto": ["ES"],
    "taifa_of_purchena": ["ES"],
    "taifa_of_rueda": ["ES"],
    "taifa_of_segura": ["ES"],
    "taifa_of_seville": ["ES"],
    "taifa_of_tavira": ["PT"],
    "taifa_of_tejada": ["ES"],
    "saxe_coburg_eisenach": ["DE"],
    "saxe_marksuhl": ["DE"],
    "saxe_zeitz": ["DE"],
}


def main() -> dict[str, int]:
    # Imported locally -- see fix_ambiguous_country_codes.py's identical
    # comment for why (test patchability).
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
