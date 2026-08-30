// Two-segment broken linear scale: years at or before `segmentBreak` get a
// small fixed share of the width (deep time is real but visually
// uninformative at true scale -- see docs/plans/2026-08-30-explore-hierarchy-timeline.md
// Task 2); years after get the rest, at a uniform linear rate. Both segments
// are individually linear -- proportions are honest within each segment,
// just not across the break. `marginLeft` reserves a fixed left-hand gutter
// (e.g. for persistent axis/tier labels): every x(year) is shifted right by
// that amount, so callers should pass `innerWidth` already excluding it.
function createTimeScale(domainStart, domainEnd, segmentBreak, innerWidth, deepTimeFraction = 0.1, marginLeft = 0) {
  const deepTimeWidth = innerWidth * deepTimeFraction;
  const recentWidth = innerWidth - deepTimeWidth;
  const deepSpan = segmentBreak - domainStart;
  const recentSpan = domainEnd - segmentBreak;

  function x(year) {
    if (year <= segmentBreak) {
      const fraction = deepSpan > 0 ? (year - domainStart) / deepSpan : 0;
      return marginLeft + fraction * deepTimeWidth;
    }
    const fraction = recentSpan > 0 ? (year - segmentBreak) / recentSpan : 0;
    return marginLeft + deepTimeWidth + fraction * recentWidth;
  }

  function width(start, end) {
    const clampedStart = Math.max(domainStart, start);
    const clampedEnd = Math.min(domainEnd, end ?? domainEnd);
    return Math.max(2, x(clampedEnd) - x(clampedStart));
  }

  // "Nice" round-number tick years (1/2/5 x10^n), restricted to the recent
  // segment -- deep-time ticks would be too sparse/large to be useful in a
  // 10%-width block. Mirrors app.js's niceTickStep but returns actual years,
  // not a step, since ticks must respect the segment break.
  function tickYears(targetCount = 8) {
    const rawStep = recentSpan / targetCount;
    const magnitude = 10 ** Math.floor(Math.log10(Math.max(1, rawStep)));
    const candidates = [1, 2, 5, 10].map((m) => m * magnitude);
    const step = candidates.find((c) => recentSpan / c <= targetCount * 1.5) || candidates[candidates.length - 1];
    const ticks = [];
    for (let year = Math.ceil(segmentBreak / step) * step; year <= domainEnd; year += step) {
      ticks.push(year);
    }
    return ticks;
  }

  return { x, width, tickYears, deepTimeWidth, recentWidth };
}
