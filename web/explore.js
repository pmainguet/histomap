// ROADMAP.md item 0: minimal hand-authoring path for a brand-new polity or
// period, alongside the existing Wikidata-ingestion and period-conversion
// paths. Lives here (the page-level controller) rather than
// explore_details.js -- that file is entity-detail-panel logic, this is a
// page-level "create" action with no existing record to attach to yet.
// Reuses the same postJson/escapeHtml/REBUILD_NOTE helpers and
// .country-checklist/.country-filter CSS classes as the geography editor
// (explore_details.js) so the two stay visually and behaviorally
// consistent.
function createEntityDialogHtml(geographyOptions) {
  const countries = [...(geographyOptions?.countries || [])].sort((a, b) => a.label.localeCompare(b.label));
  return `<dialog class="create-entity-dialog">
    <h2>New entity</h2>
    <div class="detail-edit-row">
      <label>Type
        <select name="create-kind">
          <option value="polity">Polity</option>
          <option value="period">Period</option>
          <option value="event">Event</option>
        </select>
      </label>
    </div>
    <div class="detail-edit-row"><label class="create-entity-name">Name <input type="text" name="create-name" required></label></div>
    <div class="detail-edit-row">
      <label><span class="create-start-label">Start year</span> <input type="number" name="create-start" required></label>
      <label class="create-entity-end-field">End year <input type="number" name="create-end"></label>
      <label class="create-entity-open-ended"><input type="checkbox" name="create-open-ended"> Still ongoing (polity only)</label>
    </div>
    <small>Negative years are BCE -- e.g. -500 for 500 BCE.</small>
    <fieldset class="create-entity-countries"><legend>Present countries</legend>
      <input class="country-filter" type="search" placeholder="Filter countries…" aria-label="Filter country list">
      <div class="country-checklist">${countries.map((country) => `<label data-country-search="${escapeHtml(`${country.label} ${country.code}`.toLowerCase())}"><input type="checkbox" name="create-country" value="${escapeHtml(country.code)}"> ${escapeHtml(country.label)} <small>${escapeHtml(country.code)}</small></label>`).join("")}</div>
      <small>At least one is required -- it drives placement in the timeline.</small>
    </fieldset>
    <small class="create-entity-event-note" hidden>An event's detail_of/bounds attachment is set afterward, via the raw-fields editor or the events review queue.</small>
    <p class="create-entity-status" role="status"></p>
    <div class="detail-edit-row create-entity-actions">
      <button type="button" class="create-entity-cancel">Cancel</button>
      <button type="button" class="create-entity-submit">Create</button>
    </div>
  </dialog>`;
}

