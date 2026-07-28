/* Agent Console — single-page frontend (vanilla JS). */

const State = {
  token: localStorage.getItem("ac_token") || null,
  user: JSON.parse(localStorage.getItem("ac_user") || "null"),
  route: "dashboard",
};

/* --------------------------------------------------------------------- */
/* API helper                                                            */
/* --------------------------------------------------------------------- */
async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (State.token) headers["Authorization"] = `Bearer ${State.token}`;
  let payload;
  if (form) {
    payload = form; // FormData; browser sets content-type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  if (res.status === 401) {
    logout(false);
    throw new Error("Session expired. Please sign in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || `Request failed (${res.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

/* --------------------------------------------------------------------- */
/* Utilities                                                             */
/* --------------------------------------------------------------------- */
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 3800);
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function fmtDuration(sec) {
  sec = Number(sec) || 0;
  if (!sec) return "—";
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

const STATUS_BADGE = {
  completed: "green", delivered: "green", connected: "green", active: "green", running: "green",
  failed: "red", "no-answer": "yellow", busy: "yellow", voicemail: "blue", pending: "gray",
  draft: "gray", paused: "yellow", disabled: "red", received: "blue", sent: "gray", read: "green",
};
const badge = (v) => `<span class="badge ${STATUS_BADGE[v] || "gray"}">${esc(v)}</span>`;

function roleBadge(role) {
  const map = { admin: "accent", supervisor: "blue", agent: "gray" };
  return `<span class="badge ${map[role] || "gray"}">${esc(role)}</span>`;
}

/* --------------------------------------------------------------------- */
/* Modal helper                                                          */
/* --------------------------------------------------------------------- */
function openModal(title, bodyHtml, footHtml) {
  const root = $("#modalRoot");
  root.innerHTML = `
    <div class="modal-backdrop">
      <div class="modal">
        <div class="modal-head"><h3>${esc(title)}</h3><button class="x" data-close>×</button></div>
        <div class="modal-body">${bodyHtml}</div>
        ${footHtml ? `<div class="modal-foot">${footHtml}</div>` : ""}
      </div>
    </div>`;
  root.querySelector("[data-close]").onclick = closeModal;
  root.querySelector(".modal-backdrop").onclick = (e) => {
    if (e.target.classList.contains("modal-backdrop")) closeModal();
  };
  return root.querySelector(".modal");
}
function closeModal() { $("#modalRoot").innerHTML = ""; }

/* --------------------------------------------------------------------- */
/* Auth                                                                  */
/* --------------------------------------------------------------------- */
async function doLogin(e) {
  e.preventDefault();
  const email = $("#loginEmail").value.trim();
  const password = $("#loginPassword").value;
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Signing in…";
  try {
    const data = await api("/auth/login", { method: "POST", body: { email, password } });
    State.token = data.token;
    State.user = data.user;
    localStorage.setItem("ac_token", data.token);
    localStorage.setItem("ac_user", JSON.stringify(data.user));
    boot();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    btn.disabled = false; btn.textContent = "Sign in";
  }
}

async function logout(callApi = true) {
  if (callApi) { try { await api("/auth/logout", { method: "POST" }); } catch {} }
  State.token = null; State.user = null;
  localStorage.removeItem("ac_token"); localStorage.removeItem("ac_user");
  $("#appView").classList.add("hidden");
  $("#loginView").classList.remove("hidden");
}

/* --------------------------------------------------------------------- */
/* Boot + routing                                                        */
/* --------------------------------------------------------------------- */
function boot() {
  if (!State.token || !State.user) {
    $("#loginView").classList.remove("hidden");
    $("#appView").classList.add("hidden");
    return;
  }
  $("#loginView").classList.add("hidden");
  $("#appView").classList.remove("hidden");
  $("#whoName").textContent = State.user.name;
  $("#whoRole").textContent = State.user.role;

  const isAdmin = State.user.role === "admin";
  $$("[data-admin]").forEach((el) => el.classList.toggle("hidden", !isAdmin));

  navigate(location.hash.replace("#", "") || "dashboard");
}

function navigate(route) {
  if (route === "admin" && State.user.role !== "admin") route = "dashboard";
  State.route = route;
  location.hash = route;
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
  const routes = {
    dashboard: renderDashboard, campaigns: renderCampaigns, agents: renderAgents,
    dial: renderDial, cdr: renderCDR, whatsapp: renderWhatsApp, admin: renderAdmin,
  };
  (routes[route] || renderDashboard)();
}

/* --------------------------------------------------------------------- */
/* Pages                                                                 */
/* --------------------------------------------------------------------- */
function pageHead(title, sub, actionsHtml = "") {
  return `<div class="page-head"><div><h2>${esc(title)}</h2><p class="sub">${esc(sub)}</p></div>
    <div>${actionsHtml}</div></div>`;
}

async function renderDashboard() {
  const main = $("#main");
  main.innerHTML = pageHead("Dashboard", "Live overview of your contact center");
  try {
    const d = await api("/dashboard");
    main.innerHTML += `
      <div class="grid kpis">
        <div class="card kpi"><div class="label">Total Calls</div><div class="value">${d.calls_total}</div></div>
        <div class="card kpi"><div class="label">Answer Rate</div><div class="value">${d.answer_rate}<small>%</small></div></div>
        <div class="card kpi"><div class="label">Avg Duration</div><div class="value">${fmtDuration(Math.round(d.avg_duration_sec))}</div></div>
        <div class="card kpi"><div class="label">Campaigns Running</div><div class="value">${d.campaigns_running}<small>/ ${d.campaigns_total}</small></div></div>
        <div class="card kpi"><div class="label">Campaign Agents</div><div class="value">${d.agents_total}</div></div>
        <div class="card kpi"><div class="label">WhatsApp Channels</div><div class="value">${d.wa_channels}</div></div>
        <div class="card kpi"><div class="label">WhatsApp Messages</div><div class="value">${d.wa_messages}</div></div>
        <div class="card kpi"><div class="label">Users</div><div class="value">${d.users_total}</div></div>
      </div>
      <div class="two-col">
        <div class="card">
          <h3 style="margin-top:0;">Calls by status</h3>
          ${d.by_status.length ? d.by_status.map((s) => `
            <div style="display:flex;justify-content:space-between;padding:0.4rem 0;border-bottom:1px solid var(--border);">
              <span>${badge(s.status)}</span><b>${s.n}</b></div>`).join("") : '<p class="sub">No calls yet.</p>'}
        </div>
        <div class="card">
          <h3 style="margin-top:0;">Recent calls</h3>
          <div class="table-wrap" style="border:none;">
          <table><thead><tr><th>To</th><th>Dir</th><th>Status</th><th>Duration</th><th>Time</th></tr></thead>
          <tbody>${d.recent_calls.map((c) => `<tr>
            <td class="mono">${esc(c.to_number)}</td><td>${esc(c.direction)}</td>
            <td>${badge(c.status)}</td><td>${fmtDuration(c.duration_sec)}</td>
            <td>${fmtTime(c.started_at)}</td></tr>`).join("") ||
            '<tr><td colspan="5" class="sub">No calls yet.</td></tr>'}</tbody></table></div>
        </div>
      </div>`;
  } catch (err) { toast(err.message, "err"); }
}

/* ---------- Campaigns ---------- */
async function renderCampaigns() {
  const main = $("#main");
  const head = pageHead("Campaigns", "Outbound calling campaigns",
    `<button class="btn-primary" id="newCampaignBtn">+ New Campaign</button>`);
  let body = "";
  let campaigns = [];
  try {
    campaigns = (await api("/campaigns")).campaigns;
    body = !campaigns.length
      ? emptyState("📣", "No campaigns yet", "Create your first outbound campaign to get started.")
      : `<div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Agent</th><th>Caller ID</th><th>Progress</th><th>Status</th><th></th></tr></thead>
      <tbody>${campaigns.map((c) => {
        const t = c.contacts.total, done = c.contacts.called + c.contacts.failed;
        const pct = t ? Math.round(100 * done / t) : 0;
        return `<tr>
          <td><b>${esc(c.name)}</b><div class="sub" style="font-size:0.78rem;">CPS ${c.cps} · max ${c.max_concurrent} · retry ${c.retry_attempts}</div></td>
          <td>${esc(c.agent_name || "—")}</td>
          <td class="mono">${esc(c.caller_id || "—")}</td>
          <td>${done}/${t} <span class="sub">(${pct}%)</span></td>
          <td>${badge(c.status)}</td>
          <td style="white-space:nowrap;">
            ${c.status === "running"
              ? `<button class="btn-sm" data-act="pause" data-id="${c.id}">Pause</button>`
              : `<button class="btn-sm" data-act="start" data-id="${c.id}">${c.status === "paused" ? "Resume" : "Start"}</button>`}
            <button class="btn-sm" data-view="${c.id}">Contacts</button>
            <button class="btn-sm btn-danger" data-del="${c.id}">Delete</button>
          </td></tr>`;
      }).join("")}</tbody></table></div>`;
  } catch (err) { toast(err.message, "err"); body = emptyState("⚠️", "Could not load campaigns", err.message); }

  main.innerHTML = head + body;
  $("#newCampaignBtn").onclick = openCampaignModal;
  $$("[data-act]").forEach((b) => b.onclick = () => campaignAction(b.dataset.id, b.dataset.act));
  $$("[data-del]").forEach((b) => b.onclick = () => deleteCampaign(b.dataset.del));
  $$("[data-view]").forEach((b) => b.onclick = () => viewCampaign(b.dataset.view));
}

async function campaignAction(id, action) {
  try {
    const r = await api(`/campaigns/${id}/action?action=${action}`, { method: "POST" });
    toast(action === "start" || action === "resume"
      ? `Campaign ${r.status} — dialed ${r.dialed} contact(s)` : `Campaign ${r.status}`, "ok");
    renderCampaigns();
  } catch (err) { toast(err.message, "err"); }
}
async function deleteCampaign(id) {
  if (!confirm("Delete this campaign and its contacts?")) return;
  try { await api(`/campaigns/${id}`, { method: "DELETE" }); toast("Campaign deleted", "ok"); renderCampaigns(); }
  catch (err) { toast(err.message, "err"); }
}

async function viewCampaign(id) {
  try {
    const { campaign, contacts } = await api(`/campaigns/${id}`);
    const rows = contacts.map((c) => `<tr>
      <td class="mono">${esc(c.to_number)}</td><td>${esc(c.name || "—")}</td>
      <td>${badge(c.status)}</td><td>${c.attempts}</td></tr>`).join("") ||
      '<tr><td colspan="4" class="sub">No contacts uploaded yet.</td></tr>';
    openModal(`${campaign.name} — Contacts (${campaign.contacts.total})`,
      `<div class="field">
        <div class="dropzone">
          <div class="head"><div><h4>Upload contacts CSV</h4><p>Must include a <b>to</b> column.</p></div></div>
          <input type="file" id="csvUpload" accept=".csv" style="margin-top:0.8rem;" />
        </div>
      </div>
      <div class="table-wrap"><table><thead><tr><th>To</th><th>Name</th><th>Status</th><th>Attempts</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`,
      `<button class="btn" data-close-2>Close</button>`);
    $("[data-close-2]").onclick = closeModal;
    $("#csvUpload").onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const form = new FormData(); form.append("file", file);
      try {
        const r = await api(`/campaigns/${id}/contacts`, { method: "POST", form });
        toast(`Imported ${r.imported}, skipped ${r.skipped}`, "ok");
        viewCampaign(id);
      } catch (err) { toast(err.message, "err"); }
    };
  } catch (err) { toast(err.message, "err"); }
}

async function openCampaignModal() {
  let agents = [];
  try { agents = (await api("/agents")).agents; } catch {}
  const agentField = agents.length
    ? `<select id="c_agent">${agents.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select>`
    : `<div style="color:var(--red);font-size:0.85rem;">No agents found — create one in Campaign Agents first</div>`;

  openModal("New Campaign", `
    <div class="field"><label>Name <span class="req">*</span></label>
      <input id="c_name" placeholder="Q1 Appointment Reminders" /></div>
    <div class="field"><label>Agent <span class="req">*</span></label>${agentField}</div>
    <div class="row">
      <div class="field"><label>CPS <span class="req">*</span><span class="limit-note">account limit: <b>1</b></span></label>
        <input id="c_cps" type="number" min="1" value="1" /></div>
      <div class="field"><label>Max Concurrent <span class="req">*</span><span class="limit-note">account limit: <b>3</b></span></label>
        <input id="c_max" type="number" min="1" value="3" /></div>
    </div>
    <div class="field"><label>Timezone</label>
      <select id="c_tz">${["Asia/Kolkata","UTC","America/New_York","Europe/London","Asia/Dubai","Asia/Singapore"]
        .map((t) => `<option>${t}</option>`).join("")}</select></div>
    <div class="field"><label>Caller ID Strategy</label>
      <select id="c_strategy">
        <option value="fixed">Fixed — single caller ID for all contacts</option>
        <option value="round_robin">Round robin — rotate across numbers</option>
      </select></div>
    <div class="field"><label>Caller ID <span class="req">*</span></label>
      <input id="c_callerid" placeholder="+911171366938" />
      <div class="hint">Used as the caller ID for every call in this campaign.</div></div>
    <div class="field"><label class="toggle"><input type="checkbox" id="c_window" /><span class="track"></span> Daily calling window</label></div>
    <div class="row" id="c_window_fields" style="display:none;">
      <div class="field"><label>Window start</label><input id="c_wstart" type="time" value="09:00" /></div>
      <div class="field"><label>Window end</label><input id="c_wend" type="time" value="18:00" /></div>
    </div>
    <div class="field"><label>Retry Attempts (0–5)</label><input id="c_retry" type="number" min="0" max="5" value="2" /></div>
    <div class="field"><label>Webhook URL (optional)</label>
      <input id="c_webhook" placeholder="https://your-server.com/campaign-webhooks" /></div>
  `, `<button class="btn" data-close-2>Cancel</button>
      <button class="btn-primary" id="c_submit" ${agents.length ? "" : "disabled"}>Create Campaign</button>`);

  $("[data-close-2]").onclick = closeModal;
  $("#c_window").onchange = (e) => {
    $("#c_window_fields").style.display = e.target.checked ? "grid" : "none";
  };
  $("#c_submit").onclick = async () => {
    const body = {
      name: $("#c_name").value.trim(),
      agent_id: agents.length ? Number($("#c_agent").value) : null,
      cps: Number($("#c_cps").value),
      max_concurrent: Number($("#c_max").value),
      timezone: $("#c_tz").value,
      caller_id_strategy: $("#c_strategy").value,
      caller_id: $("#c_callerid").value.trim(),
      window_enabled: $("#c_window").checked,
      window_start: $("#c_wstart").value,
      window_end: $("#c_wend").value,
      retry_attempts: Number($("#c_retry").value),
      webhook_url: $("#c_webhook").value.trim(),
    };
    if (!body.name) return toast("Campaign name is required", "err");
    if (!body.caller_id) return toast("Caller ID is required", "err");
    try {
      await api("/campaigns", { method: "POST", body });
      toast("Campaign created", "ok"); closeModal(); renderCampaigns();
    } catch (err) { toast(err.message, "err"); }
  };
}

/* ---------- Campaign Agents ---------- */
async function renderAgents() {
  const main = $("#main");
  const head = pageHead("Campaign Agents", "Voice agents used to run your campaigns",
    `<button class="btn-primary" id="newAgentBtn">+ New Agent</button>`);
  let body = "";
  try {
    const { agents } = await api("/agents");
    body = !agents.length
      ? emptyState("🤖", "No agents yet", "Create a campaign agent to power your outbound calls.")
      : `<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr));">
      ${agents.map((a) => `<div class="card">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <h3 style="margin:0 0 0.3rem;">${esc(a.name)}</h3>
          <button class="btn-sm btn-danger" data-del="${a.id}">Delete</button>
        </div>
        <p class="sub">${esc(a.description || "No description")}</p>
        <div style="margin-top:0.6rem;">${badge(a.voice)}</div>
      </div>`).join("")}</div>`;
  } catch (err) { toast(err.message, "err"); body = emptyState("⚠️", "Could not load agents", err.message); }

  main.innerHTML = head + body;
  $("#newAgentBtn").onclick = openAgentModal;
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this agent?")) return;
    try { await api(`/agents/${b.dataset.del}`, { method: "DELETE" }); toast("Agent deleted", "ok"); renderAgents(); }
    catch (err) { toast(err.message, "err"); }
  });
}

