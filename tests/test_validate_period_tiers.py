import unittest

from build import validate_period_tiers
from schema import Period


def period(id_: str, tier: str, broader: list[str] | None = None) -> Period:
    return Period(
        id=id_,
        canonical_name=id_,
        kind="historical",
        tier=tier,
        start=1000,
        end=1500,
        authority="test",
        source_urls=["https://example.com"],
        broader_periods=broader or [],
    )


class ValidatePeriodTiersTests(unittest.TestCase):
    def test_valid_three_tier_chain_has_no_errors(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("regional_a", "regional_era", ["macro_a"]),
            period("period_a", "period", ["regional_a"]),
        ]
        self.assertEqual(validate_period_tiers(periods), [])

    def test_period_may_point_straight_at_macro_chapter(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["macro_a"]),
        ]
        self.assertEqual(validate_period_tiers(periods), [])

    def test_macro_chapter_with_a_parent_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("macro_b", "macro_chapter", ["macro_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("macro_b", errors[0])

    def test_regional_era_with_two_parents_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("macro_b", "macro_chapter"),
            period("regional_a", "regional_era", ["macro_a", "macro_b"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("regional_a", errors[0])

    def test_regional_era_parented_to_a_period_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["macro_a"]),
            period("regional_a", "regional_era", ["period_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertEqual(len(errors), 1)
        self.assertIn("regional_a", errors[0])

    def test_cycle_is_an_error(self) -> None:
        periods = [
            period("macro_a", "macro_chapter"),
            period("period_a", "period", ["period_b"]),
            period("period_b", "period", ["period_a"]),
        ]
        errors = validate_period_tiers(periods)
        self.assertTrue(any("cycle" in e for e in errors))

    def test_period_with_no_broader_periods_is_valid(self) -> None:
        self.assertEqual(validate_period_tiers([period("period_a", "period")]), [])

    def test_regional_era_with_no_broader_periods_is_valid(self) -> None:
        self.assertEqual(validate_period_tiers([period("regional_a", "regional_era")]), [])


if __name__ == "__main__":
    unittest.main()
