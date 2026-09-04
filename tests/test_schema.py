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


class PolityEndDateTests(unittest.TestCase):
    def test_same_year_start_and_end_is_valid(self) -> None:
        # A state can genuinely start and end within the same calendar year
        # at year-level precision (Inner Mongolian People's Republic:
        # 1945-09-09 to 1945-11-06, both year 1945) -- found live, 1
        # September 2026.
        polity = Polity(**polity_kwargs(start=1945, end=1945))
        self.assertEqual(polity.end, 1945)

    def test_end_strictly_before_start_is_still_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(start=1380, end=1200))


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


class PolityParentRetirementTests(unittest.TestCase):
    def test_parent_field_no_longer_accepted(self) -> None:
        # Pydantic v2 defaults to extra="ignore" (no model_config override in
        # schema.py), so an unknown kwarg is silently dropped rather than
        # raising -- construction still succeeds, just without the attribute.
        polity = Polity(**polity_kwargs(parent="spain"))
        self.assertFalse(hasattr(polity, "parent"))
        self.assertNotIn("parent", Polity.model_fields)

    def test_subdivision_parent_status_field_no_longer_accepted(self) -> None:
        polity = Polity(**polity_kwargs(subdivision_parent_status="pending"))
        self.assertFalse(hasattr(polity, "subdivision_parent_status"))
        self.assertNotIn("subdivision_parent_status", Polity.model_fields)

    def test_detail_of_rejects_self_reference(self) -> None:
        with self.assertRaises(ValidationError):
            Polity(**polity_kwargs(id="loop", detail_of="loop"))


if __name__ == "__main__":
    unittest.main()