function openAgentModal() {
  openModal("New Campaign Agent", `
    <div class="field"><label>Name <span class="req">*</span></label><input id="a_name" placeholder="Appointment Reminder Bot" /></div>
    <div class="field"><label>Description</label><input id="a_desc" placeholder="What this agent does" /></div>
    <div class="field"><label>Voice</label>
      <select id="a_voice">${["en-IN-neural","en-US-neural","hi-IN-neural","default"].map((v)=>`<option>${v}</option>`).join("")}</select></div>
    <div class="field"><label>Prompt / Script</label><textarea id="a_prompt" rows="4" placeholder="You are a friendly assistant…"></textarea></div>
  `, `<button class="btn" data-close-2>Cancel</button><button class="btn-primary" id="a_submit">Create Agent</button>`);
  $("[data-close-2]").onclick = closeModal;
  $("#a_submit").onclick = async () => {
    const body = { name: $("#a_name").value.trim(), description: $("#a_desc").value.trim(),
      voice: $("#a_voice").value, prompt: $("#a_prompt").value.trim() };
    if (!body.name) return toast("Agent name is required", "err");
    try { await api("/agents", { method: "POST", body }); toast("Agent created", "ok"); closeModal(); renderAgents(); }
    catch (err) { toast(err.message, "err"); }
  };
}

