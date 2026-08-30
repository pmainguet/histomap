import unittest

from pipeline.build_explore_tree import AUTO_GENERATED_AUTHORITY, best_chapter_for_polity, build_explore_tree


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
                  historical_regions: list[str] | None = None) -> dict:
    """Build a minimal period fixture dict."""
    return {
        "id": id_, "tier": "period", "canonical_name": id_, "start": start, "end": end,
        "broader_periods": broader or [],
        "geography": {"continents": continents or [], "historical_regions": historical_regions or []},
    }


def polity(id_: str, start: int, end: int | None, continent: str, region: str | None = None,
           tier: str = "global", present_countries: list[str] | None = None) -> dict:
    """Build a minimal polity fixture dict."""
    return {
        "id": id_, "canonical_name": id_, "start": start, "end": end,
        "visibility_tier": tier,
        "geography": {
            "primary_continent": continent, "continents": [continent],
            "primary_historical_region": region, "historical_regions": [region] if region else [],
            "present_countries": present_countries or [],
        },
    }


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
            polity("out_of_scope", -2500, -2400, "africa", "north_africa", tier="detailed"),
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

    def test_out_of_scope_polity_excluded(self) -> None:
        tree = build_explore_tree(self.polities, self.periods, self.period_links)
        region_bucket = tree["chapters"][0]["polities_by_historical_region"]["north_africa"]
        self.assertNotIn("out_of_scope", {e["id"] for e in region_bucket})

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


if __name__ == "__main__":
    unittest.main()
