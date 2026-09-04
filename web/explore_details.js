// Detail + edit panel for /explore -- mirrors app.js's showDetails/
// showPeriodDetails (the "/" timeline's panel), plus its own editing
// actions: convert a polity's entity_type or demote it to a period
// (POST .../convert-to-period), convert a period to an entity/polity
// (POST .../promote-to-entity), and a general "Edit fields" raw editor
// (PATCH .../fields) for anything else in the record (tier,
// broader_periods, dates, ...) that has no dedicated control. See
// STATUS.md's "review workspace" section for why this replaced the
// earlier read-only-only design.
//
// IMPORTANT: /explore's chart bands (which row/lane something renders in)
// come from the separately pre-built explore_tree.json, not from the
// politiesById/periodsById maps these edits update live -- an edit here
// updates the detail panel and the in-memory cache immediately, but the
// chart itself only reflects it after the next `build` run. Every save
// confirmation says so explicitly.

const explorePanel = document.querySelector("#details");
const explorePanelBackdrop = document.querySelector("#detail-backdrop");

const ENTITY_TYPE_OPTIONS = [
  "polity", "civilization", "subdivision", "micronation",
  "culture", "people", "tribe", "archaeological_horizon",
];
const PERIOD_KIND_OPTIONS = ["historical", "archaeological", "protohistorical", "prehistorical"];

const REBUILD_NOTE = "Saved. The record is updated; run a build for /explore's chart bands to reflect it.";