/* ---------- Manual Dial ---------- */
function renderDial() {
  const main = $("#main");
  main.innerHTML = pageHead("Manual Dial", "Place an ad-hoc outbound call");
  main.innerHTML += `<div class="card dialer">
    <div class="field"><label>Caller ID (from)</label><input id="d_from" placeholder="+911171366938" /></div>
    <div class="num-display" id="d_display"></div>
    <input id="d_to" class="hidden" />
    <div class="keypad">${["1","2","3","4","5","6","7","8","9","*","0","#"].map((k)=>`<button data-key="${k}">${k}</button>`).join("")}</div>
    <div class="field" style="margin-top:1rem;"><label>Notes</label><input id="d_notes" placeholder="Optional call notes" /></div>
    <div style="display:flex;gap:0.6rem;">
      <button class="btn-primary" id="d_call" style="flex:1;justify-content:center;">📞 Call</button>
      <button class="btn" id="d_back">⌫</button>
    </div>
  </div>`;
  const disp = $("#d_display"), hidden = $("#d_to");
  const sync = () => disp.textContent = hidden.value || "Enter number";
  sync();
  $$("[data-key]").forEach((b) => b.onclick = () => { hidden.value += b.dataset.key; sync(); });
  $("#d_back").onclick = () => { hidden.value = hidden.value.slice(0, -1); sync(); };
  disp.onclick = () => { const v = prompt("Enter number", hidden.value); if (v !== null) { hidden.value = v; sync(); } };
  $("#d_call").onclick = async () => {
    const to = hidden.value.trim();
    if (to.length < 3) return toast("Enter a valid number", "err");
    try {
      const { call } = await api("/dial", { method: "POST",
        body: { to_number: to, from_number: $("#d_from").value.trim(), notes: $("#d_notes").value.trim() } });
      toast(`Call to ${to} — ${call.status} (${fmtDuration(call.duration_sec)})`, "ok");
      hidden.value = ""; $("#d_notes").value = ""; sync();
    } catch (err) { toast(err.message, "err"); }
  };
}

