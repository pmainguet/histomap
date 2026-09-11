// Standalone /population page: the same per-continent population chart as
// /explore's Population lane (see explore_timeline.js's drawPopulationRow/
// renderPopulationChart and explore.js's buildPopulationSeries, all shared
// via classic-script global scope -- see population.html's load order),
// just full-size on its own page with nothing else competing for room.
//
// Deliberately minimal compared to explore.js: no tree/polities/periods/
// events data at all, no group-by/geo-filter, no search. Only what
// renderPopulationChart and renderPopulationDetails (explore_details.js)
// actually need.

async function main() {
  const container = document.querySelector("#population-chart");
  const resetLink = document.querySelector("#zoom-reset");

  let fullSeries = [];
  // Full data domain, from the series itself -- not tree.axis.domain_start
  // (-3,000,000, the paleolithic origin used by /explore's full hierarchy
  // chart), since population data itself never reaches back past 10,000
  // BCE and that empty multi-million-year prefix would just waste width.
  let fullDomain = { start: -10000, end: 2025 };
  let zoomRange = null;

  const padded = (start, end) => {
    const span = Math.max(1, end - start);
    const pad = Math.min(span * 0.1, 5000);
    return { start: start - pad, end: end + pad };
  };

  const draw = () => {
    const domain = zoomRange || fullDomain;
    const series = fullSeries.filter((entry) => entry.year >= domain.start && entry.year <= domain.end);
    renderPopulationChart(container, series, domain, onSelect);
  };

  const zoomToRange = (start, end) => {
    zoomRange = padded(Math.max(fullDomain.start, start), Math.min(fullDomain.end, end));
    resetLink.hidden = false;
    draw();
  };

  const resetZoom = () => {
    zoomRange = null;
    resetLink.hidden = true;
    draw();
  };

  const populationById = new Map();
  const detailCtx = {
    onZoomToRange: (start, end) => zoomToRange(start, end),
    onResetZoom: resetZoom,
    populationById,
  };

  const onSelect = (kind, id) => {
    if (kind === "population") showExploreDetails("population", id, detailCtx);
  };

  try {
    let hydeByContinent = [];
    try {
      const hydeResponse = await fetch("/population_by_continent.json");
      if (hydeResponse.ok) hydeByContinent = await hydeResponse.json();
    } catch {
      hydeByContinent = []; // falls back to WORLD_POPULATION_ESTIMATES below -- see buildPopulationSeries
    }
    fullSeries = buildPopulationSeries(hydeByContinent);
    populationById.clear();
    for (const entry of fullSeries) populationById.set(entry.id, entry);
    if (fullSeries.length > 0) {
      fullDomain = { start: fullSeries[0].year, end: fullSeries[fullSeries.length - 1].year };
    }

    resetLink.addEventListener("click", (event) => {
      event.preventDefault();
      resetZoom();
    });
    document.querySelector("#zoom-to-years").addEventListener("click", () => {
      const startValue = document.querySelector("#zoom-start-year").value;
      const endValue = document.querySelector("#zoom-end-year").value;
      if (startValue === "" || endValue === "") return;
      const start = Number(startValue);
      const end = Number(endValue);
      if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return;
      zoomToRange(start, end);
    });

    draw();
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load population data (${error.message}).</p>`;
  }
}

main();