function wireCreateEntityDialog(triggerButton, geographyOptions, { onCreated }) {
  document.body.insertAdjacentHTML("beforeend", createEntityDialogHtml(geographyOptions));
  const dialog = document.querySelector(".create-entity-dialog");
  const status = dialog.querySelector(".create-entity-status");
  const kindSelect = dialog.querySelector('[name="create-kind"]');
  const startLabel = dialog.querySelector(".create-start-label");
  const endField = dialog.querySelector(".create-entity-end-field");
  const endInput = dialog.querySelector('[name="create-end"]');
  const openEndedField = dialog.querySelector(".create-entity-open-ended");
  const openEndedCheckbox = dialog.querySelector('[name="create-open-ended"]');
  const countriesFieldset = dialog.querySelector(".create-entity-countries");
  const eventNote = dialog.querySelector(".create-entity-event-note");
  const setStatus = (message, isError) => {
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(isError));
  };
  // A period requires a finite end (schema.py has no open-ended period) --
  // the "still ongoing" shortcut only makes sense for a polity. An event
  // (ROADMAP.md item 5) has a single `year` instead of a start/end range,
  // and no present_countries of its own (its placement comes from its
  // detail_of/bounds attachment, set afterward) -- so it hides the whole
  // End year/Still ongoing/Present countries block and relabels Start year.
  const syncFieldsForKind = () => {
    const kind = kindSelect.value;
    const isEvent = kind === "event";
    const isPeriod = kind === "period";
    startLabel.textContent = isEvent ? "Year" : "Start year";
    endField.hidden = isEvent;
    openEndedField.hidden = isEvent || isPeriod;
    countriesFieldset.hidden = isEvent;
    eventNote.hidden = !isEvent;
    if (isPeriod || isEvent) openEndedCheckbox.checked = false;
    endInput.disabled = openEndedCheckbox.checked;
    if (openEndedCheckbox.checked) endInput.value = "";
  };
  kindSelect.addEventListener("change", syncFieldsForKind);
  openEndedCheckbox.addEventListener("change", syncFieldsForKind);
  dialog.querySelector(".country-filter").addEventListener("input", (event) => {
    const query = event.target.value.trim().toLowerCase();
    dialog.querySelectorAll(".country-checklist label").forEach((label) => {
      label.hidden = query.length > 0 && !label.dataset.countrySearch.includes(query);
    });
  });
  triggerButton.addEventListener("click", () => {
    dialog.querySelector('[name="create-name"]').value = "";
    dialog.querySelector('[name="create-start"]').value = "";
    endInput.value = "";
    openEndedCheckbox.checked = false;
    kindSelect.value = "polity";
    dialog.querySelectorAll('[name="create-country"]:checked').forEach((input) => { input.checked = false; });
    syncFieldsForKind();
    setStatus("", false);
    dialog.showModal();
  });
  dialog.querySelector(".create-entity-cancel").addEventListener("click", () => dialog.close());
  dialog.querySelector(".create-entity-submit").addEventListener("click", async () => {
    const kind = kindSelect.value;
    const canonicalName = dialog.querySelector('[name="create-name"]').value.trim();
    const start = dialog.querySelector('[name="create-start"]').value;
    const end = openEndedCheckbox.checked ? null : endInput.value;
    const presentCountries = [...dialog.querySelectorAll('[name="create-country"]:checked')].map((input) => input.value);
    if (!canonicalName || start === "" || (kind === "period" && (end === "" || end === null))) {
      setStatus(`Name and ${kind === "event" ? "year" : "start year"}${kind === "period" ? ", and end year," : ""} are required.`, true);
      return;
    }
    if (kind !== "event" && !presentCountries.length) {
      setStatus("At least one present country is required.", true);
      return;
    }
    const endpoint = kind === "polity" ? "/api/polities" : kind === "period" ? "/api/periods" : "/api/events";
    const body = kind === "event"
      ? { canonical_name: canonicalName, year: Number(start) }
      : {
          canonical_name: canonicalName,
          start: Number(start),
          end: end === "" || end === null ? null : Number(end),
          present_countries: presentCountries,
        };
    try {
      const result = await postJson(endpoint, "POST", body);
      const record = result.document;
      onCreated(kind, record);
      const rebuildNote = kind === "event"
        ? "Saved. It's in the events review queue until confirmed there."
        : REBUILD_NOTE;
      setStatus(`Created "${record.canonical_name}" (${record.id}). ${rebuildNote}`, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

// ROADMAP.md item: a search field next to the top controls -- select a
// result to zoom the timeline to it and open its side panel. Searches
// polities and periods in parallel (same dual-search pattern
// wireDetailOfEditor already uses in explore_details.js); events aren't
// searched here since there's no /api/events/search endpoint (the events
// review queue and the shared Events lane are the ways to reach one today).
function wireEntitySearch(detailCtx, zoomToRange, onSelect) {
  const input = document.querySelector("#entity-search");
  const resultsEl = document.querySelector(".entity-search-results");
  if (!input || !resultsEl) return;
  const searchOneKind = async (url, kind) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    return payload.items.map((item) => ({ ...item, kind }));
  };
  const closeResults = () => { resultsEl.hidden = true; resultsEl.innerHTML = ""; };
  const runSearch = async () => {
    const query = input.value.trim();
    if (query.length < 2) { closeResults(); return; }
    const q = encodeURIComponent(query);
    const [politiesFound, periodsFound] = await Promise.all([
      searchOneKind(`/api/polities/search?q=${q}&limit=10`, "polity"),
      searchOneKind(`/api/periods/search?q=${q}&limit=10`, "period"),
    ]);
    const candidates = [...politiesFound, ...periodsFound]
      .sort((a, b) => b.search_score - a.search_score)
      .slice(0, 10);
    if (!candidates.length) {
      resultsEl.hidden = false;
      resultsEl.innerHTML = "<p>No matches found.</p>";
      return;
    }
    resultsEl.hidden = false;
    resultsEl.innerHTML = candidates.map((item) => {
      const id = item.polity_id || item.period_id;
      return `<button type="button" class="entity-search-choice" data-entity-search-id="${escapeHtml(id)}" data-entity-search-kind="${item.kind}">
        <strong>${escapeHtml(item.canonical_name)}</strong>
        <span>${item.kind === "period" ? "Period" : "Polity"} · ${formatYear(item.canonical_start)}–${formatYear(item.canonical_end)}</span>
      </button>`;
    }).join("");
    resultsEl.querySelectorAll("[data-entity-search-id]").forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.entitySearchId;
        const kind = button.dataset.entitySearchKind;
        const record = kind === "polity" ? detailCtx.politiesById.get(id) : detailCtx.periodsById.get(id);
        if (!record) return;
        zoomToRange(record.start, record.end ?? detailCtx.domainEnd, record.detail_of || id);
        onSelect(kind, id);
        input.value = "";
        closeResults();
      });
    });
  };
  // Debounced, not a live-as-you-type flood -- one request ~200ms after
  // typing settles, same idea as any other search-while-typing field.
  let debounceHandle = null;
  input.addEventListener("input", () => {
    window.clearTimeout(debounceHandle);
    debounceHandle = window.setTimeout(() => { runSearch().catch(() => {}); }, 200);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeResults();
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".entity-search-wrapper")) closeResults();
  });
}

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

  // Detail-of reveal state (see explore_timeline.js's DETAIL_PANEL_HEIGHT
  // section) -- owned here, not by the render function, so it survives the
  // re-renders that zoom/groupBy/showPolities changes already trigger.
  // Holds container ids (a Polities-row entry's own id) whose detail panel
  // is open; no persistence across reload, several can be open at once.
  const expandedIds = new Set();
  const isExpanded = (id) => expandedIds.has(id);
  const toggleExpand = (id) => {
    if (expandedIds.has(id)) expandedIds.delete(id);
    else expandedIds.add(id);
    draw();
  };

  const padded = (start, end) => {
    const span = Math.max(1, end - start);
    const pad = Math.min(span * 0.1, 5000);
    return { start: start - pad, end: end + pad };
  };

  const zoomToRange = (start, end, expandId) => {
    zoomRange = padded(start, end);
    // Auto-open the enclosing panel for whatever's being zoomed to -- a
    // detail_of entity's container id (see explore_details.js callers), or
    // harmlessly an id with no details at all (no-op in that case).
    if (expandId) expandedIds.add(expandId);
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
      // ROADMAP.md item: "all" | "main" | "hide" -- was a boolean show/hide.
      showPolities: showPolitiesInput.value,
      geoFilter: geoFilterSelect.hidden ? null : geoFilterSelect.value,
      // Built once from the full, unzoomed tree (see below) so era colors
      // stay stable across zoom/filter re-renders instead of shifting as the
      // visible era subset changes.
      eraColorMap,
      isExpanded,
      onToggleExpand: toggleExpand,
      // ROADMAP.md item 5: the shared Events lane -- a flat list, not part
      // of the tree (an event's placement comes from its own `year`, not
      // from tree nesting the way chapters/eras/periods are).
      events: detailCtx ? [...detailCtx.eventsById.values()] : [],
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
    const [treeResponse, politiesResponse, periodsResponse, periodLinksResponse, transitionsResponse, eventsResponse, geographyOptionsResponse] = await Promise.all([
      fetch("/explore_tree.json"),
      fetch("/data.json"),
      fetch("/periods.json"),
      fetch("/period_links.json"),
      fetch("/transitions.json"),
      fetch("/events.json"),
      fetch("/api/options/geography"),
    ]);
    for (const response of [treeResponse, politiesResponse, periodsResponse, periodLinksResponse, transitionsResponse, eventsResponse, geographyOptionsResponse]) {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    }
    fullTree = await treeResponse.json();
    eraColorMap = buildEraColorMap(fullTree);
    const polities = await politiesResponse.json();
    const periods = await periodsResponse.json();
    const periodLinks = await periodLinksResponse.json();
    const transitions = await transitionsResponse.json();
    // ROADMAP.md item 5 -- published (eligibility: accepted) events only,
    // same "review stays invisible until accepted" policy events.json
    // itself already enforces at build time.
    const events = await eventsResponse.json();
    const geographyOptions = await geographyOptionsResponse.json();
    detailCtx = {
      politiesById: new Map(polities.map((polity) => [polity.id, polity])),
      periodsById: new Map(periods.map((period) => [period.id, period])),
      eventsById: new Map(events.map((event) => [event.id, event])),
      periodLinks,
      transitions,
      geographyOptions,
      domainEnd: fullTree.axis.domain_end,
      onZoomToRange: zoomToRange,
      onResetZoom: resetZoom,
      onEdit: revealBuildButton,
    };
    updateGeoFilterOptions();
    draw();
    // Deep link for jumping here from elsewhere (e.g. /consolidation-review's
    // "Edit in /explore" link) straight to one record, zoomed and with its
    // detail panel already open -- ?entity=<id>, looked up as a polity first
    // (the common case), then a period, then an event (ROADMAP.md item 5).
    // Silently does nothing if the id isn't found, rather than showing an
    // error -- the rest of the page still loads and works normally either way.
    const entityId = new URLSearchParams(location.search).get("entity");
    if (entityId) {
      const record = detailCtx.politiesById.get(entityId) || detailCtx.periodsById.get(entityId);
      if (record) {
        const kind = detailCtx.politiesById.has(entityId) ? "polity" : "period";
        zoomToRange(record.start, record.end ?? fullTree.axis.domain_end, record.detail_of || entityId);
        onSelect(kind, entityId);
      } else {
        const event = detailCtx.eventsById.get(entityId);
        if (event) {
          zoomToRange(event.year, event.year, (event.detail_of || [])[0] || entityId);
          onSelect("event", entityId);
        }
      }
    }
    wireCreateEntityDialog(document.querySelector("[data-create-entity]"), geographyOptions, {
      onCreated: (kind, record) => {
        if (kind === "polity") detailCtx.politiesById.set(record.id, record);
        else if (kind === "period") detailCtx.periodsById.set(record.id, record);
        else detailCtx.eventsById.set(record.id, record);
        revealBuildButton();
      },
    });
    wireEntitySearch(detailCtx, zoomToRange, onSelect);
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
    // ROADMAP.md item: an explicit start/end year selector to zoom in/out,
    // alongside the existing click-a-band and "Zoom to this" panel button
    // ways to do it.
    document.querySelector("#zoom-to-years").addEventListener("click", () => {
      const startValue = document.querySelector("#zoom-start-year").value;
      const endValue = document.querySelector("#zoom-end-year").value;
      if (startValue === "" || endValue === "") return;
      const start = Number(startValue);
      const end = Number(endValue);
      if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return;
      zoomToRange(start, end);
    });
  } catch (error) {
    container.innerHTML = `<p class="error">Could not load explore_tree.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