/* ---------- CDR ---------- */
async function renderCDR() {
  const main = $("#main");
  main.innerHTML = pageHead("Call Detail Records", "Every call placed and received");
  main.innerHTML += `<div class="toolbar">
    <input id="cdr_search" placeholder="Search number…" />
    <select id="cdr_dir"><option value="">All directions</option><option>outbound</option><option>inbound</option><option>manual</option></select>
    <select id="cdr_status"><option value="">All statuses</option>${
      ["completed","failed","no-answer","busy","voicemail"].map((s)=>`<option>${s}</option>`).join("")}</select>
    <div class="spacer"></div>
    <button class="btn" id="cdr_export">Export CSV</button>
  </div><div id="cdr_table"></div>`;

  async function load() {
    const params = new URLSearchParams();
    if ($("#cdr_search").value.trim()) params.set("search", $("#cdr_search").value.trim());
    if ($("#cdr_dir").value) params.set("direction", $("#cdr_dir").value);
    if ($("#cdr_status").value) params.set("status", $("#cdr_status").value);
    try {
      const { calls } = await api(`/cdr?${params.toString()}`);
      $("#cdr_table").innerHTML = calls.length ? `<div class="table-wrap"><table>
        <thead><tr><th>ID</th><th>Direction</th><th>From</th><th>To</th><th>Agent</th><th>Campaign</th><th>Status</th><th>Duration</th><th>Time</th></tr></thead>
        <tbody>${calls.map((c)=>`<tr>
          <td>#${c.id}</td><td>${esc(c.direction)}</td>
          <td class="mono">${esc(c.from_number||"—")}</td><td class="mono">${esc(c.to_number)}</td>
          <td>${esc(c.agent_name||"—")}</td><td>${esc(c.campaign_name||"—")}</td>
          <td>${badge(c.status)}</td><td>${fmtDuration(c.duration_sec)}</td><td>${fmtTime(c.started_at)}</td>
        </tr>`).join("")}</tbody></table></div>`
        : emptyState("📄", "No records", "No calls match your filters yet.");
      window.__cdr = calls;
    } catch (err) { toast(err.message, "err"); }
  }
  $("#cdr_search").oninput = debounce(load, 300);
  $("#cdr_dir").onchange = load;
  $("#cdr_status").onchange = load;
  $("#cdr_export").onclick = () => exportCSV(window.__cdr || []);
  load();
}

