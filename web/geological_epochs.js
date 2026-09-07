// ICS-ratified boundaries (2018), converted to the calendar-year display
// convention used elsewhere in this app. Deliberately NOT a periods/*.yaml
// record or a Period.tier value -- see ONTOLOGY.md's "Why this exists" and
// "Tree, lanes, graph" sections for why this stays a static display-only
// asset rather than a data-layer citizen. Segment widths are proportional
// and not rescaled for readability; the sub-Pleistocene epochs render as
// thin slivers by design. Informational, not a primary navigation element
// (no click/zoom handler, unlike every data-driven row below it) -- but
// found live, 7 September 2026, genuinely invisible rather than merely
// understated: the row's fill matched the page background exactly, and
// its band names were never drawn as visible text (only inert SVG
// <title> tooltips). Both fixed in explore_timeline.js/styles.css.
const GEOLOGICAL_EPOCHS = [
  { id: "pleistocene", name: "Pleistocene", start: -2588000, end: -9701 },
  { id: "greenlandian", name: "Greenlandian (Early Holocene)", start: -9701, end: -6237 },
  { id: "northgrippian", name: "Northgrippian (Middle Holocene)", start: -6237, end: -2251 },
  { id: "meghalayan", name: "Meghalayan (Late Holocene)", start: -2251, end: null },
];
