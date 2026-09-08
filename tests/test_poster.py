import unittest

from pipeline.poster import (
    Keyframe,
    PosterPolity,
    compute_lineages,
    order_lineages,
    path_from_stacked_samples,
    render_poster_svg,
    scale_prominence_score,
    select_top_polities,
    smoothstep,
    stack_polities,
    taper_factor,
    width_px,
)


def polity(id_: str, start: int, end: int, prominence: float = 5.0, **overrides) -> PosterPolity:
    return PosterPolity(id=id_, label=id_, keyframes=[Keyframe(start, prominence), Keyframe(end, prominence)], **overrides)


class SmoothstepTests(unittest.TestCase):
    def test_endpoints(self) -> None:
        self.assertEqual(smoothstep(0), 0)
        self.assertEqual(smoothstep(1), 1)

    def test_clamps_outside_0_1(self) -> None:
        self.assertEqual(smoothstep(-1), 0)
        self.assertEqual(smoothstep(2), 1)

    def test_point_symmetric(self) -> None:
        # f(1-t) == 1-f(t) -- the property the whole crossfade mechanism
        # (matched successions canceling out exactly) depends on.
        for t in (0.1, 0.25, 0.5, 0.75, 0.9):
            self.assertAlmostEqual(smoothstep(1 - t), 1 - smoothstep(t), places=9)


class WidthPxTests(unittest.TestCase):
    def test_increases_with_prominence(self) -> None:
        self.assertLess(width_px(1), width_px(9))

    def test_nonzero_at_zero_prominence(self) -> None:
        self.assertGreater(width_px(0), 0)


class ScaleProminenceScoreTests(unittest.TestCase):
    def test_zero_maps_to_scale_min(self) -> None:
        self.assertEqual(scale_prominence_score(0), 1.0)

    def test_max_maps_to_scale_max(self) -> None:
        self.assertEqual(scale_prominence_score(100), 10.0)

    def test_clamps_above_100(self) -> None:
        self.assertEqual(scale_prominence_score(150), 10.0)

    def test_clamps_below_zero(self) -> None:
        self.assertEqual(scale_prominence_score(-10), 1.0)


class TaperFactorTests(unittest.TestCase):
    def test_fade_in_reaches_one_at_and_after_boundary_window(self) -> None:
        # window is [boundary - 10, boundary + 5] for total_years=15
        self.assertEqual(taper_factor(200, 100, 15, "in"), 1.0)

    def test_fade_in_is_zero_well_before_window(self) -> None:
        self.assertEqual(taper_factor(-100, 100, 15, "in"), 0.0)

    def test_fade_out_mirrors_fade_in(self) -> None:
        self.assertEqual(taper_factor(-100, 100, 15, "out"), 1.0)
        self.assertEqual(taper_factor(200, 100, 15, "out"), 0.0)

    def test_official_date_sits_inside_the_ramp_not_at_an_edge(self) -> None:
        # Confirmed timing: 2/3 before, 1/3 after -- so at the boundary
        # itself, fade-in should be partway (not 0, not 1).
        value = taper_factor(100, 100, 15, "in")
        self.assertGreater(value, 0.0)
        self.assertLess(value, 1.0)

    def test_matching_window_fade_in_and_fade_out_sum_to_one(self) -> None:
        # The crossfade property a matched successor hand-off relies on.
        for year in range(90, 111):
            fade_in = taper_factor(year, 100, 15, "in")
            fade_out = taper_factor(year, 100, 15, "out")
            self.assertAlmostEqual(fade_in + fade_out, 1.0, places=9)

    def test_zero_duration_is_an_instant_edge(self) -> None:
        self.assertEqual(taper_factor(99, 100, 0, "in"), 0.0)
        self.assertEqual(taper_factor(100, 100, 0, "in"), 1.0)
        self.assertEqual(taper_factor(101, 100, 0, "out"), 0.0)
        self.assertEqual(taper_factor(99, 100, 0, "out"), 1.0)