function exportCSV(rows) {
  if (!rows.length) return toast("Nothing to export", "err");
  const cols = ["id","direction","from_number","to_number","agent_name","campaign_name","status","duration_sec","started_at"];
  const csv = [cols.join(",")].concat(rows.map((r) =>
    cols.map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "cdr.csv"; a.click();
}

/* ---------- WhatsApp ---------- */
async function renderWhatsApp() {
  const main = $("#main");
  const head = pageHead("WhatsApp Channels", "Connect and manage your WhatsApp Business accounts",
    `<button class="btn-primary" id="connectBtn">+ Connect Channel</button>`);
  let body = "", channels = [];
  try {
    channels = (await api("/wa/channels")).channels;
    body = !channels.length
      ? `<div class="card"><div class="empty">
        <div class="ico">📶</div>
        <h3>No channels connected</h3>
        <p>Connect your WhatsApp Business account to start sending and receiving messages.</p>
        <button class="btn-primary" id="connectBtn2" style="margin-top:1rem;">+ Connect Your First Channel</button>
      </div></div>`
      : `<div class="two-col">
      <div class="card stack" id="chanList">
        ${channels.map((c, i) => `<div class="channel-item ${i===0?"active":""}" data-chan="${c.id}">
          <div><div class="nm">${esc(c.display_name)}</div><div class="ph">${esc(c.phone_number)}</div></div>
          <div style="text-align:right;">${badge(c.status)}<div class="ph">${c.message_count} msgs</div></div>
        </div>`).join("")}
      </div>
      <div class="card" id="chatPanel"></div>
    </div>`;
  } catch (err) { toast(err.message, "err"); body = emptyState("⚠️", "Could not load channels", err.message); }

  main.innerHTML = head + body;
  $("#connectBtn").onclick = openChannelModal;
  const connect2 = $("#connectBtn2");
  if (connect2) connect2.onclick = openChannelModal;
  if (channels.length) {
    $$("[data-chan]").forEach((el) => el.onclick = () => {
      $$("[data-chan]").forEach((x) => x.classList.remove("active"));
      el.classList.add("active");
      openChat(el.dataset.chan, channels.find((c) => c.id == el.dataset.chan));
    });
    openChat(channels[0].id, channels[0]);
  }
}

async function openChat(channelId, channel) {
  const panel = $("#chatPanel");
  panel.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.8rem;">
      <div><b>${esc(channel.display_name)}</b> <span class="ph">${esc(channel.phone_number)}</span></div>
      <button class="btn-sm btn-danger" id="delChan">Disconnect</button></div>
    <div class="field"><input id="chat_peer" placeholder="Recipient number e.g. +9198…" /></div>
    <div class="msg-list" id="msgList"></div>
    <div style="display:flex;gap:0.6rem;margin-top:0.8rem;">
      <input id="chat_body" placeholder="Type a message…" />
      <button class="btn-primary" id="chat_send">Send</button></div>`;
  $("#delChan").onclick = async () => {
    if (!confirm("Disconnect this channel?")) return;
    try { await api(`/wa/channels/${channelId}`, { method: "DELETE" }); toast("Channel disconnected", "ok"); renderWhatsApp(); }
    catch (err) { toast(err.message, "err"); }
  };
  async function loadMsgs() {
    const { messages } = await api(`/wa/channels/${channelId}/messages`);
    const list = $("#msgList");
    list.innerHTML = messages.map((m) => `<div class="msg ${m.direction === "outbound" ? "out" : "in"}">
      ${esc(m.body)}<div class="meta">${esc(m.peer)} · ${fmtTime(m.created_at)} · ${esc(m.status)}</div></div>`).join("")
      || '<p class="sub" style="margin:auto;">No messages yet — send one below.</p>';
    list.scrollTop = list.scrollHeight;
  }
  $("#chat_send").onclick = async () => {
    const to = $("#chat_peer").value.trim(), body = $("#chat_body").value.trim();
    if (!to) return toast("Enter a recipient number", "err");
    if (!body) return toast("Type a message", "err");
    try {
      await api(`/wa/channels/${channelId}/messages`, { method: "POST", body: { to_number: to, body } });
      $("#chat_body").value = ""; loadMsgs();
    } catch (err) { toast(err.message, "err"); }
  };
  $("#chat_body").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#chat_send").click(); });
  loadMsgs();
}

function openChannelModal() {
  openModal("Connect WhatsApp Channel", `
    <div class="field"><label>Display Name <span class="req">*</span></label><input id="w_name" placeholder="Support Line" /></div>
    <div class="field"><label>Phone Number <span class="req">*</span></label><input id="w_phone" placeholder="+911171366938" /></div>
    <div class="field"><label>Provider</label>
      <select id="w_provider"><option value="meta">Meta (WhatsApp Cloud API)</option><option value="twilio">Twilio</option><option value="360dialog">360dialog</option></select></div>
    <div class="row">
      <div class="field"><label>Phone Number ID</label><input id="w_pnid" placeholder="Optional" /></div>
      <div class="field"><label>WABA ID</label><input id="w_waba" placeholder="Optional" /></div>
    </div>
    <p class="hint">In production this launches the provider's embedded signup / OAuth flow.</p>
  `, `<button class="btn" data-close-2>Cancel</button><button class="btn-primary" id="w_submit">Connect Channel</button>`);
  $("[data-close-2]").onclick = closeModal;
  $("#w_submit").onclick = async () => {
    const body = { display_name: $("#w_name").value.trim(), phone_number: $("#w_phone").value.trim(),
      provider: $("#w_provider").value, phone_number_id: $("#w_pnid").value.trim(), waba_id: $("#w_waba").value.trim() };
    if (!body.display_name || !body.phone_number) return toast("Name and phone number are required", "err");
    try { await api("/wa/channels", { method: "POST", body }); toast("Channel connected", "ok"); closeModal(); renderWhatsApp(); }
    catch (err) { toast(err.message, "err"); }
  };
}

/* ---------- Admin / Users ---------- */
async function renderAdmin() {
  const main = $("#main");
  const head = pageHead("Users", "Manage console access and roles",
    `<button class="btn-primary" id="newUserBtn">+ Add User</button>`);
  let body = "", users = [];
  try {
    users = (await api("/users")).users;
    body = `<div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th></th></tr></thead>
      <tbody>${users.map((u) => `<tr>
        <td><b>${esc(u.name)}</b></td><td class="mono">${esc(u.email)}</td>
        <td>${roleBadge(u.role)}</td><td>${badge(u.status)}</td><td>${fmtTime(u.created_at)}</td>
        <td style="white-space:nowrap;">
          <button class="btn-sm" data-edit="${u.id}">Edit</button>
          ${u.id === State.user.id ? "" : `<button class="btn-sm btn-danger" data-del="${u.id}">Delete</button>`}
        </td></tr>`).join("")}</tbody></table></div>`;
  } catch (err) { toast(err.message, "err"); body = emptyState("⚠️", "Could not load users", err.message); }

  main.innerHTML = head + body;
  $("#newUserBtn").onclick = () => openUserModal();
  $$("[data-edit]").forEach((b) => b.onclick = () => {
    const u = users.find((x) => x.id == b.dataset.edit); openUserModal(u);
  });
  $$("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this user?")) return;
    try { await api(`/users/${b.dataset.del}`, { method: "DELETE" }); toast("User deleted", "ok"); renderAdmin(); }
    catch (err) { toast(err.message, "err"); }
  });
}

function openUserModal(user = null) {
  const editing = !!user;
  openModal(editing ? "Edit User" : "Add User", `
    <div class="field"><label>Name <span class="req">*</span></label><input id="u_name" value="${esc(user?.name || "")}" /></div>
    <div class="field"><label>Email <span class="req">*</span></label>
      <input id="u_email" type="email" value="${esc(user?.email || "")}" ${editing ? "disabled" : ""} /></div>
    <div class="row">
      <div class="field"><label>Role</label>
        <select id="u_role">${["agent","supervisor","admin"].map((r)=>`<option ${user?.role===r?"selected":""}>${r}</option>`).join("")}</select></div>
      ${editing ? `<div class="field"><label>Status</label>
        <select id="u_status"><option ${user.status==="active"?"selected":""}>active</option><option ${user.status==="disabled"?"selected":""}>disabled</option></select></div>` : ""}
    </div>
    <div class="field"><label>${editing ? "New Password (leave blank to keep)" : "Password"} ${editing ? "" : '<span class="req">*</span>'}</label>
      <input id="u_pass" type="password" placeholder="Min 6 characters" /></div>
  `, `<button class="btn" data-close-2>Cancel</button><button class="btn-primary" id="u_submit">${editing ? "Save" : "Create User"}</button>`);
  $("[data-close-2]").onclick = closeModal;
  $("#u_submit").onclick = async () => {
    const name = $("#u_name").value.trim(), pass = $("#u_pass").value, role = $("#u_role").value;
    try {
      if (editing) {
        const body = { name, role, status: $("#u_status").value };
        if (pass) body.password = pass;
        await api(`/users/${user.id}`, { method: "PATCH", body });
        toast("User updated", "ok");
      } else {
        const email = $("#u_email").value.trim();
        if (!name || !email) return toast("Name and email are required", "err");
        if (pass.length < 6) return toast("Password must be at least 6 characters", "err");
        await api("/users", { method: "POST", body: { name, email, password: pass, role } });
        toast("User created", "ok");
      }
      closeModal(); renderAdmin();
    } catch (err) { toast(err.message, "err"); }
  };
}

/* --------------------------------------------------------------------- */
/* Shared bits                                                           */
/* --------------------------------------------------------------------- */
function emptyState(icon, title, sub) {
  return `<div class="card"><div class="empty"><div class="ico">${icon}</div>
    <h3>${esc(title)}</h3><p>${esc(sub)}</p></div></div>`;
}
function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/* --------------------------------------------------------------------- */
/* Init                                                                  */
/* --------------------------------------------------------------------- */
$("#loginForm").addEventListener("submit", doLogin);
$("#logoutBtn").addEventListener("click", () => logout(true));
$$("#nav a").forEach((a) => a.addEventListener("click", () => navigate(a.dataset.route)));
window.addEventListener("hashchange", () => {
  const r = location.hash.replace("#", "");
  // Only react to external hash changes (e.g. back/forward); navigate() itself
  // sets the hash, and that echo must not trigger a duplicate render.
  if (State.token && r && r !== State.route) navigate(r);
});
boot();
