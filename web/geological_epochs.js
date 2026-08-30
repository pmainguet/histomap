// ICS-ratified boundaries (2018), converted to the calendar-year display
// convention used elsewhere in this app. Deliberately NOT a periods/*.yaml
// record or a Period.tier value -- see ONTOLOGY.md's "Why this exists" and
// "Tree, lanes, graph" sections for why this stays a static display-only
// asset rather than a data-layer citizen. Segment widths are proportional
// and not rescaled for readability; the sub-Pleistocene epochs render as
// thin slivers by design (this band is informational/decorative, aria-hidden,
// not a primary navigation element).
const GEOLOGICAL_EPOCHS = [
  { id: "pleistocene", name: "Pleistocene", start: -2588000, end: -9701 },
  { id: "greenlandian", name: "Greenlandian (Early Holocene)", start: -9701, end: -6237 },
  { id: "northgrippian", name: "Northgrippian (Middle Holocene)", start: -6237, end: -2251 },
  { id: "meghalayan", name: "Meghalayan (Late Holocene)", start: -2251, end: null },
];