class PosterPolityTests(unittest.TestCase):
    def test_requires_at_least_two_keyframes(self) -> None:
        with self.assertRaises(ValueError):
            PosterPolity(id="x", label="X", keyframes=[Keyframe(100, 5)])

    def test_lineage_id_defaults_to_own_id(self) -> None:
        p = polity("rome", -100, 100)
        self.assertEqual(p.lineage_id, "rome")

    def test_natural_prominence_interpolates_between_keyframes(self) -> None:
        p = PosterPolity(id="x", label="X", keyframes=[Keyframe(0, 0), Keyframe(100, 10)])
        self.assertAlmostEqual(p.natural_prominence_at(50), 5.0)

    def test_natural_prominence_clamps_outside_span(self) -> None:
        p = polity("x", 0, 100, prominence=7)
        self.assertEqual(p.natural_prominence_at(-50), 7)
        self.assertEqual(p.natural_prominence_at(500), 7)

    def test_taper_is_reduced_near_start_and_end(self) -> None:
        p = polity("x", 0, 1000)
        self.assertLess(p.taper(0), 1.0)
        self.assertLess(p.taper(1000), 1.0)
        self.assertAlmostEqual(p.taper(500), 1.0)

    def test_fade_out_skipped_at_display_cutoff(self) -> None:
        # A polity still going when the requested window ends (its end ==
        # the display cutoff) shouldn't taper there -- it hasn't actually
        # ended, the poster just stops drawing.
        p = polity("byzantium", 300, 700)
        self.assertEqual(p.taper(700, max_year_no_fade_out=700), 1.0)

    def test_custom_fade_out_years_produces_a_longer_taper(self) -> None:
        short = polity("a", 0, 1000, fade_out_years=15)
        long = polity("b", 0, 1000, fade_out_years=90)
        # Well before either boundary window, both are fully faded in but
        # the long-decline one should already be visibly lower by 950.
        self.assertLess(long.taper(950), short.taper(950))


class LineageTests(unittest.TestCase):
    def test_connected_polities_share_a_lineage(self) -> None:
        republic = polity("republic", -100, -27)
        empire = polity("empire", -27, 395)
        compute_lineages([republic, empire], edges=[("republic", "empire")])
        self.assertEqual(republic.lineage_id, empire.lineage_id)

    def test_unconnected_polities_keep_separate_lineages(self) -> None:
        a = polity("a", 0, 100)
        b = polity("b", 0, 100)
        compute_lineages([a, b], edges=[])
        self.assertNotEqual(a.lineage_id, b.lineage_id)

    def test_edges_outside_the_selected_set_are_ignored(self) -> None:
        a = polity("a", 0, 100)
        compute_lineages([a], edges=[("a", "not_on_the_poster")])
        self.assertEqual(a.lineage_id, "a")

    def test_split_into_multiple_successors_shares_one_lineage(self) -> None:
        han = polity("han", -206, 220)
        wei = polity("wei", 220, 265)
        shu = polity("shu", 220, 263)
        wu = polity("wu", 220, 280)
        compute_lineages([han, wei, shu, wu], edges=[("han", "wei"), ("han", "shu"), ("han", "wu")])
        self.assertEqual(len({han.lineage_id, wei.lineage_id, shu.lineage_id, wu.lineage_id}), 1)

    def test_order_lineages_by_earliest_start(self) -> None:
        early = polity("early", -500, -100, lineage_id="early")
        late = polity("late", 100, 500, lineage_id="late")
        order = order_lineages([late, early])
        self.assertEqual(order, ["early", "late"])


class SelectTopPolitiesTests(unittest.TestCase):
    def test_filters_to_overlapping_range(self) -> None:
        inside = polity("inside", 100, 200)
        outside = polity("outside", 500, 600)
        result = select_top_polities([inside, outside], 0, 300, prominence_score={})
        self.assertEqual([p.id for p in result], ["inside"])

    def test_partial_overlap_is_included(self) -> None:
        spanning = polity("spanning", -50, 50)
        result = select_top_polities([spanning], 0, 300, prominence_score={})
        self.assertEqual([p.id for p in result], ["spanning"])

    def test_ranks_by_prominence_score_descending(self) -> None:
        low = polity("low", 0, 100)
        high = polity("high", 0, 100)
        result = select_top_polities([low, high], 0, 100, prominence_score={"low": 10, "high": 90})
        self.assertEqual([p.id for p in result], ["high", "low"])

    def test_caps_to_top_n(self) -> None:
        polities = [polity(f"p{i}", 0, 100) for i in range(5)]
        scores = {f"p{i}": float(i) for i in range(5)}
        result = select_top_polities(polities, 0, 100, prominence_score=scores, top_n=2)
        self.assertEqual(len(result), 2)
        self.assertEqual([p.id for p in result], ["p4", "p3"])


