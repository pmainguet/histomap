// ICS-ratified Pleistocene boundary, converted to the calendar-year display
// convention used elsewhere in this app. Deliberately NOT a periods/*.yaml
// record or a Period.tier value -- see ONTOLOGY.md's "Why this exists" and
// "Tree, lanes, graph" sections for why this stays a static display-only
// asset rather than a data-layer citizen. Informational, not a primary
// navigation element (no click/zoom handler, unlike every data-driven row
// below it, including the epoch lane -- see explore_timeline.js -- that
// Holocene moved to, 8 September 2026): a Histomap record wasn't needed
// here since no Wikipedia gap-check item nor live request has asked for
// Pleistocene's own click/zoom/detail_of support yet, unlike Holocene's.
// If that changes, follow the same pattern: a real periods/*.yaml record
// with epoch_lane: true, not an addition to this array.
const GEOLOGICAL_EPOCHS = [
  { id: "pleistocene", name: "Pleistocene", start: -2588000, end: -9701 },
];
