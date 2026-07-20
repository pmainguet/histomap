import unittest

from pipeline.filter_wikidata_types import classify


STRONG_ALLOW = {"Q6256", "Q3624078"}
CONTEXTUAL_ALLOW = {"Q133442", "Q148837"}
DENY = {"Q515", "Q1549591", "Q839954"}


class WikidataTypeFilterTests(unittest.TestCase):
    def decide(self, qid: str, types: set[str], overrides: dict[str, str] | None = None) -> str:
        return classify(
            qid,
            types,
            strong_allow_types=STRONG_ALLOW,
            contextual_allow_types=CONTEXTUAL_ALLOW,
            deny_types=DENY,
            review_types=set(),
            overrides=overrides or {},
        ).decision

    def test_country_is_accepted(self) -> None:
        self.assertEqual(self.decide("Q96", {"Q6256", "Q3624078"}), "accepted")

    def test_modern_city_is_excluded(self) -> None:
        self.assertEqual(self.decide("Q1524", {"Q515", "Q1549591"}), "excluded")

    def test_historical_polis_wins_over_archaeological_site(self) -> None:
        self.assertEqual(
            self.decide(
                "Q844930",
                {"Q148837", "Q133442", "Q839954"},
                {"Q844930": "accepted"},
            ),
            "accepted",
        )

    def test_mixed_modern_city_state_goes_to_review(self) -> None:
        self.assertEqual(self.decide("Q64", {"Q133442", "Q515"}), "review")

    def test_unknown_type_goes_to_review(self) -> None:
        self.assertEqual(self.decide("Q1", {"Q999"}), "review")

    def test_override_takes_precedence(self) -> None:
        self.assertEqual(self.decide("Q1", {"Q6256"}, {"Q1": "excluded"}), "excluded")


if __name__ == "__main__":
    unittest.main()