async function postJson(url, method, body) {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function optionsHtml(options, selected) {
  return options.map((value) =>
    `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(displayTerm(value))}</option>`
  ).join("");
}

// Geography editor -- polities only (periods have no geography endpoint).
// Mirrors app.js's geographyEditorMarkup/syncContinentsFromCountries/
// saveGeography ("/"'s own equivalent) closely enough that the two stay easy
// to compare, just renamed to this file's detail-* class convention.
function geographyEditorHtml(polity, geographyOptions) {
  const selectedContinents = new Set(polity.geography?.continents || []);
  const selectedCountries = new Set(polity.geography?.present_countries || []);
  const countries = [...(geographyOptions?.countries || [])].sort((a, b) => {
    const selectedDifference = Number(selectedCountries.has(b.code)) - Number(selectedCountries.has(a.code));
    return selectedDifference || a.label.localeCompare(b.label);
  });
  return `<details class="detail-geography-edit">
    <summary>Edit geography</summary>
    <fieldset><legend>Continents</legend><div class="geography-checkboxes">
      ${(geographyOptions?.continents || []).map((continent) => `<label><input type="checkbox" name="detail-continent" value="${escapeHtml(continent)}" ${selectedContinents.has(continent) ? "checked" : ""}> ${escapeHtml(displayTerm(continent))}</label>`).join("")}
    </div></fieldset>
    <label class="geography-primary">Primary continent / swimlane
      <select name="detail-primary-continent"><option value="">Automatic</option>${(geographyOptions?.continents || []).map((continent) => `<option value="${escapeHtml(continent)}" ${polity.geography?.primary_continent === continent ? "selected" : ""}>${escapeHtml(displayTerm(continent))}</option>`).join("")}</select>
    </label>
    <fieldset><legend>Present countries</legend>
      <input class="country-filter" type="search" placeholder="Filter countries…" aria-label="Filter country list">
      <div class="country-checklist">${countries.map((country) => `<label data-country-search="${escapeHtml(`${country.label} ${country.code}`.toLowerCase())}"><input type="checkbox" name="detail-country" value="${escapeHtml(country.code)}" ${selectedCountries.has(country.code) ? "checked" : ""}> ${escapeHtml(country.label)} <small>${escapeHtml(country.code)}</small></label>`).join("")}</div>
      <small>Choosing countries automatically updates the continents above.</small>
    </fieldset>
    <div class="detail-edit-row"><button type="button" class="detail-save-geography">Save geography</button></div>
  </details>`;
}

function wireGeographyEditor(polity, ctx, onSaved, setStatus) {
  const editor = explorePanel.querySelector(".detail-geography-edit");
  if (!editor) return;
  const syncContinentsFromCountries = () => {
    const selectedCountries = new Set(
      [...editor.querySelectorAll('input[name="detail-country"]:checked')].map((input) => input.value),
    );
    const inferred = new Set(
      (ctx.geographyOptions?.countries || [])
        .filter((country) => selectedCountries.has(country.code))
        .flatMap((country) => country.continents || []),
    );
    editor.querySelectorAll('input[name="detail-continent"]').forEach((input) => {
      input.checked = inferred.has(input.value);
    });
    const primary = editor.querySelector('[name="detail-primary-continent"]');
    if (primary.value && !inferred.has(primary.value)) primary.value = "";
  };
  editor.querySelectorAll('input[name="detail-country"]').forEach((input) => {
    input.addEventListener("change", syncContinentsFromCountries);
  });
  const filterInput = editor.querySelector(".country-filter");
  filterInput.addEventListener("input", () => {
    const query = filterInput.value.trim().toLowerCase();
    editor.querySelectorAll(".country-checklist label").forEach((label) => {
      label.hidden = query.length > 0 && !label.dataset.countrySearch.includes(query);
    });
  });
  editor.querySelector(".detail-save-geography").addEventListener("click", async () => {
    const continents = [...editor.querySelectorAll('input[name="detail-continent"]:checked')].map((input) => input.value);
    const countries = [...editor.querySelectorAll('input[name="detail-country"]:checked')].map((input) => input.value);
    const primary = editor.querySelector('[name="detail-primary-continent"]').value || null;
    if (primary && !continents.includes(primary)) {
      setStatus("Primary continent must also be checked.", true);
      return;
    }
    try {
      const payload = await postJson(`/api/polities/${encodeURIComponent(polity.id)}/geography`, "PATCH", {
        continents, primary_continent: primary, present_countries: countries,
      });
      const updated = { ...polity, geography: payload.geography, manual_overrides: payload.manual_overrides };
      ctx.politiesById.set(polity.id, updated);
      onSaved(updated);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

function detailOfCandidateButton(candidate) {
  return `<button type="button" class="type-choice detail-of-choice" data-detail-of-id="${escapeHtml(candidate.polity_id)}">
    <strong>${escapeHtml(candidate.canonical_name)}</strong>
    <span>Histomap ID: ${escapeHtml(candidate.polity_id)} · ${formatYear(candidate.canonical_start)}–${formatYear(candidate.canonical_end)}</span>
  </button>`;
}

// Search-and-pick-a-parent pattern (the /subdivision-review workflow this
// once mirrored was removed -- see ROADMAP.md), PATCHing `detail_of` via
// the same generic /fields endpoint the
// raw editor above already uses (it merges rather than replaces, so a bare
// `{ detail_of: ... }` body is enough). Only rendered (see
// detailOfEditorHtml) when the record has no `detail_of` yet -- once set,
// the panel shows a plain "Clear" button instead, no search box.
function wireDetailOfEditor(polity, ctx, onSaved, setStatus) {
  const editor = explorePanel.querySelector(".detail-of-edit");
  if (!editor) return;
  const saveDetailOf = async (targetId) => {
    try {
      const result = await postJson(`/api/polities/${encodeURIComponent(polity.id)}/fields`, "PATCH", { detail_of: targetId });
      ctx.politiesById.set(polity.id, result.document);
      onSaved(result.document);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  };
  const clearButton = editor.querySelector(".detail-of-clear");
  if (clearButton) {
    clearButton.addEventListener("click", () => saveDetailOf(null));
    return;
  }
  const input = editor.querySelector("#detail-of-search");
  const resultsEl = editor.querySelector(".detail-of-search-results");
  const runSearch = async () => {
    const query = input.value.trim();
    if (query.length < 2) {
      resultsEl.innerHTML = "<p>Enter at least two characters.</p>";
      return;
    }
    const response = await fetch(`/api/polities/search?q=${encodeURIComponent(query)}&limit=10`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const candidates = payload.items.filter((item) => item.polity_id !== polity.id);
    resultsEl.innerHTML = candidates.length
      ? candidates.map(detailOfCandidateButton).join("")
      : "<p>No matches found.</p>";
    resultsEl.querySelectorAll(".detail-of-choice").forEach((button) => {
      button.addEventListener("click", () => {
        const targetId = button.dataset.detailOfId;
        // A chained detail_of (A detail_of B detail_of C) isn't supported --
        // build_explore_tree.py's Pass 2 excludes any polity carrying
        // `detail_of` from its own top-level entry, so B would vanish
        // entirely (no top-level band to attach A's chip under) rather than
        // nest two levels deep. Point at the top-level container instead.
        const target = ctx.politiesById.get(targetId);
        if (target?.detail_of) {
          setStatus(`"${target.canonical_name}" is itself a detail of another entity -- pick its own top-level container instead.`, true);
          return;
        }
        saveDetailOf(targetId);
      });
    });
  };
  editor.querySelector(".detail-of-search-btn").addEventListener("click", () => runSearch().catch((error) => setStatus(error.message, true)));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch().catch((error) => setStatus(error.message, true));
    }
  });
}

// Shared by both renderPolityDetails and renderPeriodDetails: the
// "Convert to..." + "Edit fields" block, and the wiring for both. `kind`
// is "polity" or "period"; `record` is the current cached document;
// `onSaved(updatedRecord)` re-renders the panel with fresh data after any
// successful save, so the displayed details never go stale.
// ROADMAP.md "0 bis" -- the /consolidation-review "detail_of" decision and
// the raw edit-fields textarea were previously the only ways to set this
// field; this gives it a friendly search-and-pick control right in
// /explore's own side panel, mirroring subdivision_review.js's identical
// "find another polity" parent-picker (same /api/polities/search endpoint,
// same .parent-search/.type-choice/.type-choice-list markup and CSS).
function detailOfEditorHtml(record, politiesById) {
  const current = record.detail_of ? polityRefButton(politiesById, record.detail_of) : null;
  return `<details class="detail-of-edit">
    <summary>Set as detail of</summary>
    ${current
      ? `<p>Currently a detail of ${current}. <button class="detail-of-clear" type="button">Clear</button></p>`
      : `<p>Not currently marked as a detail of another entity.</p>
         <div class="parent-search">
           <label for="detail-of-search">Find the container entity</label>
           <div><input id="detail-of-search" type="search" placeholder="Name or Histomap ID"><button class="detail-of-search-btn" type="button">Search</button></div>
           <div class="detail-of-search-results type-choice-list"></div>
         </div>`}
  </details>`;
}

function editControlsHtml(kind, record, geographyOptions, politiesById) {
  const convertBlock = kind === "polity"
    ? `<div class="detail-edit-row">
         <select class="detail-entity-type-select" name="entity-type" aria-label="Entity type">${optionsHtml(ENTITY_TYPE_OPTIONS, record.entity_type || "polity")}</select>
         <button class="detail-convert-entity-type" type="button">Set entity type</button>
       </div>
       <div class="detail-edit-row">
         <button class="detail-convert-to-period" type="button">Convert to period</button>
       </div>
       ${detailOfEditorHtml(record, politiesById)}
       ${geographyEditorHtml(record, geographyOptions)}`
    : `<div class="detail-edit-row">
         <select class="detail-entity-type-select" name="entity-type" aria-label="Entity type">${optionsHtml(ENTITY_TYPE_OPTIONS, "polity")}</select>
         <button class="detail-convert-to-entity" type="button">Convert to entity</button>
       </div>
       <div class="detail-edit-row">
         <select class="detail-period-kind-select" name="period-kind" aria-label="Period type">${optionsHtml(PERIOD_KIND_OPTIONS, record.kind || "historical")}</select>
         <button class="detail-set-period-kind" type="button">Set period type</button>
       </div>`;
  return `<details class="detail-edit">
      <summary>Edit</summary>
      ${convertBlock}
      <details class="detail-raw-edit">
        <summary>Edit fields</summary>
        <textarea class="detail-raw-textarea" name="raw-fields" aria-label="Raw record fields (JSON)" rows="14" spellcheck="false">${escapeHtml(JSON.stringify(record, null, 2))}</textarea>
        <div class="detail-edit-row">
          <button class="detail-raw-save" type="button">Save fields</button>
        </div>
      </details>
      <p class="detail-edit-status" role="status"></p>
    </details>`;
}

function wireEditControls(kind, record, ctx, onSaved) {
  // Re-queries the live element every call rather than capturing it once --
  // onSaved(updated) fully re-renders the panel (so displayed dates/entity
  // type/etc. reflect the save), which replaces this element; setting the
  // message before that re-render would just get wiped by it, so every
  // handler below calls onSaved() first, then setStatus() against the fresh
  // element that re-render just created.
  const setStatus = (message, isError) => {
    const status = explorePanel.querySelector(".detail-edit-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(isError));
  };
  const idPath = kind === "polity" ? `/api/polities/${encodeURIComponent(record.id)}` : `/api/periods/${encodeURIComponent(record.id)}`;
  if (kind === "polity") wireDetailOfEditor(record, ctx, onSaved, setStatus);
  if (kind === "polity") wireGeographyEditor(record, ctx, onSaved, setStatus);

  if (kind === "polity") {
    explorePanel.querySelector(".detail-convert-entity-type").addEventListener("click", async () => {
      const entityType = explorePanel.querySelector(".detail-entity-type-select").value;
      try {
        await postJson(`${idPath}/entity-type`, "PATCH", { entity_type: entityType });
        const updated = { ...record, entity_type: entityType };
        ctx.politiesById.set(record.id, updated);
        onSaved(updated);
        ctx.onEdit?.();
        setStatus(REBUILD_NOTE, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    explorePanel.querySelector(".detail-convert-to-period").addEventListener("click", async () => {
      if (!confirm(`Convert "${record.canonical_name}" to a period? It will stop appearing in the Polities row after the next build.`)) return;
      try {
        const result = await postJson(`${idPath}/convert-to-period`, "POST");
        ctx.onEdit?.();
        setStatus(`${REBUILD_NOTE} New period id: ${result.period_id}.`, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  } else {
    explorePanel.querySelector(".detail-convert-to-entity").addEventListener("click", async () => {
      const entityType = explorePanel.querySelector(".detail-entity-type-select").value;
      if (!confirm(`Convert "${record.canonical_name}" to a polity (entity type: ${entityType})? The period record will be deleted after the next build.`)) return;
      try {
        const result = await postJson(`${idPath}/promote-to-entity`, "POST", { entity_type: entityType });
        ctx.onEdit?.();
        setStatus(`${REBUILD_NOTE} New polity id: ${result.entity_id}.`, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    explorePanel.querySelector(".detail-set-period-kind").addEventListener("click", async () => {
      const kindValue = explorePanel.querySelector(".detail-period-kind-select").value;
      try {
        await postJson(`${idPath}/kind`, "PATCH", { kind: kindValue });
        const updated = { ...record, kind: kindValue };
        ctx.periodsById.set(record.id, updated);
        onSaved(updated);
        ctx.onEdit?.();
        setStatus(REBUILD_NOTE, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  }

  explorePanel.querySelector(".detail-raw-save").addEventListener("click", async () => {
    const textarea = explorePanel.querySelector(".detail-raw-textarea");
    let fields;
    try {
      fields = JSON.parse(textarea.value);
    } catch (error) {
      setStatus(`Invalid JSON: ${error.message}`, true);
      return;
    }
    try {
      const result = await postJson(`${idPath}/fields`, "PATCH", fields);
      if (kind === "polity") ctx.politiesById.set(record.id, result.document);
      else ctx.periodsById.set(record.id, result.document);
      onSaved(result.document);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

// escapeHtml, displayTerm live in common.js, loaded first on /explore.

const exploreCountryNames = new Intl.DisplayNames(["en"], { type: "region" });

const TIER_KICKER = {
  macro_chapter: "Macro chapter",
  regional_era: "Regional era",
  period: "Period",
};

// A record's own id may not resolve (e.g. a broader_periods/successor
// pointing at something outside the currently-loaded set) -- fall back to
// a displayable version of the raw id rather than showing nothing.
function periodLabel(periodsById, id) {
  return periodsById.get(id)?.canonical_name || displayTerm(id);
}

function polityLabel(politiesById, id) {
  return politiesById.get(id)?.canonical_name || displayTerm(id);
}

function periodRefButton(periodsById, id) {
  const label = periodLabel(periodsById, id);
  return periodsById.has(id)
    ? `<button class="entity-link" type="button" data-explore-period-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`
    : escapeHtml(label);
}

function polityRefButton(politiesById, id) {
  const label = polityLabel(politiesById, id);
  return politiesById.has(id)
    ? `<button class="entity-link" type="button" data-explore-polity-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`
    : escapeHtml(label);
}

function externalLinksForPeriod(period) {
  const links = Object.entries(period.external_ids || {}).map(([source, value]) => {
    const url = String(value).startsWith("http") ? value
      : source === "wikidata" ? `https://www.wikidata.org/wiki/${encodeURIComponent(value)}` : "";
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTerm(source))} ↗</a>` : "";
  }).filter(Boolean);
  links.push(...(period.source_urls || []).map((url, index) =>
    `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1} ↗</a>`));
  return links;
}

function externalLinksForPolity(polity) {
  const wikidata = polity.external_ids?.wikidata;
  const wikipedia = polity.external_ids?.wikipedia_en
    || (wikidata ? `https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/${encodeURIComponent(wikidata)}` : "");
  const seshat = polity.external_ids?.seshat || [];
  const centroid = polity.geography?.centroid;
  return [
    wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(wikidata)}) ↗</a>` : "",
    wikipedia ? `<a href="${escapeHtml(wikipedia)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "",
    seshat.length ? `<a href="https://www.seshat-db.com/api/core/polities/?search=${encodeURIComponent(polity.canonical_name)}" target="_blank" rel="noopener noreferrer">Seshat (${escapeHtml(seshat.join(", "))}) ↗</a>` : "",
    centroid ? `<a href="https://www.openstreetmap.org/?mlat=${centroid.lat}&mlon=${centroid.lon}#map=5/${centroid.lat}/${centroid.lon}" target="_blank" rel="noopener noreferrer">View location ↗</a>` : "",
  ].filter(Boolean);
}

function renderPeriodDetails(period, ctx) {
  const { periodsById, politiesById, periodLinks } = ctx;
  const countries = (period.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const contained = [...periodsById.values()].filter((candidate) => (candidate.broader_periods || []).includes(period.id));
  const predecessors = [...periodsById.values()].filter((candidate) => (candidate.successors || []).includes(period.id));
  const linked = periodLinks.filter((link) => link.period_id === period.id);
  const externalLinks = externalLinksForPeriod(period);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <p class="detail-kicker">${escapeHtml(TIER_KICKER[period.tier] || "Period")}</p>
    <h2>${escapeHtml(period.canonical_name)}</h2>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <p>${escapeHtml(period.notes || "Sourced chronological context; this record is not a polity.")}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(period.start)}–${formatYear(period.end)}</dd>
      <dt>Period type</dt><dd>${escapeHtml(displayTerm(period.kind))}</dd>
      <dt>Authority</dt><dd>${escapeHtml(period.authority || "unknown")}</dd>
      <dt>Continents</dt><dd>${escapeHtml((period.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${(period.geography?.historical_regions || []).length ? `<dt>Historical regions</dt><dd>${escapeHtml(period.geography.historical_regions.map(displayTerm).join(", "))}</dd>` : ""}
      ${(period.broader_periods || []).length ? `<dt>Part of</dt><dd>${period.broader_periods.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${contained.length ? `<dt>Contains</dt><dd>${contained.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${(period.successors || []).length ? `<dt>Followed by</dt><dd>${period.successors.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${linked.length ? `<dt>Linked entities</dt><dd class="detail-links">${linked.map((link) => `${polityRefButton(politiesById, link.entity_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>
    ${editControlsHtml("period", period)}`;

  wireExplorePanel(ctx, period.start, period.end, period.id);
  wireEditControls("period", period, ctx, (updated) => renderPeriodDetails(updated, ctx));
  explorePanel.querySelectorAll("[data-explore-period-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = periodsById.get(button.dataset.explorePeriodId);
      if (target) renderPeriodDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-polity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = politiesById.get(button.dataset.explorePolityId);
      if (target) renderPolityDetails(target, ctx);
    });
  });
}

function renderPolityDetails(polity, ctx) {
  const { periodsById, politiesById, periodLinks } = ctx;
  const description = polity.text?.short_adult_en || polity.text?.long_en || polity.notes;
  const descriptionText = description || "Draft record; description pending review.";
  const aliases = [polity.names?.aliases_en?.replaceAll(" | ", ", "), polity.names?.fr].filter(Boolean).join("; ");
  const countries = (polity.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const centroid = polity.geography?.centroid;
  const duration = polity.end == null ? null : polity.end - polity.start;
  const children = [...politiesById.values()].filter((candidate) => candidate.parent === polity.id);
  const predecessors = [...politiesById.values()].filter((candidate) => (candidate.successors || []).includes(polity.id));
  const relevantPeriods = periodLinks.filter((link) => link.entity_id === polity.id);
  const relevantTransitions = (ctx.transitions || []).filter((transition) => [...transition.from, ...transition.to].includes(polity.id));
  const externalLinks = externalLinksForPolity(polity);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <h2>${escapeHtml(polity.canonical_name)}</h2>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <p>${escapeHtml(descriptionText)}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}${duration ? ` (${duration.toLocaleString()} years)` : ""}</dd>
      <dt>Entity type</dt><dd>${escapeHtml(displayTerm(polity.entity_type || "polity"))}</dd>
      ${aliases ? `<dt>Other names</dt><dd>${escapeHtml(aliases)}</dd>` : ""}
      ${polity.parent ? `<dt>Part of</dt><dd>${polityRefButton(politiesById, polity.parent)}</dd>` : ""}
      ${children.length ? `<dt>Contains</dt><dd>${children.map((item) => polityRefButton(politiesById, item.id)).join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => polityRefButton(politiesById, item.id)).join(", ")}</dd>` : ""}
      ${(polity.successors || []).length ? `<dt>Followed by</dt><dd>${polity.successors.map((id) => polityRefButton(politiesById, id)).join(", ")}</dd>` : ""}
      <dt>Continents</dt><dd>${escapeHtml((polity.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${centroid ? `<dt>Approx. location</dt><dd>${centroid.lat.toFixed(2)}°, ${centroid.lon.toFixed(2)}°</dd>` : ""}
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100 (${escapeHtml(polity.visibility_tier || "detailed")})</dd>
      <dt>Historical weight</dt><dd>${polity.weight_imputed ? "estimated" : "source-based"}</dd>
      ${(polity.sources || []).length ? `<dt>Data sources</dt><dd>${escapeHtml(polity.sources.map(displayTerm).join(", "))}</dd>` : ""}
      ${relevantTransitions.length ? `<dt>Transitions</dt><dd class="detail-links">${relevantTransitions.map((transition) => {
        const label = `${formatYear(transition.year)}: ${escapeHtml(transition.label)}`;
        return transition.source_urls?.[0] ? `<a href="${escapeHtml(transition.source_urls[0])}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : label;
      }).join("<br>")}</dd>` : ""}
      ${relevantPeriods.length ? `<dt>Historical periods</dt><dd class="detail-links">${relevantPeriods.map((link) => `${periodRefButton(periodsById, link.period_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>
    ${editControlsHtml("polity", polity, ctx.geographyOptions, politiesById)}`;

  wireExplorePanel(ctx, polity.start, polity.end ?? ctx.domainEnd, polity.detail_of || polity.id);
  wireEditControls("polity", polity, ctx, (updated) => renderPolityDetails(updated, ctx));
  explorePanel.querySelectorAll("[data-explore-polity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = politiesById.get(button.dataset.explorePolityId);
      if (target) renderPolityDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-period-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = periodsById.get(button.dataset.explorePeriodId);
      if (target) renderPeriodDetails(target, ctx);
    });
  });
}

function wireExplorePanel(ctx, start, end, expandId) {
  explorePanel.querySelector(".detail-close").addEventListener("click", closeExploreDetails);
  explorePanel.querySelector(".zoom-explore").addEventListener("click", () => {
    closeExploreDetails();
    // expandId auto-opens the enclosing panel for a detail_of entity's
    // container (see explore.js's zoomToRange) so "Zoom to this" on a
    // hidden detail reveals it, not just its neighbourhood.
    ctx.onZoomToRange(start, end, expandId);
  });
  explorePanel.querySelector(".reset-explore").addEventListener("click", () => {
    closeExploreDetails();
    ctx.onResetZoom();
  });
  explorePanel.classList.add("is-open");
  explorePanelBackdrop.classList.add("is-open");
  explorePanel.setAttribute("aria-hidden", "false");
  explorePanel.querySelector(".detail-close").focus();
}

function closeExploreDetails() {
  explorePanel.classList.remove("is-open");
  explorePanelBackdrop.classList.remove("is-open");
  explorePanel.setAttribute("aria-hidden", "true");
}

explorePanelBackdrop.addEventListener("click", closeExploreDetails);

// kind: "chapter" | "era" | "period" -> periodsById; "polity" -> politiesById.
// Silently no-ops if the id isn't found (e.g. data not loaded yet) rather
// than throwing and breaking the click handler for every other band.
function showExploreDetails(kind, id, ctx) {
  if (kind === "polity") {
    const polity = ctx.politiesById.get(id);
    if (polity) renderPolityDetails(polity, ctx);
    return;
  }
  const period = ctx.periodsById.get(id);
  if (period) renderPeriodDetails(period, ctx);
}
