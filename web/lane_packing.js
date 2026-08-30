// Greedy interval-graph coloring: assigns each item (already sorted by
// start ascending) to the first lane whose last-placed item ends at or
// before this item's start, opening a new lane otherwise. Produces the
// minimum number of lanes needed so that no two items in the same lane
// overlap. `getRange` extracts each item's {start, end} for the overlap
// check -- defaults to the item's own start/end (time-domain), but a
// caller can pass a pixel-space accessor that also accounts for label
// width, so items whose LABELS would visually overlap (even if their
// time ranges don't) get pushed to separate lanes too. Used for rows
// where entries aren't mutually exclusive (regional eras, named periods,
// polities within one region).
function packIntoLanes(items, getRange = (item) => ({ start: item.start, end: item.end })) {
  const lanes = [];
  for (const item of items) {
    const { start, end } = getRange(item);
    const itemEnd = end ?? Infinity;
    let placed = false;
    for (const lane of lanes) {
      const last = lane[lane.length - 1];
      const lastEnd = getRange(last).end ?? Infinity;
      if (lastEnd <= start) {
        lane.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) lanes.push([item]);
  }
  return lanes;
}
