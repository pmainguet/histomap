async function main() {
  const container = document.querySelector("#hierarchy-chart");
  const toggle = document.querySelector("#polities-toggle");
  const resetLink = document.querySelector("#zoom-reset");
  let fullTree = null;
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

  const draw = () => {
    const tree = zoomRange ? filterTreeToRange(fullTree, zoomRange.start, zoomRange.end) : fullTree;
    resetLink.hidden = !zoomRange;
    renderHierarchyTimeline(tree, container, toggle.value, onSelect);
  };

  // Click opens the detail panel (informational only -- see
  // explore_details.js); zooming happens from a button inside the panel,
  // matching "/"'s own click-opens-panel pattern.
  let detailCtx = null;
  const onSelect = (kind, id) => {
    if (detailCtx) showExploreDetails(kind, id, detailCtx);
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
    };
    draw();
    toggle.addEventListener("change", draw);
    resetLink.addEventListener("click", (event) => {
      event.preventDefault();
      resetZoom();
    });
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load explore_tree.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
