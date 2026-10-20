// BlockLog frontend: plain JavaScript, no framework.
// Core loop: pick exercise -> see last time / best / target -> log set fast.

const $ = (id) => document.getElementById(id);
const QUEUE_KEY = "blocklog.pendingSets";
const LAST_EX_KEY = "blocklog.lastExercise";

// --- tiny API helper -----------------------------------------------------------
async function api(path, options = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  if (res.status === 401) { location.href = "/login"; throw new Error("login required"); }
  const body = res.status === 204 ? null : await res.json();
  if (!res.ok) throw new Error(body?.error || res.statusText);
  return body;
}

// localStorage can throw (private mode, storage full), so wrap every access.
function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(key));
    localStorage.setItem(key, JSON.stringify(value));
  } catch { return null; }
}

// --- offline queue ---------------------------------------------------------------
// If a POST fails because there's no signal, keep the set on the phone and
// resend later. client_id lets the server ignore duplicates.
function queue() { return store(QUEUE_KEY) || []; }

async function flushQueue() {
  const pending = queue();
  if (!pending.length || !navigator.onLine) return;
  const stillPending = [];
  for (const set of pending) {
    try { await api("/sets", { method: "POST", body: JSON.stringify(set) }); }
    catch { stillPending.push(set); }
  }
  store(QUEUE_KEY, stillPending);
  if (stillPending.length < pending.length) loadSummary();
}

function updateOnlineBanner() { $("offline-banner").hidden = navigator.onLine; }

// --- exercises -------------------------------------------------------------------
async function loadExercises(selectId) {
  const list = await api("/exercises");
  const sel = $("exercise");
  sel.innerHTML = list.length
    ? list.map((e) => `<option value="${e.id}">${escapeHtml(e.name)}</option>`).join("")
    : `<option value="">Add your first exercise →</option>`;
  const remembered = selectId || store(LAST_EX_KEY);
  if (remembered && list.some((e) => String(e.id) === String(remembered))) sel.value = remembered;
  loadSummary();
}

$("add-exercise-toggle").addEventListener("click", () => {
  $("add-exercise").hidden = !$("add-exercise").hidden;
  $("new-name").focus();
});

$("add-exercise").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const ex = await api("/exercises", {
      method: "POST",
      body: JSON.stringify({ name: $("new-name").value, size: $("new-size").value }),
    });
    $("new-name").value = "";
    $("add-exercise").hidden = true;
    loadExercises(ex.id);
  } catch (err) { alertMsg(err.message); }
});

$("exercise").addEventListener("change", () => {
  store(LAST_EX_KEY, $("exercise").value);
  loadSummary();
});

// --- recall: last time / best / target -------------------------------------------
const fmtSet = (s) => `${s.weight_kg}kg × ${s.reps}${s.rpe ? ` @ RPE ${s.rpe}` : ""}`;

async function loadSummary() {
  const id = $("exercise").value;
  if (!id) return;
  try {
    const data = await api(`/exercises/${id}/summary`);
    $("last-session").innerHTML = data.last_session.length
      ? data.last_session.map((s) => `<li>${fmtSet(s)}</li>`).join("")
      : `<li class="muted">Nothing logged yet</li>`;
    $("best").textContent = data.best ? `${data.best.weight_kg}kg × ${data.best.reps}` : "–";
    $("target").textContent = data.target
      ? `${data.target.sets}×${data.target.reps} @ ${data.target.weight_kg}kg`
      : "–";
    // Prefill with last set so logging the same weight is one tap.
    const last = data.last_session.at(-1);
    if (last) { $("weight").value = last.weight_kg; $("reps").value = last.reps; }
    else if (data.target) { $("weight").value = data.target.weight_kg; $("reps").value = data.target.reps; }
  } catch { /* offline: keep whatever is on screen */ }
}

async function loadBlock() {
  try {
    const b = await api("/blocks/active");
    $("block-status").textContent = b
      ? `${b.name} · week ${Math.min(b.current_week, b.length_weeks)} of ${b.length_weeks}`
      : "No active block";
  } catch { /* offline */ }
}

// --- logging -------------------------------------------------------------------
document.querySelectorAll("[data-step]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const [field, delta] = btn.dataset.step.split(":");
    const input = $(field);
    const current = parseFloat(input.value) || (field === "rpe" ? 7 : 0);
    let next = current + parseFloat(delta);
    if (input.min !== "") next = Math.max(parseFloat(input.min), next);
    if (input.max !== "") next = Math.min(parseFloat(input.max), next);
    input.value = next;
  });
});

$("log-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!$("exercise").value) return alertMsg("Add an exercise first.");
  const set = {
    client_id: crypto.randomUUID(),
    exercise_id: Number($("exercise").value),
    weight_kg: Number($("weight").value),
    reps: Number($("reps").value),
    rpe: $("rpe").value === "" ? null : Number($("rpe").value),
    performed_at: new Date().toISOString(),
  };
  try {
    await api("/sets", { method: "POST", body: JSON.stringify(set) });
    alertMsg(`Logged ${fmtSet(set)}`);
    loadSummary();
  } catch (err) {
    if (!navigator.onLine || err instanceof TypeError) {
      store(QUEUE_KEY, [...queue(), set]);
      alertMsg(`Saved offline: ${fmtSet(set)}`);
    } else {
      alertMsg(err.message);
    }
  }
});

$("recovery-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/recovery", {
      method: "POST",
      body: JSON.stringify({ kind: $("rec-kind").value, duration_min: Number($("rec-min").value) }),
    });
    alertMsg("Recovery session logged");
  } catch (err) { alertMsg(err.message); }
});

// --- utils ---------------------------------------------------------------------
function alertMsg(text) { $("log-msg").textContent = text; }
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// --- start -----------------------------------------------------------------------
window.addEventListener("online", () => { updateOnlineBanner(); flushQueue(); });
window.addEventListener("offline", updateOnlineBanner);
updateOnlineBanner();
loadExercises();
loadBlock();
flushQueue();

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
