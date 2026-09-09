import unittest

from pipeline.build_explore_tree import (
    AUTO_GENERATED_AUTHORITY,
    CIVILIZATION_BACKDROP_AUTHORITY,
    best_chapter_for_polity,
    build_explore_tree,
)


def chapter(id_: str, start: int, end: int) -> dict:
    """Build a minimal macro-chapter fixture dict."""
    return {"id": id_, "tier": "macro_chapter", "canonical_name": id_, "start": start, "end": end, "broader_periods": []}


def era(
    id_: str,
    start: int,
    end: int,
    chapter_id: str,
    continents: list[str],
    regions: list[str] | None = None,
    authority: str | None = None,
) -> dict:
    """Build a minimal regional-era fixture dict. `authority` defaults to
    None (not auto-generated); pass AUTO_GENERATED_AUTHORITY to simulate an
    era created by generate_modern_regional_eras.py."""
    return {
        "id": id_, "tier": "regional_era", "canonical_name": id_, "start": start, "end": end,
        "broader_periods": [chapter_id],
        "geography": {"continents": continents, "historical_regions": regions or []},
        "authority": authority,
    }


def named_period(id_: str, start: int, end: int, broader: list[str] | None = None, continents: list[str] | None = None,
                  historical_regions: list[str] | None = None, authority: str | None = None,
                  detail_of: str | None = None, epoch_lane: bool = False) -> dict:
    """Build a minimal period fixture dict."""
    doc = {
        "id": id_, "tier": "period", "canonical_name": id_, "start": start, "end": end,
        "broader_periods": broader or [],
        "geography": {"continents": continents or [], "historical_regions": historical_regions or []},
        "authority": authority,
        "epoch_lane": epoch_lane,
    }
    if detail_of is not None:
        doc["detail_of"] = detail_of
    return doc


def polity(id_: str, start: int, end: int | None, continent: str, region: str | None = None,
           present_countries: list[str] | None = None, entity_type: str | None = None,
           detail_of: str | None = None) -> dict:
    """Build a minimal polity fixture dict."""
    doc = {
        "id": id_, "canonical_name": id_, "start": start, "end": end,
        "geography": {
            "primary_continent": continent, "continents": [continent],
            "primary_historical_region": region, "historical_regions": [region] if region else [],
            "present_countries": present_countries or [],
        },
    }
    if entity_type is not None:
        doc["entity_type"] = entity_type
    if detail_of is not None:
        doc["detail_of"] = detail_of
    return doc


class BestChapterForPolityTests(unittest.TestCase):
    def test_picks_chapter_containing_polity(self) -> None:
        chapters = [chapter("early", -3500, -1200), chapter("classical", -1200, 500)]
        best = best_chapter_for_polity(polity("p1", -2000, -1900, "africa"), chapters, 2100)
        self.assertEqual(best["id"], "early")

    def test_returns_none_when_no_overlap(self) -> None:
        chapters = [chapter("early", -3500, -1200)]
        self.assertIsNone(best_chapter_for_polity(polity("p1", 1000, 1100, "africa"), chapters, 2100))


class BuildExploreTreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            chapter("macro_early", -3500, -1200),
            era("egypt_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
            era("meso_era", -3500, -1200, "macro_early", ["asia"], ["west_asia"]),
            named_period("old_kingdom", -2686, -2181, broader=["egypt_era"]),
            named_period("heuristic_period", -3000, -2800, continents=["africa"]),
        ]
        self.period_links = [
            {"period_id": "old_kingdom", "entity_id": "old_kingdom_egypt", "relation": "part_of_periodization"},
        ]
        self.polities = [
            polity("old_kingdom_egypt", -2686, -2181, "africa", "north_africa"),
            polity("unlinked_egyptian", -2500, -2400, "africa", "north_africa"),
        ]

    def test_all_nine_chapter_slots_present_even_with_one_chapter_fixture(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        self.assertEqual([c["id"] for c in tree["chapters"]], ["macro_early"])

    def test_era_nests_under_its_chapter(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        chapter_out = tree["chapters"][0]
        self.assertEqual({e["id"] for e in chapter_out["eras"]}, {"egypt_era", "meso_era"})

    def test_curated_period_nests_under_its_curated_era(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertIn("old_kingdom", [p["id"] for p in egypt_era["periods"]])
        curated = next(p for p in egypt_era["periods"] if p["id"] == "old_kingdom")
        self.assertTrue(curated["curated"])

    def test_heuristic_period_nests_under_best_geography_matched_era(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        heuristic = [p for p in egypt_era["periods"] if p["id"] == "heuristic_period"]
        self.assertEqual(len(heuristic), 1)
        self.assertFalse(heuristic[0]["curated"])

    def test_curated_polity_bucketed_by_own_geography_and_flagged_curated(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        curated_entry = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertTrue(curated_entry["curated"])

    def test_unlinked_in_scope_polity_placed_heuristically(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        heuristic_entry = next(e for e in region_bucket if e["id"] == "unlinked_egyptian")
        self.assertFalse(heuristic_entry["curated"])

    def test_detail_of_polity_excluded_from_its_own_bucket_entry(self) -> None:
        polities = [*self.polities, polity(
            "francoist_spain", -2500, -2400, "africa", "north_africa", detail_of="old_kingdom_egypt",
        )]
        tree = build_explore_tree(polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        self.assertNotIn("francoist_spain", {e["id"] for e in region_bucket})

    def test_detail_of_polity_attached_to_its_container_entry(self) -> None:
        polities = [*self.polities, polity(
            "francoist_spain", -2500, -2400, "africa", "north_africa", detail_of="old_kingdom_egypt",
        )]
        tree = build_explore_tree(polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertEqual([d["id"] for d in container["details"]], ["francoist_spain"])
        self.assertEqual(container["details"][0]["canonical_name"], "francoist_spain")

    def test_multi_level_detail_of_chain_nests_recursively(self) -> None:
        """ROADMAP.md item 0: a detail_of target can itself be a detail_of
        another entity's detail (Kingdom of Castile -> Crown of Castile ->
        Hispanic Monarchy, 22 such real chains as of 4 September 2026). The
        middle entity never gets its own top-level bucket entry, but its own
        nested detail must still surface -- under the top-level container's
        details list, recursively, not orphaned."""
        polities = [*self.polities, polity(
            "crown_of_castile", -2600, -2400, "africa", "north_africa", detail_of="old_kingdom_egypt",
        ), polity(
            "kingdom_of_castile", -2600, -2500, "africa", "north_africa", detail_of="crown_of_castile",
        )]
        tree = build_explore_tree(polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        middle = next(d for d in container["details"] if d["id"] == "crown_of_castile")
        self.assertEqual([d["id"] for d in middle["details"]], ["kingdom_of_castile"])

    def test_detail_of_polity_detail_carries_polity_kind(self) -> None:
        polities = [*self.polities, polity(
            "francoist_spain", -2500, -2400, "africa", "north_africa", detail_of="old_kingdom_egypt",
        )]
        tree = build_explore_tree(polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertEqual(container["details"][0]["kind"], "polity")

    def test_event_detail_of_attaches_to_its_target_entrys_details(self) -> None:
        # ROADMAP.md item 5 / docs/plans/2026-09-07-events-lane-design.md:
        # an event's detail_of is a list (unlike a polity/period's single
        # detail_of) -- one event can be a detail of several entities at
        # once. A single `year` stands in for start/end.
        events = [{"id": "some_event", "canonical_name": "Some Event", "year": -2450, "detail_of": ["old_kingdom_egypt"]}]
        tree = build_explore_tree(self.polities, self.periods, self.period_links, events=events)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        detail = next(d for d in container["details"] if d["id"] == "some_event")
        self.assertEqual(detail["kind"], "event")
        self.assertEqual(detail["start"], -2450)
        self.assertEqual(detail["end"], -2450)

    def test_event_can_be_a_detail_of_two_entities_at_once(self) -> None:
        events = [{
            "id": "shared_event", "canonical_name": "Shared Event", "year": -2450,
            "detail_of": ["old_kingdom_egypt", "unlinked_egyptian"],
        }]
        tree = build_explore_tree(self.polities, self.periods, self.period_links, events=events)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        first_container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        second_container = next(e for e in region_bucket if e["id"] == "unlinked_egyptian")
        self.assertIn("shared_event", [d["id"] for d in first_container["details"]])
        self.assertIn("shared_event", [d["id"] for d in second_container["details"]])

    def test_event_bounds_attaches_to_its_target_periods_details(self) -> None:
        # ROADMAP.md item 0 (8 September 2026): an event's bounds (the
        # era/chapter/period it starts or ends) used to only ever show up
        # via its own Events-lane marker -- it never attached to the
        # target period's own "details" the way detail_of does above.
        events = [{
            "id": "old_kingdom_ends", "canonical_name": "Old Kingdom collapses", "year": -2181,
            "bounds": [{"target": "old_kingdom", "edge": "end"}],
        }]
        tree = build_explore_tree(self.polities, self.periods, self.period_links, events=events)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        container = next(p for p in egypt_era["periods"] if p["id"] == "old_kingdom")
        detail = next(d for d in container["details"] if d["id"] == "old_kingdom_ends")
        self.assertEqual(detail["kind"], "event")
        self.assertEqual(detail["start"], -2181)
        self.assertEqual(detail["end"], -2181)

    def test_event_can_bound_two_periods_at_once(self) -> None:
        events = [{
            "id": "shared_boundary", "canonical_name": "Shared Boundary", "year": -2181,
            "bounds": [{"target": "old_kingdom", "edge": "end"}, {"target": "heuristic_period", "edge": "start"}],
        }]
        tree = build_explore_tree(self.polities, self.periods, self.period_links, events=events)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        old_kingdom_container = next(p for p in egypt_era["periods"] if p["id"] == "old_kingdom")
        self.assertIn("shared_boundary", [d["id"] for d in old_kingdom_container["details"]])

    def test_no_events_argument_leaves_tree_unaffected(self) -> None:
        # events defaults to None -- every existing call site (build.py
        # before this feature, every other test in this file) must keep
        # working unchanged.
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertNotIn("details", container)

    def test_detail_of_period_excluded_from_its_own_top_level_entry(self) -> None:
        # Direct request, live, 7 September 2026: periods can be details of
        # other periods (or of a polity), same mechanism as polities --
        # Initial Jomon should nest under Jomon period, not show as its own
        # separate Period-row band.
        periods = [*self.periods, named_period(
            "initial_jomon", -9200, -5301, continents=["asia"], detail_of="old_kingdom",
        )]
        tree = build_explore_tree(self.polities, periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertNotIn("initial_jomon", [p["id"] for p in egypt_era["periods"]])

    def test_detail_of_period_attached_to_its_period_container(self) -> None:
        periods = [*self.periods, named_period(
            "initial_jomon", -9200, -5301, continents=["asia"], detail_of="old_kingdom",
        )]
        tree = build_explore_tree(self.polities, periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        container = next(p for p in egypt_era["periods"] if p["id"] == "old_kingdom")
        self.assertEqual([d["id"] for d in container["details"]], ["initial_jomon"])
        self.assertEqual(container["details"][0]["kind"], "period")

    def test_detail_of_period_can_target_a_polity(self) -> None:
        # The reverse of the usual case: a period nested under a POLITY's
        # own top-level entry, not another period's.
        periods = [*self.periods, named_period(
            "brief_phase", -2600, -2500, continents=["africa"], detail_of="old_kingdom_egypt",
        )]
        tree = build_explore_tree(self.polities, periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        container = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertEqual([d["id"] for d in container["details"]], ["brief_phase"])
        self.assertEqual(container["details"][0]["kind"], "period")

    def test_container_without_details_has_no_details_key(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        plain = next(e for e in region_bucket if e["id"] == "unlinked_egyptian")
        self.assertNotIn("details", plain)

    def test_axis_segment_break_is_earliest_chapter_end(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        self.assertEqual(tree["axis"]["segment_break"], -1200)

    def test_heuristic_period_placement_still_yields_curated_polity(self) -> None:
        """Reproduces the Fix 1 bug: a period placed heuristically (no
        broader_periods, via rank_candidates) under an era must still yield a
        curated=true polity entry when period_links.yaml links an entity into
        that period -- the curated fact lives in the polity-to-period link,
        not in the period's own era placement."""
        periods = [
            chapter("macro_early", -3500, -1200),
            era("egypt_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
            named_period("old_kingdom", -2686, -2181, continents=["africa"]),  # no broader_periods -- heuristic placement
        ]
        period_links = [{"period_id": "old_kingdom", "entity_id": "old_kingdom_egypt", "relation": "part_of_periodization"}]
        polities = [polity("old_kingdom_egypt", -2686, -2181, "africa", "north_africa")]
        tree = build_explore_tree(polities, periods, period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        entry = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertTrue(entry["curated"])

    def test_polity_entry_includes_present_countries(self) -> None:
        """Verify that present_countries values from a polity's geography
        dict thread through correctly into the output entry."""
        polities = [polity("old_kingdom_egypt", -2686, -2181, "africa", "north_africa", present_countries=["EG"])]
        tree = build_explore_tree(polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        entry = next(e for e in region_bucket if e["id"] == "old_kingdom_egypt")
        self.assertEqual(entry["present_countries"], ["EG"])

    def test_era_entry_includes_primary_continent(self) -> None:
        """Verify that primary_continent, derived from an era's geography
        dict with the same fallback logic as polity bucketing, threads
        through correctly into the output entry -- so the /explore era row
        can group by continent."""
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertEqual(egypt_era["primary_continent"], "africa")

    def test_period_entry_includes_primary_continent(self) -> None:
        """Verify that primary_continent, derived from a period's geography
        dict with the same fallback logic as polity bucketing, threads
        through correctly into the output entry -- so the /explore period
        row can group by continent."""
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        heuristic = next(p for p in egypt_era["periods"] if p["id"] == "heuristic_period")
        self.assertEqual(heuristic["primary_continent"], "africa")

    def test_era_entry_includes_primary_historical_region(self) -> None:
        """Verify that primary_historical_region, derived from an era's
        geography dict with the same fallback logic as polity bucketing,
        threads through correctly into the output entry -- so the /explore
        era row can split the Asia continent bucket by historical region."""
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        meso_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "meso_era")
        self.assertEqual(meso_era["primary_historical_region"], "west_asia")

    def test_period_entry_includes_primary_historical_region(self) -> None:
        """Verify that primary_historical_region, derived from a period's
        geography dict with the same fallback logic as polity bucketing,
        threads through correctly into the output entry -- so the /explore
        period row can split the Asia continent bucket by historical
        region."""
        periods = [
            chapter("macro_early", -3500, -1200),
            era("meso_era", -3500, -1200, "macro_early", ["asia"], ["west_asia"]),
            named_period("meso_period", -3000, -2800, broader=["meso_era"], continents=["asia"],
                         historical_regions=["west_asia"]),
        ]
        tree = build_explore_tree([], periods, [])
        meso_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "meso_era")
        period = next(p for p in meso_era["periods"] if p["id"] == "meso_period")
        self.assertEqual(period["primary_historical_region"], "west_asia")


class AutoGeneratedEraMergeTests(unittest.TestCase):
    """Fix 3: auto-generated continent x chapter placeholder eras (from
    generate_modern_regional_eras.py) collapse into a single combined
    display row per chapter, while hand-curated eras stay untouched."""

    def test_multiple_auto_generated_eras_merge_into_one_with_union_of_periods(self) -> None:
        periods = [
            chapter("macro_modern", 1500, 1800),
            era("africa_modern_era", 1500, 1800, "macro_modern", ["africa"], authority=AUTO_GENERATED_AUTHORITY),
            era("asia_modern_era", 1500, 1800, "macro_modern", ["asia"], authority=AUTO_GENERATED_AUTHORITY),
            named_period("africa_period", 1500, 1600, broader=["africa_modern_era"]),
            named_period("asia_period", 1600, 1700, broader=["asia_modern_era"]),
        ]
        tree = build_explore_tree([], periods, [])
        eras_out = tree["chapters"][0]["eras"]
        self.assertEqual(len(eras_out), 1)
        merged = eras_out[0]
        self.assertEqual(merged["id"], "macro_modern_by_continent_era")
        self.assertEqual({p["id"] for p in merged["periods"]}, {"africa_period", "asia_period"})

    def test_single_auto_generated_era_left_as_is(self) -> None:
        periods = [
            chapter("macro_modern", 1500, 1800),
            era("africa_modern_era", 1500, 1800, "macro_modern", ["africa"], authority=AUTO_GENERATED_AUTHORITY),
            named_period("africa_period", 1500, 1600, broader=["africa_modern_era"]),
        ]
        tree = build_explore_tree([], periods, [])
        eras_out = tree["chapters"][0]["eras"]
        self.assertEqual(len(eras_out), 1)
        self.assertEqual(eras_out[0]["id"], "africa_modern_era")

    def test_curated_era_untouched_while_auto_generated_ones_merge(self) -> None:
        periods = [
            chapter("macro_modern", 1500, 1800),
            era("hand_curated_era", 1500, 1800, "macro_modern", ["europe"]),
            era("africa_modern_era", 1500, 1800, "macro_modern", ["africa"], authority=AUTO_GENERATED_AUTHORITY),
            era("asia_modern_era", 1500, 1800, "macro_modern", ["asia"], authority=AUTO_GENERATED_AUTHORITY),
            named_period("curated_period", 1500, 1600, broader=["hand_curated_era"]),
            named_period("africa_period", 1500, 1600, broader=["africa_modern_era"]),
            named_period("asia_period", 1600, 1700, broader=["asia_modern_era"]),
        ]
        tree = build_explore_tree([], periods, [])
        eras_out = tree["chapters"][0]["eras"]
        self.assertEqual({e["id"] for e in eras_out}, {"hand_curated_era", "macro_modern_by_continent_era"})
        curated_era = next(e for e in eras_out if e["id"] == "hand_curated_era")
        self.assertEqual([p["id"] for p in curated_era["periods"]], ["curated_period"])
        merged_era = next(e for e in eras_out if e["id"] == "macro_modern_by_continent_era")
        self.assertEqual({p["id"] for p in merged_era["periods"]}, {"africa_period", "asia_period"})


class CivilizationsCultureLaneTests(unittest.TestCase):
    """The Civilizations & Cultures lane: entity_type-tagged polities and
    name-matched civilization periods, routed out of the ordinary Polities
    row / Period row into their own flat per-chapter lane."""

    def setUp(self) -> None:
        self.base_periods = [
            chapter("macro_early", -3500, -1200),
            era("egypt_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
        ]

    def test_entity_type_civilization_polity_routed_to_lane_not_polities_row(self) -> None:
        polities = [polity("nubian_civilization", -2500, -1500, "africa", "north_africa", entity_type="civilization")]
        tree = build_explore_tree(polities, self.base_periods, [])
        chapter_out = tree["chapters"][0]
        self.assertEqual([e["id"] for e in chapter_out["civilizations"]], ["nubian_civilization"])
        all_polity_ids = {e["id"] for bucket in chapter_out["polities_by_historical_region"].values() for e in bucket}
        self.assertNotIn("nubian_civilization", all_polity_ids)

    def test_entity_type_culture_people_tribe_all_routed_to_lane(self) -> None:
        polities = [
            polity("some_culture", -2500, -1500, "africa", "north_africa", entity_type="culture"),
            polity("some_people", -2500, -1500, "africa", "north_africa", entity_type="people"),
            polity("some_tribe", -2500, -1500, "africa", "north_africa", entity_type="tribe"),
        ]
        tree = build_explore_tree(polities, self.base_periods, [])
        lane_ids = {e["id"] for e in tree["chapters"][0]["civilizations"]}
        self.assertEqual(lane_ids, {"some_culture", "some_people", "some_tribe"})

    def test_lane_polity_entry_always_curated_and_carries_entity_type(self) -> None:
        polities = [polity("nubian_civilization", -2500, -1500, "africa", "north_africa", entity_type="civilization")]
        tree = build_explore_tree(polities, self.base_periods, [])
        entry = tree["chapters"][0]["civilizations"][0]
        self.assertTrue(entry["curated"])
        self.assertEqual(entry["source"], "polity")
        self.assertEqual(entry["entity_type"], "civilization")

    def test_plain_polity_entity_type_unaffected(self) -> None:
        """A polity with no entity_type (or entity_type="polity") still
        renders in the ordinary Polities row, not the new lane."""
        polities = [polity("old_kingdom_egypt", -2500, -1500, "africa", "north_africa")]
        tree = build_explore_tree(polities, self.base_periods, [])
        self.assertEqual(tree["chapters"][0]["civilizations"], [])
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        self.assertIn("old_kingdom_egypt", {e["id"] for e in region_bucket})

    def test_civilization_named_period_routed_to_lane_not_era(self) -> None:
        periods = [*self.base_periods, named_period("minoan_civilization", -2700, -1450, continents=["africa"])]
        tree = build_explore_tree([], periods, [])
        chapter_out = tree["chapters"][0]
        self.assertEqual([e["id"] for e in chapter_out["civilizations"]], ["minoan_civilization"])
        egypt_era = next(e for e in chapter_out["eras"] if e["id"] == "egypt_era")
        self.assertNotIn("minoan_civilization", {p["id"] for p in egypt_era["periods"]})

    def test_name_matched_lane_period_entry_not_curated(self) -> None:
        """A name-heuristic match (no CIVILIZATION_BACKDROP_AUTHORITY) is a
        guess, not a classification -- curated=False."""
        periods = [*self.base_periods, named_period("minoan_civilization", -2700, -1450, continents=["africa"])]
        tree = build_explore_tree([], periods, [])
        entry = tree["chapters"][0]["civilizations"][0]
        self.assertFalse(entry["curated"])
        self.assertEqual(entry["source"], "period")

    def test_civilization_backdrop_authority_routes_to_lane_and_is_curated(self) -> None:
        """A period carrying CIVILIZATION_BACKDROP_AUTHORITY belongs in the
        lane even when its canonical_name doesn't contain "civilization"/
        "culture" (reproduces the babylonia_period/chinese_empire_period
        case: their source polity was deleted, so the entity_type-lineage
        path no longer applies, but the authority marker still does) --
        and, unlike a bare name-match, this is curated=True."""
        periods = [*self.base_periods, named_period("babylonia", -1900, -1300, continents=["asia"], authority=CIVILIZATION_BACKDROP_AUTHORITY)]
        tree = build_explore_tree([], periods, [])
        chapter_out = next(c for c in tree["chapters"] if c["id"] == "macro_early")
        self.assertEqual([e["id"] for e in chapter_out["civilizations"]], ["babylonia"])
        entry = chapter_out["civilizations"][0]
        self.assertTrue(entry["curated"])
        self.assertEqual(entry["source"], "period")
        egypt_era = next(e for e in chapter_out["eras"] if e["id"] == "egypt_era")
        self.assertNotIn("babylonia", {p["id"] for p in egypt_era["periods"]})

    def test_culture_named_period_also_matches(self) -> None:
        periods = [*self.base_periods, named_period("nok_culture", -2000, -1500, continents=["africa"])]
        tree = build_explore_tree([], periods, [])
        self.assertEqual([e["id"] for e in tree["chapters"][0]["civilizations"]], ["nok_culture"])

    def test_regional_era_tier_with_civilization_in_name_not_pulled_into_lane(self) -> None:
        """Guards the tier check in _is_civilization_lane_period: a
        regional_era is a structural grouping node, not an entity, even if
        its name happens to contain "civilization"."""
        periods = [
            chapter("macro_early", -3500, -1200),
            era("early_civilizations_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
        ]
        tree = build_explore_tree([], periods, [])
        self.assertEqual(tree["chapters"][0]["civilizations"], [])
        self.assertEqual([e["id"] for e in tree["chapters"][0]["eras"]], ["early_civilizations_era"])

    def test_non_matching_period_still_nests_under_era_as_before(self) -> None:
        periods = [*self.base_periods, named_period("old_kingdom", -2686, -2181, broader=["egypt_era"])]
        tree = build_explore_tree([], periods, [])
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertIn("old_kingdom", {p["id"] for p in egypt_era["periods"]})

    def test_lane_placed_in_correct_chapter_by_date_overlap(self) -> None:
        periods = [
            chapter("macro_early", -3500, -1200),
            chapter("macro_classical", -1200, 500),
            named_period("late_culture", -900, -200),
        ]
        tree = build_explore_tree([], periods, [])
        early = next(c for c in tree["chapters"] if c["id"] == "macro_early")
        classical = next(c for c in tree["chapters"] if c["id"] == "macro_classical")
        self.assertEqual(early["civilizations"], [])
        self.assertEqual([e["id"] for e in classical["civilizations"]], ["late_culture"])

    def test_civilization_period_source_routes_plain_named_companion_period(self) -> None:
        """A period generated from an entity_type-tagged polity promoted to
        timeline_role: period (id convention "<polity_id>_period") is
        eligible for the lane via civilization_period_sources, even though
        its canonical_name is a plain copy of the polity's name and doesn't
        match the text heuristic (reproduces the ancient_egypt_period case)."""
        periods = [*self.base_periods, named_period("ancient_egypt_period", -4000, -29, continents=["africa"])]
        tree = build_explore_tree([], periods, [], civilization_period_sources={"ancient_egypt": "civilization"})
        chapter_out = tree["chapters"][0]
        self.assertEqual([e["id"] for e in chapter_out["civilizations"]], ["ancient_egypt_period"])
        egypt_era = next(e for e in chapter_out["eras"] if e["id"] == "egypt_era")
        self.assertNotIn("ancient_egypt_period", {p["id"] for p in egypt_era["periods"]})

    def test_civilization_period_source_entry_is_curated_and_carries_entity_type(self) -> None:
        periods = [*self.base_periods, named_period("ancient_egypt_period", -4000, -29, continents=["africa"])]
        tree = build_explore_tree([], periods, [], civilization_period_sources={"ancient_egypt": "civilization"})
        entry = tree["chapters"][0]["civilizations"][0]
        self.assertTrue(entry["curated"])
        self.assertEqual(entry["entity_type"], "civilization")

    def test_period_id_not_in_sources_stays_in_ordinary_era(self) -> None:
        """Only an exact "<id>_period" match against civilization_period_sources
        routes a period into the lane -- an unrelated period ending in
        "_period" that isn't in the lookup is untouched."""
        periods = [*self.base_periods, named_period("some_other_period", -2686, -2181, broader=["egypt_era"])]
        tree = build_explore_tree([], periods, [], civilization_period_sources={"ancient_egypt": "civilization"})
        self.assertEqual(tree["chapters"][0]["civilizations"], [])
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertIn("some_other_period", {p["id"] for p in egypt_era["periods"]})

    def test_missing_civilization_period_sources_defaults_to_empty(self) -> None:
        """build_explore_tree still works when called without the new
        parameter (existing callers/tests use the 3-arg form)."""
        periods = [*self.base_periods, named_period("old_kingdom", -2686, -2181, broader=["egypt_era"])]
        tree = build_explore_tree([], periods, [])
        egypt_era = next(e for e in tree["chapters"][0]["eras"] if e["id"] == "egypt_era")
        self.assertIn("old_kingdom", {p["id"] for p in egypt_era["periods"]})

    def test_lane_entries_sorted_by_start_then_id(self) -> None:
        polities = [
            polity("later_civilization", -2000, -1500, "africa", entity_type="civilization"),
            polity("earlier_civilization", -3000, -2500, "africa", entity_type="civilization"),
        ]
        tree = build_explore_tree(polities, self.base_periods, [])
        self.assertEqual(
            [e["id"] for e in tree["chapters"][0]["civilizations"]],
            ["earlier_civilization", "later_civilization"],
        )


class EpochLaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.periods = [
            chapter("macro_early", -3500, -1200),
            era("egypt_era", -3100, -1070, "macro_early", ["africa"], ["north_africa"]),
        ]

    def test_epoch_lane_period_reaches_the_top_level_epochs_list(self) -> None:
        periods = [*self.periods, named_period("holocene", -9701, 2100, epoch_lane=True)]
        tree = build_explore_tree([], periods, [])
        self.assertEqual([e["id"] for e in tree["epochs"]], ["holocene"])

    def test_epoch_lane_period_excluded_from_the_ordinary_period_row(self) -> None:
        periods = [*self.periods, named_period("holocene", -9701, 2100, epoch_lane=True)]
        tree = build_explore_tree([], periods, [])
        all_period_ids = {p["id"] for era_entry in tree["chapters"][0]["eras"] for p in era_entry["periods"]}
        self.assertNotIn("holocene", all_period_ids)

    def test_epoch_lane_period_gets_its_detail_of_children_attached(self) -> None:
        periods = [
            *self.periods,
            named_period("holocene", -9701, 2100, epoch_lane=True),
            named_period("greenlandian", -9701, -6237, detail_of="holocene"),
        ]
        tree = build_explore_tree([], periods, [])
        holocene_entry = next(e for e in tree["epochs"] if e["id"] == "holocene")
        self.assertEqual([d["id"] for d in holocene_entry["details"]], ["greenlandian"])
        self.assertEqual(holocene_entry["details"][0]["kind"], "period")

    def test_non_epoch_period_is_not_in_epochs_list(self) -> None:
        periods = [*self.periods, named_period("old_kingdom", -2686, -2181, broader=["egypt_era"])]
        tree = build_explore_tree([], periods, [])
        self.assertEqual(tree["epochs"], [])

    def test_epochs_sorted_by_start(self) -> None:
        periods = [
            *self.periods,
            named_period("later_epoch", -1000, 2100, epoch_lane=True),
            named_period("earlier_epoch", -9701, -1000, epoch_lane=True),
        ]
        tree = build_explore_tree([], periods, [])
        self.assertEqual([e["id"] for e in tree["epochs"]], ["earlier_epoch", "later_epoch"])


if __name__ == "__main__":
    unittest.main()
