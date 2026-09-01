"""Regression tests for consolidation_review_queue()'s suggested_decision
logic in server/app.py.

Each test below is a real example found live during identity-review work:
a false positive or false negative that got root-caused and fixed. Add a
case here whenever a new one turns up, so the fix can't silently regress
the next time the scoring logic is touched.
"""

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from server.app import create_app

WEB_FILES = (
    "explore.html", "explore.js", "explore_timeline.js", "explore_details.js",
    "geological_epochs.js", "timeline_scale.js", "lane_packing.js", "common.js",
    "type_review.html", "styles.css",
    "type_review.js", "subdivision_review.js",
    "subdivision_review.html",
    "reviews.html", "reviews.js", "consolidation_review.html", "consolidation_review.js",
    "review_build.js",
)

BASE = {
    "entity_type": "polity", "entity_type_confidence": "high",
    "start_confidence": "low", "end_confidence": "low",
    "sources": ["wikidata"], "eligibility": "accepted",
}


def build_app(root: Path, polities: list[dict], relationships: list[dict] | None = None) -> TestClient:
    """Spin up a minimal histomap server against `root`, seeded with
    `polities` and (optionally) a Wikidata relationship cache."""
    (root / "web").mkdir()
    (root / "reports").mkdir()
    (root / "polities").mkdir()
    (root / "periods").mkdir()
    (root / "sources").mkdir()
    (root / "sources" / "wikidata_country_metadata.json").write_text("{}", encoding="utf-8")
    (root / "sources" / "wikidata_relationships.json").write_text(
        json.dumps(relationships or []), encoding="utf-8"
    )
    (root / "sources" / "wikidata_direct_types.json").write_text("{}", encoding="utf-8")
    for name in WEB_FILES:
        (root / "web" / name).write_text(name, encoding="utf-8")
    (root / "data.json").write_text("[]", encoding="utf-8")
    (root / "transitions.json").write_text("[]", encoding="utf-8")
    (root / "periods.json").write_text("[]", encoding="utf-8")
    (root / "period_links.json").write_text("[]", encoding="utf-8")
    (root / "period_links.yaml").write_text("[]\n", encoding="utf-8")
    for polity in polities:
        (root / "polities" / f"{polity['id']}.yaml").write_text(
            yaml.safe_dump(polity), encoding="utf-8"
        )
    return TestClient(create_app(root))


class ConsolidationSuggestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def suggestion_for(
        self, reviewed_id: str, candidate_id: str, polities: list[dict], relationships=None
    ) -> str | None:
        client = build_app(self.root, polities, relationships)
        queue = client.get("/api/consolidation-reviews", params={"limit": 100}).json()["items"]
        row = next((item for item in queue if item["id"] == reviewed_id), None)
        self.assertIsNotNone(row, f"{reviewed_id} did not reach the consolidation queue")
        candidate = next((c for c in row["candidates"] if c["id"] == candidate_id), None)
        self.assertIsNotNone(candidate, f"{candidate_id} was not a candidate for {reviewed_id}")
        return candidate["suggested_decision"]

    def test_syrian_arab_republic_phase_of_syria(self) -> None:
        # Syria's own Wikidata aliases genuinely include "Syrian Arab
        # Republic" -- exact_name_match, target dates contain source.
        polities = [
            {**BASE, "id": "syria", "canonical_name": "Syria", "external_ids": {"wikidata": "Q858"},
             "names": {"aliases_en": "Syrian Arab Republic"}, "start": 1920, "end": None,
             "prominence_score": 40, "geography": {"present_countries": ["SY"]}},
            {**BASE, "id": "syrian_arab_republic", "canonical_name": "Syrian Arab Republic",
             "external_ids": {"wikidata": "Q131404661"}, "start": 1963, "end": 2024,
             "prominence_score": 20, "geography": {"present_countries": ["SY"]}},
        ]
        self.assertEqual(self.suggestion_for("syrian_arab_republic", "syria", polities), "phase_of")

    def test_french_first_republic_candidate_phase_of_france(self) -> None:
        # Reverse direction: the REVIEWED entity (France) is the broad
        # continuous polity; the CANDIDATE (French First Republic) is the
        # bounded historical phase. Only ever a *candidate* for another
        # entity if its own prominence_score is >= the reviewed entity's
        # (the queue only offers more-or-equally-prominent candidates) --
        # true in the real data (French First Republic 50.19 > France
        # 44.97), reproduced here rather than picked arbitrarily.
        polities = [
            {**BASE, "id": "france", "canonical_name": "France", "external_ids": {"wikidata": "Q142"},
             "start": 481, "end": None, "prominence_score": 45, "geography": {"present_countries": ["FR"]}},
            {**BASE, "id": "french_first_republic", "canonical_name": "French First Republic",
             "external_ids": {"wikidata": "Q58296"}, "names": {"aliases_en": "France"},
             "start": 1792, "end": 1804, "prominence_score": 50, "geography": {"present_countries": ["FR"]}},
        ]
        self.assertEqual(
            self.suggestion_for("france", "french_first_republic", polities), "candidate_phase_of"
        )

    def test_yugoslavia_regime_of_place_with_finite_end(self) -> None:
        # "Federal People's Republic of Yugoslavia" reads as "<regime type>
        # of Yugoslavia" and has a finite end (1963) -- a genuine completed
        # phase, no exact alias needed.
        polities = [
            {**BASE, "id": "yugoslavia", "canonical_name": "Yugoslavia", "external_ids": {"wikidata": "Q36704"},
             "start": 1918, "end": 1992, "prominence_score": 40, "geography": {"present_countries": ["RS", "YU"]}},
            {**BASE, "id": "federal_peoples_republic_of_yugoslavia",
             "canonical_name": "Federal People's Republic of Yugoslavia",
             "external_ids": {"wikidata": "Q1290149"}, "start": 1945, "end": 1963,
             "prominence_score": 20, "geography": {"present_countries": ["RS"]}},
        ]
        self.assertEqual(
            self.suggestion_for("federal_peoples_republic_of_yugoslavia", "yugoslavia", polities),
            "phase_of",
        )

    def test_realm_of_new_zealand_open_ended_regime_of_place_not_suggested(self) -> None:
        # "Realm of New Zealand" also reads as "<X> of New Zealand", but
        # unlike Yugoslavia's regime, it's still open-ended (no finite
        # end) -- the OPPOSITE relationship (a broader container, not a
        # completed phase). With no Wikidata relationship data either, no
        # signal should confidently fire.
        polities = [
            {**BASE, "id": "new_zealand", "canonical_name": "New Zealand", "external_ids": {"wikidata": "Q664"},
             "start": 1841, "end": None, "prominence_score": 40, "geography": {"present_countries": ["NZ"]}},
            {**BASE, "id": "realm_of_new_zealand", "canonical_name": "Realm of New Zealand",
             "external_ids": {"wikidata": "Q889033"}, "start": 1983, "end": None,
             "prominence_score": 20, "geography": {"present_countries": ["NZ"]}},
        ]
        self.assertIsNone(self.suggestion_for("realm_of_new_zealand", "new_zealand", polities))

    def test_realm_of_new_zealand_documented_part_of(self) -> None:
        # New Zealand's own Wikidata P361 ("part of") claim names Realm of
        # New Zealand directly -- should suggest candidate_part_of (New
        # Zealand is part of the Realm), not phase_of.
        polities = [
            {**BASE, "id": "new_zealand", "canonical_name": "New Zealand", "external_ids": {"wikidata": "Q664"},
             "start": 1841, "end": None, "prominence_score": 40, "geography": {"present_countries": ["NZ"]}},
            {**BASE, "id": "realm_of_new_zealand", "canonical_name": "Realm of New Zealand",
             "external_ids": {"wikidata": "Q889033"}, "start": 1983, "end": None,
             "prominence_score": 20, "geography": {"present_countries": ["NZ"]}},
        ]
        relationships = [{"source": "Q664", "property": "P361", "target": "Q889033"}]
        self.assertEqual(
            self.suggestion_for("realm_of_new_zealand", "new_zealand", polities, relationships),
            "candidate_part_of",
        )

    def test_czechoslovak_socialist_republic_phase_of_wins_over_part_of(self) -> None:
        # Czechoslovak Socialist Republic has a direct P361 claim to
        # Czechoslovakia AND its own dates nest cleanly inside
        # Czechoslovakia's broader span, with a finite end -- that
        # combination should win as phase_of, not the plain part_of
        # fallback the raw P361 claim would otherwise suggest. The alias
        # "Socialist Republic of Czechoslovakia" is real data (not just a
        # test fixture convenience) -- it's what actually puts this pair in
        # the queue's candidate pool at all, via the shared "czechoslovakia"
        # token.
        polities = [
            {**BASE, "id": "czechoslovakia", "canonical_name": "Czechoslovakia",
             "external_ids": {"wikidata": "Q33946"}, "start": 1918, "end": 1992,
             "prominence_score": 48, "geography": {"present_countries": ["CZ", "SK"]}},
            {**BASE, "id": "czechoslovak_socialist_republic",
             "canonical_name": "Czechoslovak Socialist Republic",
             "names": {"aliases_en": "Socialist Republic of Czechoslovakia"},
             "external_ids": {"wikidata": "Q853348"}, "start": 1948, "end": 1990,
             "prominence_score": 42, "geography": {"present_countries": ["CZ", "SK"]}},
        ]
        relationships = [{"source": "Q853348", "property": "P361", "target": "Q33946"}]
        self.assertEqual(
            self.suggestion_for(
                "czechoslovak_socialist_republic", "czechoslovakia", polities, relationships
            ),
            "phase_of",
        )

    def test_west_virginia_still_open_ended_withholds_suggestion(self) -> None:
        # West Virginia seceded from Virginia in 1863 and both states have
        # coexisted separately ever since -- a partition, not a phase. Its
        # name has the same "<qualifier> <place>" shape as a genuine regime
        # name (Francoist Spain, Nazi Germany), so the naming pattern alone
        # can't rule out a phase relationship -- but West Virginia is still
        # open-ended (no finite end), which real regime names almost never
        # are, so the algorithm withholds rather than guessing either way.
        # No documented Wikidata claim either. A human still has to call
        # this one, same as before, just without a false "independent"
        # asserted with unwarranted confidence.
        polities = [
            {**BASE, "id": "virginia", "canonical_name": "Virginia", "external_ids": {"wikidata": "Q1370"},
             "start": 1788, "end": None, "prominence_score": 40, "geography": {"present_countries": ["US"]}},
            {**BASE, "id": "west_virginia", "canonical_name": "West Virginia",
             "external_ids": {"wikidata": "Q1371"}, "start": 1863, "end": None,
             "prominence_score": 25, "geography": {"present_countries": ["US"]}},
        ]
        self.assertIsNone(self.suggestion_for("west_virginia", "virginia", polities))

    def test_francoist_spain_bare_qualifier_naming_pattern_suggests_phase_of(self) -> None:
        # "Francoist Spain" doesn't fit the explicit "<regime type> of
        # <place>" pattern (no "of"), but it's the far more common English
        # shape for naming a historical regime/era -- and it has a finite
        # end (1975) plus dates nesting exactly inside Spain's continuous
        # span (1516-present), unlike West Virginia's open-ended dates.
        polities = [
            {**BASE, "id": "spain", "canonical_name": "Spain", "external_ids": {"wikidata": "Q29"},
             "start": 1516, "end": None, "prominence_score": 45, "geography": {"present_countries": ["ES"]}},
            {**BASE, "id": "francoist_spain", "canonical_name": "Francoist Spain",
             "external_ids": {"wikidata": "Q13474305"}, "start": 1939, "end": 1975,
             "prominence_score": 30, "geography": {"present_countries": ["ES"]}},
        ]
        self.assertEqual(self.suggestion_for("francoist_spain", "spain", polities), "phase_of")

    def test_appenzell_cantons_likely_siblings_suggest_independent(self) -> None:
        # Split from one original Appenzell canton in 1513 -- identical
        # date ranges, different names, distinct Wikidata items: siblings,
        # not one a phase of the other.
        polities = [
            {**BASE, "id": "canton_of_appenzell_innerrhoden",
             "canonical_name": "Canton of Appenzell Innerrhoden",
             "external_ids": {"wikidata": "Q12094"}, "start": 1513, "end": None,
             "prominence_score": 20, "geography": {"present_countries": ["CH"]}},
            {**BASE, "id": "canton_of_appenzell_ausserrhoden",
             "canonical_name": "Canton of Appenzell Ausserrhoden",
             "external_ids": {"wikidata": "Q12079"}, "start": 1513, "end": None,
             "prominence_score": 20, "geography": {"present_countries": ["CH"]}},
        ]
        self.assertEqual(
            self.suggestion_for(
                "canton_of_appenzell_ausserrhoden", "canton_of_appenzell_innerrhoden", polities
            ),
            "independent",
        )

    def test_bourbon_restoration_alias_reused_different_era_suggests_independent(self) -> None:
        # Bourbon Restoration in France carries an alias "Kingdom of
        # France" -- the restored monarchy genuinely was called that --
        # but Kingdom of France (987-1791) and Bourbon Restoration
        # (1815-1830) are distinct Wikidata items with non-overlapping
        # dates: the same name reused for a different era, not a phase.
        polities = [
            {**BASE, "id": "kingdom_of_france", "canonical_name": "Kingdom of France",
             "external_ids": {"wikidata": "Q70972"}, "start": 987, "end": 1791,
             "prominence_score": 40, "geography": {"present_countries": ["FR"]}},
            {**BASE, "id": "bourbon_restoration_in_france", "canonical_name": "Bourbon Restoration in France",
             "external_ids": {"wikidata": "Q207162"}, "names": {"aliases_en": "Kingdom of France"},
             "start": 1815, "end": 1830, "prominence_score": 20, "geography": {"present_countries": ["FR"]}},
        ]
        self.assertEqual(
            self.suggestion_for("bourbon_restoration_in_france", "kingdom_of_france", polities),
            "independent",
        )

    def test_same_wikidata_item_mismatched_dates_flags_qid_conflict(self) -> None:
        # Roman Republic and Ancient Rome both carry the same Wikidata QID
        # in this dataset despite covering very different centuries --
        # almost certainly one record has a misattributed QID, not a
        # genuine identity match. Should not suggest same_entity.
        polities = [
            {**BASE, "id": "ancient_rome", "canonical_name": "Ancient Rome",
             "external_ids": {"wikidata": "Q1747689"}, "start": -752, "end": 476,
             "prominence_score": 59, "geography": {"present_countries": ["IT"]}},
            {**BASE, "id": "roman_republic", "canonical_name": "Roman Republic",
             "external_ids": {"wikidata": "Q1747689"}, "start": -509, "end": -27,
             "prominence_score": 81, "geography": {"present_countries": ["IT"]}},
        ]
        self.assertIsNone(self.suggestion_for("ancient_rome", "roman_republic", polities))

    def test_akragas_mismatched_estimated_start_blocks_date_contains(self) -> None:
        # Akragas's own record starts 580 BCE, Agrigento's starts 579 BCE --
        # independently-estimated ancient dates rarely agree to the year, but
        # date-containment intentionally has no tolerance for that (an
        # earlier +/-10-year tolerance masked genuine boundary mismatches
        # too broadly, found live 1 September 2026): a 1-year gap on the
        # containing side is enough to withhold the suggestion rather than
        # guess. A reviewer still has to confirm this one by hand.
        polities = [
            {**BASE, "id": "agrigento", "canonical_name": "Agrigento", "external_ids": {"wikidata": "Q13678"},
             "names": {"aliases_en": "Akragas"}, "start": -579, "end": None,
             "prominence_score": 30, "geography": {"present_countries": ["IT"]}},
            {**BASE, "id": "akragas", "canonical_name": "Akragas", "external_ids": {"wikidata": "Q3607380"},
             "start": -580, "end": 406, "prominence_score": 20, "geography": {"present_countries": ["IT"]}},
        ]
        self.assertIsNone(self.suggestion_for("akragas", "agrigento", polities))

    def test_akragas_matching_estimated_start_suggests_phase_of(self) -> None:
        # Same pair, but with matching start years -- confirms exact
        # containment (no tolerance) still fires when the boundaries agree.
        polities = [
            {**BASE, "id": "agrigento", "canonical_name": "Agrigento", "external_ids": {"wikidata": "Q13678"},
             "names": {"aliases_en": "Akragas"}, "start": -580, "end": None,
             "prominence_score": 30, "geography": {"present_countries": ["IT"]}},
            {**BASE, "id": "akragas", "canonical_name": "Akragas", "external_ids": {"wikidata": "Q3607380"},
             "start": -580, "end": 406, "prominence_score": 20, "geography": {"present_countries": ["IT"]}},
        ]
        self.assertEqual(self.suggestion_for("akragas", "agrigento", polities), "phase_of")

    def test_thuringia_year_range_suffix_still_reads_as_regime_of(self) -> None:
        # "State of Thuringia (1920-1952)" carries a trailing disambiguator
        # in its own canonical_name -- stripped naively, "State of
        # Thuringia" clearly reads as "<regime type> of Thuringia" with a
        # finite end, but the raw suffix used to break that
        # endswith(" of thuringia") check and fall through to
        # no_identity_signal/independent instead.
        polities = [
            {**BASE, "id": "thuringia", "canonical_name": "Thuringia",
             "external_ids": {"wikidata": "Q1197"}, "start": 1920, "end": None,
             "prominence_score": 30, "geography": {"present_countries": ["DE"]}},
            {**BASE, "id": "state_of_thuringia_19201952",
             "canonical_name": "State of Thuringia (1920–1952)",
             "external_ids": {"wikidata": "Q1585375"}, "start": 1920, "end": 1952,
             "prominence_score": 20, "geography": {"present_countries": ["DE"]}},
        ]
        self.assertEqual(
            self.suggestion_for("state_of_thuringia_19201952", "thuringia", polities),
            "phase_of",
        )

    def test_exact_name_match_phase_of_allowed_when_both_sides_open_ended(self) -> None:
        # A finite end is NOT required for phase_of: an exact alias match
        # with clean date nesting should suggest phase_of even when the
        # reviewed entity (the one that would be retired) is itself still
        # open-ended/"present" -- the backend approximates a missing end
        # rather than refusing the decision, so the suggestion shouldn't be
        # more conservative than the backend it feeds.
        polities = [
            {**BASE, "id": "sharifian_empire", "canonical_name": "Sharifian Empire",
             "external_ids": {"wikidata": "Q1234567"}, "names": {"aliases_en": "Morocco"},
             "start": 1549, "end": None, "prominence_score": 30,
             "geography": {"present_countries": ["MA"]}},
            {**BASE, "id": "morocco", "canonical_name": "Morocco", "external_ids": {"wikidata": "Q1028"},
             "start": 788, "end": None, "prominence_score": 45,
             "geography": {"present_countries": ["MA"]}},
        ]
        self.assertEqual(self.suggestion_for("sharifian_empire", "morocco", polities), "phase_of")

    def test_missing_geography_on_both_sides_does_not_count_as_compatible(self) -> None:
        # An exact name match with clean date nesting but no
        # present_countries recorded on EITHER side should NOT be enough for
        # phase_of on its own -- with nothing to inherit from, missing
        # geography data is unknown, not a green light, so it must not stand
        # in for an actual overlap (found live, 1 September 2026).
        polities = [
            {**BASE, "id": "some_kingdom", "canonical_name": "Some Kingdom",
             "external_ids": {"wikidata": "Q9000001"}, "names": {"aliases_en": "Testland"},
             "start": 1200, "end": 1400, "prominence_score": 20,
             "geography": {"present_countries": []}},
            {**BASE, "id": "testland", "canonical_name": "Testland", "external_ids": {"wikidata": "Q9000002"},
             "start": 900, "end": None, "prominence_score": 25, "geography": {"present_countries": []}},
        ]
        self.assertIsNone(self.suggestion_for("some_kingdom", "testland", polities))

    def test_republic_of_georgia_inherits_geography_from_matched_country(self) -> None:
        # "Republic of Georgia (1990-1992)" has no present_countries of its
        # own, but reads as "<regime> of Georgia" with a finite end, and its
        # dates (1991-1992) nest exactly inside Georgia's (1991-present).
        # Since only the phase side is missing geography while the matched
        # country has it, that's not a conflict -- a phase with no geography
        # of its own reasonably shares its parent's location (found live, 1
        # September 2026).
        polities = [
            {**BASE, "id": "georgia", "canonical_name": "Georgia", "external_ids": {"wikidata": "Q230"},
             "start": 1991, "end": None, "prominence_score": 30,
             "geography": {"present_countries": ["GE"]}},
            {**BASE, "id": "republic_of_georgia_19901992",
             "canonical_name": "Republic of Georgia (1990–1992)",
             "external_ids": {"wikidata": "Q3456400"}, "start": 1991, "end": 1992,
             "prominence_score": 20, "geography": {"present_countries": []}},
        ]
        self.assertEqual(
            self.suggestion_for("republic_of_georgia_19901992", "georgia", polities), "phase_of"
        )

    def test_syrian_federation_demonym_naming_pattern_suggests_phase_of(self) -> None:
        # "Syrian Federation" doesn't end with "Syria" (it ends with
        # "Federation") -- the demonym "Syrian" is the FIRST word instead.
        # Exact date nesting (1922-1925 inside 1920-present) and matching
        # geography, plus a finite end, should still suggest phase_of. The
        # "State of Syria" alias is what actually puts this pair in the
        # candidate pool at all (shared "syria" token) -- token-sharing is
        # the pool-entry gate, separate from the naming-pattern signal under
        # test here.
        polities = [
            {**BASE, "id": "syria", "canonical_name": "Syria", "external_ids": {"wikidata": "Q858"},
             "start": 1920, "end": None, "prominence_score": 40,
             "geography": {"present_countries": ["SY"]}},
            {**BASE, "id": "syrian_federation", "canonical_name": "Syrian Federation",
             "names": {"aliases_en": "State of Syria"},
             "external_ids": {"wikidata": "Q12183911"}, "start": 1922, "end": 1925,
             "prominence_score": 20, "geography": {"present_countries": ["SY"]}},
        ]
        self.assertEqual(self.suggestion_for("syrian_federation", "syria", polities), "phase_of")

    def test_spain_under_the_restoration_prefix_naming_pattern_suggests_phase_of(self) -> None:
        # "Spain under the Restoration" starts with the exact outer name
        # "Spain" followed by a descriptor, rather than ending with it.
        polities = [
            {**BASE, "id": "spain", "canonical_name": "Spain", "external_ids": {"wikidata": "Q29"},
             "start": 1516, "end": None, "prominence_score": 45, "geography": {"present_countries": ["ES"]}},
            {**BASE, "id": "spain_under_the_restoration", "canonical_name": "Spain under the Restoration",
             "external_ids": {"wikidata": "Q1044536"}, "start": 1874, "end": 1931,
             "prominence_score": 25, "geography": {"present_countries": ["ES"]}},
        ]
        self.assertEqual(
            self.suggestion_for("spain_under_the_restoration", "spain", polities), "phase_of"
        )

    def test_first_brazilian_republic_mid_sentence_demonym_suggests_phase_of(self) -> None:
        # The demonym "Brazilian" falls in the MIDDLE of "First Brazilian
        # Republic" -- neither first nor last word alone would catch it;
        # the per-token demonym scan does. "United States of Brazil" (the
        # real official English name of Brazil during this era) is what
        # puts this pair in the candidate pool at all (shared "brazil"
        # token) -- token-sharing is the pool-entry gate, separate from the
        # naming-pattern signal under test here.
        polities = [
            {**BASE, "id": "brazil", "canonical_name": "Brazil", "external_ids": {"wikidata": "Q155"},
             "start": 1822, "end": None, "prominence_score": 45, "geography": {"present_countries": ["BR"]}},
            {**BASE, "id": "first_brazilian_republic", "canonical_name": "First Brazilian Republic",
             "names": {"aliases_en": "United States of Brazil"},
             "external_ids": {"wikidata": "Q2414171"}, "start": 1889, "end": 1930,
             "prominence_score": 25, "geography": {"present_countries": ["BR"]}},
        ]
        self.assertEqual(
            self.suggestion_for("first_brazilian_republic", "brazil", polities), "phase_of"
        )


if __name__ == "__main__":
    unittest.main()
