/* ===== CourtVision Frontend Logic ===== */
const API = "/api/v1";

const state = {
  team: null,
  teamName: null,
  season: null,
  roster: null,       // full RosterChart from /roster/{abbr}
  lastSim: null,
  simRoster: [],      // normalized rotation rows for sorting
  editPlayers: [],    // roster editor rows (with _rating, _minutes)
  fullRoster: [],     // NBA data roster rows
};

const sortState = {
  sim: { key: "minutes", dir: "desc" },
  edit: { key: "rating", dir: "desc" },
  full: { key: "points_per_game", dir: "desc" },
};

/* generic sorter */
function sortRows(arr, key, type, dir) {
  const sorted = [...arr].sort((a, b) => {
    if (type === "num") return (parseFloat(a[key]) || 0) - (parseFloat(b[key]) || 0);
    const av = String(a[key] ?? "").toLowerCase();
    const bv = String(b[key] ?? "").toLowerCase();
    return av < bv ? -1 : av > bv ? 1 : 0;
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

function markSortedHeader(group, key, dir) {
  const table = document.querySelector(`.sortable-table[data-group="${group}"]`);
  if (!table) return;
  table.querySelectorAll("th.sortable").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.key === key) th.classList.add(dir === "desc" ? "sorted-desc" : "sorted-asc");
  });
}

/* delegated click handler for all sortable headers */
document.addEventListener("click", (e) => {
  const th = e.target.closest("th.sortable");
  if (!th) return;
  const table = th.closest(".sortable-table");
  const group = table.dataset.group;
  const key = th.dataset.key;
  const type = th.dataset.type;
  const cur = sortState[group];
  // toggle direction; default new column to desc for numbers, asc for text
  if (cur.key === key) cur.dir = cur.dir === "desc" ? "asc" : "desc";
  else cur.dir = type === "num" ? "desc" : "asc";
  cur.key = key;
  cur.type = type;
  if (group === "sim") renderSimRoster();
  else if (group === "edit") renderRosterRows();
  else if (group === "full") renderFullRosterRows();
});

/* ---------- helpers ---------- */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function toast(msg, type = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.classList.remove("hidden");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.add("hidden"), 3200);
}

function showOverlay(text = "Working…") {
  $("#overlayText").textContent = text;
  $("#overlay").classList.remove("hidden");
}
function hideOverlay() { $("#overlay").classList.add("hidden"); }

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

/* ---------- navigation ---------- */
$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const view = btn.dataset.view;
    $$(".view").forEach((v) => v.classList.remove("active"));
    $(`#view-${view}`).classList.add("active");
    if (view === "roster") loadRosterEditor();
  });
});

/* ---------- init ---------- */
async function init() {
  setGreeting();
  await loadTeams();
  checkAgent();
  // default team
  if ($("#teamSelect").value) {
    state.team = $("#teamSelect").value;
  }
}

function setGreeting() {
  const h = new Date().getHours();
  let word = "Good evening";
  if (h < 12) word = "Good morning";
  else if (h < 18) word = "Good afternoon";
  const subs = [
    "Let's build a contender.",
    "The season's yours to shape.",
    "Time to make some moves.",
    "Every minute counts — literally.",
    "Trust the process. Then simulate it.",
  ];
  $("#greetTitle").textContent = `${word}, GM`;
  $("#greetSub").textContent = subs[Math.floor(Math.random() * subs.length)];
}

async function loadTeams() {
  try {
    const teams = await api("/nba/teams");
    const sel = $("#teamSelect");
    sel.innerHTML = "";
    teams
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.abbreviation;
        opt.textContent = `${t.name} (${t.abbreviation})`;
        sel.appendChild(opt);
      });
    // default to Lakers if present
    const lal = [...sel.options].find((o) => o.value === "LAL");
    if (lal) lal.selected = true;
    state.team = sel.value;
    sel.addEventListener("change", onTeamChange);
  } catch (e) {
    toast("Could not load teams: " + e.message, "error");
  }
}

