/* ===== CourtVision Frontend Logic ===== */
const API = "/api/v1";

const state = {
  team: null,
  teamName: null,
  season: localStorage.getItem("cv_season") || "2024-25",
  roster: null,
  lastSim: null,
  baselineSim: null,
  simRoster: [],
  editPlayers: [],
  fullRoster: [],
  tradeOut: [],
  tradeIn: [],
  tradeSearchResults: [],
};

const sortState = {
  sim: { key: "minutes", dir: "desc" },
  edit: { key: "rating", dir: "desc" },
  full: { key: "points_per_game", dir: "desc" },
};

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

function showError(msg) {
  const el = $("#errorBanner");
  if (!msg) { el.classList.add("hidden"); return; }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function showOverlay(text = "Working…") {
  $("#overlayText").textContent = text;
  $("#overlay").classList.remove("hidden");
}
function hideOverlay() { $("#overlay").classList.add("hidden"); }

function friendlyError(err, status) {
  const msg = String(err || "");
  if (status === 503 || msg.includes("NBA") || msg.includes("unavailable"))
    return "NBA stats are temporarily unavailable. Try again in a minute, or switch to the 2024-25 season.";
  if (status === 429) return "Too many requests — give it a moment and try again.";
  if (status === 404) return msg || "Not found.";
  return msg || "Something went wrong.";
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); detail = j.detail || detail; } catch (_) {}
    throw new Error(friendlyError(typeof detail === "string" ? detail : JSON.stringify(detail), res.status));
  }
  return res.json();
}

function seasonParam() {
  return `season=${encodeURIComponent(state.season)}`;
}

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

document.addEventListener("click", (e) => {
  const th = e.target.closest("th.sortable");
  if (!th) return;
  const table = th.closest(".sortable-table");
  const group = table.dataset.group;
  const key = th.dataset.key;
  const type = th.dataset.type;
  const cur = sortState[group];
  if (cur.key === key) cur.dir = cur.dir === "desc" ? "asc" : "desc";
  else cur.dir = type === "num" ? "desc" : "asc";
  cur.key = key;
  cur.type = type;
  if (group === "sim") renderSimRoster();
  else if (group === "edit") renderRosterRows();
  else if (group === "full") renderFullRosterRows();
});

/* ---------- navigation ---------- */
$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const view = btn.dataset.view;
    $$(".view").forEach((v) => v.classList.remove("active"));
    $(`#view-${view}`).classList.add("active");
    if (view === "roster") loadRosterEditor();
    if (view === "trade") loadTradeDesk();
    if (view === "compare") prepCompareView();
  });
});

/* ---------- init ---------- */
async function init() {
  setGreeting();
  $("#seasonSelect").value = state.season;
  $("#seasonSelect").addEventListener("change", onSeasonChange);
  await loadTeams();
  checkAgent();
  if ($("#teamSelect").value) state.team = $("#teamSelect").value;
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
    const cmp = $("#compareTeamB");
    sel.innerHTML = "";
    cmp.innerHTML = "";
    teams.sort((a, b) => a.name.localeCompare(b.name)).forEach((t) => {
      [{ el: sel, val: t.abbreviation, text: `${t.name} (${t.abbreviation})` }].forEach(({ el, val, text }) => {
        const opt = document.createElement("option");
        opt.value = val;
        opt.textContent = text;
        el.appendChild(opt);
      });
      const opt2 = document.createElement("option");
      opt2.value = t.abbreviation;
      opt2.textContent = `${t.name} (${t.abbreviation})`;
      cmp.appendChild(opt2);
    });
    const okc = [...sel.options].find((o) => o.value === "OKC");
    if (okc) okc.selected = true;
    state.team = sel.value;
    sel.addEventListener("change", onTeamChange);
    const okcB = [...cmp.options].find((o) => o.value === "LAL");
    if (okcB) okcB.selected = true;
  } catch (e) {
    toast("Could not load teams: " + e.message, "error");
  }
}

