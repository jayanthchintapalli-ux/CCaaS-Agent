// Frontend logic: call POST /summarize and render the returned summary.

// If the page is served by the FastAPI app, same-origin works. Otherwise
// point this at the backend (e.g. "http://localhost:8000").
const API_BASE = "";

const caseInput = document.getElementById("caseId");
const button = document.getElementById("summarizeBtn");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");

function show(el, html, isError = false) {
  el.innerHTML = html;
  el.classList.remove("hidden");
  el.classList.toggle("error", isError);
}

function hide(el) {
  el.classList.add("hidden");
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function list(items) {
  if (!items || items.length === 0) return "<em>None</em>";
  return (
    "<ul>" + items.map((i) => `<li>${escapeHtml(i)}</li>`).join("") + "</ul>"
  );
}

function renderSummary(caseId, summary) {
  const html = `
    <h2>Summary for ${escapeHtml(caseId)}</h2>
    <div class="field">
      <div class="label">Issue</div>
      <div>${escapeHtml(summary.issue)}</div>
    </div>
    <div class="field">
      <div class="label">Actions taken</div>
      ${list(summary.actions_taken)}
    </div>
    <div class="field">
      <div class="label">Resolution status</div>
      <span class="badge">${escapeHtml(summary.resolution_status)}</span>
    </div>
    <div class="field">
      <div class="label">Sentiment</div>
      <span class="badge">${escapeHtml(summary.sentiment)}</span>
    </div>
    <div class="field">
      <div class="label">Follow-ups</div>
      ${list(summary.follow_ups)}
    </div>
    <div class="field">
      <div class="label">Readable summary</div>
      <pre>${escapeHtml(summary.text || "")}</pre>
    </div>
  `;
  show(resultEl, html);
}

async function summarize() {
  const caseId = caseInput.value.trim();
  hide(resultEl);

  if (!caseId) {
    show(statusEl, "Please enter a case ID.", true);
    return;
  }

  button.disabled = true;
  show(statusEl, "Summarizing…");

  try {
    const resp = await fetch(`${API_BASE}/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId }),
    });

    const data = await resp.json().catch(() => ({}));

    if (!resp.ok) {
      const detail = data.detail || `Request failed (${resp.status}).`;
      show(statusEl, escapeHtml(detail), true);
      return;
    }

    hide(statusEl);
    renderSummary(data.case_id, data.summary);
  } catch (err) {
    show(statusEl, `Network error: ${escapeHtml(err.message)}`, true);
  } finally {
    button.disabled = false;
  }
}

button.addEventListener("click", summarize);
caseInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") summarize();
});
