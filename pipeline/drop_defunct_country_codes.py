"""One-off cleanup: drop dissolved-state ISO codes (SU/Soviet Union,
CS/Czechoslovakia-then-Serbia&Montenegro, DD/East Germany) from
present_countries wherever a real, still-existing country code already
sits alongside them -- found live, 7 September 2026, via a user report
that "Soviet Union" showed up in /explore's present-countries picker next
to "Russia".

present_countries is meant to answer "which modern country is this
historical territory in today" -- a dissolved state is never a valid
answer to that question, so these codes should never have been offered
as choices at all (see server/app.py's DEFUNCT_COUNTRY_CODES, which now
excludes them from the picker going forward). This script cleans up the
data side: every affected record already carries its real modern code(s)
alongside the defunct one (e.g. Georgian SSR: [GE, SU]) EXCEPT
gorno_altai_autonomous_soviet_socialist_republic, whose present_countries
was bare `[SU]` -- Gorno-Altai is part of the modern Altai Republic,
itself part of Russia, so that one gets a hand-verified `[RU]` rather
than a blanket "SU always means Russia" assumption (most SU-tagged
records here are Armenia, Georgia, Ukraine, etc. -- NOT Russia; see
pipeline/fix_ambiguous_country_codes.py's docstring for why a single
SU->RU table entry would be wrong for most of them).

Deliberately does NOT touch YU (Yugoslavia) -- historical_regions.py's
own docstring already established every YU-tagged record in this dataset
genuinely is Yugoslavia/a Yugoslav successor, no ambiguity, so YU stays a
legitimate present_countries code, unlike SU/CS/DD here.

Idempotent -- re-running only touches a record that still has the
cleanup to do."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

DEFUNCT_CODES = {"SU", "CS", "DD"}
# The one record left with a bare, unresolved defunct code after dropping
# it from everywhere it sits alongside a real one.
BARE_CODE_CORRECTIONS: dict[str, list[str]] = {
    "gorno_altai_autonomous_soviet_socialist_republic": ["RU"],
}


def _clean_countries(countries: list[str]) -> list[str]:
    remaining = [code for code in countries if code not in DEFUNCT_CODES]
    return remaining if remaining else countries


def _apply(directory: Path) -> int:
    fixed = 0
    for path in sorted(directory.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        geography = document.get("geography") or {}
        countries = geography.get("present_countries") or []
        if not any(code in DEFUNCT_CODES for code in countries):
            continue
        record_id = document.get("id", path.stem)
        updated = BARE_CODE_CORRECTIONS.get(record_id) or _clean_countries(countries)
        if updated == countries:
            continue
        geography["present_countries"] = sorted(set(updated))
        document["geography"] = geography
        manual_overrides = set(document.get("manual_overrides", []))
        manual_overrides.add("geography")
        document["manual_overrides"] = sorted(manual_overrides)
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        fixed += 1
    return fixed


def main(root: Path = ROOT) -> dict[str, int]:
    return {
        "polities_fixed": _apply(root / "polities"),
        "periods_fixed": _apply(root / "periods"),
    }


if __name__ == "__main__":
    result = main()
    print(f"polities fixed: {result['polities_fixed']}; periods fixed: {result['periods_fixed']}")
