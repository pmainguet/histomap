async function main() {
  const container = document.querySelector("#hierarchy-chart");
  const showPolitiesInput = document.querySelector("#show-polities");
  const groupBySelect = document.querySelector("#group-by");
  const geoFilterSelect = document.querySelector("#geo-filter");
  const geoFilterLabel = document.querySelector("#geo-filter-label");
  const resetLink = document.querySelector("#zoom-reset");
  const buildButton = document.querySelector("[data-build-timeline]");
  let fullTree = null;
  let eraColorMap = null;
  let zoomRange = null;

  const padded = (start, end) => {
    const span = Math.max(1, end - start);
    const pad = Math.min(span * 0.1, 5000);
    return { start: start - pad, end: end + pad };
  };

  const zoomToRange = (start, end) => {
    zoomRange = padded(start, end);
    draw();
  };

  const resetZoom = () => {
    zoomRange = null;
    draw();
  };

  // The "Filter to" control (narrow every grouped row down to one continent/
  // country) only makes sense alongside Continent/Country grouping -- hidden
  // and reset to "All" when Group by is "None", so it can never silently
  // apply a stale filter the viewer can no longer see or change.
  const updateGeoFilterOptions = () => {
    const groupBy = groupBySelect.value;
    const hidden = groupBy === "none";
    geoFilterSelect.hidden = hidden;
    geoFilterLabel.hidden = hidden;
    if (hidden) {
      geoFilterSelect.value = "all";
      return;
    }
    const tree = zoomRange ? filterTreeToRange(fullTree, zoomRange.start, zoomRange.end) : fullTree;
    const previous = geoFilterSelect.value;
    const options = collectGeoFilterOptions(tree, groupBy);
    geoFilterSelect.replaceChildren(
      new Option("All", "all"),
      ...options.map((opt) => new Option(opt.label, opt.value)),
    );
    // Keep the previous selection if it's still a valid option for the new
    // grouping mode (e.g. switching Continent -> Country resets to "All"
    // since a continent key is meaningless as a country key).
    geoFilterSelect.value = options.some((opt) => opt.value === previous) ? previous : "all";
  };

  const draw = () => {
    const tree = zoomRange ? filterTreeToRange(fullTree, zoomRange.start, zoomRange.end) : fullTree;
    resetLink.hidden = !zoomRange;
    renderHierarchyTimeline(tree, container, {
      groupBy: groupBySelect.value,
      showPolities: showPolitiesInput.checked,
      geoFilter: geoFilterSelect.hidden ? null : geoFilterSelect.value,
      // Built once from the full, unzoomed tree (see below) so era colors
      // stay stable across zoom/filter re-renders instead of shifting as the
      // visible era subset changes.
      eraColorMap,
    }, onSelect);
  };

  // Click opens the detail panel (informational only -- see
  // explore_details.js); zooming happens from a button inside the panel,
  // matching "/"'s own click-opens-panel pattern.
  let detailCtx = null;
  const onSelect = (kind, id) => {
    if (detailCtx) showExploreDetails(kind, id, detailCtx);
  };

  // The "Build timeline" button (review_build.js, shared with /reviews) is
  // hidden until the side panel actually saves something -- explore_tree.json
  // is a separate pre-built artifact, so an edit here has no visible effect
  // on the chart until a build runs; showing the button unconditionally
  // would suggest one is always needed, which is only true once something
  // has actually changed this session.
  const revealBuildButton = () => {
    buildButton.hidden = false;
  };

  try {
    const [treeResponse, politiesResponse, periodsResponse, periodLinksResponse] = await Promise.all([
      fetch("/explore_tree.json"),
      fetch("/data.json"),
      fetch("/periods.json"),
      fetch("/period_links.json"),
    ]);
    for (const response of [treeResponse, politiesResponse, periodsResponse, periodLinksResponse]) {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    }
    fullTree = await treeResponse.json();
    eraColorMap = buildEraColorMap(fullTree);
    const polities = await politiesResponse.json();
    const periods = await periodsResponse.json();
    const periodLinks = await periodLinksResponse.json();
    detailCtx = {
      politiesById: new Map(polities.map((polity) => [polity.id, polity])),
      periodsById: new Map(periods.map((period) => [period.id, period])),
      periodLinks,
      domainEnd: fullTree.axis.domain_end,
      onZoomToRange: zoomToRange,
      onResetZoom: resetZoom,
      onEdit: revealBuildButton,
    };
    updateGeoFilterOptions();
    draw();
    showPolitiesInput.addEventListener("change", draw);
    groupBySelect.addEventListener("change", () => {
      updateGeoFilterOptions();
      draw();
    });
    geoFilterSelect.addEventListener("change", draw);
    resetLink.addEventListener("click", (event) => {
      event.preventDefault();
      resetZoom();
    });
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load explore_tree.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
