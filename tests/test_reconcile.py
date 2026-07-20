import unittest

from pipeline.reconcile import CandidateScore, date_compatibility, decide, normalize_name, score_candidate


class ReconciliationTests(unittest.TestCase):
    def test_phase_name_normalization(self) -> None:
        self.assertEqual(normalize_name("Late Roman Republic"), "roman republic")
        self.assertEqual(normalize_name("Roman Empire - Principate"), "roman empire")
        self.assertEqual(normalize_name("Achaemenid Empire", strip_types=True), "achaemenid")

    def test_date_containment_scores_full_match(self) -> None:
        self.assertEqual(date_compatibility(-264, -134, -509, -27), 1.0)
        self.assertEqual(date_compatibility(100, 200, 300, 400), 0.0)

    def test_scores_many_to_one_phase_highly(self) -> None:
        seshat = {
            "canonical_name": "Middle Roman Republic",
            "start_year": -264,
            "end_year": -134,
            "world_region": "Europe",
        }
        canonical = {
            "id": "roman_republic",
            "canonical_name": "Roman Republic",
            "names": {},
            "start": -509,
            "end": -27,
            "geography": {"continents": ["europe"]},
        }
        score = score_candidate(seshat, canonical)
        self.assertEqual(score.name_score, 100)
        self.assertEqual(score.date_score, 100)
        self.assertGreaterEqual(score.total_score, 90)

    def test_substring_without_shared_token_is_capped(self) -> None:
        seshat = {
            "canonical_name": "Funan II",
            "start_year": 540,
            "end_year": 639,
            "world_region": "Southeast Asia",
        }
        misleading = {
            "id": "nan",
            "canonical_name": "Nan",
            "names": {},
            "start": 500,
            "end": 700,
            "geography": {"continents": ["asia"]},
        }
        self.assertLessEqual(score_candidate(seshat, misleading).name_score, 75)

    def test_partial_alias_does_not_auto_match_related_polity(self) -> None:
        seshat = {
            "canonical_name": "Early Merovingian",
            "start_year": 481,
            "end_year": 542,
            "world_region": "Europe",
        }
        related = {
            "id": "alamannia",
            "canonical_name": "Alamannia",
            "names": {"aliases_en": "merovingian duchy of Alamannia"},
            "start": 300,
            "end": 911,
            "geography": {"continents": ["europe"]},
        }
        score = score_candidate(seshat, related)
        self.assertGreater(score.name_score, score.primary_name_score)
        self.assertLess(score.primary_name_score, 88)

    def test_auto_match_requires_clear_margin(self) -> None:
        first = CandidateScore("one", "One", 100, 100, 100, 100, 100, 100)
        close = CandidateScore("two", "Two", 99, 99, 100, 100, 100, 98)
        self.assertEqual(decide([first, close], {"one": "accepted"})[0], "review")
        distant = CandidateScore("two", "Two", 80, 80, 70, 50, 50, 70)
        self.assertEqual(decide([first, distant], {"one": "accepted"})[0], "auto")


if __name__ == "__main__":
    unittest.main()
