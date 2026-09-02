import unittest

from pydantic import ValidationError

from schema import Period, Polity


def period_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_period",
        "canonical_name": "Test Period",
        "kind": "historical",
        "start": 1000,
        "end": 1500,
        "authority": "test",
        "source_urls": ["https://example.com"],
    }
    value.update(overrides)
    return value


def polity_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_polity",
        "canonical_name": "Test Polity",
        "start": 1000,
        "start_confidence": "low",
        "end_confidence": "low",
    }
    value.update(overrides)
    return value


class PeriodTierTests(unittest.TestCase):
    def test_tier_defaults_to_period(self) -> None:
        period = Period(**period_kwargs())
        self.assertEqual(period.tier, "period")

    def test_macro_chapter_tier_is_valid(self) -> None:
        period = Period(**period_kwargs(tier="macro_chapter"))
        self.assertEqual(period.tier, "macro_chapter")

    def test_invalid_tier_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Period(**period_kwargs(tier="subperiod"))  # not a tier value; see design summary #1


class YearFloorTests(unittest.TestCase):
    def test_deep_prehistory_start_is_valid(self) -> None:
        period = Period(**period_kwargs(start=-2_000_000, end=-1_000_000))
        self.assertEqual(period.start, -2_000_000)

    def test_below_new_floor_still_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Period(**period_kwargs(start=-3_000_001, end=-3_000_000))


class PolityDetailOfTests(unittest.TestCase):
    def test_polity_accepts_detail_of_and_deprecated(self) -> None:
        polity = Polity(**polity_kwargs(
            detail_of="spain",
            deprecated={
                "consolidation_status": "phase_of",
                "consolidated_into": "spain",
                "period": {"id": "francoist_spain_period", "kind": "historical"},
            },
        ))
        self.assertEqual(polity.detail_of, "spain")
        self.assertEqual(polity.deprecated["consolidation_status"], "phase_of")

    def test_polity_rejects_retired_consolidation_status_values(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="phase_of"))
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="part_of"))

    def test_polity_same_entity_still_requires_consolidated_into(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(consolidation_status="same_entity"))


if __name__ == "__main__":
    unittest.main()