function onSeasonChange() {
  state.season = $("#seasonSelect").value;
  localStorage.setItem("cv_season", state.season);
  state.roster = null;
  state.lastSim = null;
  state.baselineSim = null;
  $("#seasonBadge").textContent = "Season " + state.season;
  $("#simResults").classList.add("hidden");
  $("#simEmpty").classList.remove("hidden");
  showError(state.season === "2025-26"
    ? "2025-26 stats may be incomplete early in the season. 2024-25 is the most reliable."
    : null);
  if ($("#view-roster").classList.contains("active")) loadRosterEditor(true);
  if ($("#view-trade").classList.contains("active")) loadTradeDesk();
}

function onTeamChange() {
  state.team = $("#teamSelect").value;
  state.roster = null;
  state.lastSim = null;
  state.baselineSim = null;
  $("#simResults").classList.add("hidden");
  $("#simEmpty").classList.remove("hidden");
  if ($("#view-roster").classList.contains("active")) loadRosterEditor(true);
  if ($("#view-trade").classList.contains("active")) loadTradeDesk();
}

/* ===================== SIMULATE ===================== */
$("#runSimBtn").addEventListener("click", runSimulation);
$("#iterInput").addEventListener("input", () => {
  $("#iterLabel").textContent = (parseInt($("#iterInput").value) || 1000).toLocaleString();
});

