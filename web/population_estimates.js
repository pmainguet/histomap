// Static reference data for the Population lane (ROADMAP.md item, 10
// September 2026) -- world population estimates over time, deliberately NOT
// a polities/*.yaml or periods/*.yaml record: like GEOLOGICAL_EPOCHS (see
// geological_epochs.js and ONTOLOGY.md's "Why this exists"/"Tree, lanes,
// graph" sections), this is a small, growable, hand-curated reference table
// with zero coupling to broader_periods/detail_of/period_links.yaml -- it
// isn't a "thing that existed" the way a polity or event is, so it doesn't
// belong in the data layer those model. Unlike GEOLOGICAL_EPOCHS, each point
// here IS individually clickable (see explore_timeline.js's drawPopulationRow
// and explore_details.js's renderPopulationDetails) since every figure below
// is a specific, sourced claim worth being able to check.
//
// Values are best-estimate point figures picked from published ranges, not
// the ranges themselves -- ancient/medieval figures come from the U.S.
// Census Bureau's compiled "Historical Estimates of World Population" (a
// synthesis of several demographers, chiefly Biraben and Durand); the
// 1804-2022 "billion" milestones come from the UN Population Division, as
// compiled on Wikipedia's "World population milestones" page. `label: true`
// marks the points worth a permanent on-band text label (roughly one per
// era) rather than relying on hover alone -- the rest are still individually
// clickable, just not labeled by default to avoid crowding the band.
const CENSUS_SOURCE = {
  name: "U.S. Census Bureau, Historical Estimates of World Population",
  url: "https://www.census.gov/data/tables/time-series/demo/international-programs/historical-est-worldpop.html",
};
const MILESTONE_SOURCE = {
  name: "UN Population Division, via Wikipedia's World population milestones",
  url: "https://en.wikipedia.org/wiki/World_population_milestones",
};

const WORLD_POPULATION_ESTIMATES = [
  { id: "pop_-10000", year: -10000, population: 1_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_-8000", year: -8000, population: 5_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_-4000", year: -4000, population: 7_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_-3000", year: -3000, population: 14_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_-2000", year: -2000, population: 27_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_-1000", year: -1000, population: 50_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_-500", year: -500, population: 100_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_-400", year: -400, population: 162_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1", year: 1, population: 230_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_500", year: 500, population: 190_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_700", year: 700, population: 210_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1000", year: 1000, population: 265_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_1200", year: 1200, population: 400_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1340", year: 1340, population: 443_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1400", year: 1400, population: 375_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_1500", year: 1500, population: 460_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1650", year: 1650, population: 545_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1700", year: 1700, population: 640_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1750", year: 1750, population: 770_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1804", year: 1804, population: 1_000_000_000, label: true, source: MILESTONE_SOURCE },
  { id: "pop_1850", year: 1850, population: 1_260_000_000, label: false, source: CENSUS_SOURCE },
  { id: "pop_1900", year: 1900, population: 1_650_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_1927", year: 1927, population: 2_000_000_000, label: false, source: MILESTONE_SOURCE },
  { id: "pop_1950", year: 1950, population: 2_500_000_000, label: true, source: CENSUS_SOURCE },
  { id: "pop_1960", year: 1960, population: 3_000_000_000, label: false, source: MILESTONE_SOURCE },
  { id: "pop_1974", year: 1974, population: 4_000_000_000, label: false, source: MILESTONE_SOURCE },
  { id: "pop_1987", year: 1987, population: 5_000_000_000, label: true, source: MILESTONE_SOURCE },
  { id: "pop_1999", year: 1999, population: 6_000_000_000, label: false, source: MILESTONE_SOURCE },
  { id: "pop_2011", year: 2011, population: 7_000_000_000, label: false, source: MILESTONE_SOURCE },
  { id: "pop_2022", year: 2022, population: 8_000_000_000, label: true, source: MILESTONE_SOURCE },
];