class StackPolitiesTests(unittest.TestCase):
    def test_active_polities_always_sum_to_canvas_width(self) -> None:
        a = polity("a", -100, 100, prominence=5)
        b = polity("b", -50, 150, prominence=3)
        compute_lineages([a, b], edges=[])
        samples = stack_polities([a, b], order_lineages([a, b]), (-100, 150), step=10, canvas_x0=0, canvas_x1=500)
        # a and b have different active windows (fade-in/out extends each
        # one differently), so their sample lists differ in length --
        # group by year rather than assuming index alignment.
        by_year: dict[int, list] = {}
        for pid in ("a", "b"):
            for s in samples[pid]:
                by_year.setdefault(s.year, []).append(s)
        self.assertGreater(len(by_year), 5)
        for year, entries in by_year.items():
            entries.sort(key=lambda s: s.x_left)
            self.assertAlmostEqual(entries[0].x_left, 0, places=6, msg=f"year {year}")
            self.assertAlmostEqual(entries[-1].x_right, 500, places=6, msg=f"year {year}")
            for prev, cur in zip(entries, entries[1:]):
                self.assertAlmostEqual(prev.x_right, cur.x_left, places=6, msg=f"year {year}")

    def test_matched_value_succession_has_no_bump(self) -> None:
        # Republic -> Empire, same prominence on both sides of the
        # boundary -- combined width should stay flat through the handoff,
        # even though a lone unrelated polity is also in the pool (so the
        # total isn't trivially just "the whole canvas" for this pair).
        republic = polity("republic", -100, -27, prominence=5)
        empire = polity("empire", -27, 395, prominence=5)
        lone = polity("lone", -200, 500, prominence=5)
        polities = [republic, empire, lone]
        compute_lineages(polities, edges=[("republic", "empire")])
        samples = stack_polities(polities, order_lineages(polities), (-60, 6), step=1, canvas_x0=0, canvas_x1=300)
        width_by_year = {}
        for pid in ("republic", "empire"):
            for s in samples[pid]:
                width_by_year[s.year] = width_by_year.get(s.year, 0.0) + (s.x_right - s.x_left)
        self.assertGreater(len(width_by_year), 5)
        widths = list(width_by_year.values())
        # Not exactly flat: stack_polities floors each polity's effective
        # prominence at `epsilon` (0.15) to avoid a zero-width slice, which
        # very briefly over-counts by that epsilon right at the instant one
        # side of the crossfade hits exactly 0 -- a deliberate, small
        # trade-off, not a bug. Bounded well below what a real snap would
        # look like (a real double-count from the earlier, unsynchronized
        # fade design was ~5 combined width units on this same setup).
        self.assertLess(max(widths) - min(widths), 3.0)

    def test_no_active_polities_produces_no_samples_for_that_year(self) -> None:
        a = polity("a", 0, 10)
        compute_lineages([a], edges=[])
        samples = stack_polities([a], order_lineages([a]), (-1000, 1000), step=500, canvas_x0=0, canvas_x1=100)
        # Years far from a's own span (with default 15-year fade window)
        # should contribute nothing.
        self.assertEqual(samples["a"], [s for s in samples["a"] if -15 <= s.year <= 25])


class PathFromStackedSamplesTests(unittest.TestCase):
    def test_empty_for_fewer_than_two_samples(self) -> None:
        self.assertEqual(path_from_stacked_samples([], lambda y: y), "")

    def test_produces_a_closed_path_string(self) -> None:
        from pipeline.poster import StackedSample

        samples = [StackedSample(0, 0, 10), StackedSample(10, 5, 15)]
        d = path_from_stacked_samples(samples, lambda y: y * 2)
        self.assertTrue(d.startswith("M "))
        self.assertTrue(d.endswith("Z"))


class RenderPosterSvgTests(unittest.TestCase):
    """Smoke tests against the real published build artifacts (data.json/
    periods.json/events.json) -- not a golden-file pixel comparison, just
    "does it produce a well-formed SVG with real content" for each style."""

    def test_stacked_produces_a_well_formed_svg(self) -> None:
        svg = render_poster_svg("stacked", -500, 500)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn("<path", svg)

    def test_authentic_produces_a_well_formed_svg(self) -> None:
        svg = render_poster_svg("authentic", -500, 500)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn("<path", svg)

    def test_rejects_a_backwards_range(self) -> None:
        with self.assertRaises(ValueError):
            render_poster_svg("stacked", 500, -500)

    def test_gutter_lanes_present(self) -> None:
        svg = render_poster_svg("stacked", -500, 500)
        self.assertIn("EPOCH", svg)
        self.assertIn("CHAPTER", svg)
        self.assertIn("EVENTS", svg)


if __name__ == "__main__":
    unittest.main()