function onTeamChange() {
  state.team = $("#teamSelect").value;
  state.roster = null;
  state.lastSim = null;
  // reset simulate view
  $("#simResults").classList.add("hidden");
  $("#simEmpty").classList.remove("hidden");
  // reload roster editor if visible
  if ($("#view-roster").classList.contains("active")) loadRosterEditor();
}

async function checkAgent() {
  try {
    const s = await api("/agent/status");
    const dot = $("#agentDot");
    const txt = $("#agentStatusText");
    if (s.agent_available) {
      dot.className = "dot on";
      txt.textContent = `Gemini · ${s.model || "ready"}`;
    } else {
      dot.className = "dot off";
      txt.textContent = "Fallback mode (no LLM)";
    }
  } catch (e) {
    $("#agentDot").className = "dot off";
    $("#agentStatusText").textContent = "Agent offline";
  }
}

/* ===================== SIMULATE ===================== */
$("#runSimBtn").addEventListener("click", runSimulation);
$("#iterInput").addEventListener("input", () => {
  const v = parseInt($("#iterInput").value) || 1000;
  $("#iterLabel").textContent = v.toLocaleString();
});

async function runSimulation() {
  if (!state.team) return toast("Pick a team first", "error");
  const iterations = Math.max(100, Math.min(10000, parseInt($("#iterInput").value) || 1000));
  showOverlay(`Simulating ${iterations.toLocaleString()} seasons for ${state.team}…`);
  try {
    const sim = await api(`/simulate/season/${state.team}?iterations=${iterations}`);
    state.lastSim = sim;
    renderSim(sim);
    toast("Simulation complete", "success");
  } catch (e) {
    toast("Simulation failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderSim(sim) {
  $("#simEmpty").classList.add("hidden");
  $("#simResults").classList.remove("hidden");
  $("#seasonBadge").textContent = "Season " + (sim.season || "");

  const sp = sim.season_projection;
  const pp = sim.playoff_projection;
  const wins = sp.mean_wins;
  const losses = 82 - wins;

  $("#statRecord").textContent = `${wins.toFixed(1)}–${losses.toFixed(1)}`;
  $("#statWinPct").textContent = (sp.win_pct * 100).toFixed(1) + "% win rate";
  $("#statRating").textContent = sim.team_rating.toFixed(1);
  $("#statPlayoff").textContent = (pp.playoff_probability * 100).toFixed(1) + "%";
  $("#statSeed").textContent = pp.projected_seed ? `Projected #${pp.projected_seed} seed` : "Outside top 8";
  $("#statRange").textContent = `${Math.round(sp.percentile_10)}–${Math.round(sp.percentile_90)}`;

  $("#distMeta").textContent =
    `median ${sp.median_wins} wins · σ ${sp.std_wins.toFixed(1)} · ${sim.iterations.toLocaleString()} runs`;

  renderDistribution(sp.win_distribution);

  // normalize rotation rows for sortable table
  state.simRoster = (sim.roster_summary || []).map((p) => ({
    name: p.name,
    position: p.position,
    minutes: p.minutes,
    ppg: p.ppg,
    rating: p.rating,
  }));
  renderSimRoster();
  renderAnalystTake(sim);
}

function renderAnalystTake(sim) {
  const el = $("#analystTake");
  const tagsEl = $("#takeTags");
  if (!el) return;
  const sp = sim.season_projection;
  const pp = sim.playoff_projection;
  const wins = Math.round(sp.mean_wins);
  const losses = 82 - wins;
  const pct = (sp.win_pct * 100).toFixed(1);
  const playoff = pp.playoff_probability;
  const top = (sim.roster_summary || [])[0];
  const team = sim.team_name;

  // tier language
  let tier, tone;
  if (wins >= 55) { tier = "a genuine title threat"; tone = "good"; }
  else if (wins >= 47) { tier = "a solid playoff team"; tone = "good"; }
  else if (wins >= 40) { tier = "squarely in the play-in mix"; tone = ""; }
  else if (wins >= 30) { tier = "a season away from contention"; tone = "warn"; }
  else { tier = "in full development mode"; tone = "warn"; }

  const acc = (t) => `<span class="accent">${t}</span>`;
  let text =
    `Across ${acc(sim.iterations.toLocaleString() + " simulated seasons")}, the ${team} settle in around ` +
    `${acc(wins + "–" + losses)} (${pct}% wins) — ${tier}. `;
  if (top) {
    text += `${acc(top.name)} anchors the group at ${top.minutes} minutes a night. `;
  }
  if (playoff >= 0.6) text += `The postseason looks like a formality at ${acc((playoff * 100).toFixed(0) + "%")} odds.`;
  else if (playoff >= 0.2) text += `A playoff berth is live but far from safe (${acc((playoff * 100).toFixed(0) + "%")}).`;
  else text += `Come playoff time, they're on the outside looking in for now (${(playoff * 100).toFixed(0)}% odds).`;

  el.innerHTML = text;

  if (tagsEl) {
    const seed = pp.projected_seed ? `#${pp.projected_seed} seed` : "Lottery-bound";
    tagsEl.innerHTML =
      `<span class="take-tag ${tone}">${tier.replace(/^a |^in /, "")}</span>` +
      `<span class="take-tag">${seed}</span>` +
      `<span class="take-tag">Rating ${sim.team_rating.toFixed(1)}</span>`;
  }
}

function renderDistribution(dist) {
  const chart = $("#distChart");
  const axis = $("#distAxis");
  chart.innerHTML = "";
  if (axis) axis.innerHTML = "";
  if (!dist || Object.keys(dist).length === 0) {
    chart.innerHTML = '<p class="muted">No distribution data.</p>';
    return;
  }
  const entries = Object.entries(dist)
    .map(([w, p]) => [parseInt(w), p])
    .sort((a, b) => a[0] - b[0]);
  const max = Math.max(...entries.map((e) => e[1]));
  entries.forEach(([w, p]) => {
    const bar = document.createElement("div");
    bar.className = "bar" + (p === max ? " peak" : "");
    bar.style.height = `${Math.max(3, (p / max) * 100)}%`;
    bar.innerHTML = `<span class="bar-tip">${w} wins · ${(p * 100).toFixed(1)}%</span>`;
    chart.appendChild(bar);
  });

  // axis: fewest wins → most likely → most wins
  if (axis) {
    const minW = entries[0][0];
    const maxW = entries[entries.length - 1][0];
    const peakW = entries.find((e) => e[1] === max)[0];
    axis.innerHTML =
      `<span>${minW} W</span>` +
      `<span>most likely · <span>${peakW} W</span></span>` +
      `<span>${maxW} W</span>`;
  }
}

function renderSimRoster() {
  const { key, dir, type } = sortState.sim;
  const rows = sortRows(state.simRoster, key, type || "num", dir);
  const tb = $("#simRosterTable tbody");
  tb.innerHTML = "";
  rows.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td><span class="pos-badge">${p.position}</span></td>
      <td>${p.minutes}</td>
      <td>${p.ppg}</td>
      <td><span class="rating-pill">${p.rating}</span></td>`;
    tb.appendChild(tr);
  });
  markSortedHeader("sim", key, dir);
}

/* ===================== ROSTER EDITOR ===================== */
$("#reloadRosterBtn").addEventListener("click", () => loadRosterEditor(true));
$("#saveRosterBtn").addEventListener("click", saveRoster);

async function loadRosterEditor(force = false) {
  if (!state.team) return;
  if (state.roster && !force) { renderRosterEditor(); return; }
  showOverlay(`Loading ${state.team} roster…`);
  try {
    const chart = await api(`/roster/${state.team}`);
    state.roster = chart;
    state.season = chart.season;
    $("#seasonBadge").textContent = "Season " + chart.season;
    renderRosterEditor();
  } catch (e) {
    toast("Could not load roster: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderRosterEditor() {
  const chart = state.roster;
  const allocMap = {};
  (chart.minute_allocations || []).forEach((m) => (allocMap[m.player_id] = m.minutes));

  // build normalized editable rows once; sorting works on this array
  state.editPlayers = (chart.players || []).map((p) => ({
    player_id: p.player_id,
    name: p.name,
    position: p.position,
    ppg: Number(p.points_per_game ?? 0),
    rating: Number(ratingOf(p)),
    minutes: allocMap[p.player_id] ?? 0,
  }));
  renderRosterRows();
  $("#rosterMsg").classList.add("hidden");
}

function syncEditMinutes() {
  // capture any edits currently in the inputs before re-sorting
  $$("#rosterEditTable .min-input").forEach((i) => {
    const pid = parseInt(i.dataset.pid);
    const row = state.editPlayers.find((r) => r.player_id === pid);
    if (row) row.minutes = parseFloat(i.value) || 0;
  });
}

function renderRosterRows() {
  syncEditMinutes();
  const { key, dir, type } = sortState.edit;
  const rows = sortRows(state.editPlayers, key, type || "num", dir);
  const tb = $("#rosterEditTable tbody");
  tb.innerHTML = "";
  rows.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td><span class="pos-badge">${p.position}</span></td>
      <td>${p.ppg.toFixed(1)}</td>
      <td><span class="rating-pill">${p.rating.toFixed(1)}</span></td>
      <td><input class="min-input" type="number" min="0" max="48" step="0.5"
                 value="${p.minutes}" data-pid="${p.player_id}" data-name="${p.name}" /></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll(".min-input").forEach((inp) =>
    inp.addEventListener("input", updateMinutesTotal)
  );
  updateMinutesTotal();
  markSortedHeader("edit", key, dir);
}

function ratingOf(p) {
  // Backend computes overall_rating server-side; approximate here for display
  const base =
    (p.points_per_game || 0) * 0.35 +
    (p.rebounds_per_game || 0) * 0.15 +
    (p.assists_per_game || 0) * 0.2 +
    (p.steals_per_game || 0) * 2 +
    (p.blocks_per_game || 0) * 2 +
    (p.plus_minus || 0) * 0.5 +
    (p.win_shares || 0) * 3;
  const eff = ((p.field_goal_pct || 0) - 0.42) * 20 + ((p.three_point_pct || 0) - 0.35) * 10;
  return Math.max(0, Math.min(100, base + eff + 30)).toFixed(1);
}

function updateMinutesTotal() {
  let total = 0;
  $$("#rosterEditTable .min-input").forEach((i) => (total += parseFloat(i.value) || 0));
  const el = $("#minutesTotal");
  el.textContent = `${total.toFixed(1)} / 240 min`;
  el.className = "minutes-total " + (total > 240 ? "over" : "ok");
}

async function saveRoster() {
  if (!state.roster) return;
  const allocations = [];
  $$("#rosterEditTable .min-input").forEach((i) => {
    const mins = parseFloat(i.value) || 0;
    if (mins > 0) {
      allocations.push({
        player_id: parseInt(i.dataset.pid),
        player_name: i.dataset.name,
        minutes: mins,
      });
    }
  });
  const total = allocations.reduce((s, a) => s + a.minutes, 0);
  if (total > 240) {
    showRosterMsg(`Total minutes (${total.toFixed(1)}) exceeds 240. Reduce before saving.`, "error");
    return;
  }

  showOverlay("Saving allocations & simulating…");
  try {
    await api(`/roster/${state.team}`, {
      method: "PUT",
      body: JSON.stringify({ team_abbreviation: state.team, minute_allocations: allocations }),
    });
    // re-simulate with new minutes
    const sim = await api(`/simulate/season/${state.team}?iterations=1000`);
    state.lastSim = sim;
    showRosterMsg(
      `Saved. New projection: ${sim.season_projection.mean_wins.toFixed(1)} wins · ` +
      `${(sim.playoff_projection.playoff_probability * 100).toFixed(1)}% playoff odds.`,
      "success"
    );
    renderSim(sim);
    toast("Roster updated & re-simulated", "success");
  } catch (e) {
    showRosterMsg("Save failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function showRosterMsg(msg, type) {
  const el = $("#rosterMsg");
  el.textContent = msg;
  el.className = `inline-msg ${type}`;
  el.classList.remove("hidden");
}

/* ===================== GM AGENT CHAT ===================== */
$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#chatInput").value.trim();
  if (text) sendChat(text);
});

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) {
    sendChat(e.target.textContent);
  }
});

async function sendChat(text) {
  const welcome = $(".chat-welcome");
  if (welcome) welcome.remove();

  $("#chatInput").value = "";
  addMsg("user", text);
  const typingEl = addTyping();

  try {
    const res = await api("/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, team_context: state.team }),
    });
    typingEl.remove();
    addBotMsg(res);
  } catch (e) {
    typingEl.remove();
    addMsg("bot", "⚠️ " + e.message);
  }
}

function addMsg(role, text) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = `
    <div class="msg-avatar">${role === "user" ? "YOU" : "CV"}</div>
    <div class="msg-body">${formatText(text)}</div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function addBotMsg(res) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "msg bot";
  let tools = "";
  if (res.tool_calls && res.tool_calls.length) {
    tools = `<div class="tool-tags">${res.tool_calls
      .map((t) => `<span class="tool-tag">${t.tool}</span>`)
      .join("")}</div>`;
  }
  const modeLabel = res.mode === "agent" ? "Gemini agent" : "Simulation engine";
  div.innerHTML = `
    <div class="msg-avatar">CV</div>
    <div class="msg-body">${formatText(res.response)}
      ${tools}
      <div class="msg-meta">via ${modeLabel}</div>
    </div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function addTyping() {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = `
    <div class="msg-avatar">CV</div>
    <div class="msg-body"><div class="typing"><span></span><span></span><span></span></div></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function formatText(text) {
  return String(text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "\n");
}

/* ===================== NBA DATA ===================== */
$("#loadFullRosterBtn").addEventListener("click", loadFullRoster);
$("#searchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#searchInput").value.trim();
  if (q) searchPlayer(q);
});

async function loadFullRoster() {
  if (!state.team) return;
  showOverlay(`Fetching ${state.team} roster from NBA…`);
  try {
    const data = await api(`/nba/roster/${state.team}`);
    state.fullRoster = (data.players || []).map((p) => ({
      name: p.name,
      position: p.position || "-",
      points_per_game: Number(p.points_per_game ?? 0),
      rebounds_per_game: Number(p.rebounds_per_game ?? 0),
      assists_per_game: Number(p.assists_per_game ?? 0),
    }));
    renderFullRosterRows();
  } catch (e) {
    toast("Roster fetch failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderFullRosterRows() {
  const tb = $("#fullRosterTable tbody");
  tb.innerHTML = "";
  if (!state.fullRoster.length) {
    tb.innerHTML = '<tr><td colspan="5" class="muted">No player data returned.</td></tr>';
    return;
  }
  const { key, dir, type } = sortState.full;
  const rows = sortRows(state.fullRoster, key, type || "num", dir);
  rows.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.name}</td>
      <td><span class="pos-badge">${p.position}</span></td>
      <td>${p.points_per_game.toFixed(1)}</td>
      <td>${p.rebounds_per_game.toFixed(1)}</td>
      <td>${p.assists_per_game.toFixed(1)}</td>`;
    tb.appendChild(tr);
  });
  markSortedHeader("full", key, dir);
}

function fmt(v) {
  if (v === null || v === undefined) return "—";
  return typeof v === "number" ? v.toFixed(1) : v;
}

async function searchPlayer(q) {
  const box = $("#searchResults");
  box.innerHTML = '<p class="muted">Searching…</p>';
  try {
    const results = await api(`/nba/search/${encodeURIComponent(q)}`);
    box.innerHTML = "";
    if (!results.length) {
      box.innerHTML = '<p class="muted">No players found.</p>';
      return;
    }
    results.forEach((p) => {
      const div = document.createElement("div");
      div.className = "search-item";
      div.innerHTML = `
        <span>${p.full_name}</span>
        <span class="badge-active ${p.is_active ? "yes" : "no"}">${p.is_active ? "Active" : "Retired"}</span>`;
      box.appendChild(div);
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">Search failed: ${e.message}</p>`;
  }
}

/* ---------- go ---------- */
init();
