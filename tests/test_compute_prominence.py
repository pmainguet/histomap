import unittest

from pipeline.compute_prominence import score_prominence, tier_for


class ComputeProminenceTests(unittest.TestCase):
    def test_major_independent_polity_is_global(self) -> None:
        score = score_prominence(
            sitelinks=120,
            start=-550,
            end=-330,
            has_parent_country=False,
            authoritative=True,
            editorial=False,
        )
        self.assertEqual(tier_for(score), "global")

    def test_subordinate_entity_is_demoted(self) -> None:
        independent = score_prominence(
            sitelinks=25,
            start=1800,
            end=None,
            has_parent_country=False,
            authoritative=False,
            editorial=False,
        )
        subordinate = score_prominence(
            sitelinks=25,
            start=1800,
            end=None,
            has_parent_country=True,
            authoritative=False,
            editorial=False,
        )
        self.assertGreater(independent, subordinate)
        self.assertEqual(tier_for(subordinate), "detailed")

    def test_editorial_work_can_promote_a_borderline_record(self) -> None:
        plain = score_prominence(
            sitelinks=5,
            start=1000,
            end=1500,
            has_parent_country=False,
            authoritative=False,
            editorial=False,
        )
        edited = score_prominence(
            sitelinks=5,
            start=1000,
            end=1500,
            has_parent_country=False,
            authoritative=False,
            editorial=True,
        )
        self.assertLess(plain, edited)


if __name__ == "__main__":
    unittest.main()
