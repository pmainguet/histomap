// Greedy interval-graph coloring: assigns each item (already sorted by
// start ascending) to the first lane whose last-placed item ends at or
// before this item's start, opening a new lane otherwise. Produces the
// minimum number of lanes needed so that no two items in the same lane
// overlap in time. Used for rows where entries aren't mutually exclusive
// in time (regional eras, named periods, polities within one region).
function packIntoLanes(items) {
  const lanes = [];
  for (const item of items) {
    const itemEnd = item.end ?? Infinity;
    let placed = false;
    for (const lane of lanes) {
      const last = lane[lane.length - 1];
      const lastEnd = last.end ?? Infinity;
      if (lastEnd <= item.start) {
        lane.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) lanes.push([item]);
  }
  return lanes;
}
