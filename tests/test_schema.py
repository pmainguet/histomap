import unittest

from pydantic import ValidationError

from schema import Event, Period, Polity


def period_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_period",
        "canonical_name": "Test Period",
        "start": 1000,
        "end": 1500,
        "authority": "test",
        "source_urls": ["https://example.com"],
    }
    value.update(overrides)
    return value


def event_kwargs(**overrides: object) -> dict:
    value = {
        "id": "test_event",
        "canonical_name": "Test Event",
        "year": 1200,
        "authority": "test",
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


class PolitySourceUrlsTests(unittest.TestCase):
    def test_source_urls_defaults_to_empty_list(self) -> None:
        polity = Polity(**polity_kwargs())
        self.assertEqual(polity.source_urls, [])

    def test_source_urls_accepts_a_list_of_urls(self) -> None:
        # ROADMAP.md item 6 -- Period/Event/Transition already had this
        # field; Polity did not, so source_urls set in several hand-authored
        # polity YAML files was silently dropped by extra="ignore" and never
        # reached data.json (found live, 8 September 2026, while wiring up
        # the /explore side panel's Wikipedia summary).
        polity = Polity(**polity_kwargs(source_urls=["https://en.wikipedia.org/wiki/Test"]))
        self.assertEqual(polity.source_urls, ["https://en.wikipedia.org/wiki/Test"])


class VisibilityTierRetirementTests(unittest.TestCase):
    def test_visibility_tier_field_no_longer_accepted(self) -> None:
        polity = Polity(**polity_kwargs(visibility_tier="global"))
        self.assertFalse(hasattr(polity, "visibility_tier"))
        self.assertNotIn("visibility_tier", Polity.model_fields)

    def test_visibility_override_field_no_longer_accepted(self) -> None:
        polity = Polity(**polity_kwargs(visibility_override="global"))
        self.assertFalse(hasattr(polity, "visibility_override"))
        self.assertNotIn("visibility_override", Polity.model_fields)

    def test_visibility_tier_enum_no_longer_exported(self) -> None:
        import schema
        self.assertFalse(hasattr(schema, "VisibilityTier"))


class PeriodPromotedFromTests(unittest.TestCase):
    def test_promoted_from_defaults_to_none(self) -> None:
        period = Period(**period_kwargs())
        self.assertIsNone(period.promoted_from)

    def test_promoted_from_accepts_source_polity_id(self) -> None:
        period = Period(**period_kwargs(promoted_from="some_polity"))
        self.assertEqual(period.promoted_from, "some_polity")


class PeriodDetailOfTests(unittest.TestCase):
    def test_detail_of_defaults_to_none(self) -> None:
        period = Period(**period_kwargs())
        self.assertIsNone(period.detail_of)

    def test_detail_of_accepts_a_target_id(self) -> None:
        period = Period(**period_kwargs(detail_of="jomon_period"))
        self.assertEqual(period.detail_of, "jomon_period")

    def test_detail_of_rejects_self_reference(self) -> None:
        with self.assertRaises(ValidationError):
            Period(**period_kwargs(id="loop", detail_of="loop"))


class PeriodKindRetirementTests(unittest.TestCase):
    def test_kind_field_no_longer_accepted(self) -> None:
        period = Period(**period_kwargs(kind="historical"))
        self.assertFalse(hasattr(period, "kind"))
        self.assertNotIn("kind", Period.model_fields)

    def test_period_no_longer_requires_kind(self) -> None:
        kwargs = period_kwargs()
        kwargs.pop("kind", None)
        Period(**kwargs)  # must not raise

    def test_deprecated_defaults_to_none(self) -> None:
        period = Period(**period_kwargs())
        self.assertIsNone(period.deprecated)

    def test_deprecated_accepts_the_old_kind_value(self) -> None:
        period = Period(**period_kwargs(deprecated={"kind": "historical"}))
        self.assertEqual(period.deprecated["kind"], "historical")


class EventTests(unittest.TestCase):
    def test_minimal_event_defaults_to_review_eligibility(self) -> None:
        event = Event(**event_kwargs())
        self.assertEqual(event.eligibility.value, "review")
        self.assertEqual(event.detail_of, [])
        self.assertEqual(event.bounds, [])

    def test_detail_of_and_bounds_are_both_lists(self) -> None:
        event = Event(**event_kwargs(
            detail_of=["some_civilization", "some_other_polity"],
            bounds=[{"target": "some_era", "edge": "end"}, {"target": "next_era", "edge": "start"}],
        ))
        self.assertEqual(event.detail_of, ["some_civilization", "some_other_polity"])
        self.assertEqual(event.bounds[0].target, "some_era")
        self.assertEqual(event.bounds[0].edge, "end")
        self.assertEqual(event.bounds[1].edge, "start")

    def test_bounds_rejects_a_duplicate_target_edge_pair(self) -> None:
        with self.assertRaises(ValidationError):
            Event(**event_kwargs(bounds=[
                {"target": "some_era", "edge": "end"},
                {"target": "some_era", "edge": "end"},
            ]))

    def test_bounds_allows_the_same_target_with_different_edges(self) -> None:
        # Not realistic (an era can't both start and end the same event),
        # but the schema itself doesn't need to forbid it -- build.py's
        # date-tolerance validation is where a genuinely wrong pairing
        # gets caught.
        event = Event(**event_kwargs(bounds=[
            {"target": "some_era", "edge": "end"},
            {"target": "some_era", "edge": "start"},
        ]))
        self.assertEqual(len(event.bounds), 2)

    def test_id_must_be_snake_case(self) -> None:
        with self.assertRaises(ValidationError):
            Event(**event_kwargs(id="Not-Snake-Case"))

    def test_year_out_of_range_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            Event(**event_kwargs(year=999_999_999))

    def test_authority_is_required(self) -> None:
        kwargs = event_kwargs()
        kwargs.pop("authority")
        with self.assertRaises(ValidationError):
            Event(**kwargs)


class PeriodEpochLaneTests(unittest.TestCase):
    def test_epoch_lane_defaults_to_false(self) -> None:
        period = Period(**period_kwargs())
        self.assertFalse(period.epoch_lane)

    def test_epoch_lane_accepts_true(self) -> None:
        period = Period(**period_kwargs(epoch_lane=True))
        self.assertTrue(period.epoch_lane)


if __name__ == "__main__":
    unittest.main()
