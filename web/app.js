// SaansSaathi dashboard. Talks to the HTTP API: GET /schools, GET /status, POST /run-now.
const API = (window.SAANS_CONFIG && window.SAANS_CONFIG.apiBase || "").replace(/\/$/, "");
const $ = (id) => document.getElementById(id);
const CATS = [
  ["Good", 50, "#00B050"], ["Satisfactory", 100, "#92D050"], ["Moderate", 200, "#FFFF00"],
  ["Poor", 300, "#FF9900"], ["Very Poor", 400, "#FF0000"], ["Severe", 500, "#C00000"],
];
const STATUS_TEXT = { pending: "Awaiting approval", approved: "Approved", sending: "Sending", sent: "Sent to parents", skipped: "Skipped" };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let school = null, last = null, running = null, pollTimer = null;

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function init() {
  try {
    const { schools } = await api("/schools");
    $("school").innerHTML = schools.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
    const saved = (() => { try { return localStorage.getItem("saans-school"); } catch { return null; } })();
    if (saved && schools.some((s) => s.id === saved)) $("school").value = saved;
  } catch (e) {
    showErr("Could not reach the API. " + e.message);
    return;
  }
  $("school").onchange = () => { try { localStorage.setItem("saans-school", $("school").value); } catch {} refresh(); };
  $("run").onclick = runNow;
  $("toggle-table").onclick = () => { const t = $("table"); t.hidden = !t.hidden; $("toggle-table").textContent = t.hidden ? "Show table" : "Hide table"; };
  refresh();
  schedule();
}

function schedule() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { await refresh(); schedule(); }, running ? 2500 : 15000);
}

function showErr(msg) { const e = $("err"); e.textContent = msg; e.hidden = !msg; }

async function refresh() {
  try {
    const st = await api(`/status?school=${encodeURIComponent($("school").value)}`);
    render(st);
    showErr("");
  } catch (e) { showErr("Could not load status. " + e.message); }
}

async function runNow() {
  const live = document.querySelector("input[name=mode]:checked").value === "live";
  const q = new URLSearchParams({ school: $("school").value });
  if (!live) q.set("replay", $("replay").value);
  $("run").disabled = true;
  showErr("");
  running = { since: last && last.plan_id, startedAt: Date.now() };
  setSteps(0);
  try {
    await api(`/run-now?${q}`, { method: "POST" });
  } catch (e) {
    showErr("Run failed. " + e.message);
    running = null; $("run").disabled = false; return;
  }
  schedule();
}

function setSteps(n) {
  const steps = $("steps");
  steps.hidden = false;
  [...steps.children].forEach((li, i) => { li.className = i < n ? "done" : i === n ? "now" : ""; });
  if (n >= steps.children.length) [...steps.children].forEach((li) => (li.className = "done"));
}

function render(st) {
  school = st.school;
  last = st.latest;
  $("s-hours").textContent = Math.round(st.impact.child_hours).toLocaleString("en-IN");
  $("s-parents").textContent = st.impact.parents_reached.toLocaleString("en-IN");
  $("s-subs").textContent = st.subscribers.total.toLocaleString("en-IN");

  if (running) {
    const fresh = last && last.plan_id !== running.since;
    if (!fresh) setSteps(Date.now() - running.startedAt > 4000 ? 1 : 0);
    else if (last.status === "pending") setSteps(2);
    else if (last.status === "approved" || last.status === "sending") setSteps(3);
    else { setSteps(4); running = null; $("run").disabled = false; }
    if (fresh && last.status === "pending") $("run").disabled = false;
    if (Date.now() - running?.startedAt > 180000) { running = null; $("run").disabled = false; showErr("Still waiting. Check the worker logs."); }
  }

  const chip = $("status");
  chip.className = "chip " + (last ? last.status : "");
  chip.textContent = last ? STATUS_TEXT[last.status] || last.status : "No plan";
  if (!last) {
    $("plan").innerHTML = `<p class="empty">No plan yet for ${esc(school.name)}. Run the check above.</p>`;
    $("chart").innerHTML = '<p class="empty">–</p>'; $("legend").innerHTML = ""; $("table").innerHTML = "";
    $("messages").innerHTML = `<p class="empty">Parents join on Telegram with <b>/join ${esc(school.join_code)}</b>.</p>`;
    return;
  }
  const p = last.plan;
  renderPlan(p, last);
  renderChart(p);
  renderMessages(last);
}

