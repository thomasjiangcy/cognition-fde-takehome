const POLL_INTERVAL_MS = 5000;

const completedMetric = document.querySelector("#metric-completed");
const inProgressMetric = document.querySelector("#metric-in-progress");
const failedMetric = document.querySelector("#metric-failed");
const dashboardMessage = document.querySelector("#dashboard-message");
const liveMode = document.querySelector("#live-mode");
const runsBody = document.querySelector("#runs-body");

let pollTimer = null;
let refreshing = false;

function cell(content) {
  const element = document.createElement("td");
  if (content instanceof Node) {
    element.append(content);
  } else {
    element.textContent = content;
  }
  return element;
}

function externalLink(label, url) {
  const link = document.createElement("a");
  link.href = url;
  link.textContent = label;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function statusBadge(state) {
  const badge = document.createElement("span");
  badge.className = "badge";
  const label = state.replaceAll("_", " ");
  const variants = {
    completed: "success",
    failed: "danger",
    in_progress: "warning",
    queued: "secondary",
  };
  if (state in variants) {
    badge.classList.add(variants[state]);
  }
  if (state === "in_progress") {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    spinner.setAttribute("aria-hidden", "true");
    badge.append(spinner, ` ${label}`);
  } else {
    badge.textContent = label;
  }
  return badge;
}

function renderRuns(runs) {
  if (runs.length === 0) {
    const row = document.createElement("tr");
    const empty = cell("No workflow runs yet.");
    empty.colSpan = 6;
    row.append(empty);
    runsBody.replaceChildren(row);
    return;
  }

  const rows = runs.map((run) => {
    const row = document.createElement("tr");
    const subject = run.subject_url
      ? externalLink(run.subject_title ?? run.event_type, run.subject_url)
      : run.subject_title ?? run.event_type;
    const session = run.devin_session_url
      ? externalLink("View session", run.devin_session_url)
      : "Not started";
    row.append(
      cell(run.source),
      cell(subject),
      cell(run.workflow_name),
      cell(statusBadge(run.state)),
      cell(new Date(run.created_at).toLocaleString()),
      cell(session),
    );
    return row;
  });
  runsBody.replaceChildren(...rows);
}

function showError() {
  const alert = document.createElement("p");
  alert.role = "alert";
  alert.dataset.variant = "error";
  alert.textContent = "Dashboard data is temporarily unavailable.";
  dashboardMessage.replaceChildren(alert);
}

function scheduleRefresh() {
  window.clearTimeout(pollTimer);
  pollTimer = null;
  if (liveMode.checked) {
    pollTimer = window.setTimeout(refreshDashboard, POLL_INTERVAL_MS);
  }
}

async function refreshDashboard() {
  if (refreshing) {
    return;
  }

  refreshing = true;
  window.clearTimeout(pollTimer);
  pollTimer = null;
  try {
    const response = await fetch("/api/dashboard", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`Dashboard request failed with status ${response.status}`);
    }

    const dashboard = await response.json();
    completedMetric.textContent = String(dashboard.metrics.completed);
    inProgressMetric.textContent = String(dashboard.metrics.in_progress);
    failedMetric.textContent = String(dashboard.metrics.failed);
    dashboardMessage.replaceChildren();
    renderRuns(dashboard.runs);
  } catch (error) {
    showError();
  } finally {
    refreshing = false;
    scheduleRefresh();
  }
}

liveMode.addEventListener("change", () => {
  if (liveMode.checked) {
    refreshDashboard();
  } else {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
});

refreshDashboard();