async function runSimulation() {
  if (!state.team) return toast("Pick a team first", "error");
  const iterations = Math.max(100, Math.min(10000, parseInt($("#iterInput").value) || 1000));
  showOverlay(`Simulating ${iterations.toLocaleString()} seasons for ${state.team}…`);
  showError(null);
  try {
    await api(`/roster/${state.team}?${seasonParam()}&reload=false`);
    const sim = await api(`/simulate/season/${state.team}?iterations=${iterations}&${seasonParam()}`);
    state.lastSim = sim;
    renderSim(sim);
    toast("Simulation complete", "success");
  } catch (e) {
    showError(e.message);
    toast("Simulation failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderSim(sim) {
  $("#simEmpty").classList.add("hidden");
  $("#simResults").classList.remove("hidden");
  $("#seasonBadge").textContent = "Season " + (sim.season || state.season);

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
  $("#distMeta").textContent = `median ${sp.median_wins} wins · σ ${sp.std_wins.toFixed(1)} · ${sim.iterations.toLocaleString()} runs`;

  renderDistribution(sp.win_distribution);
  renderPlayoffBracket(pp.bracket || {});
  state.simRoster = (sim.roster_summary || []).map((p) => ({ ...p }));
  renderSimRoster();
  renderAnalystTake(sim);
}

function renderPlayoffBracket(bracket) {
  const el = $("#playoffBracket");
  if (!el) return;
  const rows = [
    ["Make playoffs", bracket.make_playoffs],
    ["Win Round 1", bracket.win_round_1],
    ["Win Round 2", bracket.win_round_2],
    ["Reach Finals", bracket.reach_finals],
    ["Win title", bracket.win_championship],
  ];
  el.innerHTML = rows.map(([label, pct]) => {
    const p = ((pct || 0) * 100).toFixed(1);
    return `<div class="bracket-row">
      <span class="bracket-label">${label}</span>
      <div class="bracket-track"><div class="bracket-fill" style="width:${p}%"></div></div>
      <span class="bracket-pct">${p}%</span>
    </div>`;
  }).join("");
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
  const ring = pp.bracket?.win_championship || 0;

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
  if (top) text += `${acc(top.name)} anchors the group at ${top.minutes} minutes a night. `;
  if (playoff >= 0.6) text += `The postseason looks like a formality at ${acc((playoff * 100).toFixed(0) + "%")} odds.`;
  else if (playoff >= 0.2) text += `A playoff berth is live but far from safe (${acc((playoff * 100).toFixed(0) + "%")}).`;
  else text += `Come playoff time, they're on the outside looking in for now (${(playoff * 100).toFixed(0)}% odds).`;
  if (ring >= 0.08) text += ` Title odds sit around ${acc((ring * 100).toFixed(0) + "%")}.`;

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
  const entries = Object.entries(dist).map(([w, p]) => [parseInt(w), p]).sort((a, b) => a[0] - b[0]);
  const max = Math.max(...entries.map((e) => e[1]));
  entries.forEach(([w, p]) => {
    const bar = document.createElement("div");
    bar.className = "bar" + (p === max ? " peak" : "");
    bar.style.height = `${Math.max(3, (p / max) * 100)}%`;
    bar.innerHTML = `<span class="bar-tip">${w} wins · ${(p * 100).toFixed(1)}%</span>`;
    chart.appendChild(bar);
  });
  if (axis) {
    const minW = entries[0][0];
    const maxW = entries[entries.length - 1][0];
    const peakW = entries.find((e) => e[1] === max)[0];
    axis.innerHTML = `<span>${minW} W</span><span>most likely · <span>${peakW} W</span></span><span>${maxW} W</span>`;
  }
}

function renderSimRoster() {
  const { key, dir, type } = sortState.sim;
  const rows = sortRows(state.simRoster, key, type || "num", dir);
  const tb = $("#simRosterTable tbody");
  tb.innerHTML = "";
  rows.forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.name}</td><td><span class="pos-badge">${p.position}</span></td>
      <td>${p.minutes}</td><td>${p.ppg}</td><td><span class="rating-pill">${p.rating}</span></td>`;
    tb.appendChild(tr);
  });
  markSortedHeader("sim", key, dir);
}

function renderComparisonGrid(container, comparison) {
  const base = comparison.baseline;
  const cur = comparison.current;
  const dWins = comparison.wins_delta;
  const dRating = comparison.rating_delta;
  const dPlayoff = comparison.playoff_delta;

  const deltaClass = (v) => (v > 0.05 ? "up" : v < -0.05 ? "down" : "flat");
  const fmtDelta = (v, suffix = "") => {
    const sign = v > 0 ? "+" : "";
    return `${sign}${typeof v === "number" ? v.toFixed(1) : v}${suffix}`;
  };

  container.innerHTML = `
    <div class="compare-card">
      <div class="label">Baseline wins</div>
      <div class="value">${base.season_projection.mean_wins.toFixed(1)}</div>
    </div>
    <div class="compare-card">
      <div class="label">After changes</div>
      <div class="value">${cur.season_projection.mean_wins.toFixed(1)}</div>
      <div class="delta ${deltaClass(dWins)}">${fmtDelta(dWins)} wins</div>
    </div>
    <div class="compare-card">
      <div class="label">Playoff odds</div>
      <div class="value">${(cur.playoff_projection.playoff_probability * 100).toFixed(0)}%</div>
      <div class="delta ${deltaClass(dPlayoff)}">${fmtDelta(dPlayoff * 100, " pts")}</div>
    </div>
    <div class="compare-card">
      <div class="label">Team rating</div>
      <div class="value">${cur.team_rating.toFixed(1)}</div>
      <div class="delta ${deltaClass(dRating)}">${fmtDelta(dRating)}</div>
    </div>
    <div class="compare-card">
      <div class="label">Title odds</div>
      <div class="value">${((cur.playoff_projection.bracket?.win_championship || 0) * 100).toFixed(1)}%</div>
    </div>
    <div class="compare-card">
      <div class="label">Ring delta</div>
      <div class="value">${fmtDelta(
        ((cur.playoff_projection.bracket?.win_championship || 0) -
          (base.playoff_projection.bracket?.win_championship || 0)) * 100,
        " pts"
      )}</div>
    </div>`;
}

/* ===================== ROSTER EDITOR ===================== */
$("#reloadRosterBtn").addEventListener("click", resetRoster);
$("#saveRosterBtn").addEventListener("click", saveRoster);

async function resetRoster() {
  if (!state.team) return;
  showOverlay("Resetting to original roster…");
  try {
    await api(`/roster/${state.team}/reset`, { method: "POST" });
    state.roster = null;
    state.baselineSim = null;
    await loadRosterEditor(true);
    $("#baselinePanel").classList.add("hidden");
    toast("Roster reset to baseline", "success");
  } catch (e) {
    toast("Reset failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

async function loadRosterEditor(force = false) {
  if (!state.team) return;
  if (state.roster && !force) { renderRosterEditor(); return; }
  showOverlay(`Loading ${state.team} roster…`);
  showError(null);
  try {
    const chart = await api(`/roster/${state.team}?${seasonParam()}&reload=${force}`);
    state.roster = chart;
    state.season = chart.season;
    $("#seasonBadge").textContent = "Season " + chart.season;
    renderRosterEditor();
    if (force) await refreshBaselineComparison();
  } catch (e) {
    showError(e.message);
    toast("Could not load roster: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderRosterEditor() {
  const chart = state.roster;
  const allocMap = {};
  (chart.minute_allocations || []).forEach((m) => (allocMap[m.player_id] = m.minutes));
  state.editPlayers = (chart.players || []).map((p) => ({
    player_id: p.player_id,
    name: p.name,
    position: p.position,
    ppg: Number(p.points_per_game ?? 0),
    rating: Number(p.overall_rating ?? 0),
    minutes: allocMap[p.player_id] ?? 0,
  }));
  renderRosterRows();
  $("#rosterMsg").classList.add("hidden");
}

function syncEditMinutes() {
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
    tr.innerHTML = `<td>${p.name}</td><td><span class="pos-badge">${p.position}</span></td>
      <td>${p.ppg.toFixed(1)}</td><td><span class="rating-pill">${p.rating.toFixed(1)}</span></td>
      <td><input class="min-input" type="number" min="0" max="48" step="0.5"
        value="${p.minutes}" data-pid="${p.player_id}" data-name="${p.name}" /></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll(".min-input").forEach((inp) => inp.addEventListener("input", updateMinutesTotal));
  updateMinutesTotal();
  markSortedHeader("edit", key, dir);
}

function updateMinutesTotal() {
  let total = 0;
  $$("#rosterEditTable .min-input").forEach((i) => (total += parseFloat(i.value) || 0));
  const el = $("#minutesTotal");
  el.textContent = `${total.toFixed(1)} / 240 min`;
  el.className = "minutes-total " + (total > 240 ? "over" : "ok");
}

async function refreshBaselineComparison() {
  try {
    const cmp = await api(`/roster/${state.team}/compare-baseline?iterations=800`);
    state.baselineSim = cmp;
    $("#baselinePanel").classList.remove("hidden");
    renderComparisonGrid($("#baselineCompare"), cmp);
  } catch (_) {
    $("#baselinePanel").classList.add("hidden");
  }
}

async function saveRoster() {
  if (!state.roster) return;
  const allocations = [];
  $$("#rosterEditTable .min-input").forEach((i) => {
    const mins = parseFloat(i.value) || 0;
    if (mins > 0) allocations.push({
      player_id: parseInt(i.dataset.pid),
      player_name: i.dataset.name,
      minutes: mins,
    });
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
    const cmp = await api(`/roster/${state.team}/compare-baseline?iterations=1000`);
    state.baselineSim = cmp;
    state.lastSim = cmp.current;
    $("#baselinePanel").classList.remove("hidden");
    renderComparisonGrid($("#baselineCompare"), cmp);
    showRosterMsg(
      `Saved. ${cmp.current.season_projection.mean_wins.toFixed(1)} wins ` +
      `(${cmp.wins_delta >= 0 ? "+" : ""}${cmp.wins_delta.toFixed(1)} vs baseline).`,
      "success"
    );
    renderSim(cmp.current);
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

/* ===================== TRADE DESK ===================== */
$("#tradeSearchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  searchTradePlayer($("#tradeSearchInput").value.trim());
});
$("#runTradeBtn").addEventListener("click", executeTrade);

async function loadTradeDesk() {
  if (!state.team) return;
  try {
    const chart = await api(`/roster/${state.team}?${seasonParam()}`);
    state.roster = chart;
    const sel = $("#tradeOutSelect");
    sel.innerHTML = "";
    chart.players.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.player_id;
      opt.textContent = `${p.name} · ${p.overall_rating?.toFixed?.(1) ?? "?"} rating · ${p.points_per_game} PPG`;
      sel.appendChild(opt);
    });
    sel.onchange = updateTradePreview;
    state.tradeIn = [];
    state.tradeOut = [];
    $("#tradeIncomingList").innerHTML = '<p class="muted small">Search for a player to acquire.</p>';
    $("#tradePreview").classList.add("hidden");
    $("#tradeResults").classList.add("hidden");
  } catch (e) {
    toast("Could not load roster for trade: " + e.message, "error");
  }
}

async function searchTradePlayer(q) {
  if (!q) return;
  $("#tradeIncomingList").innerHTML = '<p class="muted">Searching…</p>';
  try {
    const results = await api(`/nba/search/${encodeURIComponent(q)}`);
    state.tradeSearchResults = results.filter((p) => p.is_active).slice(0, 8);
    const list = $("#tradeIncomingList");
    list.innerHTML = "";
    if (!state.tradeSearchResults.length) {
      list.innerHTML = '<p class="muted">No active players found.</p>';
      return;
    }
    for (const p of state.tradeSearchResults) {
      const preview = await api(`/nba/player/${p.id}?${seasonParam()}`).catch(() => null);
      const div = document.createElement("div");
      div.className = "trade-incoming-item";
      div.dataset.pid = p.id;
      div.innerHTML = `<span>${p.full_name}</span>
        <span class="rating-pill">${preview ? preview.rating : "…"}</span>`;
      div.onclick = () => selectTradeIn(p.id, div);
      list.appendChild(div);
    }
  } catch (e) {
    $("#tradeIncomingList").innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

function selectTradeIn(pid, el) {
  $$(".trade-incoming-item").forEach((i) => i.classList.remove("selected"));
  el.classList.add("selected");
  state.tradeIn = [parseInt(pid)];
  updateTradePreview();
}

function updateTradePreview() {
  const sel = $("#tradeOutSelect");
  state.tradeOut = [...sel.selectedOptions].map((o) => parseInt(o.value));
  if (!state.tradeOut.length && !state.tradeIn.length) {
    $("#tradePreview").classList.add("hidden");
    return;
  }
  $("#tradePreview").classList.remove("hidden");
  const outNames = [...sel.selectedOptions].map((o) => o.textContent.split(" · ")[0]);
  const inName = $(".trade-incoming-item.selected span")?.textContent || "—";
  $("#tradePreviewGrid").innerHTML = `
    <div class="trade-side"><h4>Outgoing (${state.tradeOut.length})</h4>
      ${outNames.map((n) => `<div class="trade-player-chip"><span>${n}</span></div>`).join("") || '<p class="muted">None selected</p>'}
    </div>
    <div class="trade-side"><h4>Incoming (${state.tradeIn.length})</h4>
      ${state.tradeIn.length ? `<div class="trade-player-chip"><span>${inName}</span></div>` : '<p class="muted">Search & click a player</p>'}
    </div>`;
}

async function executeTrade() {
  if (!state.tradeOut.length && !state.tradeIn.length) {
    return toast("Pick at least one player to trade", "error");
  }
  showOverlay("Applying trade & running simulation…");
  try {
    const res = await api(`/roster/${state.team}/trade?iterations=1000`, {
      method: "POST",
      body: JSON.stringify({
        remove_player_ids: state.tradeOut,
        add_player_ids: state.tradeIn,
      }),
    });
    state.roster = res.roster;
    state.lastSim = res.comparison.current;
    $("#tradeResults").classList.remove("hidden");
    renderComparisonGrid($("#tradeCompare"), res.comparison);
    renderSim(res.comparison.current);
    toast("Trade simulated — check results below", "success");
    $$(".nav-item").forEach((b) => b.classList.remove("active"));
    $$(".view").forEach((v) => v.classList.remove("active"));
    // stay on trade view but user can switch to simulate
  } catch (e) {
    toast("Trade failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

/* ===================== COMPARE ===================== */
$("#runCompareBtn").addEventListener("click", runCompare);

function prepCompareView() {
  if (state.team) {
    const sel = $("#compareTeamB");
    const other = [...sel.options].find((o) => o.value !== state.team);
    if (other && sel.value === state.team) other.selected = true;
  }
}

async function runCompare() {
  const teamA = state.team;
  const teamB = $("#compareTeamB").value;
  if (!teamA || !teamB) return toast("Pick both teams", "error");
  if (teamA === teamB) return toast("Pick two different teams", "error");

  showOverlay(`Comparing ${teamA} vs ${teamB}…`);
  try {
    const res = await api("/simulate/compare", {
      method: "POST",
      body: JSON.stringify({ team_a: teamA, team_b: teamB, iterations: 1000, season: state.season }),
    });
    renderCompare(res);
    toast("Comparison complete", "success");
  } catch (e) {
    toast("Compare failed: " + e.message, "error");
  } finally {
    hideOverlay();
  }
}

function renderCompare(res) {
  $("#compareEmpty").classList.add("hidden");
  $("#compareResults").classList.remove("hidden");
  const a = res.team_a;
  const b = res.team_b;
  $("#compareMatchup").innerHTML =
    `${a.team_name} <span class="muted">vs</span> ${b.team_name} · ` +
    `<strong>${res.wins_winner}</strong> projects more wins`;

  const col = (sim, isWinner) => {
    const br = sim.playoff_projection.bracket || {};
    return `<div class="compare-team-col ${isWinner ? "winner" : ""}">
      <h3>${sim.team_name}</h3>
      <div class="compare-stat-line"><span>Projected record</span><span>${sim.season_projection.mean_wins.toFixed(1)}–${(82 - sim.season_projection.mean_wins).toFixed(1)}</span></div>
      <div class="compare-stat-line"><span>Win rate</span><span>${(sim.season_projection.win_pct * 100).toFixed(1)}%</span></div>
      <div class="compare-stat-line"><span>Team rating</span><span>${sim.team_rating.toFixed(1)}</span></div>
      <div class="compare-stat-line"><span>Playoff odds</span><span>${(sim.playoff_projection.playoff_probability * 100).toFixed(0)}%</span></div>
      <div class="compare-stat-line"><span>Title odds</span><span>${((br.win_championship || 0) * 100).toFixed(1)}%</span></div>
      <div class="compare-stat-line"><span>Top player</span><span>${sim.roster_summary[0]?.name || "—"}</span></div>
    </div>`;
  };

  $("#compareSideBySide").innerHTML =
    col(a, res.wins_winner === a.team_abbreviation) +
    col(b, res.wins_winner === b.team_abbreviation);
}

/* ===================== GM AGENT ===================== */
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

$("#chatForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#chatInput").value.trim();
  if (text) sendChat(text);
});

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) sendChat(e.target.textContent);
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
    addMsg("bot", e.message);
  }
}

function addMsg(role, text) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.innerHTML = `<div class="msg-avatar">${role === "user" ? "YOU" : "CV"}</div>
    <div class="msg-body">${formatText(text)}</div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function addBotMsg(res) {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "msg bot";
  let tools = "";
  if (res.tool_calls?.length) {
    tools = `<div class="tool-tags">${res.tool_calls.map((t) => `<span class="tool-tag">${t.tool}</span>`).join("")}</div>`;
  }
  div.innerHTML = `<div class="msg-avatar">CV</div><div class="msg-body">${formatText(res.response)}${tools}
    <div class="msg-meta">via ${res.mode === "agent" ? "Gemini agent" : "Simulation engine"}</div></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function addTyping() {
  const log = $("#chatLog");
  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = `<div class="msg-avatar">CV</div><div class="msg-body"><div class="typing"><span></span><span></span><span></span></div></div>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function formatText(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "\n");
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
    const data = await api(`/nba/roster/${state.team}?${seasonParam()}`);
    state.fullRoster = (data.players || []).map((p) => ({
      name: p.name, position: p.position || "-",
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
  sortRows(state.fullRoster, key, type || "num", dir).forEach((p) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${p.name}</td><td><span class="pos-badge">${p.position}</span></td>
      <td>${p.points_per_game.toFixed(1)}</td><td>${p.rebounds_per_game.toFixed(1)}</td>
      <td>${p.assists_per_game.toFixed(1)}</td>`;
    tb.appendChild(tr);
  });
  markSortedHeader("full", key, dir);
}

async function searchPlayer(q) {
  const box = $("#searchResults");
  box.innerHTML = '<p class="muted">Searching…</p>';
  try {
    const results = await api(`/nba/search/${encodeURIComponent(q)}`);
    box.innerHTML = "";
    if (!results.length) { box.innerHTML = '<p class="muted">No players found.</p>'; return; }
    results.forEach((p) => {
      const div = document.createElement("div");
      div.className = "search-item";
      div.innerHTML = `<span>${p.full_name}</span>
        <span class="badge-active ${p.is_active ? "yes" : "no"}">${p.is_active ? "Active" : "Retired"}</span>`;
      box.appendChild(div);
    });
  } catch (e) {
    box.innerHTML = `<p class="muted">${e.message}</p>`;
  }
}

init();
