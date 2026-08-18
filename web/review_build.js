const buildButtons = document.querySelectorAll("[data-build-timeline]");

function setButtonState(button, state) {
  if (!button.dataset.label) button.dataset.label = button.textContent.trim();
  button.disabled = state === "running";
  button.setAttribute("aria-busy", state === "running" ? "true" : "false");
  if (state === "running") {
    button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>Rebuilding…</span>`;
  } else if (state === "complete") {
    button.innerHTML = `<span class="button-check" aria-hidden="true">✓</span><span>Timeline updated</span>`;
  } else if (state === "failed") {
    button.innerHTML = `<span aria-hidden="true">×</span><span>Build failed</span>`;
  } else {
    button.textContent = button.dataset.label;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function statusFor(button) {
  return button.parentElement.querySelector("[data-build-status]");
}

async function pollBuild(button) {
  const response = await fetch("/api/actions/status");
  if (!response.ok) throw new Error(await response.text());
  const job = await response.json();
  if (job.status === "queued" || job.status === "running") {
    window.setTimeout(() => pollBuild(button).catch((error) => fail(button, error)), 500);
  } else if (job.status === "complete") {
    setButtonState(button, "complete");
    const status = statusFor(button);
    if (status) status.textContent = "Generated timeline files are current. Refresh the timeline page to view them.";
    window.setTimeout(() => setButtonState(button, "idle"), 2200);
  } else if (job.status === "failed") {
    fail(button, new Error("Check the server output for validation details."));
  }
}

function fail(button, error) {
  setButtonState(button, "failed");
  const status = statusFor(button);
  if (status) status.textContent = `Build failed: ${error.message}`;
  window.setTimeout(() => setButtonState(button, "idle"), 3000);
}

async function startBuild(button) {
  setButtonState(button, "running");
  const status = statusFor(button);
  if (status) status.textContent = "Validating and regenerating timeline files…";
  try {
    const response = await fetch("/api/actions/build", { method: "POST" });
    if (!response.ok) throw new Error((await response.json()).detail || await response.text());
    await pollBuild(button);
  } catch (error) {
    fail(button, error);
  }
}

buildButtons.forEach((button) => button.addEventListener("click", () => startBuild(button)));