function renderPlan(p, rec) {
  const d = new Date(p.date + "T00:00:00");
  const when = d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  const mode = p.mode === "replay" ? "replay of a past day" : "live forecast";
  const worst = p.worst ? `Worst hour ${p.worst.time}: <b>${p.worst.aqi}</b> ${esc(p.worst.category)}` : "";
  const clean = p.cleanest ? ` · Cleanest ${p.cleanest.time}: <b>${p.cleanest.aqi}</b>` : "";
  const blocks = p.blocks.map((b) => {
    const label = { reschedule: "MOVE", indoors: "INDOORS", keep: "KEEP" }[b.action];
    return `<li><span class="tag ${b.action}">${label}</span><span>${esc(b.reason)}</span></li>`;
  }).join("");
  const adv = p.advisories.length ? `<ul class="advisories">${p.advisories.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : "";
  const sent = rec.status === "sent" ? ` · reached ${rec.parents_reached} parent(s)` : "";
  $("plan").innerHTML = `<p class="meta">${esc(p.school_name)} · ${when} (${mode})<br>${worst}${clean}</p>
    <ul class="blocks">${blocks}</ul>${adv}
    <p class="muted">${p.child_hours_protected.toLocaleString("en-IN")} child-hours moved out of AQI (est.) 201+ air${sent}. Messages: ${esc(rec.messages.source)}.</p>`;
}

function catColor(aqi) { return (CATS.find((c) => aqi <= c[1]) || CATS[CATS.length - 1])[2]; }

function renderChart(p) {
  const hours = p.hours.filter((h) => h.aqi != null);
  chartW = Math.round($("chart").getBoundingClientRect().width) || 640;
  const W = Math.max(300, chartW), H = 240, padL = 34, padR = 8, padT = 22, padB = 28;
  const top = Math.max(300, Math.ceil(Math.max(...hours.map((h) => h.aqi)) / 100) * 100);
  const y = (v) => padT + (H - padT - padB) * (1 - v / top);
  const slot = (W - padL - padR) / hours.length;
  const bw = Math.min(44, slot * 0.6);
  const cleanest = p.cleanest && p.cleanest.hour;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="AQI (est.) for each school hour">`;
  for (let v = 0; v <= top; v += 100) {
    svg += `<line x1="${padL}" x2="${W - padR}" y1="${y(v)}" y2="${y(v)}" stroke="var(--grid)" stroke-width="1"/>`;
    svg += `<text x="${padL - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="var(--ink-3)">${v}</text>`;
  }
  hours.forEach((h, i) => {
    const cx = padL + slot * i + slot / 2, x = cx - bw / 2, yt = y(h.aqi), base = y(0), r = Math.min(4, (base - yt) / 2);
    const path = `M${x},${base} V${yt + r} Q${x},${yt} ${x + r},${yt} H${x + bw - r} Q${x + bw},${yt} ${x + bw},${yt + r} V${base} Z`;
    const isClean = h.hour === cleanest;
    svg += `<g class="bar" data-i="${i}">`;
    svg += `<rect x="${cx - slot / 2}" y="${padT}" width="${slot}" height="${base - padT}" fill="transparent"/>`;
    svg += `<path d="${path}" fill="${catColor(h.aqi)}"${isClean ? ` stroke="var(--ring)" stroke-width="2"` : ""}/>`;
    if (isClean || (p.worst && h.hour === p.worst.hour)) {
      const nearEnd = cx + 50 > W - padR;
      svg += `<text x="${nearEnd ? x + bw : cx}" y="${yt - 6}" text-anchor="${nearEnd ? "end" : "middle"}" font-size="12" font-weight="600" fill="var(--ink)">${h.aqi}${isClean ? " · cleanest" : ""}</text>`;
    }
    svg += `<text x="${cx}" y="${H - 8}" text-anchor="middle" font-size="12" fill="var(--ink-2)">${h.time}</text></g>`;
  });
  svg += `<line x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}" stroke="var(--ink-3)" stroke-width="1"/></svg><div class="tip" id="tip"></div>`;
  $("chart").innerHTML = svg;

  const tip = $("tip"), box = $("chart");
  box.querySelectorAll(".bar").forEach((g) => {
    const h = hours[+g.dataset.i];
    g.addEventListener("pointerenter", () => {
      const r = g.getBoundingClientRect(), b = box.getBoundingClientRect();
      tip.textContent = `${h.time} · AQI (est.) ${h.aqi} ${h.category} · PM2.5 ${h.pm25} · PM10 ${h.pm10}`;
      tip.style.left = Math.min(Math.max(r.left - b.left + r.width / 2, 110), b.width - 110) + "px";
      tip.style.top = (r.top - b.top + 20) + "px";
      tip.style.opacity = 1;
    });
    g.addEventListener("pointerleave", () => (tip.style.opacity = 0));
  });

  const present = CATS.filter((c) => hours.some((h) => catColor(h.aqi) === c[2]));
  const closed = p.windows_closed.length ? `<em>Windows closed ${p.windows_closed.map((w) => w.join("–")).join(", ")}</em>` : "";
  $("legend").innerHTML = present.map((c) => `<span style="--c:${c[2]}">${c[0]}</span>`).join("") + closed;
  $("table").innerHTML = `<table><thead><tr><th>Hour</th><th class="num">AQI (est.)</th><th>Category</th><th class="num">PM2.5</th><th class="num">PM10</th></tr></thead><tbody>${
    hours.map((h) => `<tr><td>${h.time}</td><td class="num">${h.aqi}</td><td>${esc(h.category)}</td><td class="num">${h.pm25}</td><td class="num">${h.pm10}</td></tr>`).join("")
  }</tbody></table><p class="muted">µg/m³, hourly forecast. Source: Open-Meteo / CAMS.</p>`;
}

function renderMessages(rec) {
  const m = rec.messages;
  $("messages").innerHTML = `<div class="muted">हिन्दी (voice note: Amazon Polly, Kajal)</div><div class="msg" lang="hi">${esc(m.parent_hi)}</div>
    <div class="muted">English</div><div class="msg">${esc(m.parent_en)}</div>
    <p class="muted">Parents join on Telegram with <b>/join ${esc(school.join_code)}</b>.</p>`;
}

let chartW = 0;
new ResizeObserver(([entry]) => {
  const w = Math.round(entry.contentRect.width);
  if (last && Math.abs(w - chartW) > 4) renderChart(last.plan);
}).observe($("chart"));

init();
