async function main() {
  const container = document.querySelector("#hierarchy-chart");
  const toggle = document.querySelector("#polities-toggle");
  try {
    const response = await fetch("/explore_tree.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const tree = await response.json();
    const draw = () => renderHierarchyTimeline(tree, container, toggle.value);
    draw();
    toggle.addEventListener("change", draw);
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load explore_tree.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
