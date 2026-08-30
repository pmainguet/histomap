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

  const onZoom = (start, end) => {
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
    renderHierarchyTimeline(tree, container, toggle.value, onZoom);
  };

  try {
    const response = await fetch("/explore_tree.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    fullTree = await response.json();
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
